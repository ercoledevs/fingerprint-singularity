"""Native/reference parity, including failures and conversion at the FFI boundary."""
import copy
import hashlib
import importlib
import json
import random
import runpy
from pathlib import Path

import pytest

from singularity import kernel, native, resilient_kernel as reference


def snapshot():
    return dict(schema='singularity/v3', scope='native-test', probe='web/v2', engine='blink',
                signals=dict(platform='macos', cores=8, memory=8, language='en', timezone='Europe/Rome'),
                detail=dict(gpu='a' * 64, fonts='b' * 64, canvas='c' * 64))


@pytest.fixture
def extension():
    return pytest.importorskip('singularity_native')


def outcome(call, *args):
    try:
        return call(*args)
    except (kernel.Invalid, ValueError) as exc:
        return dict(error=str(exc))


def test_backend_selection_and_required_native(monkeypatch):
    real_import = importlib.import_module
    def absent(name):
        if name == 'singularity_native':
            raise ModuleNotFoundError(name, name=name)
        return real_import(name)
    monkeypatch.setattr(importlib, 'import_module', absent)
    monkeypatch.setenv('SINGULARITY_KERNEL', 'auto')
    assert runpy.run_path(native.__file__)['BACKEND'] == 'python'
    monkeypatch.setenv('SINGULARITY_KERNEL', 'python')
    assert runpy.run_path(native.__file__)['BACKEND'] == 'python'
    monkeypatch.setenv('SINGULARITY_KERNEL', 'rust')
    with pytest.raises(RuntimeError, match='Rust kernel required'):
        runpy.run_path(native.__file__)
    monkeypatch.setenv('SINGULARITY_KERNEL', 'typo')
    with pytest.raises(RuntimeError, match='must be auto, python or rust'):
        runpy.run_path(native.__file__)


def test_loaded_native_contract(extension, monkeypatch):
    monkeypatch.setenv('SINGULARITY_KERNEL', 'rust')
    assert runpy.run_path(native.__file__)['BACKEND'] == 'rust'
    monkeypatch.setattr(extension, 'CONTRACT_VERSION', -1)
    with pytest.raises(RuntimeError, match='Incompatible'):
        runpy.run_path(native.__file__)


def test_native_seeded_matching_and_validation_parity(extension):
    rng = random.Random(403918)
    def generated():
        s = snapshot()
        s['engine'] = rng.choice(['blink', 'gecko', 'webkit', None])
        s['signals'] = dict(platform=rng.choice(['macos', 'windows', None]),
                            cores=rng.choice([4, 8, 8.0, None]), memory=rng.choice([0.25, 0.5, 8, None]),
                            language=rng.choice(['en', 'it', None]), timezone=rng.choice(['UTC', 'Europe/Rome', None]))
        s['detail'] = {k: rng.choice([None, 'a' * 64, 'b' * 64]) for k in s['detail']}
        return s
    for _ in range(5000):
        s = generated()
        candidates = [dict(id=f'c{i}', snapshot=generated()) for i in range(rng.randrange(9))]
        before = copy.deepcopy((s, candidates))
        assert extension.validate(s) == reference.validate_python(s)
        assert extension.match_resilient(s, candidates) == reference.match_python(s, candidates)
        assert (s, candidates) == before
    for count in (0, 1, 16, 64, 256, 257):
        s = snapshot()
        candidates = [dict(id=f'c{i}', snapshot=s) for i in range(count)]
        assert outcome(extension.match_resilient, s, candidates) == outcome(reference.match_python, s, candidates)


def test_native_invalid_inputs_and_error_order(extension):
    s = snapshot()
    cases = [(s, None), (s, ()), (None, []), ({}, [None] * 257),
             (s, [None]), (s, [dict(id='a', snapshot=s, extra=1)]),
             (s, [dict(id='a', snapshot=s), dict(id='a', snapshot={})]),
             (s, [dict(id='a', snapshot={**s, 'scope': 'other'})])]
    for field in ['cores', 'memory', 'language', 'timezone']:
        for bad in [True, False, {}, [], -1, 3, float('nan'), float('inf'), '8', '', '\ud800', 'en\n']:
            changed = copy.deepcopy(s); changed['signals'][field] = bad
            cases.append((changed, []))
    for section, key, values in [
        (None, 'scope', ['', 'a' * 129, 'é', 'a\n', True, None]),
        (None, 'probe', ['web/v1', '', None, '\ud800']),
        (None, 'schema', ['singularity/v2', '', None, '\ud800']),
        ('detail', 'gpu', [True, {}, 'A' * 64, 'g' * 64, 'a' * 63, 'a' * 65, 'a' * 64 + '\n', '\ud800']),
        (None, 'engine', [True, {}, [], 1, 'unknown']),
        ('signals', 'platform', [True, {}, [], 1, 'unknown']),
    ]:
        for bad in values:
            changed = copy.deepcopy(s)
            (changed[section] if section else changed)[key] = bad
            cases.append((changed, []))
    for key in s:
        changed = copy.deepcopy(s); del changed[key]; cases.append((changed, []))
    for bad_id in [True, '', 'a' * 129, 'a/b', 'é', 'a\n', '\ud800']:
        cases.append((s, [dict(id=bad_id, snapshot=s)]))
    sparse = copy.deepcopy(s); sparse['detail'] = dict(gpu=None, fonts=None, canvas=None)
    cases.append((sparse, [dict(id='a', snapshot={})]))
    class DictSubclass(dict):
        pass
    class ListSubclass(list):
        pass
    class StrSubclass(str):
        pass
    class IntSubclass(int):
        pass
    cases.extend([(DictSubclass(s), []), (s, ListSubclass()),
                  (s, [dict(id=StrSubclass('a'), snapshot=s)]),
                  ({**s, 'signals': {**s['signals'], 'cores': IntSubclass(8)}}, [])])
    # Unsupported revision objects use the reference, preserving Python equality.
    for observation, candidates in cases:
        expected = outcome(reference.match_python, observation, candidates)
        def native_or_reference(s, pool):
            try:
                return extension.match_resilient(s, pool)
            except extension.UnsupportedInput:
                return reference.match_python(s, pool)
        actual = outcome(native_or_reference, observation, candidates)
        assert actual == expected, (observation, candidates, expected, actual)


def test_native_validation_copies_preserves_float_and_hashes(extension):
    s = snapshot(); s['signals']['cores'] = 8.0; s['signals']['memory'] = 0.25
    validated = extension.validate(s)
    assert type(validated['signals']['cores']) is float
    assert validated is not s and validated['signals'] is not s['signals'] and validated['detail'] is not s['detail']
    # JSON order for the validator's public return is the reference's order too.
    assert json.dumps(validated) == json.dumps(reference.validate_python(s))
    assert kernel.digest(s) == 'sg3_' + hashlib.sha256(reference.canonicalize(s).encode()).hexdigest()


def test_python_object_enum_fallback(extension, monkeypatch):
    class Text(str):
        pass
    monkeypatch.setattr(reference, 'accelerator', extension)
    s = snapshot(); s['engine'] = Text('blink'); s['signals']['platform'] = Text('macos')
    assert reference.validate(s) == reference.validate_python(s)
    assert reference.match(s, [dict(id='a', snapshot=s)]) == reference.match_python(s, [dict(id='a', snapshot=s)])


def test_native_error_translation_and_no_unexpected_fallback(extension, monkeypatch):
    monkeypatch.setattr(reference, 'accelerator', extension)
    with pytest.raises(kernel.Invalid) as exc:
        reference.match(snapshot(), [None] * 257)
    assert exc.value.code == 'LIMIT_EXCEEDED'
    def broken(*args):
        raise RuntimeError('unexpected native failure')
    monkeypatch.setattr(extension, 'match_resilient', broken)
    with pytest.raises(RuntimeError, match='unexpected native failure'):
        reference.match(snapshot(), [])
