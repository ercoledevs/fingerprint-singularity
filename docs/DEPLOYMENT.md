# Self-hosted deployment

## Quick start

Install Docker Engine with Compose v2 and Python 3.9+ on the server. Allow roughly 2 GB RAM for the default stack, plus disk for retained events and backups.

```sh
git clone https://github.com/ercoledevs/fingerprint-singularity.git
cd fingerprint-singularity
python3 scripts/setup.py
docker compose --profile web up --build -d --wait
```

Open `http://localhost:8080`. The generated `.admin-password` contains the initial password for `admin`. `.env` contains deployment secrets. Both files are mode `0600`, ignored by Git, and excluded from Docker build contexts. Setup refuses to overwrite an existing configuration unless `--rotate` is explicitly supplied.

The stack includes FastAPI, MongoDB and an Nginx/Vue console. MongoDB is on an internal network with no host port; the API uses a database-scoped read/write account. The reverse proxy is bound to `127.0.0.1:8080` by default. Named volumes retain the database and independent deletion ledger across container restarts.

## Public HTTPS endpoint

Choose the external origin during first setup:

```sh
python3 scripts/setup.py --origin https://identity.example.com
docker compose --profile web up --build -d --wait
```

Place your existing HTTPS reverse proxy in front of `127.0.0.1:8080`, preserving the request path and `Origin` header. For example, a host-installed Caddy configuration is:

```caddyfile
identity.example.com {
    reverse_proxy 127.0.0.1:8080
}
```

Configure DNS and certificate issuance for your server. The external origin must match `APP_ORIGIN` exactly, without a trailing slash. Keep the private upstream bound to loopback. Do not expose MongoDB, add extra API workers, or run multiple API replicas. The web UI uses secure cookies when `APP_ORIGIN` is HTTPS.

Set each application's origin in the backoffice. The browser SDK uses project-specific CORS; administration stays on the console origin. For additional abuse protection, apply request limits at your public reverse proxy.

## Headless server

For CLI/API use without Vue:

```sh
docker compose --profile headless up --build -d --wait
```

The gateway serves `/api/` only. The CLI installs independently with Python 3.12+ and `pipx install ./server`. Browser applications can bundle the npm package client and point it at the headless endpoint.

Both profiles use the same host port. Switch deliberately:

```sh
# Full console → headless
docker compose --profile web stop web
docker compose --profile headless up -d --wait

# Headless → full console
docker compose --profile headless stop gateway
docker compose --profile web up --build -d --wait
```

## Health, updates and credentials

`GET /api/health` checks database connectivity. Compose healthchecks gate startup. Inspect service state with `docker compose ps` and logs with `docker compose logs api`. Access logs are disabled on the API; avoid logging request bodies or credentials in your outer proxy.

To rotate the application secret and admin password:

```sh
docker compose stop api
python3 scripts/setup.py --rotate
docker compose --profile web up -d --force-recreate api web
```

For headless mode, replace `--profile web` and `web` with `--profile headless` and `gateway`. Rotation invalidates existing admin sessions and remembered-browser tokens. It preserves MongoDB credentials and the project public keys. Database-account rotation is a separate operator procedure and must update the Mongo user as well as `.env`.

Before an update, take a backup, record the current Git commit and image versions, then pull/build the desired release. Keep the old commit available for rollback. Do not run an older release against a future schema without its migration guidance. This release uses `singularity-backup/v1` and has no automatic schema migration.

## Consistent backup

Stop the API before creating an offline snapshot. The maintenance process takes the same worker lock, so it refuses concurrent operation with a running API.

```sh
mkdir -p backups
chmod 700 backups
docker compose stop api
umask 077
docker compose run --rm --no-deps -T api \
  python -m singularity.maintenance backup > backups/singularity.jsonl
docker compose --profile web up -d api
```

Verify that the command succeeded before treating the output as a backup. It ends with a completion record. Store the archive encrypted off-server, and retain the matching application version. Admin sessions are excluded.

The **`identity_state` volume is independent of database backups**. It contains a state ID and a durable deletion ledger. Keep a current copy of that volume independently, including cancellations made after older database backups. Never restore an older deletion ledger over a newer one. If that independent state is lost, the supplied restore procedure refuses a state-ID mismatch.

## Restore and deletion replay

Restoration replaces database contents. Keep the API stopped throughout. Retain the current `identity_state` volume; do not use `docker compose down -v` on a live installation.

```sh
docker compose stop api
python3 scripts/setup.py --rotate
docker compose run --rm --no-deps -T api \
  python -m singularity.maintenance restore --replace < backups/singularity.jsonl
docker compose --profile web up -d --force-recreate api web
```

The restore checks the archive format/completion, matching independent state and changed application secret before replacement. It uses a quarantine marker during replacement, removes restored possession tokens, excludes admin sessions and replays the deletion ledger before reopening. An interrupted restore leaves the marker and blocks API startup; repeat the complete restore with the same current ledger. Do not remove the marker to bypass an incomplete restore.

After restoration, sign in with the newly generated password, check health and retained events, and verify that recently deleted visitors remain absent. Expired records are excluded from reads even before TTL cleanup. Restart the chosen web/gateway service when recreating the API so its upstream address is refreshed.

## Local development

The full container stack is the supported plug-and-play path. For source development, install Node.js 22.12+ and Python 3.12+, run MongoDB on loopback port `27018`, then:

```sh
python3 scripts/setup.py
python3 -m venv .venv
.venv/bin/pip install -e 'server[server,test]'
npm ci
npm ci --prefix web
APP_ORIGIN=http://localhost:8081 .venv/bin/python scripts/dev-api.py
# In another terminal:
npm run dev --prefix web
```

The development script uses the separate `singularity_dev` database and `.local-state` directory. Automated database tests require `TEST_MONGO_URI` pointing at a disposable MongoDB instance with permission to create isolated test databases. Do not point tests at production.
