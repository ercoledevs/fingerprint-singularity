import asyncio
from types import SimpleNamespace
from singularity import api


def test_total_body_deadline_and_admission(monkeypatch):
    clock = [0.0]
    monkeypatch.setattr(api, 'time', SimpleNamespace(monotonic=lambda: clock[0]))
    called, messages = [], []
    async def app(*args): called.append(True)
    async def receive():
        clock[0] += 3
        return {'type': 'http.request', 'body': b'', 'more_body': True}
    async def send(message): messages.append(message)
    limits = api.Limits(app)
    asyncio.run(limits({'type': 'http', 'path': '/', 'headers': []}, receive, send))
    assert messages[0]['status'] == 408 and not called
    assert limits.active == 0 and clock[0] <= 12
    messages.clear(); limits.active = 32
    asyncio.run(limits({'type': 'http', 'path': '/', 'headers': []}, receive, send))
    assert messages[0]['status'] == 503 and not called
