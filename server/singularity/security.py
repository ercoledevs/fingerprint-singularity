import base64
import hashlib
import hmac
import json
import os
import secrets
from datetime import datetime, timezone
from urllib.parse import urlsplit


def now():
    value = datetime.now(timezone.utc)
    return value.replace(microsecond=(value.microsecond // 1000) * 1000)


def uid(prefix):
    return prefix + secrets.token_hex(16)


def password_hash(password, salt=None):
    salt = salt or secrets.token_hex(16)
    return salt + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()


def verify_password(password, encoded):
    try:
        salt, _ = encoded.split(":")
        return hmac.compare_digest(password_hash(password, salt), encoded)
    except ValueError:
        return False


def mac(key, value):
    return hmac.new(key.encode(), value.encode(), hashlib.sha256).hexdigest()


def origin(value):
    u = urlsplit(value)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.path or u.query or u.fragment:
        raise ValueError("An origin must be scheme://host[:port], without a path")
    if u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise ValueError("Remote origins require HTTPS")
    # Ports are parsed here too, rejecting malformed input.
    _ = u.port
    return value


def seal_cursor(key, payload):
    raw = base64.urlsafe_b64encode(json.dumps(payload, separators=(",", ":")).encode()).decode().rstrip("=")
    return raw + "." + mac(key, raw)


def open_cursor(key, value):
    if len(value) > 2048:
        raise ValueError("Invalid cursor")
    raw, signature = value.split(".")
    if not hmac.compare_digest(signature, mac(key, raw)):
        raise ValueError("Invalid cursor")
    return json.loads(base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4)))


def settings():
    secret = os.environ.get("SINGULARITY_SECRET", "")
    password = os.environ.get("ADMIN_PASSWORD_HASH", "")
    if len(secret) < 48 or len(password) < 80:
        raise RuntimeError("Run scripts/setup.py to generate server credentials")
    return dict(secret=secret, password=password, username=os.environ.get("ADMIN_USER", "admin"),
                origin=origin(os.environ.get("APP_ORIGIN", "http://localhost:8080")),
                mongo=os.environ["MONGO_URI"], state=os.environ.get("STATE_DIR", "/state"),
                demo_key=os.environ["DEMO_PUBLIC_KEY"])
