import copy
import json
import random
import secrets
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from singularity import kernel
from singularity.detailed_kernel import compare
from test_platform import client, identify, observation, KEY, ORIGIN  # shared isolated Mongo fixture


def detailed(key=KEY):
    return dict(**observation(key), probe='web/v1', detail=dict(gpu='a' * 64, fonts='b' * 64, canvas='c' * 64)) | {'schema': 'singularity/v2'}


def test_detailed_cross_language_parity():
    rng = random.Random(728193)
    cases = []
    def generated():
        s = detailed('oracle')
        s['signals']['platform'] = rng.choice(['macos', 'windows', None])
        s['signals']['cores'] = rng.choice([4, 8, None])
        s['detail'] = {k: rng.choice([None, 'a' * 64, 'b' * 64]) for k in s['detail']}
        return s
    for i in range(2000):
        s = generated()
        candidates = [dict(id=f'c{j}', snapshot=generated()) for j in range(rng.randrange(7))]
        cases.append(dict(snapshot=s, candidates=candidates))
        if i < 100:
            cases.append(dict(op='digest', snapshot=s))
    for count in (256, 257):
        cases.append(dict(snapshot=detailed('oracle'), candidates=[dict(id=f'c{i}', snapshot=detailed('oracle')) for i in range(count)]))
    for bad in [True, {}, 'raw-model', 'x' * 64, 'a' * 65]:
        s = detailed('oracle'); s['detail']['gpu'] = bad
        cases.append(dict(snapshot=s, candidates=[]))
    expected = json.loads(subprocess.check_output(['node', 'scripts/kernel-oracle.mjs'], cwd=Path(__file__).resolve().parents[2], input=json.dumps(cases).encode()))
    actual = []
    for c in cases:
        try:
            actual.append(dict(canonical=kernel.canonicalize(c['snapshot']), digest=kernel.digest(c['snapshot'])) if c.get('op') == 'digest' else kernel.match(c['snapshot'], c['candidates']))
        except kernel.Invalid as exc:
            actual.append(dict(error=exc.code))
    assert actual == expected


def test_schema_partition_search_and_token_continuity(client):
    old = identify(client).json()
    new = identify(client, snapshot=detailed()).json()
    assert new['visitorId'] != old['visitorId'] and new['decision']['policy'] == 'support/v2'
    assert new['digest'].startswith('sg2_')
    assert identify(client).json()['visitorId'] == old['visitorId']
    assert identify(client, snapshot=detailed()).json()['visitorId'] == new['visitorId']
    rows = client.get('/api/admin/projects/demo/events', params={'prefix': 'sg2_'}).json()['items']
    assert len(rows) == 2 and all(r['snapshot']['schema'] == 'singularity/v2' for r in rows)
    token = identify(client, remember=True).json()
    remembered = identify(client, snapshot=detailed(), token=token['token']).json()
    assert remembered['visitorId'] == token['visitorId'] and remembered['method'] == 'remembered'


def test_detail_conflict_missing_and_platform_partition(client):
    first = identify(client, snapshot=detailed()).json()
    different = detailed(); different['detail']['gpu'] = 'd' * 64
    second = identify(client, snapshot=different).json()
    assert second['method'] == 'provisional' and second['visitorId'] != first['visitorId']
    assert identify(client, snapshot=detailed()).json()['visitorId'] == first['visitorId']
    sparse = detailed(); sparse['detail']['fonts'] = sparse['detail']['canvas'] = None
    assert identify(client, snapshot=sparse).json()['reason'] == 'insufficient-detail'
    # Other-platform anchors do not overflow or revive as rivals in support/v2.
    seed = client.store.events.find_one({'_id': first['eventId']})
    docs = []
    for _ in range(257):
        d = copy.deepcopy(seed); d.update(_id='evt_' + secrets.token_hex(16), visitorId='vis_' + secrets.token_hex(16), requestKey=secrets.token_hex(16))
        d['snapshot']['signals']['platform'] = 'windows'; docs.append(d)
    client.store.events.insert_many(docs)
    result = identify(client, snapshot=detailed()).json()
    assert result['decision']['candidateCount'] == 1 and result['visitorId'] == first['visitorId']


def test_bounded_wait_absorbs_healthy_burst_and_preserves_idempotency(client):
    with ThreadPoolExecutor(max_workers=32) as pool:
        responses = list(pool.map(lambda _: identify(client, snapshot=detailed()), range(64)))
    assert all(r.status_code == 200 for r in responses)
    assert len({r.json()['visitorId'] for r in responses}) == 1
    assert len({r.json()['eventId'] for r in responses}) == 64
    request = secrets.token_hex(16)
    with ThreadPoolExecutor(max_workers=16) as pool:
        replays = list(pool.map(lambda _: identify(client, snapshot=detailed(), requestId=request), range(16)))
    assert all(r.status_code == 200 for r in replays)
    assert all(r.json() == replays[0].json() for r in replays)
    assert client.store.events.count_documents({}) == 65


def test_waiter_observes_revocation_and_recovery_state(client):
    enrolled = identify(client, snapshot=detailed(), remember=True).json()
    entered = threading.Event()
    original = client.store.mutex
    class ObservedLock:
        def acquire(self, *args, **kwargs):
            entered.set()
            return original.acquire(*args, **kwargs)
        def release(self):
            return original.release()
    client.store.mutex = ObservedLock()
    def request():
        return identify(client, snapshot=detailed(), token=enrolled['token'])
    with ThreadPoolExecutor(max_workers=1) as pool:
        with original:
            future = pool.submit(request); assert entered.wait(1)
            # Same atomic mutation as revocation while the competing request is queued.
            client.store.events.update_one({'visitorId': enrolled['visitorId'], 'anchor': True}, {'$unset': {'tokenHash': ''}})
        assert future.result().status_code == 410
        with original:
            entered.clear(); future = pool.submit(request); assert entered.wait(1)
            client.store.ready = False
        try:
            assert future.result().status_code == 503
        finally:
            client.store.ready = True
            client.store.mutex = original


def test_detailed_comparison_is_not_physical_uniqueness():
    a = detailed(); b = detailed()
    assert compare(a, b)['qualifies']
    assert kernel.match(a, [dict(id='other-device', snapshot=b)])['status'] == 'matched'


def test_sparse_anchor_cannot_discriminate_a_hidden_gpu_difference():
    sparse = detailed(); sparse['detail']['gpu'] = None
    other = detailed(); other['detail']['gpu'] = 'd' * 64
    pool = [dict(id='sparse-anchor', snapshot=sparse)]
    assert kernel.match(detailed(), pool)['candidateId'] == 'sparse-anchor'
    assert kernel.match(other, pool)['candidateId'] == 'sparse-anchor'
    assert not compare(detailed(), other)['qualifies']


def test_paired_actual_api_agrees_with_simulator(client):
    import importlib.util
    script = Path(__file__).resolve().parents[2] / 'scripts/evaluate-detailed.py'
    spec = importlib.util.spec_from_file_location('paired_evaluation', script)
    evaluation = importlib.util.module_from_spec(spec); spec.loader.exec_module(evaluation)
    reports = []
    for population in ['diverse', 'office', 'clones']:
        devices = evaluation.generate(population, 913571, count=48)
        for scenario in ['repeat', 'canvas-update', 'gpu-unavailable', 'sparse-first']:
            for policy in ['envelope/v1', 'support/v2']:
                project = client.post('/api/admin/projects', json=dict(name=f'{population}-{scenario}-{policy}', origins=[ORIGIN]))
                assert project.status_code == 200
                key = project.json()['publicKey']
                rows = []
                for visit in range(2):
                    for device in devices:
                        snapshot = copy.deepcopy(evaluation.visit_snapshot(device, scenario, visit))
                        snapshot['scope'] = key
                        if policy == 'envelope/v1':
                            snapshot = {k: snapshot[k] for k in ['scope', 'signals']} | {'schema': 'singularity/v1'}
                        response = identify(client, key=key, snapshot=snapshot)
                        assert response.status_code == 200
                        rows.append(dict(deviceLabel=device['label'], visitorId=response.json()['visitorId'], browser='synthetic-adapter'))
                actual = evaluation.summarize(rows)
                expected, _ = evaluation.run(devices, scenario, policy)
                assert actual == {k: v for k, v in expected.items() if k != 'anchors'}
                reports.append(dict(population=population, scenario=scenario, policy=policy, **actual))
    out = script.parent.parent / 'artifacts/improvement-v03'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'paired-api.json').write_text(json.dumps(dict(source='Synthetic observations through FastAPI TestClient and real isolated MongoDB',
        status='PASS', projects=24, identifyRequests=2304, simulatorParity=True, outcomes=reports), indent=2))
