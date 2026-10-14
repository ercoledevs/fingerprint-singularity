# Fingerprint integration research

Research performed on 14 October 2026 using public documentation, static artifact analysis with [REA](https://github.com/morluto/rea), and read-only navigation of an authorized Fingerprint dashboard. This documents observable behavior and independently implemented integration features; it does not reproduce a proprietary server identification model.

## Evidence and limits

The analyzed npm artifact was `@fingerprint/agent` **4.1.6**, downloaded from the official npm registry and checked against its published SHA-512 integrity value. REA 6.4.0 parsed the extracted shipped files without executing the SDK. The evidence graph contained 34 nodes and 35 edges, with 23 findings and no parse failures.

- REA evidence ID: `ev_8aacc9743afa511ee6b209a9befe8f9311ca179b864a27ba65250321011c5818`
- REA artifact SHA-256: `a0f99a63bde9784a62062e99c59e12760026bc1d830f5533d576d3376b9e5962`
- Observed ESM exports: `default`, `handleAgentData`, `isFingerprintError`, `start`, `withoutDefault`.

The public package exposes a loader, interfaces and dynamic-loading boundaries. Remote components and the server model were not present in the inspected artifact. Its proprietary source was not copied into Singularity. [The separate open-source FingerprintJS collector](https://github.com/fingerprintjs/fingerprintjs/tree/v5.3.0/src) is not the commercial service's complete identification implementation.

The inspected dashboard exposed event and visitor identifiers, SDK and origin columns, plus filters for linked IDs, environment, IP/ASN and Smart Signals. The authorized workspace contained **zero identification events**, so it provided no recognition outputs or accuracy sample. No account settings were changed, keys created or paid SDK calls submitted. Private workspace references and account values are excluded from this document.

## Adopted integration patterns

| Publicly documented pattern | Singularity implementation |
| --- | --- |
| [Server event retrieval](https://docs.fingerprint.com/reference/server-api-get-event) | Project-scoped backend key and retained event lookup |
| [Freshness, origin and replay checks](https://docs.fingerprint.com/docs/protecting-from-client-side-tampering) | Explicit verification endpoint, maximum age and optional atomic consumption |
| [Useful visit timestamps](https://docs.fingerprint.com/docs/useful-timestamps) | First and previous retained visits, frozen in the event response |
| [Application metadata](https://docs.fingerprint.com/reference/js-agent-get-function) | Bounded `linkedId` and flat string tags, excluded from identity evidence |
| Dashboard filtering | Exact linked-ID/origin filters in the Vue console and CLI |

Singularity uses its own API contract, including camelCase fields; it is not a drop-in implementation of Fingerprint's API. The current commercial SDK and API use version-specific contracts, including `event_id` and `visitor_id` in v4. Older `requestId` examples should not be assumed interchangeable. See the official [start](https://docs.fingerprint.com/reference/js-agent-start-function) and [error handling](https://docs.fingerprint.com/reference/js-agent-error-handling) references when integrating that product.

Server verification strengthens event provenance and replay handling. It cannot establish that client-supplied observations or an HTTP Origin header truthfully describe a physical device. These features do not increase fingerprint entropy by themselves. Commercial accuracy claims cannot be transferred to this project; a comparison requires labeled real devices, repeated observations and actual outputs from both systems under the same protocol.

For the independently developed signal changes, see [resilient observations](RESILIENT.md). For installation and reproduction of the analysis tooling, see [REA tooling](../tools/rea/README.md).
