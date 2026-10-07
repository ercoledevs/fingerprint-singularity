"""envelope/v1: kept in parity with the TypeScript reference implementation."""
import hashlib
import json
import re

POLICY = "envelope/v1"
FAMILIES = ["platform", "compute", "locale"]
FIELDS = [("platform", "platform", 3), ("cores", "compute", 2),
          ("memory", "compute", 1), ("language", "locale", 1), ("timezone", "locale", 1)]


class Invalid(ValueError):
    def __init__(self, code="INVALID_INPUT"):
        self.code = code
        super().__init__(code)


def record(value, keys):
    if type(value) is not dict or set(value) != set(keys):
        raise Invalid()


def identifier(value, scope=False):
    if type(value) is not str or not 1 <= len(value) <= 128 or not re.fullmatch(
            r"[A-Za-z0-9._:/-]+" if scope else r"[A-Za-z0-9._:-]+", value):
        raise Invalid()
    return value


def validate_v1(value):
    record(value, ["schema", "scope", "signals"])
    if value["schema"] != "singularity/v1":
        raise Invalid("INCOMPATIBLE_SCHEMA")
    identifier(value["scope"], True)
    s = value["signals"]
    record(s, [x[0] for x in FIELDS])
    if s["platform"] is not None and s["platform"] not in ["windows", "macos", "ios", "android", "linux", "chromeos"]:
        raise Invalid()
    for key, buckets in [("cores", [1, 2, 4, 8, 16, 32, 64]), ("memory", [.25, .5, 1, 2, 4, 8, 16, 32, 64])]:
        v = s[key]
        if v is not None and (type(v) not in (int, float) or v not in buckets):
            raise Invalid()
    for key, pattern in [("language", r"[a-z]{2,8}"), ("timezone", r"[A-Za-z0-9_+/-]{1,80}")]:
        if s[key] is not None and (type(s[key]) is not str or not re.fullmatch(pattern, s[key])):
            raise Invalid()
    return {"schema": value["schema"], "scope": value["scope"], "signals": dict(s)}


def canonicalize_v1(snapshot):
    s = validate_v1(snapshot)
    values = [s["schema"], s["scope"]] + [s["signals"][f[0]] for f in FIELDS]
    values = [int(x) if type(x) is float and x.is_integer() else x for x in values]
    return json.dumps(values, separators=(",", ":"), ensure_ascii=False)


def digest_v1(snapshot):
    return "sg1_" + hashlib.sha256(canonicalize_v1(snapshot).encode()).hexdigest()


def evaluate(a, b, omitted=None):
    total = equal = comparable = 0
    seen, contradictions, contributions = set(), [], []
    for key, family, weight in FIELDS:
        if family == omitted:
            continue
        total += weight
        left, right = a["signals"][key], b["signals"][key]
        state = "missing" if left is None or right is None else "equal" if left == right else "different"
        contributions.append(dict(signal=key, family=family, weight=weight, state=state))
        if state != "missing":
            comparable += weight
            seen.add(family)
        if state == "equal":
            equal += weight
        if key == "platform" and state == "different":
            contradictions.append(key)
    similarity, coverage = equal / total, comparable / total
    return dict(policy=POLICY, similarity=similarity, coverage=coverage,
                comparableFamilies=[f for f in FAMILIES if f in seen], contradictions=contradictions,
                contributions=contributions, qualifies=not contradictions and similarity >= .75
                and coverage >= .75 and len(seen) >= (2 if omitted else 3))


def sufficient_v1(snapshot):
    return all(evaluate(snapshot, snapshot, f)["qualifies"] for f in [None, *FAMILIES])


def match_v1(snapshot, candidates):
    if type(candidates) is not list:
        raise Invalid()
    if len(candidates) > 256:
        raise Invalid("LIMIT_EXCEEDED")
    observation = validate_v1(snapshot)
    ids = set()
    for c in candidates:
        record(c, ["id", "snapshot"])
        identifier(c["id"])
        if c["id"] in ids:
            raise Invalid("DUPLICATE_ID")
        ids.add(c["id"])
        validate_v1(c["snapshot"])
        if observation["scope"] != c["snapshot"]["scope"]:
            raise Invalid("SCOPE_MISMATCH")
    def assess(omit=None):
        return [dict(id=c["id"], **evaluate(observation, c["snapshot"], omit)) for c in candidates]
    ranking = assess()
    def result(status, reason, cid=None, omissions=None):
        return dict(policy=POLICY, status=status, candidateId=cid, reason=reason,
                    candidates=ranking, omissions=omissions or [])
    def best(values):
        return min(values, key=lambda c: (-c["similarity"], c["id"]), default=None)
    def runner(values, winner):
        return best([c for c in values if c["id"] != winner["id"] and not c["contradictions"]])
    def margin(w, r):
        return r is None or w["similarity"] - r["similarity"] >= .15
    if not candidates:
        return result("unmatched", "no-candidates")
    if not sufficient_v1(observation):
        return result("abstain", "insufficient-observation")
    winner = best([c for c in ranking if c["qualifies"]])
    if winner is None:
        uncertain = any(not c["contradictions"] and (c["coverage"] < .75 or len(c["comparableFamilies"]) < 3) for c in ranking)
        return result("abstain" if uncertain else "unmatched", "insufficient-candidate-evidence" if uncertain else "no-candidate-qualified")
    if not margin(winner, runner(ranking, winner)):
        return result("abstain", "ambiguous-candidates")
    omissions = []
    for f in FAMILIES:
        reduced = assess(f)
        selected = next(c for c in reduced if c["id"] == winner["id"])
        r = runner(reduced, winner)
        omissions.append(dict(omitted=f, passes=selected["qualifies"] and margin(selected, r), candidateId=winner["id"],
                              runnerUpId=r["id"] if r else None, margin=selected["similarity"] - r["similarity"] if r else None,
                              similarity=selected["similarity"], coverage=selected["coverage"], comparableFamilies=selected["comparableFamilies"]))
    if any(not o["passes"] for o in omissions):
        return result("abstain", "unstable-under-omission", omissions=omissions)
    return result("matched", "stable-candidate", winner["id"], omissions)


def implementation(snapshot):
    if type(snapshot) is dict and snapshot.get('schema') == 'singularity/v2':
        from . import detailed_kernel
        return detailed_kernel
    return None


def policy(snapshot):
    module = implementation(snapshot)
    return module.POLICY if module else POLICY


def validate(value):
    module = implementation(value)
    return module.validate(value) if module else validate_v1(value)


def canonicalize(snapshot):
    module = implementation(snapshot)
    return module.canonicalize(snapshot) if module else canonicalize_v1(snapshot)


def digest(snapshot):
    module = implementation(snapshot)
    return module.digest(snapshot) if module else digest_v1(snapshot)


def sufficient(snapshot):
    module = implementation(snapshot)
    return module.sufficient(snapshot) if module else sufficient_v1(snapshot)


def match(snapshot, candidates):
    module = implementation(snapshot)
    return module.match(snapshot, candidates) if module else match_v1(snapshot, candidates)
