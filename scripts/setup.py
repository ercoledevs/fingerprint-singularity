#!/usr/bin/env python3
"""Generate local deployment secrets without dependencies or unsafe shell interpolation."""
import argparse
import hashlib
import os
import secrets
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


def atomic(path, value):
    if path.is_symlink():
        raise SystemExit("Refusing a symlink: " + str(path))
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        os.fchmod(fd, 0o600)
        with os.fdopen(fd, "w") as stream:
            stream.write(value)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main():
    p = argparse.ArgumentParser(description="Configure a Singularity deployment")
    p.add_argument("--origin", default="http://localhost:8080")
    p.add_argument("--rotate", action="store_true", help="Rotate application secret and admin password; preserve database credentials")
    args = p.parse_args()
    root = Path(__file__).resolve().parent.parent
    env = root / ".env"
    if env.exists() and not args.rotate:
        raise SystemExit(".env already exists; it has not been changed. Use --rotate for credential rotation.")
    u = urlsplit(args.origin)
    try:
        _ = u.port
    except ValueError:
        raise SystemExit("Invalid origin port")
    if u.scheme not in ("http", "https") or not u.hostname or u.path or u.query or u.fragment or u.username or u.password:
        raise SystemExit("Use a complete origin without a trailing slash or path")
    if u.scheme == "http" and u.hostname not in ("localhost", "127.0.0.1", "::1"):
        raise SystemExit("Use HTTPS for a remote server")
    values = dict(APP_ORIGIN=args.origin, PORT="8080", BIND_ADDRESS="127.0.0.1", ADMIN_USER="admin",
                  MONGO_ROOT_PASSWORD=secrets.token_hex(32), MONGO_APP_PASSWORD=secrets.token_hex(32),
                  DEMO_PUBLIC_KEY="pk_" + secrets.token_hex(16))
    if args.rotate:
        if not env.exists() or env.is_symlink():
            raise SystemExit("A regular existing .env is required for rotation")
        values = dict(line.split("=", 1) for line in env.read_text().splitlines() if line and not line.startswith("#"))
    password, salt = secrets.token_urlsafe(24), secrets.token_hex(16)
    values["SINGULARITY_SECRET"] = secrets.token_hex(48)
    values["ADMIN_PASSWORD_HASH"] = salt + ":" + hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 600_000).hex()
    atomic(root / ".admin-password", password + "\n")
    atomic(env, "".join(k + "=" + v + "\n" for k, v in values.items()))
    print("Configuration saved in .env (0600). Admin password saved in .admin-password (0600).")
    print("Start web: docker compose --profile web up --build -d")
    print("Or headless: docker compose --profile headless up --build -d")


if __name__ == "__main__":
    main()
