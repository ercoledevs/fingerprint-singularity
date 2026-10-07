# Terminal console

The `singularity` command is a standalone Python client for the protected administration API. It renders readable tables and event details, or returns JSON for your scripts. It does not connect directly to MongoDB.

## Install and authenticate

Python 3.12+ is required. From a cloned repository:

```sh
pipx install ./server
singularity login --url https://identity.example.com
```

Alternatively, install into a virtual environment with `python -m pip install ./server`. No server extras, Vue or Node.js are required on the CLI machine. The package has not been published to PyPI.

Login prompts for a password without echoing it. The default username is `admin`; change it with `--username`. For automation, provide one line through stdin:

```sh
singularity login --url https://identity.example.com --password-stdin < .admin-password
```

Sessions last eight hours. An explicit login saves a private `0600` session file under `~/.config/singularity/`, in a `0700` directory. Override it with the global `--session-file` argument. Symlink paths, unsafe permissions and different file owners are rejected. Keep this directory out of shared folders and backups.

TLS certificates are verified and redirects are refused. Local development permits HTTP only with a literal loopback address, such as `http://127.0.0.1:8080`.

## Explore and search

```sh
singularity projects
singularity events --project demo
singularity show evt_REPLACE_WITH_EVENT_ID --project demo
```

Event searches combine all supplied filters using **AND**:

```sh
singularity events --project demo \
  --method inferred --platform macos \
  --after 2026-10-01T00:00:00Z --before 2026-11-01T00:00:00Z

singularity events --project demo --visitor vis_REPLACE_WITH_VISITOR_ID
singularity events --project demo --digest sg1_REPLACE_WITH_DIGEST
singularity events --project demo --prefix evt_a83f --reason stable-candidate
```

| Argument | Behavior |
|---|---|
| `--event`, `--visitor`, `--digest` | Exact ID match |
| `--prefix` | Prefix of an `evt_`, `vis_`, `sg1_` or `sg2_` ID, 4–68 characters |
| `--method` | `provisional`, `inferred`, `enrolled`, `remembered`, `unassigned` |
| `--reason` | Exact decision reason, such as `ambiguous-candidates` |
| `--platform` | `macos`, `windows`, `linux`, `ios`, `android`, `chromeos` |
| `--after` | Inclusive timestamp with timezone |
| `--before` | Exclusive timestamp with timezone |
| `--limit` | 1–100 records, default 25 |
| `--cursor` | Continue a previous search with the same filters |

Dates must include a timezone. UTC `Z` is recommended. Results are ordered by creation time, newest first, then event ID. A cursor expires after 15 minutes and is bound to its project and filters. Every page checks current retention and authorization. Concurrent changes can remove rows; pagination does not freeze the database.

The API accepts typed filters rather than arbitrary MongoDB expressions. Prefixes use indexed string ranges, not user-provided regular expressions. Queries have a server deadline. There is no unbounded export command: iterate bounded pages when exporting data.

## JSON and automation

```sh
singularity --json events --project demo --limit 100 > events.json
singularity --json show evt_REPLACE_WITH_EVENT_ID --project demo
```

Global arguments, including `--json` and `--session-file`, precede the command. JSON goes to stdout; diagnostics go to stderr. Exit codes: `0` success, `1` request/authentication/network error, `2` invalid command syntax. Noninteractive login requires `--password-stdin`; no hidden interactive prompt is used.

## Sign out

```sh
singularity logout
```

Logout removes the local session file and attempts server revocation. An expired or already-revoked session is considered signed out. If the server cannot confirm revocation, the command reports that limitation; the remote session expires within eight hours. The CLI is otherwise read-only. Use the backoffice for project changes and visitor deletion.

## Offline identification evaluation

Run `singularity evaluate observations.jsonl` without signing in. Use `singularity --json evaluate observations.jsonl` for exact counts, denominators, cross-browser pairs and per-device summaries. See [Evaluation](EVALUATION.md) for the labeled data contract and collection protocol.
