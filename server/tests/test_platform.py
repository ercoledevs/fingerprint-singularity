import copy
import io
import os
import secrets
import threading
import time
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from pymongo import MongoClient
from pymongo.errors import AutoReconnect

from singularity.api import app
from singularity.maintenance import backup, restore
from singularity.security import now, password_hash
from singularity.store import Store

PASSWORD = "test-only-password-123"
KEY = "pk_" + "a" * 32
ORIGIN = "http://localhost:8080"


@pytest.fixture
def client(tmp_path, monkeypatch):
    uri = os.environ.get("TEST_MONGO_URI")
    if not uri:
        pytest.skip("TEST_MONGO_URI required for actual MongoDB acceptance")
    name = "singularity_test_" + secrets.token_hex(6)
    base = MongoClient(uri)
    # Test URI must have permission to create isolated test databases.
    from urllib.parse import urlsplit, urlunsplit
    u = urlsplit(uri)
    test_uri = urlunsplit((u.scheme, u.netloc, "/" + name, u.query, ""))
    monkeypatch.setenv("MONGO_URI", test_uri)
    monkeypatch.setenv("SINGULARITY_SECRET", "a" * 64)
    monkeypatch.setenv("ADMIN_PASSWORD_HASH", password_hash(PASSWORD))
    monkeypatch.setenv("APP_ORIGIN", ORIGIN)
    monkeypatch.setenv("DEMO_PUBLIC_KEY", KEY)
    monkeypatch.setenv("STATE_DIR", str(tmp_path / "state"))
    with TestClient(app) as c:
        c.store = app.state.store
        login = c.post("/api/admin/login", json=dict(username="admin", password=PASSWORD))
        assert login.status_code == 200, login.text
        c.headers.update({"X-CSRF-Token": login.json()["csrf"]})
        yield c
    base.drop_database(name)
    base.close()


def observation(scope=KEY):
    return dict(schema="singularity/v1", scope=scope, signals=dict(platform="macos", cores=8, memory=8, language="en", timezone="Europe/Rome"))


def identify(c, **overrides):
    key = overrides.pop("key", KEY)
    body = {"snapshot": observation(key), "requestId": secrets.token_hex(16), **overrides}
    return c.post("/api/v1/identify/" + key, json=body, headers={"Origin": ORIGIN})


def test_stateless_idempotency_and_immutable_anchor(client):
    request = secrets.token_hex(16)
    first = identify(client, requestId=request).json()
    assert first["method"] == "provisional" and first["visitorId"]
    assert identify(client, requestId=request).json() == first
    changed = observation(); changed["signals"]["memory"] = 4
    assert identify(client, requestId=request, snapshot=changed).status_code == 409
    second = identify(client, snapshot=changed).json()
    assert second["method"] == "inferred" and second["visitorId"] == first["visitorId"]
    assert second["digest"] != first["digest"]
    anchor = client.store.events.find_one({"anchor": True})
    assert anchor["snapshot"] == observation()
    assert client.store.events.count_documents({}) == 2


def test_enrollment_fresh_scoped_revocable_and_expiring(client):
    first = identify(client).json()
    enrolled = identify(client, remember=True).json()
    assert enrolled["visitorId"] != first["visitorId"] and enrolled["token"]
    token = enrolled["token"]
    request = secrets.token_hex(16)
    assert identify(client, token=token, requestId=request).json()["visitorId"] == enrolled["visitorId"]
    p = client.post("/api/admin/projects", json=dict(name="Other", origins=[ORIGIN])).json()
    assert identify(client, token=token, key=p["publicKey"]).status_code == 410
    r = client.post(f'/api/admin/projects/demo/visitors/{enrolled["visitorId"]}/revoke')
    assert r.status_code == 200
    assert identify(client, token=token, requestId=request).status_code == 410
    assert client.store.events.find_one({"visitorId": enrolled["visitorId"], "anchor": True}).get("tokenHash") is None
    enrolled2 = identify(client, remember=True).json()
    client.store.events.update_one({"visitorId": enrolled2["visitorId"], "anchor": True}, {"$set": {"expiresAt": now() - timedelta(seconds=1)}})
    assert identify(client, token=enrolled2["token"]).status_code == 410


def test_sparse_ambiguity_and_candidate_boundaries(client):
    sparse = observation(); sparse["signals"]["cores"] = None
    assert identify(client, snapshot=sparse, remember=True).json()["visitorId"] is None
    assert client.store.events.count_documents({"anchor": True}) == 0
    identify(client, remember=True)
    identify(client, remember=True)
    assert identify(client).json()["reason"] == "ambiguous-candidates"
    seed = client.store.events.find_one({"anchor": True})
    docs = []
    for i in range(254):
        d = copy.deepcopy(seed); d.update(_id="evt_seed" + str(i), visitorId="vis_seed" + str(i), requestKey="seed" + str(i)); docs.append(d)
    client.store.events.insert_many(docs)
    at_limit = identify(client).json()
    assert at_limit["decision"]["candidateCount"] == 256 and at_limit["reason"] == "ambiguous-candidates"
    extra = copy.deepcopy(seed); extra.update(_id="evt_extra", visitorId="vis_extra", requestKey="extra")
    client.store.events.insert_one(extra)
    overflow = identify(client).json()
    assert overflow["reason"] == "candidate-overflow" and overflow["visitorId"] is None
    plan = client.store.db.command("explain", {"find": "events", "filter": {"project": "demo", "anchor": True, "expiresAt": {"$gt": now()}}, "limit": 257}, verbosity="executionStats")
    assert plan["executionStats"]["totalDocsExamined"] <= 257


def test_auth_origin_body_and_schema(client):
    assert client.get("/api/admin/projects").status_code == 200
    saved = client.headers.pop("X-CSRF-Token")
    assert client.post("/api/admin/logout").status_code == 403
    client.headers["X-CSRF-Token"] = saved
    assert client.post("/api/admin/projects", json=dict(name="X", origins=[ORIGIN]), headers={"Origin": "https://attacker.example"}).status_code == 403
    assert client.post("/api/v1/identify/" + KEY, json=dict(snapshot=observation(), requestId="a" * 20)).status_code == 403
    assert client.options("/api/v1/identify/" + KEY, headers={"Origin": ORIGIN}).headers["access-control-allow-origin"] == ORIGIN
    assert client.post("/api/v1/identify/" + KEY, content=b"x" * 9000).status_code == 413
    s = observation(); s["signals"]["cores"] = True
    assert identify(client, snapshot=s).status_code == 422
    assert identify(client, bogus="x").status_code == 422
    assert client.post("/api/admin/logout").status_code == 200
    assert client.get("/api/admin/projects").status_code == 401


def test_filter_pagination_scope_and_expiry(client):
    rows = [identify(client).json() for _ in range(4)]
    path = "/api/admin/projects/demo/events"
    first = client.get(path, params=dict(limit=2, platform="macos", prefix="evt_")).json()
    assert len(first["items"]) == 2 and first["nextCursor"]
    second = client.get(path, params=dict(limit=2, platform="macos", prefix="evt_", cursor=first["nextCursor"])).json()
    assert not {e["_id"] for e in first["items"]} & {e["_id"] for e in second["items"]}
    assert client.get(path, params=dict(limit=2, cursor=first["nextCursor"])).status_code == 422
    assert client.get(path + "?method=inferred&method=enrolled").status_code == 422
    for params in [dict(prefix=".*"), dict(limit=1000), {"$where": "1"}, dict(after="2026-01-01"), dict(cursor="bad")]:
        assert client.get(path, params=params).status_code == 422
    p = client.post("/api/admin/projects", json=dict(name="Another", origins=[ORIGIN])).json()
    assert client.get(f'/api/admin/projects/{p["_id"]}/events/{rows[0]["eventId"]}').status_code == 404
    client.store.events.update_one({"_id": rows[0]["eventId"]}, {"$set": {"expiresAt": now() - timedelta(seconds=1)}})
    assert client.get(path + "/" + rows[0]["eventId"]).status_code == 404
    assert len(client.get(path).json()["items"]) == 3


def test_write_failure_retry_and_backpressure(client, monkeypatch):
    original = client.store.events.insert_one
    def fail(*a, **k):
        raise AutoReconnect("injected before write")
    monkeypatch.setattr(client.store.events, "insert_one", fail)
    request = secrets.token_hex(16)
    assert identify(client, remember=True, requestId=request).status_code == 503
    assert client.store.events.count_documents({}) == 0
    def committed_then_failed(*a, **k):
        original(*a, **k)
        raise AutoReconnect("injected after commit")
    monkeypatch.setattr(client.store.events, "insert_one", committed_then_failed)
    assert identify(client, remember=True, requestId=request).status_code == 503
    monkeypatch.setattr(client.store.events, "insert_one", original)
    retried = identify(client, remember=True, requestId=request)
    assert retried.status_code == 200 and retried.json()["token"]
    assert client.store.events.count_documents({}) == 1
    acquired, release = threading.Event(), threading.Event()
    def holder():
        with client.store.mutex:
            acquired.set(); release.wait(5)
    thread = threading.Thread(target=holder); thread.start(); acquired.wait()
    try:
        assert identify(client).status_code == 429
    finally:
        release.set(); thread.join()
    assert identify(client).status_code == 200


def test_real_backup_restore_deletion_replay_and_rotation(client):
    first = identify(client, remember=True).json()
    other = client.post("/api/admin/projects", json=dict(name="To delete", origins=[ORIGIN])).json()
    identify(client, key=other["publicKey"])
    archive = io.StringIO(); backup(client.store, archive)
    assert client.delete(f'/api/admin/projects/demo/visitors/{first["visitorId"]}').status_code == 200
    assert client.delete('/api/admin/projects/' + other["_id"]).status_code == 200
    with pytest.raises(ValueError, match="Rotate"):
        restore(client.store, io.StringIO(archive.getvalue()))
    client.store.config["secret"] = "b" * 64
    restore(client.store, io.StringIO(archive.getvalue()))
    assert client.store.events.count_documents({}) == 0
    assert client.store.projects.find_one({"_id": other["_id"]}) is None
    assert client.store.sessions.count_documents({}) == 0
    assert not client.store.quarantine.exists()


def test_recovery_failure_quarantines_and_replays(client, monkeypatch):
    e = identify(client).json()
    original = client.store.apply_deletion
    def fail(_):
        raise AutoReconnect("injected deletion failure")
    monkeypatch.setattr(client.store, "apply_deletion", fail)
    assert client.delete(f'/api/admin/projects/demo/visitors/{e["visitorId"]}').status_code == 503
    assert client.get("/api/health").status_code == 503
    monkeypatch.setattr(client.store, "apply_deletion", original)
    client.store.replay(); client.store.ready = True
    assert client.store.events.count_documents({"visitorId": e["visitorId"]}) == 0


def test_retention_disabled_enrollment_and_no_secret_output(client):
    e = identify(client, remember=True).json()
    r = client.put("/api/admin/projects/demo", json=dict(name="Live demo", origins=[ORIGIN], retentionDays=1, enrollment=False))
    assert r.status_code == 200
    assert identify(client, token=e["token"]).status_code == 410
    rows = client.get("/api/admin/projects/demo/events").json()["items"]
    assert "tokenHash" not in rows[0] and "response" not in rows[0]
    assert rows[0]["expiresAt"] < e["expiresAt"]


def test_single_worker_lock(client):
    with pytest.raises(BlockingIOError):
        Store(client.store.config)


def test_error_cors_expired_request_and_reference_redaction(client):
    request = secrets.token_hex(16)
    e = identify(client, requestId=request).json()
    bad = identify(client, token="invalid-token")
    assert bad.status_code == 410 and bad.headers['access-control-allow-origin'] == ORIGIN
    client.store.events.update_one({'_id': e['eventId']}, {'$set': {'expiresAt': now() - timedelta(seconds=1)}})
    assert identify(client, requestId=request).status_code == 410
    other = identify(client, remember=True).json()
    reference = identify(client, token=other['token']).json()
    client.store.events.update_one({'_id': reference['eventId']}, {'$set': {
        'decision.omissions': [{'runnerUpId': e['visitorId'], 'candidateId': e['visitorId']}],
        'response.decision.omissions': [{'runnerUpId': e['visitorId'], 'candidateId': e['visitorId']}]
    }})
    assert client.delete(f'/api/admin/projects/demo/visitors/{e["visitorId"]}').status_code == 200
    import json
    retained = client.store.events.find_one({'_id': reference['eventId']})
    assert e['visitorId'] not in json.dumps(retained, default=str)


def test_concurrent_assignment_retries(client):
    from concurrent.futures import ThreadPoolExecutor
    def run(_):
        request = secrets.token_hex(16)
        for _ in range(30):
            response = identify(client, requestId=request)
            if response.status_code != 429:
                return response.json()
            time.sleep(.01)
        pytest.fail('Backpressure never recovered')
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(run, range(8)))
    assert len({r['visitorId'] for r in results}) == 1
    assert len({r['eventId'] for r in results}) == 8
    assert client.store.events.count_documents({'anchor': True}) == 1


def test_synthetic_population_measurements(client):
    import itertools
    import json
    import random
    import resource
    import sys
    from pathlib import Path
    seed = client.store.events.find_one({'_id': identify(client).json()['eventId']})
    vectors = list(itertools.product(['macos','windows','linux','android'], [2,4,8,16], [2,4,8], ['en','it','de'], ['UTC','Europe/Rome','America/New_York']))
    random.Random(314159).shuffle(vectors)
    results = []
    for size in (1, 8, 64, 256, 257):
        client.store.events.delete_many({})
        docs = []
        for i in range(size):
            d = copy.deepcopy(seed)
            d.update(_id='evt_population' + str(i), visitorId='vis_population' + str(i), requestKey='population' + str(i))
            if i:
                d['snapshot']['signals'] = dict(zip(['platform','cores','memory','language','timezone'], vectors[i]))
            docs.append(d)
        client.store.events.insert_many(docs)
        durations, assigned = [], 0
        for _ in range(15):
            start = time.perf_counter()
            r = identify(client); assert r.status_code == 200
            durations.append((time.perf_counter() - start) * 1000)
            assigned += r.json()['visitorId'] is not None
        plan = client.store.db.command('explain', {'find': 'events', 'filter': {'project':'demo','anchor':True,'expiresAt':{'$gt':now()}}, 'limit':257}, verbosity='executionStats')
        examined = plan['executionStats']['totalDocsExamined']
        assert examined <= 257
        durations.sort()
        results.append(dict(candidates=size, requests=15, assigned=assigned, unassigned=15-assigned, p95Ms=round(durations[-1],3), p99Ms=round(durations[-1],3), documentsExamined=examined))
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    output = dict(workload='Deterministic synthetic observations; serial TestClient HTTP handling with actual MongoDB. Not field accuracy or network latency.',
                  mongo=client.store.db.command('buildInfo')['version'], python=sys.version.split()[0],
                  processPeakRssMiB=round(rss/(1024*1024 if sys.platform=='darwin' else 1024),2),
                  writeQueueCapacity=0, admissionLimit=32, scenarios=results)
    path = Path('artifacts/platform'); path.mkdir(parents=True, exist_ok=True)
    (path/'performance.json').write_text(json.dumps(output,indent=2))


def test_interrupted_restore_blocks_startup_and_backup(client, monkeypatch):
    identify(client, remember=True)
    archive = io.StringIO(); backup(client.store, archive)
    cfg = dict(client.store.config); cfg['secret'] = 'c' * 64
    client.store.config['secret'] = cfg['secret']
    original = client.store.db.projects.insert_one
    def fail(*args, **kwargs): raise AutoReconnect('injected replacement failure')
    monkeypatch.setattr(client.store.db.projects, 'insert_one', fail)
    # Store collection attribute is cached for injection; restore uses db[name].
    from unittest.mock import patch
    from pymongo.synchronous.collection import Collection
    original_insert = Collection.insert_one
    def injected(collection, *a, **k):
        if collection.name == 'projects': raise AutoReconnect('injected replacement failure')
        return original_insert(collection, *a, **k)
    with patch.object(Collection, 'insert_one', injected):
        with pytest.raises(AutoReconnect): restore(client.store, io.StringIO(archive.getvalue()))
    assert client.store.quarantine.exists()
    with pytest.raises(ValueError): backup(client.store, io.StringIO())
    client.store.close()
    with pytest.raises(RuntimeError, match='Restore incomplete'): Store(cfg)
    recovered = Store({**cfg, 'maintenance': True})
    with pytest.raises(ValueError): backup(recovered, io.StringIO())
    restore(recovered, io.StringIO(archive.getvalue()))
    assert recovered.events.count_documents({}) == 1
    recovered.close()
    app.state.store = Store(cfg)
    client.store = app.state.store
    assert client.store.ready and not client.store.quarantine.exists()
