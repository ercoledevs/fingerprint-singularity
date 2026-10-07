"""Offline output-ID continuity evaluation; no network or runtime policy changes."""
from collections import Counter, defaultdict
from datetime import datetime
import json
import os
import re
import stat

SCHEMA = "singularity-evaluation/v1"
REQUIRED = {"schema", "observationId", "project", "deviceLabel", "observedAt", "configuration",
            "mode", "source", "browser", "scenario", "method", "visitorId"}
LABEL = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.:/-]{0,127}", re.ASCII)
VISITOR = re.compile(r"vis_[a-f0-9]{32}", re.ASCII)
METHODS = {"stateless": {"provisional", "inferred", "unassigned"},
           "possession": {"enrolled", "remembered", "unassigned"}}
MAX_BYTES = 32 * 1024 * 1024
MAX_RECORDS = 50_000


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def load(path):
    rows, seen, chronology = [], set(), {}
    with os.fdopen(os.open(path, os.O_RDONLY | os.O_NONBLOCK), "rb") as stream:
        info = os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_size > MAX_BYTES:
            raise ValueError("Evaluation requires a regular JSONL file of at most 32 MiB")
        total = 0
        for number in range(1, MAX_RECORDS + 2):
            line = stream.readline(8193)
            if not line:
                break
            total += len(line)
            if len(line) > 8192 or total > MAX_BYTES or number > MAX_RECORDS:
                raise ValueError("Evaluation limit: 50,000 records, 8 KiB per line, 32 MiB total")
            try:
                row = json.loads(line.decode("utf-8"), object_pairs_hook=unique_object)
                validate(row)
                identity = (row["project"], row["observationId"])
                if identity in seen:
                    raise ValueError("Duplicate observation")
                seen.add(identity)
                key = cohort(row)
                timestamp = datetime.fromisoformat(row["observedAt"])
                if key in chronology and timestamp < chronology[key]:
                    raise ValueError("Observations must be chronological within each cohort")
                chronology[key] = timestamp
                if len(chronology) > 128:
                    raise ValueError("At most 128 compatible cohorts per file")
                rows.append(row)
            except (ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
                # Never echo source records, identifiers or parser snippets into diagnostics.
                raise ValueError(f"Invalid evaluation record at line {number}; check the versioned contract") from exc
    if not rows:
        raise ValueError("Evaluation file has no observations")
    return rows


def validate(row):
    if not isinstance(row, dict) or not REQUIRED <= row.keys() or row.keys() - REQUIRED - {"referenceId"}:
        raise ValueError("Invalid fields")
    if row["schema"] != SCHEMA:
        raise ValueError("Unsupported schema")
    for name in REQUIRED - {"schema", "visitorId", "observedAt"}:
        if not isinstance(row[name], str) or not LABEL.fullmatch(row[name]):
            raise ValueError("Invalid metadata")
    if row["mode"] not in METHODS or row["method"] not in METHODS[row["mode"]] or row["source"] not in {"synthetic", "empirical"}:
        raise ValueError("Incompatible provenance")
    value = row["visitorId"]
    if value is not None and (not isinstance(value, str) or not VISITOR.fullmatch(value)):
        raise ValueError("Invalid visitor ID")
    if (value is None) != (row["method"] == "unassigned"):
        raise ValueError("Unassigned requires null; assigned methods require a visitor ID")
    reference = row.get("referenceId")
    if reference is not None and (not isinstance(reference, str) or not LABEL.fullmatch(reference)):
        raise ValueError("Invalid reference ID")
    if not isinstance(row["observedAt"], str) or len(row["observedAt"]) > 40:
        raise ValueError("Invalid timestamp")
    if datetime.fromisoformat(row["observedAt"]).utcoffset() is None:
        raise ValueError("Timestamp requires timezone")


def cohort(row):
    return tuple(row[k] for k in ("project", "configuration", "mode", "source"))


def choose(n):
    return n * (n - 1) // 2


def pairs(counter):
    return sum(choose(n) for n in counter.values())


def counts(rows, field):
    """Contingency counts are linear in observations, with exact Python integers."""
    devices, covered_devices, predictions, cells = Counter(), Counter(), Counter(), Counter()
    covered = 0
    for row in rows:
        device, prediction = row["deviceLabel"], row.get(field)
        devices[device] += 1
        if prediction is not None:
            covered += 1
            covered_devices[device] += 1
            predictions[prediction] += 1
            cells[device, prediction] += 1
    return dict(pairs=choose(len(rows)), sameDevicePairs=pairs(devices), coveredPairs=choose(covered),
                coveredSameDevicePairs=pairs(covered_devices), linkedPairs=pairs(predictions), trueLinks=pairs(cells))


def rate(numerator, denominator):
    return dict(numerator=numerator, denominator=denominator, value=numerator / denominator if denominator else None)


def metrics(c):
    different = c["pairs"] - c["sameDevicePairs"]
    covered_different = c["coveredPairs"] - c["coveredSameDevicePairs"]
    false = c["linkedPairs"] - c["trueLinks"]
    missed = c["coveredSameDevicePairs"] - c["trueLinks"]
    return {**c, "differentDevicePairs": different, "coveredDifferentDevicePairs": covered_different,
            "falseLinks": false, "missedLinks": missed,
            "abstainedSameDevicePairs": c["sameDevicePairs"] - c["coveredSameDevicePairs"],
            "abstainedDifferentDevicePairs": different - covered_different,
            "rates": {"pairCoverage": rate(c["coveredPairs"], c["pairs"]),
                      "falseLinkRate": rate(false, covered_different),
                      "missedLinkRate": rate(missed, c["coveredSameDevicePairs"]),
                      "linkPrecision": rate(c["trueLinks"], c["linkedPairs"]),
                      "endToEndLinkYield": rate(c["trueLinks"], c["sameDevicePairs"])}}


def system_metrics(rows, field):
    all_counts = counts(rows, field)
    cross_browser = dict(all_counts)
    by_browser = defaultdict(list)
    for row in rows:
        by_browser[row["browser"]].append(row)
    for subset in by_browser.values():
        for name, value in counts(subset, field).items():
            cross_browser[name] -= value
    return {"allPairs": metrics(all_counts), "crossBrowserPairs": metrics(cross_browser)}


def evaluate(rows):
    groups = defaultdict(list)
    for row in rows:
        groups[cohort(row)].append(row)
    output = []
    for key, subset in sorted(groups.items()):
        by_device = defaultdict(list)
        for row in subset:
            by_device[row["deviceLabel"]].append(row)
        devices = []
        for label, visits in sorted(by_device.items()):
            c = counts(visits, "visitorId")
            devices.append(dict(deviceLabel=label, observations=len(visits),
                                assignedObservations=sum(r["visitorId"] is not None for r in visits),
                                endToEndLinkYield=rate(c["trueLinks"], c["sameDevicePairs"])))
        eligible_devices = [d["endToEndLinkYield"]["value"] for d in devices if d["observations"] > 1]
        result = dict(zip(("project", "configuration", "mode", "source"), key))
        result.update(observations=len(subset), devices=len(devices),
                      browserObservations=dict(sorted(Counter(r["browser"] for r in subset).items())),
                      scenarioObservations=dict(sorted(Counter(r["scenario"] for r in subset).items())),
                      singularity=system_metrics(subset, "visitorId"), perDevice=devices,
                      deviceBalancedLinkYield=rate(sum(eligible_devices), len(eligible_devices)))
        if any("referenceId" in row for row in subset):
            shared = [r for r in subset if r["visitorId"] is not None and r.get("referenceId") is not None]
            result["reference"] = system_metrics(subset, "referenceId")
            result["sharedCoverage"] = {"observations": rate(len(shared), len(subset)),
                                        "pairs": rate(choose(len(shared)), choose(len(subset)))}
            result["sharedAssignedSubset"] = {"observations": len(shared),
                                               "singularity": system_metrics(shared, "visitorId"),
                                               "reference": system_metrics(shared, "referenceId")}
        output.append(result)
    return {"schema": "singularity-evaluation-report/v1", "unit": "output-id-equality",
            "interpretation": "Descriptive cohort results. Pairs are dependent; synthetic data is regression evidence only.",
            "cohorts": output}


def run(path):
    return evaluate(load(path))
