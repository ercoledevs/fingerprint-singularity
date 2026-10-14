<div align="center">

![Singularity — Identification Platform](https://raw.githubusercontent.com/ercoledevs/fingerprint-singularity/main/docs/assets/banner.svg)

[![CI](https://github.com/ercoledevs/fingerprint-singularity/actions/workflows/ci.yml/badge.svg?branch=main)](https://github.com/ercoledevs/fingerprint-singularity/actions/workflows/ci.yml)
[![npm version](https://img.shields.io/npm/v/fingerprint-singularity?color=b7e49e)](https://www.npmjs.com/package/fingerprint-singularity)
[![MIT license](https://img.shields.io/badge/license-MIT-d7e7e1)](LICENSE)

**Browser observations. Explainable identification. Your own infrastructure.**

TypeScript library · Python API · MongoDB · Vue console · Terminal client

[Library](#library) · [Self-host](#self-host) · [CLI](#cli) · [Docs](#documentation) · [Support](#support)

</div>

## Library

```sh
npm install fingerprint-singularity
```

Collect scoped observations and compare them with candidates retained by your application:

```ts
import { collectResilient, continuityCode, matchResilient } from 'fingerprint-singularity'

const snapshot = await collectResilient({ scope: 'my-app.example' })
const code = await continuityCode(snapshot) // sc1_... or null
const decision = matchResilient(snapshot, []) // Supply retained candidates here.

console.log(code, decision.status, decision.candidateId)
```

The core has **zero runtime dependencies**, no network calls, cookies, storage or permission requests. It reads no screen dimensions. TypeScript declarations are included; browser hashing requires **HTTPS or localhost**.

Resilient mode normalizes recognized GPU models, checks 64 fonts and interprets canvas differences by rendering engine. A **continuity code** can be recreated from the same scoped model/font profile without storage. The backend compares retained evidence and leaves ambiguous matches unassigned. [API and upgrades →](docs/RESILIENT.md)

> [!NOTE]
> A continuity code describes a profile; the backend assigns a visitor ID from retained evidence. Identical profiles can share a code, and missing GPU/font evidence yields `null`. Browser, font, driver or privacy changes can affect continuity. Keep these IDs separate from authentication. Hashing does not anonymize the data.

## Self-host

Run the Python API, MongoDB and Vue backoffice on your server. The platform is deployed separately from the npm library.

**Requires:** Docker Compose v2 · Python 3.9+ for setup · approximately 2 GB RAM

```sh
git clone https://github.com/ercoledevs/fingerprint-singularity.git
cd fingerprint-singularity
python3 scripts/setup.py
docker compose --profile web up --build -d --wait
```

Open **[localhost:8080](http://localhost:8080)**. Sign in as `admin` with the password in `.admin-password`. Keep this file and `.env` private.

The console includes a live demo, event and visitor search, first/previous visits, project origins, retention and deletion. Server keys support event retrieval, freshness checks and one-time consumption. Connect your site with `fingerprint-singularity/client`. [Integration →](docs/PLATFORM.md) · [HTTPS, updates and backups →](docs/DEPLOYMENT.md)

<details>
<summary><strong>Upgrading an existing installation</strong></summary>

Upgrade the backend before the agent. Version 0.4 defaults to resilient mode with a new candidate pool; inferred visitor IDs can change during migration. Use `mode: 'detailed'` for v2 or `mode: 'legacy'` for v1 to retain the previous collection path. [Upgrade guide →](docs/RESILIENT.md#upgrade-order)

</details>

## CLI

Search IDs and inspect events with Rich tables, combined filters, cursor pagination and JSON output. Requires Python 3.12+ and a running API; Vue and Node.js are unnecessary on the CLI machine.

From the cloned repository:

```sh
pipx install ./server
singularity login --url http://127.0.0.1:8080
singularity events --project demo --method inferred --platform macos
singularity events --project demo --linked order:123 --origin https://shop.example
singularity --json events --project demo --prefix sc1_ --limit 100
```

<details>
<summary><strong>Run an API-only server</strong></summary>

After running `python3 scripts/setup.py`, start the headless profile. If the web profile is running, stop its web service first; both profiles use port 8080.

```sh
docker compose --profile web stop web
docker compose --profile headless up --build -d --wait
```

[CLI reference →](docs/CLI.md) · [Switch deployment profiles →](docs/DEPLOYMENT.md#headless-server)

</details>

## Documentation

| Guide | Contents |
| :--- | :--- |
| [Resilient API](docs/RESILIENT.md) | Profile codes, cross-engine matching and upgrades |
| [Detailed API](docs/DETAILED.md) | Previous v2 probes and matching contract |
| [Platform API](docs/PLATFORM.md) | Integration, identifiers, enrollment and operating limits |
| [Deployment](docs/DEPLOYMENT.md) | Docker, HTTPS, credentials, backup and recovery |
| [CLI](docs/CLI.md) | ID searches, filters, pagination and automation |
| [Evaluation](docs/EVALUATION.md) · [Verification](docs/VERIFICATION.md) | Labeled datasets, measured results and test scope |
| [Intensive 0.4 comparison](docs/INTENSIVE_0_4.md) · [Rust assessment](docs/RUST_ASSESSMENT.md) | Cache, private sessions, collision rates and measured CPU costs |
| [Architecture](docs/ARCHITECTURE.md) · [Research](docs/RESEARCH.md) | Design decisions and signal provenance |
| [Fingerprint research](docs/FINGERPRINT_RESEARCH.md) | SDK analysis, observable behavior and adopted patterns |
| [Legacy API](docs/LEGACY.md) | Original collector, contracts and family-omission policy |

<details>
<summary><strong>Develop and verify the library</strong></summary>

Requires Node.js 20+. From the cloned repository:

```sh
npm ci
npm run check                   # Build, contracts and types
npx playwright install          # Install test browsers
npm run test:browser             # Legacy browser checks and demo
npm run test:resilient-browser   # Fresh profiles, storage clearing and engine checks
npm run evaluate:resilient       # Paired synthetic v2/v3 regression fixtures
npm run test:package             # Packed consumer imports
npm run bench                   # Performance and memory
npm run demo                    # Local demo at http://127.0.0.1:4173
```

Use `npm pack` to create a tarball for local integration. CI also checks the deployed platform. See [verification evidence](docs/VERIFICATION.md) for results and limitations.

</details>

## Support

If Singularity is useful to you, [**support its development via PayPal ↗**](https://www.paypal.me/SalvatoreErcole117).

Contributions are optional. Singularity remains available under the [MIT license](LICENSE).
