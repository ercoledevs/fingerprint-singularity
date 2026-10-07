# Fingerprint Singularity

![Singularity — Fingerprint Identification](docs/assets/banner.png)

<p align="center"><img src="docs/assets/logo.png" width="64" height="64" alt="Singularity logo"></p>

**Browser observations, explainable identification, and a console you can host yourself.**

Fingerprint Singularity includes a TypeScript library, a Python API backed by MongoDB, a Vue backoffice, and a standalone terminal client. Collect display-independent observations, explore event and visitor IDs, and inspect the evidence behind each assignment.

The core library has no runtime dependencies, network calls, cookies, storage, or permission requests. The optional platform manages events, candidate storage, retention and explicit browser enrollment.

## Start the platform

Requirements: Docker Engine with Compose v2, Python 3.9+ for initial setup, and approximately 2 GB available memory.

```sh
git clone https://github.com/ercoledevs/fingerprint-singularity.git
cd fingerprint-singularity
python3 scripts/setup.py
docker compose --profile web up --build -d --wait
# Open http://localhost:8080
```

Sign in as `admin` using the password in the generated `.admin-password` file. Configuration and credentials are private local files and must not be committed.

The console includes a live identification demo, event search and inspection, project origin configuration, retention settings, and visitor token revocation/deletion. See [deployment and recovery](docs/DEPLOYMENT.md) and [platform API](docs/PLATFORM.md).

## Prefer the terminal?

Start the API-only profile and install the CLI with Python 3.12+:

```sh
docker compose --profile headless up --build -d --wait
pipx install ./server
singularity login --url http://127.0.0.1:8080
singularity projects
singularity events --project demo --method inferred --platform macos
singularity --json events --project demo --prefix evt_ --limit 100
```

Use one Compose profile at a time. The standalone CLI does not require Vue, Node.js, or direct database access. It provides Rich tables, event details, combined filters, cursor pagination and JSON output. See the [CLI reference](docs/CLI.md).

## Two different results

| Result | Meaning | What can change |
|---|---|---|
| `digest(snapshot)` | SHA-256 hash of a single observation, including its scope | Changes whenever a normalized value changes |
| `match(snapshot, candidates)` | A compatible candidate among those supplied by the application | May retain the same `candidateId` with different data, or abstain |

An application-assigned ID remains the same when that candidate is returned. To compare visits from different browsers, supply previous observations from your application, for example through your backend. No account is required. Candidate storage and retrieval are managed by your application.

## Getting started

Development requires Node.js 20+. Browser code requires modern ES modules; hashing requires Web Crypto over HTTPS or localhost.

```sh
git clone https://github.com/ercoledevs/fingerprint-singularity.git
cd fingerprint-singularity
npm ci
npm run check
npm run demo
# http://127.0.0.1:4173
```

The package is not published on npm. To use it in another project:

```sh
npm pack
# In the consuming project, install the generated tarball:
npm install /path/to/fingerprint-singularity-0.2.0.tgz
```

```ts
import { collect, digest, match, type Candidate } from 'fingerprint-singularity'

const snapshot = collect({ scope: 'my-app.example' })
const fingerprint = await digest(snapshot)

// The application supplies the full relevant set, with its own IDs and retention.
// No previous observations are available yet in this example.
const candidates: Candidate[] = []
const result = match(snapshot, candidates)

console.log(fingerprint) // sg1_<64 hexadecimal characters>: observation hash
console.log(result.status, result.reason)
if (result.status === 'matched') {
  console.log(result.candidateId) // Hypothesized continuity, not authenticated identity
}
```

Example of continuity when another browser does not expose memory:

```ts
const previous = {
  schema: 'singularity/v1' as const,
  scope: 'my-app.example',
  signals: { platform: 'linux' as const, cores: 8, memory: 8, language: 'en', timezone: 'UTC' },
}
const current = { ...previous, signals: { ...previous.signals, memory: null } }
match(current, [{ id: 'candidate-123', snapshot: previous }]).candidateId
// 'candidate-123'; the two digests differ.
```

## Signals used

| Family | Normalized value | Weight | Limitation |
|---|---|---:|---|
| Platform | `windows`, `macos`, `ios`, `android`, `linux`, `chromeos` | 3 | The reported platform can be altered; an iPad in desktop mode may appear as macOS |
| Compute | Reported core count, rounded down into buckets from 1–64 | 2 | The browser may limit it; a change often causes abstention |
| Compute | Reported memory, buckets from 0.25–64 GiB | 1 | Approximate and unavailable in some browsers |
| Locale | Primary language, without region | 1 | Configurable separately in each browser |
| Locale | Time zone name | 1 | Can change; different aliases remain distinct |

Missing or blocked data is `null` and earns no points, even when missing on both sides. The full user agent string is not collected: it is read only to derive the platform family, without retaining versions or model information. Families are operational groupings, **not statistically independent evidence**.

Screen, resolution, viewport, zoom, touch, GPU, WebGL, canvas, audio, fonts, IP, battery, and browser and operating system versions are excluded. This removes direct dependence on those measurements; it does not prove that hardware changes cannot indirectly alter other system signals.

## Matching with family omission

The `envelope/v1` policy requires:

1. Similarity and coverage of at least **0.75**, across all three families. The denominator includes missing signals. Different known platforms prevent qualification.
2. A margin of at least **0.15** over the best rival without contradictions. When there are no rivals, the margin is `null` and this check passes.
3. The same candidate must pass the checks after each of the three families is omitted in turn. Each reduced comparison requires both remaining families and recalculates the denominator.

Every reduced trial reconsiders **all** candidates, including those initially rejected. Omitting the platform also removes its veto. A candidate therefore cannot pass solely because a fragile value excluded its rivals. The result exposes contributions, coverage, contradictions, and omission trials.

These thresholds are fixed, versioned heuristics, not calibrated against a population. With the current weights, a change in core count can pass the initial threshold but fail the reduced trials. A change in a single signal with weight 1 may be tolerated. Abstention may be frequent.

| Status | Meaning |
|---|---|
| `matched` | One candidate passes every trial within the supplied set |
| `unmatched` | Empty list or no qualified candidate with sufficient evidence |
| `abstain` | Incomplete evidence, ambiguous candidates, or an unstable result in reduced trials |

Precedence: full validation → empty list → observation evidence → qualification → margin → omission trials. An error in any candidate fails the entire call; there are no partial results. `candidateId` is always `null` unless the status is `matched`. Do not automatically assign a new ID for every abstention: doing so would create falsely distinct devices. Do not automatically modify a candidate based on an uncertain match.

The diagnostic `candidates` list preserves input order; the decision and omission reports are independent of that order. Ties are not resolved by arbitrarily assigning an ID.

**Candidate selection matters:** supplying a single device with common data can produce an apparently unambiguous result. A pair of candidates with equivalent observations causes abstention. No hash or margin eliminates collisions in the source observations.

## API and contracts

- `collect({ scope, environment? }): Snapshot`: synchronous collection. The optional adapter makes tests reproducible; it is required in Node.
- `canonicalize(snapshot): string`: v1 JSON tuple, frozen order, no timestamp.
- `digest(snapshot): Promise<string>`: SHA-256 with the `sg1_` prefix; requires Web Crypto, with no random fallback.
- `compare(left, right): Comparison`: pairwise comparison. `qualifies` does not mean `matched`: it does not check rivals or reduced trials.
- `match(snapshot, candidates): MatchResult`: pure function; at most 256 candidates, with no truncation.
- `parseSnapshot(json)` / `validateSnapshot(value)`: strictly validated inputs; return a copy.
- `SCHEMA`, `POLICY_VERSION`, `POLICY`, `LIMITS`, `SingularityError`: exported contracts.

Errors expose a `code`: `INVALID_INPUT`, `INCOMPATIBLE_SCHEMA`, `SCOPE_MISMATCH`, `LIMIT_EXCEEDED`, `DUPLICATE_ID`, `BROWSER_UNAVAILABLE`, `CRYPTO_UNAVAILABLE`.

Scope and IDs: 1–128 characters in the ASCII alphabet documented by the validator. Snapshot JSON: at most 2,048 UTF-16 code units; also enforce an HTTP body limit before passing in network data. Different scopes are not compared and produce different digests. Scope is a public namespace, not an access control or protection against input modification. Objects with unknown properties, accessors, non-ordinary prototypes, or non-normalized values are rejected. A hostile JavaScript proxy in the same process is not an isolated or safe input: use size-limited JSON for untrusted data.

## Data and lifecycle

No persistent state: no cookies, localStorage, IndexedDB, HTTP calls, or recovery after deletion. Integrators decide the purpose, privacy notice, retention, expiration, and deletion of observations. Removing candidates from application storage and clearing application caches makes them unavailable to the library; there is no hidden recovery mechanism.

The data can be spoofed and may be personal data. **Do not use digests, similarity, or matches as authentication, authorization, or anti-fraud evidence.** Hashing does not make this data anonymous. There is no automatic telemetry.

Schema and policy versions are separate from the package version. Future changes to normalization or canonicalization will require a new schema; changes to weights, thresholds, or semantics will require a new policy. Do not mix schemas: the library rejects them. To roll back, reinstall the previous tarball and use only compatible candidates; this version neither runs migrations nor writes to storage.

## Verification and development

```sh
npm run check                    # build, contracts, and types
npx playwright install          # required browsers, if missing
npm run test:browser             # Chromium, Firefox, WebKit + demo
npm run bench                   # scaling, warmup, median/p95, Node heap
npm pack --dry-run              # distributed contents
```

The browser check fails if an engine cannot start: there are no silent skips. Local regression budgets: collection p95 <10 ms, matching against 256 candidates p95 <50 ms, retained Node heap after GC <32 MiB. These are verification limits for this environment, not promises for every device. Measurements do not demonstrate accuracy. Local reports in `artifacts/` are not versioned; [VERIFICATION.md](docs/VERIFICATION.md) describes the delivered run and its limitations.

Graphify indexes `src` for development queries, without external LLMs. [ARCHITECTURE.md](docs/ARCHITECTURE.md) describes modules and policy; [RESEARCH.md](docs/RESEARCH.md) records provenance and decisions. MIT license, retained from the project's original repository.
