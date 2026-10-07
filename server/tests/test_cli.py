import json
import os
import stat
import pytest
from singularity.cli import endpoint, load_session, save_session, main


def test_session_permissions_symlinks(tmp_path):
    directory = tmp_path / "private"; directory.mkdir(mode=0o700)
    path = directory / "session.json"
    save_session(path, {"url": "https://example.com", "token": "test"})
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    assert load_session(path)["token"] == "test"
    path.chmod(0o644)
    with pytest.raises(ValueError): load_session(path)
    path.unlink(); path.symlink_to(directory / "target")
    with pytest.raises(ValueError): save_session(path, {})


@pytest.mark.parametrize("url", ["http://example.com", "http://localhost", "https://user:pass@example.com", "https://example.com/path", "ftp://127.0.0.1"])
def test_remote_http_credentials_and_paths_rejected(url):
    with pytest.raises(ValueError): endpoint(url)


def test_loopback_tls_and_noninteractive(capsys, monkeypatch):
    assert endpoint("http://127.0.0.1:8080") == "http://127.0.0.1:8080"
    assert endpoint("https://identity.example.com") == "https://identity.example.com"
    monkeypatch.setattr("sys.stdin.isatty", lambda: False)
    assert main(["login"]) == 1
    captured = capsys.readouterr()
    assert not captured.out and "--password-stdin" in captured.err


@pytest.mark.parametrize('status', [200, 401, 503])
def test_logout_always_removes_local_credentials(tmp_path, monkeypatch, status):
    import httpx
    from singularity.cli import APIError
    directory = tmp_path / 'private'; directory.mkdir(mode=0o700)
    path = directory / 'session.json'
    save_session(path, dict(url='http://127.0.0.1:8080', token='test', csrf='test'))
    def result(*a, **k):
        if status != 200: raise APIError(status, 'Test failure')
        return {'ok': True}
    monkeypatch.setattr('singularity.cli.request', result)
    assert main(['--session-file', str(path), 'logout']) == (1 if status == 503 else 0)
    assert not path.exists()
