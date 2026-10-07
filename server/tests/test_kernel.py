import copy
import json
import random
import subprocess
from pathlib import Path
from singularity import kernel


BASE = dict(schema="singularity/v1", scope="oracle", signals=dict(platform="macos", cores=8, memory=8, language="en", timezone="Europe/Rome"))


def test_typescript_python_oracle():
    cases = []
    for mask in range(32):
        s = copy.deepcopy(BASE)
        for i, key in enumerate(s["signals"]):
            if mask & (1 << i):
                s["signals"][key] = None
        cases.append(dict(snapshot=s, op="digest"))
        for count in (0, 1, 2):
            cases.append(dict(snapshot=s, candidates=[dict(id=f"candidate{i}", snapshot=BASE) for i in range(count)]))
    rng = random.Random(314159)
    values = dict(platform=["macos", "windows", "linux", None], cores=[4, 8, 16, None], memory=[.25, 4, 8.0, None], language=["en", "it", None], timezone=["Europe/Rome", "UTC", None])
    for _ in range(400):
        s = {**BASE, "signals": {k: rng.choice(v) for k, v in values.items()}}
        candidates = [dict(id=f"c{i}", snapshot={**BASE, "signals": {k: rng.choice(v) for k, v in values.items()}}) for i in range(rng.randrange(5))]
        cases.append(dict(snapshot=s, candidates=candidates))
    for count in (256, 257):
        cases.append(dict(snapshot=BASE, candidates=[dict(id=f"c{i}", snapshot=BASE) for i in range(count)]))
    for value in (True, False, "8", {}, [], -1, 3):
        s = copy.deepcopy(BASE); s["signals"]["cores"] = value
        cases.append(dict(snapshot=s, candidates=[]))
    cases.extend([dict(snapshot={**BASE, "extra": 1}, candidates=[]), dict(snapshot=BASE, candidates=[dict(id="a", snapshot=BASE)] * 2),
                  dict(snapshot=BASE, candidates=[dict(id="a", snapshot={**BASE, "scope": "other"})])])
    root = Path(__file__).resolve().parents[2]
    expected = json.loads(subprocess.check_output(["node", "scripts/kernel-oracle.mjs"], cwd=root, input=json.dumps(cases).encode()))
    actual = []
    for c in cases:
        try:
            actual.append(dict(canonical=kernel.canonicalize(c["snapshot"]), digest=kernel.digest(c["snapshot"])) if c.get("op") == "digest" else kernel.match(c["snapshot"], c["candidates"]))
        except kernel.Invalid as exc:
            actual.append({"error": exc.code})
    assert actual == expected
