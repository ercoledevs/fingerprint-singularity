import copy
import io
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta

from singularity.maintenance import backup, restore
from singularity.security import now
from test_platform import client, identify, ORIGIN
from test_resilient import resilient


def server_key(client, project='demo'):
    response = client.post(f'/api/admin/projects/{project}/server-key')
    assert response.status_code == 200
    assert response.headers['cache-control'] == 'no-store'
    return response.json()['serverKey']


def test_metadata_and_frozen_retained_history(client):
    request_id = 'metadata-request-0001'
    first = identify(client, snapshot=resilient(), requestId=request_id, linkedId='order:123', tags={'flow': 'checkout'}).json()
    assert first['history'] == dict(visitorFound=False, firstSeenAt=first['createdAt'], previousSeenAt=None)
    assert first['origin'] == ORIGIN and first['linkedId'] == 'order:123'
    second = identify(client, snapshot=resilient(), linkedId='order:456', tags={'flow': 'login'}).json()
    assert second['visitorId'] == first['visitorId']
    assert second['digest'] == first['digest'] and second['continuityCode'] == first['continuityCode']
    assert second['history'] == dict(visitorFound=True, firstSeenAt=first['createdAt'], previousSeenAt=first['createdAt'])
    assert identify(client, snapshot=resilient(), requestId=request_id, linkedId='order:123', tags={'flow': 'checkout'}).json() == first
    assert identify(client, snapshot=resilient(), requestId=request_id, tags={'flow': 'other'}).status_code == 409
    rows = client.get('/api/admin/projects/demo/events', params={'linked': 'order:123', 'origin': ORIGIN}).json()['items']
    assert len(rows) == 1 and rows[0]['tags'] == {'flow': 'checkout'}
    unknown = resilient(); unknown['detail']['fonts'] = None
    assert identify(client, snapshot=unknown).json()['history'] == dict(visitorFound=False, firstSeenAt=None, previousSeenAt=None)
    for tags in [{'bad.key': 'value'}, {'$operator': 'value'}, {'n': 3}, {'long': 'x' * 257}, {str(i): 'v' for i in range(17)}]:
        assert identify(client, tags=tags).status_code == 422


def test_server_credentials_are_scoped_rotatable_and_never_in_project_results(client):
    event = identify(client, snapshot=resilient()).json()
    path = '/api/server/projects/demo/events/' + event['eventId']
    assert client.get(path).status_code == 401  # Admin session does not substitute a server key.
    key = server_key(client)
    headers = {'Authorization': 'Bearer ' + key}
    assert client.get(path, headers=headers).json()['_id'] == event['eventId']
    assert client.get(path, headers={'Authorization': 'Bearer ' + 'sk_' + '0' * 64}).status_code == 401
    other = client.post('/api/admin/projects', json={'name': 'Other', 'origins': [ORIGIN]}).json()
    assert client.get(f"/api/server/projects/{other['_id']}/events/{event['eventId']}", headers=headers).status_code == 401
    other_key = server_key(client, other['_id'])
    assert client.get(f"/api/server/projects/{other['_id']}/events/{event['eventId']}", headers={'Authorization': 'Bearer ' + other_key}).status_code == 404
    public = client.get('/api/admin/projects').json()
    assert all('serverKeyHash' not in p for p in public)
    assert next(p for p in public if p['_id'] == 'demo')['serverKeyConfigured'] is True
    rotated = server_key(client)
    assert key != rotated and client.get(path, headers=headers).status_code == 401
    new_headers = {'Authorization': 'Bearer ' + rotated}
    assert client.get(path, headers=new_headers).status_code == 200
    assert client.delete('/api/admin/projects/demo/server-key').status_code == 200
    assert client.get(path, headers=new_headers).status_code == 401
    assert key not in client.store.ledger.read_text() and rotated not in client.store.ledger.read_text()


def test_event_verification_checks_and_atomic_consumption(client):
    event = identify(client, snapshot=resilient()).json()
    key = server_key(client)
    headers = {'Authorization': 'Bearer ' + key}
    path = '/api/server/projects/demo/events/' + event['eventId'] + '/verify'
    body = {'expectedOrigin': ORIGIN, 'consume': True}
    invalid = client.post(path, json={**body, 'expectedOrigin': 'https://other.example'}, headers=headers).json()
    assert invalid['verified'] is False and invalid['consumed'] is False
    assert invalid['checks']['originMatches'] is False
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(lambda _: client.post(path, json=body, headers=headers).json(), range(4)))
    assert sum(r['verified'] for r in results) == 1
    assert sum(r['consumed'] for r in results) == 1
    assert all(r['checks']['fresh'] for r in results)
    # Replaying original identification is still idempotent; it cannot consume anew.
    assert client.post(path, json=body, headers=headers).json()['verified'] is False
    e = identify(client, snapshot=resilient()).json()
    stale = '/api/server/projects/demo/events/' + e['eventId'] + '/verify'
    client.store.events.update_one({'_id': e['eventId']}, {'$set': {'createdAt': now() - timedelta(seconds=301)}})
    result = client.post(stale, json=body, headers=headers).json()
    assert result['checks']['fresh'] is False and result['verified'] is False
    client.store.events.update_one({'_id': e['eventId']}, {'$set': {'createdAt': now() + timedelta(minutes=1)}})
    assert client.post(stale, json=body, headers=headers).json()['checks']['fresh'] is False
    client.store.events.update_one({'_id': e['eventId']}, {'$set': {'expiresAt': now() - timedelta(seconds=1)}})
    assert client.post(stale, json=body, headers=headers).status_code == 404


def test_recovery_replays_revocation_and_consumption(client):
    event = identify(client, snapshot=resilient()).json()
    key = server_key(client)
    archive = io.StringIO(); backup(client.store, archive)
    verify = '/api/server/projects/demo/events/' + event['eventId'] + '/verify'
    assert client.post(verify, json={'expectedOrigin': ORIGIN, 'consume': True}, headers={'Authorization': 'Bearer ' + key}).json()['consumed']
    assert client.delete('/api/admin/projects/demo/server-key').status_code == 200
    client.store.config['secret'] = 'b' * 64
    restore(client.store, io.StringIO(archive.getvalue()))
    assert client.store.projects.find_one({'_id': 'demo'})['serverKeyHash'] is None
    assert client.store.events.find_one({'_id': event['eventId']})['consumedAt'] is not None
    assert client.get(verify.removesuffix('/verify'), headers={'Authorization': 'Bearer ' + key}).status_code == 401


def test_historical_request_hash_remains_valid_without_new_metadata(client):
    import hashlib
    import json
    request_id = 'historical-request-01'
    first = identify(client, snapshot=resilient(), requestId=request_id).json()
    expected = hashlib.sha256(json.dumps(dict(snapshot=resilient(), requestId=request_id, remember=False, token=None), sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    record = client.store.events.find_one({'_id': first['eventId']})
    assert record['requestHash'] == expected
    original = copy.deepcopy(record['response'])
    for k in ('history', 'origin', 'linkedId', 'tags', 'continuityCode'):
        original.pop(k, None)
    client.store.events.update_one({'_id': first['eventId']}, {'$set': {'response': original}})
    retry = identify(client, snapshot=resilient(), requestId=request_id)
    assert retry.status_code == 200 and retry.json()['eventId'] == first['eventId']
