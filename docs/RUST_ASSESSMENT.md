# Rust assessment after the 0.4.0 intensive evaluation

Assessment on 14 October 2026. **A complete Rust rewrite is not justified by the measured results.** Selective native work may be useful after profiling a production workload. No Rust implementation was benchmarked, so no speedup percentage is established.

## Measured costs

The reproducible CPU benchmark uses 100 warmups and 1,000 samples per candidate count, with valid identical v3 contenders. It measures validation and matching, including ambiguity handling; it excludes HTTP, MongoDB and concurrent lock contention.

| Candidates | Node 24.21.0 median / p95 | Python 3.12.14 median / p95 |
| ---: | ---: | ---: |
| 1 | 0.0075 / 0.0104 ms | 0.0100 / 0.0103 ms |
| 16 | 0.0615 / 0.0883 ms | 0.0838 / 0.0933 ms |
| 64 | 0.2286 / 0.2644 ms | 0.3183 / 0.3437 ms |
| 256 | 0.9174 / 1.0474 ms | 1.2603 / 1.3275 ms |

The new actual-browser collector p95 was 12.8 ms in Chromium, 18.0 ms in WebKit and 14.9 ms in installed Chrome. These are local, paired observations; runtime scheduling and browser timer resolution affect timings. They are not end-to-end API latency or production throughput.

## Component decisions

| Component | Decision | Reason |
| --- | --- | --- |
| TypeScript collector | Keep TypeScript | GPU, fonts, canvas, DOM and Web Crypto determine available evidence. Rust/Wasm would call these same browser APIs. |
| Matching/canonicalization | Consider a shared Rust kernel only after profiling | Matching at the maximum candidate count is already about 1 ms. A single kernel could reduce duplicated implementation, but requires interop and migration validation. |
| Python API | Keep the current implementation pending workload profiling | The supported single-worker design serializes candidate reads, assignment and writes with a global lock. A different language does not remove that correctness constraint. |
| MongoDB | Retain; profile query plans and history lookups | Database work, index selectivity, pool behavior and durability remain relevant with a Rust client. |
| Vue console | Keep Vue | Rendering and HTTP integration dominate the dashboard; a rewrite has no measured benefit. |
| Rich CLI | Optional separate Rust distribution experiment | A standalone binary can simplify installation. Startup, size and rendering would need their own benchmark. |

Rust's compile-time memory and concurrency checks can help native implementation reliability. They do not guarantee correct identity decisions, database consistency or stable browser observations. In particular, Rust cannot reveal a GPU model masked by the browser or distinguish devices whose observed profiles coincide. [Rust language characteristics](https://rust-lang.org/).

Rust/Wasm accesses the browser through bindings such as [`web-sys`](https://wasm-bindgen.github.io/wasm-bindgen/web-sys/index.html); the [DOM example](https://wasm-bindgen.github.io/wasm-bindgen/examples/dom.html) illustrates this boundary. A candidate native Python module can use [PyO3](https://pyo3.rs/v0.28.2/). The [MongoDB Rust driver performance guidance](https://www.mongodb.com/docs/drivers/rust/current/connect/performance/) still concerns client reuse, connection pools and runtime behavior.

## Gate for a selective prototype

First measure time waiting for the API lock, candidate retrieval, kernel matching, history queries and insertion under a representative concurrency level. Record CPU, memory, p95/p99 latency, rejected requests and throughput. Optimize the dominant component rather than assuming the language is the cause.

If matching becomes a significant CPU cost, compare the existing implementation with a Rust kernel on the same inputs. Include serialization/FFI or Wasm transfer, cold startup, download size and memory, not just the inner loop. Preserve every schema, nullable value, scope, contradiction, ambiguity and overflow rule. Canonical JSON representation and field order must remain exact or existing hashes change. Keep retention, deletion, idempotency and recovery semantics covered by the existing tests.

The intensive evaluation found useful normalization gains and regressions in crowded/shared profiles. Improve those matching decisions and coverage before spending effort on a full language migration. See [the intensive results](INTENSIVE_0_4.md).

```sh
python3 scripts/prepare-intensive-sdks.py
PYTHON=python3 node scripts/benchmark-matching.mjs
```

Evidence: `artifacts/intensive-v04/matching-performance.json`. The `rust` field is deliberately `null` because no equivalent Rust comparator was run.
