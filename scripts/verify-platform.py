"""Deployed acceptance. Run only in CI's disposable Compose project."""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
import httpx

BASE = os.environ.get('PLATFORM_URL', 'http://localhost:8080')
ROOT = Path(__file__).resolve().parent.parent
COMPOSE = ['docker', 'compose', '-f', 'compose.yaml', '-f', '.github/compose.test.yaml']


def docker(*args, **kwargs):
    return subprocess.run(COMPOSE + list(args), check=True, **kwargs)


def ready():
    for _ in range(60):
        try:
            if httpx.get(BASE + '/api/health', timeout=2).status_code == 200: return
        except httpx.HTTPError: pass
        time.sleep(1)
    raise AssertionError('API failed readiness')


def login():
    c = httpx.Client(base_url=BASE, timeout=10)
    r = c.post('/api/admin/login', json=dict(username='admin', password=(ROOT / '.admin-password').read_text().strip()))
    r.raise_for_status(); c.headers['X-CSRF-Token'] = r.json()['csrf']
    return c


def main():
    if os.environ.get('CI') != 'true': raise SystemExit('This script replaces a disposable CI database; CI=true is required')
    values = dict(line.split('=', 1) for line in (ROOT / '.env').read_text().splitlines() if line)
    env = {**os.environ, 'TEST_MONGO_URI': f'mongodb://bootstrap:{values["MONGO_ROOT_PASSWORD"]}@127.0.0.1:27018/?authSource=admin'}
    subprocess.run([sys.executable, '-m', 'pytest', 'server/tests', '-q'], check=True, env=env)
    ready()
    c = login()
    p = c.post('/api/admin/projects', json=dict(name='Recovery acceptance', origins=[BASE])).json()
    observation = dict(schema='singularity/v1', scope=p['publicKey'], signals=dict(platform='macos', cores=8, memory=8, language='en', timezone='UTC'))
    response = c.post('/api/v1/identify/' + p['publicKey'], headers={'Origin': BASE}, json=dict(snapshot=observation, requestId='recovery-request-0001', remember=True))
    response.raise_for_status(); event = response.json()
    survivor_response = c.post('/api/v1/identify/' + p['publicKey'], headers={'Origin': BASE}, json=dict(snapshot=observation, requestId='recovery-survivor-001', remember=True))
    survivor_response.raise_for_status(); survivor = survivor_response.json()
    original_survivor = c.get(f'/api/admin/projects/{p["_id"]}/events/{survivor["eventId"]}').json()
    with tempfile.TemporaryDirectory() as directory:
        session = Path(directory) / 'session.json'
        cmd = [shutil.which('singularity'), '--session-file', str(session), '--json']
        def cli(*args, input=None):
            r = subprocess.run(cmd + list(args), input=input, text=True, capture_output=True)
            assert r.returncode == 0, r.stderr
            return json.loads(r.stdout)
        cli('login', '--url', BASE.replace('localhost', '127.0.0.1'), '--password-stdin', input=(ROOT / '.admin-password').read_text())
        assert any(item['_id'] == p['_id'] for item in cli('projects'))
        found = cli('events', '--project', p['_id'], '--prefix', event['eventId'][:12], '--platform', 'macos', '--method', 'enrolled', '--limit', '1')
        assert found['items'][0]['_id'] == event['eventId']
        assert cli('show', event['eventId'], '--project', p['_id'])['visitorId'] == event['visitorId']
        # Human-oriented Rich render is a separate path from JSON output.
        display = subprocess.run(cmd[:-1] + ['events', '--project', p['_id']], text=True, capture_output=True)
        assert display.returncode == 0 and 'Event explorer' in display.stdout
        cli('logout'); assert not session.exists()
    print('PASS installed CLI: login, scoped advanced search, detail, Rich/JSON, logout')
    docker('stop', 'api')
    archive = docker('run', '--rm', '--no-deps', '-T', 'api', 'python', '-m', 'singularity.maintenance', 'backup', capture_output=True).stdout
    docker('up', '-d', 'api'); ready()
    assert c.get(f'/api/admin/projects/{p["_id"]}/events/{event["eventId"]}').status_code == 200
    assert c.delete(f'/api/admin/projects/{p["_id"]}/visitors/{event["visitorId"]}').status_code == 200
    docker('stop', 'api')
    subprocess.run([sys.executable, 'scripts/setup.py', '--rotate'], check=True)
    docker('run', '--rm', '--no-deps', '-T', 'api', 'python', '-m', 'singularity.maintenance', 'restore', '--replace', input=archive)
    docker('--profile', 'web', 'up', '-d', '--force-recreate', 'api', 'web'); ready()
    assert c.get('/api/admin/projects').status_code == 401
    fresh = login()
    retained = fresh.get(f'/api/admin/projects/{p["_id"]}/events').json()['items']
    assert len(retained) == 1 and retained[0] == original_survivor
    rejected = fresh.post('/api/v1/identify/' + p['publicKey'], headers={'Origin': BASE}, json=dict(snapshot=observation, requestId='restored-token-00001', token=event['token']))
    assert rejected.status_code == 410
    docker('restart', 'mongo'); ready()
    assert fresh.get('/api/admin/projects').status_code == 200
    assert fresh.get(f'/api/admin/projects/{p["_id"]}/events/{survivor["eventId"]}').json() == original_survivor
    print('PASS deployed Mongo/API restart, offline backup/restore, deletion replay, credential rotation')
    c.close(); fresh.close()


if __name__ == '__main__': main()
