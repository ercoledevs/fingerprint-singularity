# Provenance and decision

The follow-up [identity and cross-browser research](IDENTITY_RESEARCH.md) studies additional signals and explicit identity-sharing options. Its proposals are separate from the v0.1.0 decision recorded below.

Analysis dated October 7, 2026. Reference source: [FingerprintJS](https://github.com/fingerprintjs/fingerprintjs), commit `dac5ae59409669f09aa09c0b2f44b7615b0520da`, package 5.3.0. This repository's implementation is original, with no upstream code copied.

The [agent.ts](https://github.com/fingerprintjs/fingerprintjs/blob/dac5ae59409669f09aa09c0b2f44b7615b0520da/src/agent.ts) code path serializes component values with sorted keys, then computes the hash. Sources include screen data, but there are exceptions: recent Safari versions omit resolution, and recent Safari/Firefox versions omit the frame. It is incorrect to claim that every screen change always changes FingerprintJS.

The [upstream policy](https://github.com/fingerprintjs/fingerprintjs/blob/dac5ae59409669f09aa09c0b2f44b7615b0520da/docs/version_policy.md) aims to maintain compatibility within a minor version, while allowing changes for fixes. Singularity explicitly separates the package version, observation schema, and matching policy.

Web APIs do not provide the identification guarantee originally requested. [hardwareConcurrency](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/hardwareConcurrency) can be reduced by the browser; [deviceMemory](https://developer.mozilla.org/en-US/docs/Web/API/Navigator/deviceMemory) is approximate and not universally available. The [W3C guidance](https://www.w3.org/TR/fingerprinting-guidance/) describes mitigations and persistence limitations. The user explicitly chose automatic probabilistic detection without login or pairing, giving up the absolute guarantee.

Codex Mind: five compact Forge contributions, six Council opinions, and five anonymous reviews. Outcome: `build`, medium confidence, no architectural blocker; this is not proof of accuracy. Hyper chose Relay: a single author, arithmetic verification of edge cases, tests, and separate final falsification. Agent perspectives are correlated and do not constitute provider/model diversity.

The retained idea is repeated comparison after omitting each family. The reduced data must again be sufficient to distinguish the same candidate. Identity services, automatic storage, automatic history growth, and any promise of uniqueness are excluded. Less data may produce more collisions and more abstentions; we do not have a cohort demonstrating superiority over FingerprintJS.

[Graphify](https://github.com/Graphify-Labs/graphify) 0.9.76 locally indexed 101 upstream files: 402 nodes, 976 edges, no LLM API. Upstream diagnostics: 107 missing endpoints in the raw corpus, 83 merged relationships, and 2 self-loops. Conclusions were checked again against source code; the graph is an incomplete index. No percentage of token savings was measured or claimed.

## Development index

The new library was indexed separately: 6 source files, 54 nodes, 7 communities. Central nodes include `validateSnapshot`, `match`, and `SingularityError`. The query connecting `runnerUp`, `best`, and `match` leads directly to ambiguity checks. The `index.ts` export produces no symbols of its own in the extractor; final graph diagnostics report one self-loop and do not reconstruct any relationships lost before the build. Relationships in an undirected graph do not demonstrate call direction.

With Graphify already installed, regenerate from the working tree:

```sh
graphify extract src --code-only --out .
graphify cluster-only . --no-label
graphify query 'runnerUp' --context call --budget 800
```

Local outputs `graphify-out/graph.json`, `GRAPH_REPORT.md`, and `graph.html` are excluded from the package and Git. Code extraction uses local ASTs; documents and LLM APIs do not participate in these commands. The graph helps navigation; source code and tests remain the authoritative evidence.
