"""Candidate recall and ambiguity controls against actual, isolated MongoDB."""
import copy
from datetime import timedelta
from itertools import count, product
import importlib.util
import json
from pathlib import Path
import secrets
from types import SimpleNamespace

import pytest
from pymongo.errors import ExecutionTimeout

from singularity import kernel, retrieval
from singularity.detailed_kernel import compare
from singularity.security import now
from test_detailed import detailed
from test_platform import client, identify, ORIGIN


def clone_anchor(seed, snapshot, **extra):
    item = copy.deepcopy(seed)
    item.update(_id='evt_' + secrets.token_hex(16), visitorId='vis_' + secrets.token_hex(16),
                requestKey=secrets.token_hex(16), snapshot=copy.deepcopy(snapshot), **extra)
    return item


@pytest.mark.parametrize('section,field,value', [
    ('signals', 'platform', 'windows'), ('signals', 'cores', 4),
    ('detail', 'gpu', 'd' * 64), ('detail', 'fonts', 'd' * 64), ('detail', 'canvas', 'd' * 64),
])
def test_contradictions_do_not_exhaust_retrieval_limit(client, section, field, value):
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    conflicting = detailed()
    conflicting[section][field] = value
    client.store.events.insert_many([clone_anchor(seed, conflicting) for _ in range(257)])

    result = identify(client, snapshot=detailed()).json()
    assert result['visitorId'] == first['visitorId']
    assert result['method'] == 'inferred'
    assert result['decision']['candidateCount'] == 1


def test_mongo_retrieval_matches_complete_semantic_oracle(client):
    """19,440 comparisons include every null/two-value veto-field combination."""
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    client.store.events.delete_one({'_id': first['eventId']})
    values = ([None, 'macos', 'windows'], [None, 4, 8], *[[None, 'a' * 64, 'b' * 64]] * 3)
    snapshots = []
    for platform, cores, gpu, fonts, canvas in product(*values):
        s = detailed()
        s['signals'].update(platform=platform, cores=cores)
        s['detail'].update(gpu=gpu, fonts=fonts, canvas=canvas)
        snapshots.append(s)
    anchors = [clone_anchor(seed, s) for s in snapshots]
    client.store.events.insert_many(anchors)
    candidates = [dict(id=a['visitorId'], snapshot=a['snapshot']) for a in anchors]
    query_count = 0
    for snapshot in snapshots:
        if not kernel.sufficient(snapshot):
            continue
        query_count += 1
        query = retrieval.anchor_filter('demo', snapshot, now())
        found = list(client.store.events.find(query).hint(retrieval.index_for(snapshot)))
        expected = {a['visitorId'] for a in anchors if not compare(snapshot, a['snapshot'])['contradictions']}
        assert {a['visitorId'] for a in found} == expected
        full = kernel.match(snapshot, candidates)
        pruned = kernel.match(snapshot, [dict(id=a['visitorId'], snapshot=a['snapshot']) for a in found])
        assert (pruned['status'], pruned['candidateId']) == (full['status'], full['candidateId'])
    assert query_count == 80 and len(anchors) == 243


def test_null_and_missing_fields_are_not_discarded(client):
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    for section, field in [('signals', 'platform'), ('signals', 'cores')]+[('detail', k) for k in retrieval.DETAIL_KEYS]:
        s = detailed(); s[section][field] = None
        rival = clone_anchor(seed, s)
        client.store.events.insert_one(rival)
        result = identify(client, snapshot=detailed()).json()
        assert result['visitorId'] is None and result['decision']['candidateCount'] == 2
        assert result['reason'] == ('insufficient-candidate-evidence' if section == 'signals' else 'ambiguous-candidates')
        # Missing properties are invalid snapshots, but retrieval must not hide
        # them; the unchanged kernel validation rejects the retained contender.
        client.store.events.update_one({'_id': rival['_id']}, {'$unset': {f'snapshot.{section}.{field}': ''}})
        assert identify(client, snapshot=detailed()).status_code == 422
        client.store.events.delete_one({'_id': rival['_id']})


@pytest.mark.parametrize('missing', [None, 'gpu', 'fonts', 'canvas'])
def test_compatible_clones_keep_ambiguity_and_overflow(client, missing):
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    client.store.events.insert_many([clone_anchor(seed, detailed()) for _ in range(255)])
    s = detailed()
    if missing:
        s['detail'][missing] = None
    at_limit = identify(client, snapshot=s).json()
    assert at_limit['visitorId'] is None
    assert at_limit['reason'] == 'ambiguous-candidates' and at_limit['decision']['candidateCount'] == 256
    client.store.events.insert_one(clone_anchor(seed, detailed()))
    overflow = identify(client, snapshot=s).json()
    assert overflow['visitorId'] is None
    assert overflow['reason'] == 'candidate-overflow' and overflow['decision']['candidateCount'] == 257


def test_retrieval_keeps_schema_project_anchor_and_expiry_boundaries(client):
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    at = now()
    old = detailed(); old['schema'] = 'singularity/v1'
    old.pop('probe'); old.pop('detail')
    unrelated = [clone_anchor(seed, detailed(), project='another-project'),
                 clone_anchor(seed, detailed(), anchor=False), clone_anchor(seed, old),
                 clone_anchor(seed, detailed(), expiresAt=at),
                 clone_anchor(seed, detailed(), expiresAt=at - timedelta(seconds=1))]
    client.store.events.insert_many(unrelated)
    query = retrieval.anchor_filter('demo', detailed(), at)
    found = list(client.store.events.find(query).hint(retrieval.index_for(detailed())))
    assert [a['visitorId'] for a in found] == [first['visitorId']]


def test_interrupted_retrieval_never_assigns_from_partial_results(client, monkeypatch):
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    original_find = client.store.events.find

    class InterruptedCursor:
        def hint(self, _):
            return self
        def limit(self, _):
            return self
        def max_time_ms(self, _):
            return self
        def __iter__(self):
            yield seed
            raise ExecutionTimeout('Test-only interruption after the first candidate')

    def interrupted_find(*args, **kwargs):
        query = args[0] if args else kwargs.get('filter', {})
        if query.get('anchor') is True and 'snapshot.schema' in query:
            return InterruptedCursor()
        return original_find(*args, **kwargs)

    request = secrets.token_hex(16)
    with monkeypatch.context() as patch:
        patch.setattr(client.store.events, 'find', interrupted_find)
        response = identify(client, snapshot=detailed(), requestId=request)
        assert response.status_code == 503
    assert client.store.events.count_documents({}) == 1
    response = identify(client, snapshot=detailed(), requestId=request)
    assert response.status_code == 200 and response.json()['visitorId'] == first['visitorId']
    assert client.store.events.count_documents({}) == 2


def test_index_work_stays_bounded_with_conflicts_and_expired_backlog(client):
    first = identify(client, snapshot=detailed()).json()
    seed = client.store.events.find_one({'_id': first['eventId']})
    # Query-time expiry is tested without relying on the asynchronous TTL worker.
    # Drop only the TTL index in this disposable test database; fixture drops DB.
    client.store.events.drop_index('expiresAt_1')
    measurements = []
    for missing in [None, 'gpu', 'fonts', 'canvas']:
        s = detailed()
        if missing:
            s['detail'][missing] = None
        for population in [1024, 8192]:
            for conflict in [k for k in retrieval.DETAIL_KEYS if k != missing] + ['expired']:
                docs = []
                for i in range(population):
                    other = detailed()
                    expiry = seed['expiresAt']
                    if conflict == 'expired':
                        expiry = now() - timedelta(minutes=1)
                        if missing:
                            other['detail'][missing] = f'{i % 16:064x}'
                    else:
                        other['detail'][conflict] = 'd' * 64
                    docs.append(clone_anchor(seed, other, expiresAt=expiry, retrievalFixture=True))
                client.store.events.insert_many(docs)
                assert client.store.events.count_documents({'retrievalFixture': True}) == population
                query = retrieval.anchor_filter('demo', s, now())
                hint = retrieval.index_for(s)
                plan = client.store.db.command('explain', dict(find='events', filter=query,
                    projection={'visitorId': 1, 'snapshot': 1, 'expiresAt': 1}, hint=hint, limit=257, maxTimeMS=1500), verbosity='executionStats')
                stats = plan['executionStats']
                assert stats['nReturned'] == 1
                assert stats['totalDocsExamined'] <= 16, stats
                assert stats['totalKeysExamined'] <= 256, stats
                assert 'COLLSCAN' not in json.dumps(plan['queryPlanner']['winningPlan'])
                assert hint in json.dumps(plan['queryPlanner']['winningPlan'])
                found = list(client.store.events.find(query).hint(hint).limit(257).max_time_ms(1500))
                assert [d['visitorId'] for d in found] == [first['visitorId']]
                measurements.append(dict(missing=missing, population=population, conflict=conflict, index=hint,
                    returned=stats['nReturned'], docsExamined=stats['totalDocsExamined'], keysExamined=stats['totalKeysExamined'],
                    executionTimeMillis=stats['executionTimeMillis']))
                client.store.events.delete_many({'retrievalFixture': True})
    out = Path(__file__).resolve().parents[2] / 'artifacts/improvement-retrieval'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'query-plans.json').write_text(json.dumps(measurements, indent=2))


def test_capacity_replay_matches_uncapped_oracle_per_visit(client, monkeypatch):
    from singularity import api
    script = Path(__file__).resolve().parents[2] / 'scripts/evaluate-retrieval.py'
    spec = importlib.util.spec_from_file_location('retrieval_evaluation', script)
    evaluation = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(evaluation)
    # Simulate serial visits one second apart in the rate limiter only. The rate
    # checks stay enabled; this replay measures decisions, not request throughput.
    clock = count()
    monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=lambda: next(clock)))
    reports = []
    for population, scenario in evaluation.CASES:
        for order in evaluation.ORDERS:
            project = client.post('/api/admin/projects', json=dict(name=f'{population}-{scenario}-{order}', origins=[ORIGIN]))
            assert project.status_code == 200
            key = project.json()['publicKey']
            expected, expected_rows = evaluation.run(population, scenario, order, 'uncapped-oracle')
            identities, rows = {}, []
            for (label, snapshot), oracle in zip(evaluation.visits(population, scenario, order), expected_rows, strict=True):
                snapshot['scope'] = key
                response = identify(client, key=key, snapshot=snapshot)
                assert response.status_code == 200, response.text
                event = response.json()
                assert event['decision']['status'] == oracle['status']
                oracle_id = oracle['visitorId']
                if oracle_id is None:
                    assert event['visitorId'] is None
                else:
                    if oracle_id not in identities:
                        assert event['visitorId'] is not None and event['visitorId'] not in identities.values()
                        identities[oracle_id] = event['visitorId']
                    assert event['visitorId'] == identities[oracle_id]
                rows.append(dict(deviceLabel=label, visitorId=event['visitorId'], browser='synthetic-adapter'))
            actual = evaluation.summarize(rows)
            assert actual == {k: v for k, v in expected.items() if k != 'anchors'}
            reports.append(dict(population=population, scenario=scenario, order=order, **actual))
    out = script.parent.parent / 'artifacts/improvement-retrieval'
    out.mkdir(parents=True, exist_ok=True)
    (out / 'retrieval-api.json').write_text(json.dumps(dict(source='Synthetic observations through actual FastAPI and isolated MongoDB',
        rateClock='One synthetic second per rate check; no throughput claim', oracleParityPerVisit=True,
        requests=sum(r['visits'] for r in reports), projects=len(reports), outcomes=reports), indent=2))
