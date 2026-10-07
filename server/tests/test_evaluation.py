from collections import Counter
from itertools import combinations
import json
import random

import pytest
from singularity import evaluation as ev
from singularity.cli import main


def observation(i=0, **updates):
    return {**dict(schema=ev.SCHEMA, observationId=f"obs-{i}", project="demo", deviceLabel="device-a",
                   observedAt="2026-10-07T12:00:00Z", configuration="envelope-v1-run1", mode="stateless",
                   source="synthetic", browser="chrome", scenario="baseline", method="inferred",
                   visitorId="vis_" + "a" * 32), **updates}


def brute(rows, field, cross=False):
    result = Counter(dict(pairs=0, sameDevicePairs=0, coveredPairs=0, coveredSameDevicePairs=0,
                          linkedPairs=0, trueLinks=0))
    for a, b in combinations(rows, 2):
        if cross and a["browser"] == b["browser"]:
            continue
        same = a["deviceLabel"] == b["deviceLabel"]
        covered = a.get(field) is not None and b.get(field) is not None
        linked = covered and a[field] == b[field]
        result.update(pairs=1, sameDevicePairs=int(same), coveredPairs=int(covered),
                      coveredSameDevicePairs=int(covered and same), linkedPairs=int(linked), trueLinks=int(linked and same))
    return dict(result)


def assert_metrics(actual, expected):
    for key, value in expected.items():
        assert actual[key] == value
    assert actual["falseLinks"] == expected["linkedPairs"] - expected["trueLinks"]
    assert actual["missedLinks"] == expected["coveredSameDevicePairs"] - expected["trueLinks"]
    denominators = dict(pairCoverage=(expected["coveredPairs"], expected["pairs"]),
                        falseLinkRate=(actual["falseLinks"], actual["coveredDifferentDevicePairs"]),
                        missedLinkRate=(actual["missedLinks"], expected["coveredSameDevicePairs"]),
                        linkPrecision=(expected["trueLinks"], expected["linkedPairs"]),
                        endToEndLinkYield=(expected["trueLinks"], expected["sameDevicePairs"]))
    for name, (n, d) in denominators.items():
        assert actual["rates"][name] == dict(numerator=n, denominator=d, value=n / d if d else None)


def test_contingency_metrics_against_independent_pair_oracle():
    rng = random.Random(45201)
    for _ in range(160):
        rows = [observation(i, deviceLabel=f"device-{rng.randrange(4)}", browser=rng.choice(["chrome", "firefox", "safari"]),
                            visitorId=rng.choice([None, "vis_" + "a" * 32, "vis_" + "b" * 32]),
                            referenceId=rng.choice([None, "external-a", "external-b"])) for i in range(rng.randrange(1, 18))]
        result = ev.evaluate(rows)["cohorts"][0]
        for field, system in [("visitorId", "singularity"), ("referenceId", "reference")]:
            assert_metrics(result[system]["allPairs"], brute(rows, field))
            assert_metrics(result[system]["crossBrowserPairs"], brute(rows, field, cross=True))
            shared = [r for r in rows if r["visitorId"] is not None and r["referenceId"] is not None]
            assert_metrics(result["sharedAssignedSubset"][system]["allPairs"], brute(shared, field))
            assert_metrics(result["sharedAssignedSubset"][system]["crossBrowserPairs"], brute(shared, field, cross=True))
        assert result["sharedCoverage"]["pairs"] == ev.rate(ev.choose(len(shared)), ev.choose(len(rows)))
        balanced = []
        for d in result["perDevice"]:
            visits = [r for r in rows if r["deviceLabel"] == d["deviceLabel"]]
            b = brute(visits, "visitorId")
            assert d["observations"] == len(visits)
            assert d["endToEndLinkYield"] == ev.rate(b["trueLinks"], b["sameDevicePairs"])
            if len(visits) > 1:
                balanced.append(d["endToEndLinkYield"]["value"])
        assert result["deviceBalancedLinkYield"] == ev.rate(sum(balanced), len(balanced))


def test_all_nulls_are_abstentions_not_successful_separations():
    rows = [observation(i, deviceLabel=f"device-{i // 2}", visitorId=None, method="unassigned") for i in range(4)]
    c = ev.evaluate(rows)["cohorts"][0]["singularity"]["allPairs"]
    assert c["coveredPairs"] == c["trueLinks"] == c["falseLinks"] == 0
    assert c["abstainedSameDevicePairs"] == 2 and c["abstainedDifferentDevicePairs"] == 4
    assert c["rates"]["falseLinkRate"]["value"] is None
    assert c["rates"]["endToEndLinkYield"]["value"] == 0


def write(path, rows):
    path.write_text("".join(json.dumps(r) + "\n" for r in rows))
    return path


def test_cohorts_chronology_and_deterministic_cli_without_session(tmp_path, capsys, monkeypatch):
    rows = [observation(), observation(1, project="second"), observation(2, configuration="run2"),
            observation(3, mode="possession", method="enrolled"), observation(4, source="empirical")]
    path = write(tmp_path / "input.jsonl", rows)
    monkeypatch.setattr("singularity.cli.load_session", lambda *a: pytest.fail("Offline command read a session"))
    monkeypatch.setattr("singularity.cli.httpx.Client", lambda *a, **k: pytest.fail("Offline command used networking"))
    assert main(["--json", "evaluate", str(path)]) == 0
    first = capsys.readouterr()
    assert len(json.loads(first.out)["cohorts"]) == 5 and not first.err
    assert all(c["singularity"]["allPairs"]["pairs"] == 0 for c in json.loads(first.out)["cohorts"])
    assert main(["--json", "evaluate", str(path)]) == 0
    assert capsys.readouterr().out == first.out
    assert main(["evaluate", str(path)]) == 0
    assert "Identification evaluation" in capsys.readouterr().out


@pytest.mark.parametrize("updates", [dict(visitorId=None), dict(method="unassigned"), dict(mode="possession"),
    dict(source="benchmark"), dict(observedAt="2026-10-07T12:00:00"), dict(visitorId=True),
    dict(referenceId=""), dict(deviceLabel=""), dict(extra="unknown")])
def test_malformed_records_rejected(tmp_path, updates):
    with pytest.raises(ValueError, match="line 1"):
        ev.load(write(tmp_path / "bad.jsonl", [observation(**updates)]))


def test_duplicate_chronology_keys_and_limits(tmp_path, monkeypatch):
    path = tmp_path / "bad.jsonl"
    for rows in [[observation(), observation()],
                 [observation(), observation(1, observedAt="2026-10-06T12:00:00Z")]]:
        with pytest.raises(ValueError, match="line 2"):
            ev.load(write(path, rows))
    path.write_text('{"schema":1,"schema":2}\n')
    with pytest.raises(ValueError): ev.load(path)
    path.write_text('x' * 8193)
    with pytest.raises(ValueError, match="limit"): ev.load(path)
    monkeypatch.setattr(ev, "MAX_RECORDS", 2)
    with pytest.raises(ValueError, match="limit"): ev.load(write(path, [observation(i) for i in range(3)]))
    path.write_text('')
    with pytest.raises(ValueError, match="no observations"): ev.load(path)


@pytest.mark.parametrize("encoding", ["utf-16", "utf-32", "utf-8-sig"])
def test_only_plain_utf8_is_accepted(tmp_path, encoding):
    path = tmp_path / "encoding.jsonl"
    path.write_bytes(json.dumps(observation()).encode(encoding))
    with pytest.raises(ValueError, match="line 1"):
        ev.load(path)
