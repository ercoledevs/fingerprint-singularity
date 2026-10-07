# Evaluate identification on your own observations

The standalone CLI includes an offline evaluator. It compares equality of returned visitor IDs against independently labeled physical devices. It measures output continuity, false links and missed links; it does not rerun the matcher or interpret a snapshot digest as a device ID.

```sh
singularity evaluate examples/evaluation.synthetic.jsonl
singularity --json evaluate observations.jsonl > report.json
```

No sign-in, server, MongoDB connection or outbound request is needed. The supplied example is synthetic regression data. Its percentages describe only that fixture.

## JSONL contract: `singularity-evaluation/v1`

One object per line, UTF-8, no blank lines or duplicate JSON keys. All fields below are required except `referenceId`.

```json
{"schema":"singularity-evaluation/v1","observationId":"visit-001","project":"demo","deviceLabel":"lab-device-01","observedAt":"2026-10-07T12:00:00Z","configuration":"envelope-v1-build-001-run-a","mode":"stateless","source":"empirical","browser":"chrome","scenario":"baseline","method":"provisional","visitorId":"vis_0123456789abcdef0123456789abcdef","referenceId":null}
```

| Field | Meaning |
|---|---|
| `observationId` | Unique observation within the project, including across configurations. |
| `project` | Dataset boundary. No pairs span projects. |
| `deviceLabel` | Independent, opaque physical-device label assigned by the experiment operator. Keep it stable across browsers, profiles, private sessions and visits. Label two identical machines separately. Never derive it from any predicted ID. |
| `observedAt` | ISO timestamp with timezone. Records must be chronological within each cohort. |
| `configuration` | Compatible policy, build and experiment run, including candidate population and collection settings. Change this value when those conditions are incompatible. |
| `mode` | `stateless` for `provisional`, `inferred` or `unassigned`; `possession` for `enrolled`, `remembered` or `unassigned`. |
| `source` | `empirical` for collected observations; `synthetic` for fabricated regression examples. They are never pooled. |
| `browser` | Standardized browser-family label, such as `chrome`, `firefox` or `safari`. Use the same spelling throughout. Record build details in your experiment log. |
| `scenario` | Standardized condition label, such as `baseline`, `private-session`, `browser-change`, `network-change` or `monitor-change`. |
| `method` | Provenance of this response. This is not an algorithm-version identifier. |
| `visitorId` | Returned `vis_` plus 32 lowercase hexadecimal characters, or `null` for `unassigned`. Assigned methods require an ID. |
| `referenceId` | Optional output from another system on this same observation. Missing or `null` means unavailable or abstained; a string means assigned. It is a comparator, never ground truth. |

Metadata and reference IDs use 1–128 ASCII characters: letters, numbers, `_`, `.`, `:`, `/`, `-`, starting with a letter or number. Files are limited to 50,000 observations, 8 KiB per line, 32 MiB and 128 cohorts. Invalid input fails explicitly; it is never silently truncated.

## Reading the report

A cohort has one project, configuration, mode and source. Every unordered pair inside it is eligible. No pairs cross these boundaries. The report also includes pairs whose browser labels differ, computed using the same rules. Scenario counts describe sample composition; they are not causal estimates of individual scenario effects.

Equal non-null predictions create a link. Different non-null predictions separate the pair. A pair containing a null prediction is uncovered, not a successful separation. Each rate includes its numerator and denominator; an empty denominator produces `null` rather than a perfect score.

| Measure | Definition |
|---|---|
| Pair coverage | Pairs with two assigned IDs / all eligible pairs. |
| False-link rate | Linked different-device pairs / covered different-device pairs. |
| Missed-link rate | Separated same-device pairs / covered same-device pairs. |
| Link precision | Same-device linked pairs / all linked pairs. |
| End-to-end link yield | Same-device linked pairs / all eligible same-device pairs, including uncovered pairs. |
| Device-balanced link yield | Mean of per-device end-to-end link yields, excluding devices with only one visit. The numerator is a sum of device yields, not a count of pairs. |

The JSON report retains per-device visit counts and yields, browser/scenario counts, full-coverage metrics for each system and metrics restricted to observations where both systems returned an ID. Shared coverage is explicit. Selective availability of a comparator must not be hidden by reporting only the shared subset.

Pair counts use exact Python integers and grouped contingency tables, without enumerating all pairs. Frequent visitors contribute more pairs; pairs are dependent. Results are descriptive, not confidence intervals or a population accuracy estimate. Use the per-device summary alongside pair-weighted totals.

## Collection protocol

1. Assign independent device labels before collecting results. Include distinct devices with identical hardware and software and devices sharing a NAT, office network or VPN.
2. Collect baseline visits, then vary one condition at a time: browser family, browser update, private session, cleared storage, network/VPN, monitor, zoom, timezone and language. Record the actual condition instead of assuming that a viewport resize is a physical monitor replacement.
3. Repeat after days and weeks. Keep observations chronological. Record candidate population and retention settings; changing these can change assignments.
4. Keep stateless and possession experiments separate. Enroll before subsequent possession visits, using only information available at that time. Do not retroactively assign tokens or relabel past predictions.
5. Balance visit counts across devices. Reserve devices and later time periods for evaluation when tuning a future policy; do not tune and report results on the same sample.
6. If using a reference system, record its output on the same visit and preserve unavailable results. The evaluator does not call or require a third-party service.

An increase in successful links is useful only alongside false-link counts and coverage. Version each collector or policy change and repeat the same collection matrix before adopting it.
