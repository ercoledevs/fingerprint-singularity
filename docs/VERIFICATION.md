# Version 0.3.0 verification

Local checks on **7 October 2026**, macOS arm64, Node.js 24.21.0, Python 3.12 and MongoDB 8.0.16:

| Check | Result | Scope |
|---|---|---|
| Core and client | PASS | 38 Node tests, consumer types, offline packed-package runtime/type checks |
| Backend and CLI | PASS | 50 Python tests with real isolated MongoDB databases |
| Version parity | PASS | 2,107 detailed TypeScript/Python cases, in addition to legacy parity/golden checks |
| Detailed real-browser probes | PASS locally | 400 repeated collections across Chromium 145 and WebKit 26, four ephemeral contexts per engine, viewport/DPR/reload changes |
| Font isolation | PASS | Host remote/local font overrides cannot alter probe results or initiate font downloads; blocked isolation returns null; temporary frames are removed |
| Cross-browser continuity | NOT PRESERVED in this sample | Chromium and WebKit on the same host had different canvas hashes; strict detailed matching rejected the association |
| Backend population replay | PASS | 2,304 identification requests, 24 isolated projects, synthetic observations through actual FastAPI/MongoDB; metrics equal the pure simulator |
| Legacy contention replay | PASS | 96/96 unique concurrent requests and 64/64 idempotent retries accepted; one visitor/one replay event as appropriate |
| Real-device population accuracy | UNKNOWN | No independently labeled multi-device longitudinal cohort or commercial reference outputs |

Local Firefox cannot start reliably on this macOS host. The CI workflow is configured to run all three engines on Linux, including the new detailed probe checks and full Compose/UI acceptance. A local two-engine result must not be described as a three-engine result.

## Paired synthetic evaluation

Run `python scripts/evaluate-detailed.py --out artifacts/improvement-v03` after installing the Python package. The deterministic suite evaluates **82,944 simulated policy-visits**: 3 seeds × 3 arrival orders × 3 populations × 6 scenarios × 4 policies × 64 devices × 2 visits. These repeated evaluations are not independent real devices. Features come from finite, shared GPU/font groups and coarser correlated rendering groups; device labels never enter fingerprints. Complete cloned profiles and missing-first-visit observations are deliberate counterexamples.

**Exclusive two-visit continuity** means both visits receive the same non-null ID and no other labeled simulated device receives it. **Link precision** means true same-device links divided by all assigned same-ID links; undefined denominators remain null. Coverage and false-link counts must be considered alongside either rate.

For unchanged observations, ranges across the nine seed/order combinations are:

| Synthetic population | Policy | Exclusive continuity | Link precision | Assigned visits |
|---|---|---:|---:|---:|
| Diverse profiles | Legacy v1 | 9.38–23.44% | 41.46–100% | 26.56–35.94% |
| Diverse profiles | Detailed v2 | 96.88–100% | 94.12–100% | 100% |
| Shared office profiles | Legacy v1 | 0% | 0% where defined | 1.56–3.91% |
| Shared office profiles | Detailed v2 | 26.56–32.81% | 23.88–32% | 100% |
| Identical profiles | Either | 0% | 0.79% | 100% |

The detailed policy is not uniformly better. In the office fixture it assigns more visits but makes **136–204 false pair links**, versus **0–6** for largely abstaining v1. When the synthetic canvas changes on every second visit, detailed exclusive continuity is **0%**. Sparse-first enrollment reduces separation because an anchor cannot compare a field it never observed. Complete clones remain inseparable from these inputs.

Exact-coarse equality reaches 70.31–84.38% unchanged diverse continuity; exact-detailed equality reaches the same unchanged-observation results as v2. The custom two-detail matching rule adds no measured gain in that scenario. Its additional benefit here appears when GPU evidence disappears; exact equality splits those visits. Neither experiment establishes accuracy in the wild.

The unchanged legacy API contention replay went from **4/96 accepted requests in 0.2 to 96/96 in 0.3**, using 32 client workers. This measures in-process TestClient handling with local MongoDB, not production network throughput. Processing accepted requests also takes longer than rejecting them immediately; the result is not a latency-reduction claim. Quotas and evidence floors were retained.

## Reproduce

```sh
npm ci --ignore-scripts
npm run check
npm run test:package
npm run build:console
npm run test:detailed-browser
python -m pip install './server[server,test]'
TEST_MONGO_URI=mongodb://127.0.0.1:27018 python -m pytest server/tests -q
python scripts/evaluate-detailed.py --out artifacts/improvement-v03
```

Artifacts include `paired-results.json`, `paired-observations.jsonl`, `paired-api.json` and `browsers.json`. Isolated database fixtures remove their test databases after completion. Missing MongoDB skips database checks rather than proving them. CI deploys a disposable Compose stack for the full browser/CLI/recovery checks.

---

# Version 0.2.0 platform verification

Verified on **7 October 2026**. [GitHub Actions run 37605714288](https://github.com/ercoledevs/fingerprint-singularity/actions/runs/37605714288) passed both jobs on commit `2938a59d1ca52fe26cf8591ff99908904394706d`.

| Check | Result | Evidence |
|---|---|---|
| Core library | PASS | 29 Node tests, consumer types, Chromium/Firefox/WebKit, performance budget and package dry run |
| Python backend and CLI | PASS | 42 tests against real MongoDB, including TypeScript/Python kernel parity |
| Distributed deployment | PASS | Actual Docker Compose build and startup with MongoDB 8.0.16; full web and headless profiles |
| Recovery | PASS | API/Mongo restart, offline backup/restore, retained event equality, independent deletion replay and credential rotation |
| Deployed CLI | PASS | Installed command: login, scoped combined filters, pagination-related API checks, event detail, Rich/JSON output and logout |
| Deployed browser workflows | PASS | Chromium, Firefox and WebKit: identification, fresh enrollment and token continuity, login, search/errors, project creation, delivered SDK, mobile layout and keyboard interaction |
| Sparse browser observations | PASS | Firefox's default CI environment lacked a valid language observation and memory; the UI displayed an unassigned event. A separately configured locale exercised the positive enrollment path without weakening evidence floors. |
| Offline evaluator | PASS | Pair-count regression oracle, cohort/null/reference semantics, strict input validation, independent randomized oracle and real size limits |
| Packed npm consumer | PASS locally | Offline installation into an empty project, package-name imports for core/client, execution and consumer TypeScript compilation |
| Physical-device and longitudinal accuracy | UNKNOWN | No independently labeled real-device cohort or longitudinal comparison was collected |

The browser artifact on that CI run contains desktop/mobile screenshots and redacted acceptance logs. The checks establish implementation behavior, not population identification accuracy.

## Reproduce the platform checks

Use a disposable local MongoDB instance and Python 3.12+:

```sh
python -m pip install './server[server,test]'
TEST_MONGO_URI=mongodb://127.0.0.1:27018 python -m pytest server/tests -q
npm run test:package
npm run build:console
singularity evaluate examples/evaluation.synthetic.jsonl
```

Database tests create isolated test databases. Without `TEST_MONGO_URI`, database-dependent tests are skipped; a skipped test is not a PASS. Full deployment, destructive recovery fixtures and three-engine UI acceptance run in the disposable GitHub Actions stack.

## Bounded synthetic workload

On the local macOS arm64 test host, 15 serial API samples per candidate population produced maximum observed durations of approximately 2.18 ms (1 candidate), 1.74 ms (8), 2.69 ms (64), 13.09 ms (256) and 2.41 ms (257, overflow). These are in-process API measurements with local MongoDB, not network or production latency. The deterministic synthetic populations at 64/256 candidates abstained; the workload is not a coverage or accuracy study. In version 0.2, admission was capped at 32 requests and writes used a nonwaiting lock.

---

# Historical core 0.1.0 verification

Local run on **October 7, 2026**, macOS arm64, Node.js 24.21.0. The result concerns the experimental library's contract; it does not demonstrate physical identification or accuracy across a population.

| Check | Result | Evidence |
|---|---|---|
| TypeScript compilation | PASS | `npm run build`, strict configuration and public declarations |
| Node tests | PASS | 29 tests with `node --test tests/*.test.mjs` |
| Consumer types | PASS | `npm run test:types` |
| Independent falsification | PASS | Source reread, test rerun, and reproductions of the corrected defect |
| Combinatorial invariants | PASS | Verifier: 59,049 observation/candidate state scenarios, ordering, and abstention on duplicates |
| Chromium 145.0.7632.6 | PASS | Real execution, desktop/mobile viewports, unchanged hash, checks for no storage/network use, matcher |
| WebKit 26.0 | PASS | The same real checks |
| Local Firefox 146.0.1 | UNKNOWN | plugin-container / macOS sandbox startup failure before library execution; headed mode also unavailable |
| Chromium/WebKit comparison on the same host | PASS for this case | Compatible candidate; one host, not an accuracy test |
| Node performance budget | PASS | 256 candidates, three omissions, warmup, and 200 samples |
| Physical monitor change | UNKNOWN | Signal exclusion and viewport changes verified; no hardware replacement performed |
| Stability over time / population uniqueness | UNKNOWN | No labeled cohort or longitudinal observations |

The full local browser command correctly returns exit code 1 for Firefox: **this was not an entirely green run**. The GitHub Actions pipeline is configured on Linux to run all three engines; its result must be checked against the actual commit, not inferred from configuration.

## Verified CI result

[GitHub Actions run 37590466814](https://github.com/ercoledevs/fingerprint-singularity/actions/runs/37590466814) completed successfully on commit `3570346d31ca8c5bc7a38a478991324907e41b18`. It passed 29 Node tests, type checks, Chromium, Firefox, WebKit, the benchmark, and `npm pack --dry-run`. This CI result is separate from the historical local Firefox startup failure above.

## Defect found and corrected

The verifier demonstrated that an array with a custom `Symbol.iterator` could hide rivals or supply more than 256 candidates while declaring a shorter length. Matching now captures the length and reads each numeric element through its property descriptor, without executing iterators or getters. It rejects holes, inherited elements, and accessors. The original reproductions and new regression tests pass.

## Local measurements

Node run after the fix: collection with an adapter at approximately **0.003 ms** p95; full matching with 256 candidates at approximately **0.847 ms** p95. In the available browsers, local runs meet collection p95 <10 ms and matching p95 <50 ms. Browser clocks may have reduced precision.

Retained Node heap after GC: approximately **5 KiB** in the run; pre-GC delta approximately **23 MiB**. These are noisy observations, not guaranteed maximum allocations. There is no portable measure of peak allocations across all browsers: the workload limit also follows from 5 signals, 3 omissions, and 256 candidates. Regression budget: retained heap <32 MiB.

## Reproduction

```sh
npm ci --ignore-scripts
npm run check
npx playwright install chromium firefox webkit
npm run test:browser
npm run bench
npm pack --dry-run
```

Raw reports are written to `artifacts/`, which is excluded from Git. They are not sent elsewhere. A new environment may change timings or browser availability: report failures without turning an unexecuted test into a PASS.
