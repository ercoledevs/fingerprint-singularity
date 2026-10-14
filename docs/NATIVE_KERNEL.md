# Optional Rust kernel

The backend can use a Rust extension for `support/v3` snapshot validation and
matching. Browser collection stays TypeScript, the API stays Python, and MongoDB
queries and the single-worker consistency boundary stay the same. Legacy/v1 and
detailed/v2 always use their existing Python implementations.

The extension accepts and returns Python objects through PyO3, without an
intermediate JSON transport. Candidate validation, the 256-candidate cap,
contradictions, ambiguity and incomplete-rival decisions preserve the reference
contract. Canonical JSON, digest hashing and continuity-code hashing remain in
Python; existing identifiers do not change. Unusual in-process objects requiring
custom Python equality use the Python reference instead of being normalized by
Rust. Valid JSON snapshots use the native path.

## Installation and selection

Docker builds the extension wheel in a separate stage and installs it in the API
image. Rust and the C build tools are absent from the final runtime image.
Rebuild the API to adopt it:

```sh
docker compose --profile web up --build -d --wait
```

For a local backend, install the optional extension from the checkout with
Python 3.12+ and a Rust toolchain (the CI/build image uses Rust 1.99.0):

```sh
python -m pip install './server[server,test]' ./server/native
```

The native dependency graph is committed in `server/native/Cargo.lock`; wheel
builds use that lockfile and a pinned maturin build backend. The separate Python
package remains installable without
Rust or the extension.

`SINGULARITY_KERNEL` is read at process startup:

| Value | Behavior for v3 |
| --- | --- |
| `auto` (default) | Use Rust when installed; otherwise use Python. |
| `python` | Always use the Python reference, including in the Docker image. |
| `rust` | Require the native extension; startup fails if it is absent. |

Restart the API after changing this setting. Compose forwards the environment
variable, so rollback requires no data migration:

```sh
SINGULARITY_KERNEL=python docker compose --profile web up -d --force-recreate api
```

Inspect selection locally with:

```sh
PYTHONPATH=server python -c 'from singularity.kernel import V3_BACKEND; print(V3_BACKEND)'
```

An incompatible extension contract or unexpected native error fails visibly.
Only an absent optional extension and documented Python object compatibility
use fallback; native validation failures retain `kernel.Invalid` error codes.

## Verification and performance

The native CI workflow builds a release wheel, runs Rust formatting and Clippy,
and executes the entire backend suite with both Python and required Rust against
an isolated MongoDB service. It also checks the existing TypeScript oracle and
5,000 deterministic native/reference cases, plus malformed inputs, numeric
types, field order, error precedence and nonmutation.

Reproduce locally; `TEST_MONGO_URI` must point to a test MongoDB with permission
to create and drop disposable databases:

```sh
npm ci --ignore-scripts
npm run build
PYTHONPATH=server SINGULARITY_KERNEL=python python -m pytest server/tests -q
PYTHONPATH=server SINGULARITY_KERNEL=rust python -m pytest server/tests -q
SINGULARITY_KERNEL=rust python scripts/benchmark-native.py
```

Without `TEST_MONGO_URI`, database acceptance tests are skipped. Required Rust
mode prevents a missing extension from silently passing on Python alone.

The benchmark alternates Python/Rust measurement order and includes validation,
matching, Python-to-Rust conversion and Python result allocation. It measures
both identical ambiguous contenders and a unique supported winner at 1, 16, 64
and 256 candidates, after warmup. Evidence is saved to
`artifacts/native/performance.json`. These CPU timings do not establish HTTP
latency, concurrent throughput, memory savings or faster browser collection.

### Local implementation evidence

On 14 October 2026, a release wheel built with Rust 1.99.0, PyO3 0.29.3 and
maturin 1.15.0 was tested on macOS arm64 / Python 3.12.14. The complete backend
suite passed with both forced Python and required Rust: 82 tests in each mode,
using a disposable real MongoDB. The JavaScript suite passed 45 tests and type
checks; Rust formatting and Clippy passed. Independent review compared 112,896
validation mutations with zero remaining mismatches. The Docker base manifest
was verified, but a local Docker image build/runtime was unavailable.

The final paired benchmark used 100 warmups and 1,000 samples per configuration:

| Candidates | Identical contenders, median speedup | Unique winner, median speedup |
| ---: | ---: | ---: |
| 1 | 3.03× | 3.00× |
| 16 | 2.90× | 3.12× |
| 64 | 2.85× | 2.86× |
| 256 | 2.66× | 2.58× |

These compare Python and Rust in the same paired run, including FFI. Absolute
timings vary with host load and must not be compared directly with older
independent baseline runs. The checked-in benchmark regenerates the full p50,
p95 and p99 evidence; the local results do not imply the same speedup for the API.
