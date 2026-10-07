# Research background

Fingerprint Singularity separates the package version, observation schema, and matching policy. The collector produces a bounded snapshot; the matcher evaluates candidates without changing them. See [Architecture](ARCHITECTURE.md) for module boundaries and [Identity research](IDENTITY_RESEARCH.md) for additional signals, browser communication, and optional shared-identity designs.

## Browser observations

Browser-provided values describe the environment visible to the page. [hardwareConcurrency](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency) may be reduced by the browser, and [deviceMemory](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory) is approximate and not universally available. The [W3C fingerprinting guidance](https://www.w3.org/TR/fingerprinting-guidance/) explains how browser mitigations affect observability and persistence.

The current collector uses coarse platform, CPU count, approximate memory, language, and time zone. It excludes display metrics and browser versions. Missing values remain explicit rather than being inferred from previous matches.

## Matching policy

The family-omission policy repeats candidate evaluation after excluding each signal family. The same candidate must remain distinguishable using the remaining evidence. Every reduced trial reconsiders all candidates, including those excluded by the full comparison.

The API exposes contributions, coverage, contradictions, and omission results so an application can inspect each decision. Ambiguous or insufficient evidence produces abstention. Candidate storage, retention, and retrieval belong to the integrating application.

The current thresholds are versioned heuristics. Evaluating another policy requires independently labelled observations, measurements across browser pairs and time, and explicit false-match and abstention targets. The [verification report](VERIFICATION.md) describes implementation checks; the [identity study](IDENTITY_RESEARCH.md) describes the proposed population evaluation.

## Development navigation

[Graphify](https://github.com/Graphify-Labs/graphify) can build a local index of the source modules for contributor navigation. With Graphify installed:

```sh
graphify extract src --code-only --out .
graphify cluster-only . --no-label
graphify query 'runnerUp' --context call --budget 800
```

Generated files in `graphify-out/`, `GRAPH_REPORT.md`, and `graph.html` are excluded from Git and the package. The commands above use local code extraction. Treat the graph as a navigation aid; source code and tests define the API behavior.
