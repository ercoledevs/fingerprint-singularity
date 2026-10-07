# Version 0.1.0 verification

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

Retained Node heap after GC: approximately **5 KiB** in the run; pre-GC delta approximately **23 MiB**. These are noisy observations, not guaranteed maximum allocations. There is no portable measure of peak allocations across all browsers: the workload limit also follows from 5 signals, 3 omissions, and 256 candidates. Regression budget: retained heap <32 MiB. No performance or accuracy comparison with FingerprintJS.

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
