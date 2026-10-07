# Detailed observations and upgrading to 0.3

`collectDetailed({scope})` produces a `singularity/v2` snapshot with the five legacy normalized signals, immutable probe revision `web/v1`, and three nullable hashes under `detail`: `gpu`, `fonts`, and `canvas`.

## Probe contract

- GPU: an unmasked WebGL renderer string, whitespace/case normalized. Generic, masked and known software renderer names are not used. Model and driver distinctions are retained. The context is explicitly released.
- Fonts: presence-like text-width differences for a fixed list of 16 fonts against three fixed fallback families. This is a bounded heuristic, not full installed-font enumeration. `FontFaceSet.check()` is not used because it also succeeds for nonexistent fonts.
- Canvas: one fixed 240×80 drawing with colors, curves and compositing, compared as RGBA pixels. Text is excluded because glyph rendering can depend on display density. PNG encoder metadata is excluded. Screen size, zoom and device pixel ratio are not read.

Each probe is executed twice. A throw, null result, oversized result or disagreement yields `null`. Two agreeing samples do not establish stability across sessions or defeat session-seeded browser randomization. No attempt is made to bypass restricted APIs. Every accepted value is SHA-256 hashed with `[probe revision, scope, field, raw value]`; the raw value is not retained in the snapshot. Hashing is not anonymization.

Built-in probes run in a temporary, hidden `about:blank` frame without scripts or a remote source. Its fresh document excludes the host page's styles and web-font definitions, preventing page fonts from changing the observation or triggering downloads. The frame is removed before asynchronous hashing. If this isolation is blocked, details remain null.

The canvas and typography probes may be correlated. They are supporting observations, not independent proofs of a physical device. The same complete observation can occur on different devices.

## Matching

`support/v2` requires:

1. Known, equal platform and core bucket.
2. At least two comparable, equal detailed hashes.
3. No disagreement in any comparable detail.
4. Exactly one qualifying candidate and no unresolved compatible candidate with incomplete evidence.

Locale and memory changes do not themselves contradict a detailed candidate. Known platform/core/detail conflicts remain excluded throughout the comparison; v2 does not run the legacy family-omission trials. A changed canvas, font observation or GPU renderer can split a returning visitor. Missing data can lead to abstention. An absent candidate can be created only when the observation itself meets the evidence floor.

Enrollment history matters. An anchor created with no GPU observation cannot later distinguish devices that share its font and canvas hashes but have different GPUs. The anchor stays immutable; extra fields from inferred visits do not silently strengthen it. The regression suite includes this case.

`similarity` is the fraction of the three detailed fields that agree. `coverage` is the comparable fraction. These are descriptions of the inputs, not accuracy or confidence probabilities. Equal high scores do not resolve two qualifying candidates.

## API

```ts
import {
  collectDetailed, canonicalizeDetailed, digestDetailed,
  compareDetailed, matchDetailed,
  validateDetailedSnapshot, parseDetailedSnapshot,
} from 'fingerprint-singularity'
```

`collectDetailed` is asynchronous. `environment` and synchronous `probes` adapters support reproducible tests; supplying only an environment never falls back to ambient browser probes. Probe execution is bounded for the built-in implementation; a hostile caller-supplied function cannot be interrupted in the same JavaScript process.

Canonical tuples contain schema, scope, probe revision, the five coarse signals, then GPU/fonts/canvas hashes. Digests use `sg2_`. The JSON parser rejects values over 4,096 UTF-16 code units. Candidate lists are capped at 256 and validated completely; different schemas/scopes and malformed entries are rejected, never silently discarded.

## Upgrade order

1. Upgrade the Python backend. It accepts v1 and v2 on the existing `/api/v1/identify/{publicKey}` transport endpoint.
2. Upgrade the JavaScript agent/console. `createAgent` defaults to `mode: 'detailed'`; select `mode: 'legacy'` explicitly for an older backend or existing v1 integration.
3. Retain historical v1 records unchanged. Stateless candidate pools are partitioned by schema. V2 also partitions by its permanent platform compatibility condition. Its 256 limit applies to the complete compatible platform pool; global enrollment quota remains 512.

The first detailed request may create a new visitor even if a legacy candidate exists. Valid possession tokens continue across schemas until expiry/revocation. Existing v1 exports and canonical digests are unchanged.

The console displays the schema and availability of detailed evidence. CLI exact-digest search and prefix filters accept both `sg1_` and `sg2_`.

## Concurrency

The single-worker backend retains one global atomic write section. Up to 32 admitted requests may wait; lock acquisition has a two-second budget. Timeout returns `429` with `Retry-After`. A waiter that encounters recovery quarantine returns `503` before mutation. Minute/day quotas, idempotency and deletion/revocation semantics are unchanged. The ten-second body deadline is separate from the lock budget, not an end-to-end completion guarantee.

## Browser references

- [MDN: WebGL renderer extension](https://developer.mozilla.org/en-US/docs/Web/API/WEBGL_debug_renderer_info): availability depends on browser privacy settings.
- [MDN: FontFaceSet.check](https://developer.mozilla.org/en-US/docs/Web/API/FontFaceSet/check): not an installed-font presence test.
- [WebKit: Private Browsing 2.0](https://webkit.org/blog/15697/private-browsing-2-0/): private-mode rendering protections can change observations.
