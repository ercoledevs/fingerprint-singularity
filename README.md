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
import { collectDetailed, digestDetailed, matchDetailed } from 'fingerprint-singularity'

const snapshot = await collectDetailed({ scope: 'my-app.example' })
const observationId = await digestDetailed(snapshot) // sg2_...
const decision = matchDetailed(snapshot, []) // Supply retained candidates here.

console.log(observationId, decision.status, decision.candidateId)
```

The core has **zero runtime dependencies**, no network calls, cookies, storage or permission requests. It reads no screen dimensions. TypeScript declarations are included; browser hashing requires **HTTPS or localhost**.

Detailed mode combines platform and core buckets with scoped GPU, font-availability and canvas hashes. At least two detailed signals must agree, with no comparable conflict. Missing evidence remains `null`; ambiguous matches remain unassigned. [API and examples →](docs/DETAILED.md)

> [!NOTE]
> An observation hash describes the collected data; the backend assigns a visitor ID from retained evidence. Matching does not guarantee identity; browser, font, driver or privacy changes can affect continuity. Keep these IDs separate from authentication. Hashing does not anonymize the data.

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

The console includes a live demo, event and visitor search, decision inspection, project origins, retention, and token revocation/deletion. Connect your site with `fingerprint-singularity/client`. [Integration →](docs/PLATFORM.md) · [HTTPS, updates and backups →](docs/DEPLOYMENT.md)

<details>
<summary><strong>Upgrading an existing installation</strong></summary>

Upgrade the backend before the agent. The agent and console default to detailed mode; select `createAgent({ publicKey, mode: 'legacy' })` to retain the older collection path. Existing v1 exports and records remain unchanged; v1 and v2 candidate pools are separate. [Upgrade guide →](docs/DETAILED.md#upgrade-order)

</details>

## CLI

Search IDs and inspect events with Rich tables, combined filters, cursor pagination and JSON output. Requires Python 3.12+ and a running API; Vue and Node.js are unnecessary on the CLI machine.

From the cloned repository:

```sh
pipx install ./server
singularity login --url http://127.0.0.1:8080
singularity events --project demo --method inferred --platform macos
singularity --json events --project demo --prefix evt_ --limit 100
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
| [Detailed API](docs/DETAILED.md) | Probes, matching rules, schemas and upgrades |
| [Platform API](docs/PLATFORM.md) | Integration, identifiers, enrollment and operating limits |
| [Deployment](docs/DEPLOYMENT.md) | Docker, HTTPS, credentials, backup and recovery |
| [CLI](docs/CLI.md) | ID searches, filters, pagination and automation |
| [Evaluation](docs/EVALUATION.md) · [Verification](docs/VERIFICATION.md) | Labeled datasets, measured results and test scope |
| [Architecture](docs/ARCHITECTURE.md) · [Research](docs/RESEARCH.md) | Design decisions and signal provenance |
| [Legacy API](docs/LEGACY.md) | Original collector, contracts and family-omission policy |

<details>
<summary><strong>Develop and verify the library</strong></summary>

Requires Node.js 20+. From the cloned repository:

```sh
npm ci
npm run check                   # Build, contracts and types
npx playwright install          # Install test browsers
npm run test:browser             # Legacy browser checks and demo
npm run test:detailed-browser    # Detailed probes across browser engines
npm run test:package             # Packed consumer imports
npm run bench                   # Performance and memory
npm run demo                    # Local demo at http://127.0.0.1:4173
```

Use `npm pack` to create a tarball for local integration. CI also checks the deployed platform. See [verification evidence](docs/VERIFICATION.md) for results and limitations.

</details>

## Support

If Singularity is useful to you, [**support its development via PayPal ↗**](https://www.paypal.me/SalvatoreErcole117).

Contributions are optional. Singularity remains available under the [MIT license](LICENSE).
