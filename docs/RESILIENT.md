# Resilient observations

Version 0.4 adds `singularity/v3` observations, the `web/v2` probe panel and `support/v3` matching. The network agent and console use this mode by default. Original v1 and detailed v2 exports, observation hashes and matching rules remain available unchanged.

```ts
import {
  collectResilient, continuityCode, digestResilient, matchResilient,
} from 'fingerprint-singularity'

const snapshot = await collectResilient({ scope: 'my-app.example' })
const code = await continuityCode(snapshot) // sc1_… or null
const digest = await digestResilient(snapshot) // sg3_…
const decision = matchResilient(snapshot, []) // Supply retained candidates.
```

## Three identifiers, three roles

| Identifier | Meaning | Lifetime |
| --- | --- | --- |
| `sg3_…` observation digest | Every field of a validated observation | Changes whenever an included observation changes |
| `sc1_…` continuity code | Fixed, scope-specific model/font profile | Regenerated without storage when all required values remain equal |
| `vis_…` visitor ID | Backend assignment from retained candidates or an explicit possession token | Governed by retention, deletion and matching evidence |

The continuity code is SHA-256 of this fixed JSON tuple:

```text
["continuity/v1", scope, "web/v2", platform, cores, gpuHash, fontsHash]
```

Platform, core bucket, GPU model and font profile must all be available. Otherwise the result is `null`; the collector does not substitute a weaker combination. Canvas, engine, memory, language and timezone are excluded from this code. Changing a display, clearing storage or starting a private context does not directly change these inputs. Browsers can still expose different or reduced values. Installing fonts, changing hardware or privacy settings can change the code or make it unavailable.

The same profile can exist on multiple machines. A repeatable code is therefore a profile key, not a physical-device serial number, authentication credential or calibrated probability of identity. The backend never uses this code to resurrect a deleted visitor or to skip ambiguity checks.

## Collection and normalization

- **GPU:** a conservative allowlist recognizes specific Apple, NVIDIA, AMD and Intel models. Known ANGLE, Direct3D and Metal wrappers are removed; meaningful model suffixes remain. Generic, masked, software and unrecognized renderers become `null`.
- **Fonts:** a fixed panel of 64 names is measured inside a temporary blank document isolated from host styles and downloaded fonts. All font bits form one evidence family, not 64 independent votes.
- **Canvas:** the fixed pixel probe remains useful within comparable rendering contexts. It does not use screen dimensions.
- **Engine:** a bounded user-agent read produces `blink`, `gecko`, `webkit` or `null`. Versions and the raw string are not retained. This is client-declared context, not attestation.

Each detail probe is read twice; disagreement or an exception produces `null`. The frame is removed before hashing. Detail hashes include the scope and probe revision. Collection performs no network requests, reads no storage, asks for no permissions and does not communicate with other browsers. No hidden identifier is persisted or recovered from an incognito session.

## Matching and retrieval

`compareResilient(a, b)` requires equal, known platform and core buckets. Fonts must agree, together with either GPU or canvas. Comparable GPU/font differences veto a match. Canvas differences also veto a match unless both engine families are known and different. Tolerated canvas differences remain visible in `differences`; they do not count as support.

`matchResilient(snapshot, candidates)` returns a match only when one candidate qualifies and no incomplete compatible rival remains. Multiple qualifying candidates abstain. Missing values never count as agreement. Full validation precedes selection; limits remain 256 candidates and 4,096 UTF-16 code units per parsed snapshot. Similarity and coverage are descriptive ratios, not identity probabilities.

Mongo retrieval excludes only contradictions the v3 kernel would reject. Unknown values and cross-engine canvas alternatives stay in the pool. A 257th compatible candidate causes overflow. Two partial v3 indexes cover font and GPU/font lookups; existing v2 indexes remain. Index construction occurs at API startup and may take time on a populated database. Back up first and allow sufficient disk space.

This policy trades some rendering discrimination for cross-engine continuity when model and fonts agree. Identical model/font profiles with different canvas results can share a continuity code; known same-engine canvas differences can still separate their backend visitors. Unknown or spoofed engine context is not a hardware guarantee.

## Upgrade order

1. Back up MongoDB and the independent recovery state volume. Upgrade the backend first.
2. Upgrade the SDK and console. New default observations enter a separate v3 candidate pool, so inferred visitor IDs can change during migration.
3. To keep an existing collection path, pass `mode: 'detailed'` for v2 or `mode: 'legacy'` for v1 to `createAgent`.

Existing records are not rewritten. Valid explicit enrollment tokens can preserve their assigned visitor across modes; automatic inference does not merge schema pools. API responses add `continuityCode` and event context fields. Older stored idempotent responses can omit these additions, so consumers must handle them as optional. Metadata does not enter the observation digest or matching policy.

See [verification](VERIFICATION.md) for paired synthetic results and actual browser limitations, and [platform integration](PLATFORM.md) for server-side event verification.
