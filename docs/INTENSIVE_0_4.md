# Intensive 0.4.0 comparison

Paired evaluation on **14 October 2026** against the exact public npm packages **0.3.0** and **0.4.0**, with published SHA-512 integrity verified. The prior backend 0.3.1 retains the same v2 observation/matching contract; this experiment compares SDK behavior, not retrieval performance between backend releases.

**Result:** observation digests were stable within each tested browser, but 0.4.0 did not preserve a universal ID across browsers on this host. The new profile code was available in installed Chrome and unavailable in the automated Chromium/WebKit environments. Synthetic normalization gains coexist with regressions in shared profiles.

## Actual browser matrix

One macOS arm64 physical host, three successful browser builds, **3,750 paired visits / 7,500 collector calls** in the completed matrix. Each browser contributes 250 visits per arm: persistent normal profile, cleared site data, restarted persistent profile, ten fresh incognito contexts, and ten fresh normal profiles with empty caches. Both SDKs run on every visit; their order alternates.

| Browser | Build | Stable sg2 digest | Stable sg3 digest | sc1 availability | Stable available sc1 |
| --- | --- | ---: | ---: | ---: | ---: |
| chromium | 145.0.7632.6 | 100.00% | 100.00% | 0.00% | N/A |
| webkit | 26.0 | 100.00% | 100.00% | 0.00% | N/A |
| chrome | 155.0.8059.40 | 100.00% | 100.00% | 100.00% | 100.00% |

Every digest rate has a denominator of 1,250 collected observations for that browser. A null code is unavailable and never counts as a stable identity. `sc1` has no equivalent in 0.3.0, so its previous-version value is N/A. Installed Chrome was run headlessly with a test-owned profile; Chromium and WebKit are Playwright engine builds, not claims about every branded browser.

Cache warming and eviction are proven by a cacheable server sentinel in Chromium and Chrome, ten times each. Cookie, local/session storage, Cache Storage and IndexedDB clearing are checked. Firefox/WebKit in-place HTTP cache eviction is not claimed: fresh normal profiles provide independently empty caches, and site-data clearing is a separate arm. No request routing is used in the cache experiment because Playwright routing disables HTTP caching.

Incognito means new nonpersistent Playwright contexts; repeated contexts do not become additional devices. No iframe leaks, external collection requests or page errors were observed in successful runs. Physical display replacement, real browser/OS upgrades, long-term driver/font changes and multi-device population uniqueness were not tested.

**Failed attempts retained:** local Firefox could not launch within the 20-second budget. The first Chrome attempt failed during the test-storage phase with `QuotaExceededError`, after 300 partial paired observations, including 250 baseline observations. A focused rerun completed all five arms and logged storage availability. Those partial observations are retained as diagnostics, but are excluded from the completed 3,750-visit matrix. No quota or browser privacy protections were weakened.

## Matching replay on actual observations

The unmodified public SDK matchers replay the observations against complete retained candidate pools. This is a deterministic policy replay, not an HTTP/MongoDB benchmark. Browser order is Chromium, WebKit, Chrome. The same host label is used for every visit. The first two browsers have no available GPU model; their canvas hashes differ. A compatible incomplete rival makes the v3 policy abstain on WebKit in this shared pool.

| Measure | 0.3.0 / v2 | 0.4.0 / v3 |
| --- | ---: | ---: |
| Assigned visits | 100.00% | 66.67% |
| End-to-end same-host pair continuity | 33.32% | 22.21% |
| Continuity among pairs with two assigned IDs | 33.32% | 49.98% |
| Cross-browser same-host pair continuity | 0.00% | 0.00% |
| Cross-device uniqueness | Not measurable | Not measurable |

Assignment coverage is 3,750/3,750 versus 2,500/3,750. Same-host pair continuity is 2,341,875/7,029,375 versus 1,561,250/7,029,375. There are 4,687,500 cross-browser pairs and zero successful links in either version. These pairs are dependent repeat observations of one host; no population confidence interval is inferred. The sc1 code is available on 1,250/3,750 visits (33.33%), with 100% conditional repeatability on those available values. Replaying all six browser-block arrival orders keeps v2 assignment coverage at 100%, but v3 varies from 33.33% to 66.67%. V3 end-to-end same-host pair continuity varies from 11.11% to 22.21%; when WebKit arrives first, its incomplete compatible anchor blocks the other two browsers. This is order sensitivity across different observations, not a tie broken by candidate-list order.

**Interpretation:** stable observation hashes within a browser do not establish stable visitor assignment across browsers. The v3 coverage regression here must be considered before switching an existing workload from `mode: detailed` to the new default. The profile code must not be used as a universal hardware identifier.

## Separate Linux sandbox results

The final Linux CI run completed **3,750 paired visits / 7,500 collector calls** on its own runner. Its observations are not pooled with the Mac as one device. Together, the two reported matrices contain 7,500 completed paired visits and 15,000 collector calls. Earlier repetitions and failed partial runs are not additional independent devices.

| Engine | Build | Stable digest 0.3.0 / 0.4.0 | sc1 availability | Collector p95 0.3.0 / 0.4.0 |
| --- | --- | ---: | ---: | ---: |
| chromium | 145.0.7632.6 | 100.00% / 100.00% | 0.00% | 26.00 / 58.10 ms |
| firefox | 146.0.1 | 100.00% / 100.00% | 0.00% | 17.00 / 21.00 ms |
| webkit | 26.0 | 100.00% / 100.00% | 0.00% | 38.00 / 41.00 ms |

Each digest rate is 1,250/1,250 per engine and SDK. Available sc1 codes are 0/1,250 per engine, so conditional code stability is undefined. Both matcher replays assign all 3,750 visits, retain three anchors and yield 33.32% same-host pair continuity (2,341,875/7,029,375); these are separate engine identities rather than a shared cross-browser identity. The browser matrix itself passed; that does not imply 100% hardware recognition.

The aggregate data was read from the public [CI report annotations](https://github.com/ercoledevs/fingerprint-singularity/actions/runs/38533581723), generated from the completed [Linux evidence run](https://github.com/ercoledevs/fingerprint-singularity/actions/runs/38532232703). The detailed artifact and step summary remain available in GitHub. `linux-public-aggregate.json` preserves the received numeric evidence. Runtime scheduling and headless GPU availability differ from the Mac, so timing or coverage results must not be presented as a language-only effect.

## Synthetic stability and uniqueness

**82,944 policy-visits** across 216 cohort evaluations: three fixed seeds, three arrival orders, three finite-profile populations, eight scenarios, 64 labeled simulated devices and three visits per device, evaluated by both versions. Repeated evaluations do not create independent real devices. Labels never enter collected features. Both collectors receive the same designed font bits; this does not measure the entropy gain of the larger real font panel.

“Exclusive stable devices” requires the same non-null ID on all three visits and no other labeled simulated device sharing it. Link yield includes unassigned same-device pairs. False-link rate divides false links by different-device pairs with two assigned IDs; assignment coverage is reported alongside it.

| Population / scenario | Same-device stability v2 → v3 | Exclusive stable devices v2 → v3 | False-link rate v2 → v3 | Assignment coverage v2 → v3 |
| --- | ---: | ---: | ---: | ---: |
| diverse / repeat | 100.00% → 100.00% | 97.92% → 97.92% | 0.03% → 0.03% | 100.00% → 100.00% |
| diverse / wrapper-cross-engine | 0.00% → 95.83% | 0.00% → 93.75% | 0.01% → 0.03% | 100.00% → 97.22% |
| diverse / mixed-engines | 100.00% → 100.00% | 100.00% → 95.83% | 0.00% → 0.07% | 100.00% → 100.00% |
| office / repeat | 100.00% → 100.00% | 13.54% → 13.54% | 3.62% → 3.62% | 100.00% → 100.00% |
| office / wrapper-cross-engine | 0.00% → 0.00% | 0.00% → 0.00% | 1.21% → 3.62% | 100.00% → 33.33% |
| office / mixed-engines | 100.00% → 57.64% | 46.88% → 12.50% | 1.16% → 6.25% | 100.00% → 62.96% |
| clones / repeat | 100.00% → 100.00% | 0.00% → 0.00% | 100.00% → 100.00% | 100.00% → 100.00% |
| clones / wrapper-cross-engine | 0.00% → 100.00% | 0.00% → 0.00% | 33.33% → 100.00% | 100.00% → 100.00% |
| clones / mixed-engines | 100.00% → 100.00% | 0.00% → 0.00% | 32.29% → 100.00% | 100.00% → 100.00% |

The diverse wrapper/cross-engine fixture improves stability from 0% to 95.83% and exclusive stable devices from 0% to 93.75%. This is not a global accuracy percentage. Office-like mixed-engine profiles regress: stability falls from 100% to 57.64%, exclusive stable devices from 46.88% to 12.50%, and false-link rate rises from 1.16% to 6.25%. Complete cloned profiles remain inseparable. The full JSON includes GPU loss, sparse first observations, font changes and same-engine rendering updates.

## Performance and reproduction

| Browser | Collector p95 0.3.0 | Collector p95 0.4.0 |
| --- | ---: | ---: |
| chromium | 7.70 ms | 12.80 ms |
| webkit | 16.00 ms | 18.00 ms |
| chrome | 12.80 ms | 14.90 ms |

Digest/code hashing timings are recorded separately in the JSON. No end-to-end production latency or Rust speedup is inferred. See [Rust assessment](RUST_ASSESSMENT.md).

```sh
python3 scripts/prepare-intensive-sdks.py
BROWSERS=chromium,firefox,webkit node scripts/intensive-browser-check.mjs
node scripts/intensive-synthetic-check.mjs
PYTHON=python3 node scripts/benchmark-matching.mjs
```

For installed Chrome use `BROWSERS=chrome INTENSIVE_OUT=artifacts/intensive-chrome`. Merge completed runs from the same host with `node scripts/summarize-intensive.mjs artifacts/intensive-v04 artifacts/intensive-chrome`. Do not merge different hosts as one physical device. Raw results remain under ignored artifacts; the [Linux intensive workflow](https://github.com/ercoledevs/fingerprint-singularity/actions/runs/38532232703) publishes separate artifacts for its own host.

Evidence: `sdk-provenance.json`, `browsers.json`, `observations.jsonl`, `combined-macos.json`, `synthetic.json`, and `matching-performance.json`. Public SDK source and runtime contracts were not modified for this evaluation.
