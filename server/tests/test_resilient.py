import copy
import json
import random
import subprocess
from datetime import timedelta
from itertools import product
from pathlib import Path

from singularity import kernel, retrieval
from singularity.resilient_kernel import compare, continuity_code
from singularity.security import now
from test_platform import client, identify, KEY
from test_detailed import detailed
from test_retrieval import clone_anchor


def resilient(scope=KEY):
    return detailed(scope) | dict(schema='singularity/v3', probe='web/v2', engine='blink')


def test_resilient_cross_language_parity():
    rng = random.Random(403917)
    def generated():
        s = resilient('oracle')
        s['engine'] = rng.choice(['blink', 'webkit', 'gecko', None])
        s['signals']['platform'] = rng.choice(['macos', 'windows', None])
        s['signals']['cores'] = rng.choice([4, 8, None])
        s['detail'] = {k: rng.choice([None, 'a' * 64, 'b' * 64]) for k in s['detail']}
        return s
    cases = []
    for i in range(2000):
        s = generated()
        cases.append(dict(snapshot=s, candidates=[dict(id=f'c{j}', snapshot=generated()) for j in range(rng.randrange(7))]))
        if i < 100:
            cases += [dict(op='digest', snapshot=s), dict(op='code', snapshot=s)]
    for count in (256, 257):
        cases.append(dict(snapshot=resilient('oracle'), candidates=[dict(id=f'c{i}', snapshot=resilient('oracle')) for i in range(count)]))
    for bad in [True, {}, 'raw-model', 'x' * 64, 'a' * 65]:
        s = resilient('oracle'); s['detail']['gpu'] = bad
        cases.append(dict(snapshot=s, candidates=[]))
    expected = json.loads(subprocess.check_output(['node', 'scripts/kernel-oracle.mjs'], cwd=Path(__file__).resolve().parents[2], input=json.dumps(cases).encode()))
    actual = []
    for c in cases:
        try:
            s = c['snapshot']
            actual.append(continuity_code(s) if c.get('op') == 'code' else dict(canonical=kernel.canonicalize(s), digest=kernel.digest(s)) if c.get('op') == 'digest' else kernel.match(s, c['candidates']))
        except kernel.Invalid as exc:
            actual.append(dict(error=exc.code))
    assert actual == expected


def test_continuity_survives_canvas_locale_and_retention_without_resurrecting_visitor(client):
    original = resilient()
    first = identify(client, snapshot=original).json()
    changed = copy.deepcopy(original)
    changed['engine'] = 'webkit'
    changed['detail']['canvas'] = 'd' * 64
    changed['signals'].update(language='it', timezone='Europe/Rome', memory=None)
    second = identify(client, snapshot=changed).json()
    assert second['visitorId'] == first['visitorId'] and second['method'] == 'inferred'
    assert second['continuityCode'] == first['continuityCode']
    assert second['digest'] != first['digest']
    assert second['decision']['comparison']['differences'] == ['canvas']
    assert client.store.events.find_one({'anchor': True})['snapshot'] == original
    # Emulate query-time TTL expiry without relying on the asynchronous TTL worker.
    client.store.events.update_many({}, {'$set': {'expiresAt': now() - timedelta(seconds=1)}})
    recreated = identify(client, snapshot=original).json()
    assert recreated['visitorId'] != first['visitorId']
    assert recreated['continuityCode'] == first['continuityCode']
    assert recreated['method'] == 'provisional'
    assert client.delete('/api/admin/projects/demo/visitors/' + recreated['visitorId']).status_code == 200
    after_delete = identify(client, snapshot=original).json()
    assert after_delete['visitorId'] != recreated['visitorId']
    assert after_delete['continuityCode'] == recreated['continuityCode']
    # Startup/restore deletion replay cannot erase later observations sharing a code.
    client.store.replay()
    assert client.store.events.find_one({'_id': after_delete['eventId']})
    for params in [{'code': first['continuityCode']}, {'prefix': 'sc1_'}, {'prefix': 'sg3_'}]:
        response = client.get('/api/admin/projects/demo/events', params=params)
        assert response.status_code == 200
        assert [e['_id'] for e in response.json()['items']] == [after_delete['eventId']]
    assert client.get('/api/admin/projects/demo/events', params={'code': first['continuityCode'], 'prefix': 'sc1_'}).status_code == 422


def test_v3_schema_pool_and_missing_gpu_code(client):
    old = identify(client, snapshot=detailed()).json()
    new = identify(client, snapshot=resilient()).json()
    assert new['visitorId'] != old['visitorId']
    assert new['decision']['policy'] == 'support/v3' and new['digest'].startswith('sg3_')
    assert old['continuityCode'] is None
    masked = resilient(); masked['engine'] = 'webkit'; masked['detail']['gpu'] = None
    masked['detail']['canvas'] = 'e' * 64
    event = identify(client, snapshot=masked).json()
    assert event['continuityCode'] is None and event['visitorId'] is None
    assert event['reason'] == 'insufficient-candidate-evidence'


def test_v3_mongo_filter_matches_full_oracle_including_canvas_disagreements(client):
    first = identify(client, snapshot=resilient()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    client.store.events.delete_one({'_id': first['eventId']})
    snapshots = []
    values = ([None, 'macos', 'windows'], [None, 4, 8], *[[None, 'a' * 64, 'b' * 64]] * 3)
    for platform, cores, gpu, fonts, canvas in product(*values):
        s = resilient(); s['engine'] = [None, 'blink', 'webkit', 'gecko'][len(snapshots) % 4]; s['signals'].update(platform=platform, cores=cores)
        s['detail'].update(gpu=gpu, fonts=fonts, canvas=canvas); snapshots.append(s)
    anchors = [clone_anchor(seed, s) for s in snapshots]
    client.store.events.insert_many(anchors)
    complete = [dict(id=a['visitorId'], snapshot=a['snapshot']) for a in anchors]
    queries = 0
    for s in snapshots:
        if not kernel.sufficient(s):
            continue
        queries += 1
        found = list(client.store.events.find(retrieval.anchor_filter('demo', s, now())).hint(retrieval.index_for(s)))
        expected = {a['visitorId'] for a in anchors if not compare(s, a['snapshot'])['contradictions']}
        assert {a['visitorId'] for a in found} == expected
        full = kernel.match(s, complete)
        pruned = kernel.match(s, [dict(id=a['visitorId'], snapshot=a['snapshot']) for a in found])
        assert (full['status'], full['candidateId']) == (pruned['status'], pruned['candidateId'])
    assert queries == 64 and len(anchors) == 243


def test_canvas_conflicting_rivals_cannot_be_pruned_before_limit(client):
    first = identify(client, snapshot=resilient()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    rival = resilient(); rival['engine'] = 'webkit'; rival['detail']['canvas'] = 'f' * 64
    client.store.events.insert_many([clone_anchor(seed, rival) for _ in range(255)])
    event = identify(client, snapshot=resilient()).json()
    assert event['visitorId'] is None and event['reason'] == 'ambiguous-candidates'
    assert event['decision']['candidateCount'] == 256
    client.store.events.insert_one(clone_anchor(seed, rival))
    event = identify(client, snapshot=resilient()).json()
    assert event['visitorId'] is None and event['reason'] == 'candidate-overflow'
