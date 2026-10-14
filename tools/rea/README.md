# Optional REA research tools

This private tooling package pins [Reverse Engineer Anything](https://github.com/morluto/rea) (`rea-agents` 6.4.0). It is excluded from the published Singularity SDK and Docker images. It does not add a runtime dependency or change global MCP configuration.

Requires Node.js `^22.19.0`, `^24.11.0` or `>=26.0.0`.

```sh
npm ci --prefix tools/rea --ignore-scripts
npm --prefix tools/rea run rea -- --help
```

Analyze a locally downloaded, shipped JavaScript application or SDK artifact:

```sh
tools/rea/node_modules/.bin/rea analyze-javascript-application \
  /absolute/path/to/extracted-sdk \
  --max-heap-mb 256 --analysis-timeout-ms 45000 --format json \
  > /tmp/sdk-evidence.json
```

Use the artifact's publisher, exact version and verified integrity value as provenance. This command parses artifact text; it does not execute the analyzed SDK or recover a remote server's implementation. Treat unresolved dynamic imports as unknowns. Do not commit credentials, private dashboard exports or third-party proprietary source.

The bounded analysis used for this release is documented in [Fingerprint research](../../docs/FINGERPRINT_RESEARCH.md). Its raw local outputs live under ignored `artifacts/rea-research/`.
