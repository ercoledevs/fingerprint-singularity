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

On the local macOS arm64 test host, 15 serial API samples per candidate population produced maximum observed durations of approximately 2.18 ms (1 candidate), 1.74 ms (8), 2.69 ms (64), 13.09 ms (256) and 2.41 ms (257, overflow). These are in-process API measurements with local MongoDB, not network or production latency. The deterministic synthetic populations at 64/256 candidates abstained; the workload is not a coverage or accuracy study. Admission is capped at 32 requests and writes use a nonwaiting lock.

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
