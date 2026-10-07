"""support/v2: exact support from at least two available detailed probes."""
import hashlib
import json
import re
from .kernel import Invalid, identifier, record, validate_v1

POLICY = 'support/v2'
KEYS = ['gpu', 'fonts', 'canvas']


def validate(value):
    record(value, ['schema', 'scope', 'signals', 'probe', 'detail'])
    if value['schema'] != 'singularity/v2' or value['probe'] != 'web/v1':
        raise Invalid('INCOMPATIBLE_SCHEMA')
    coarse = validate_v1(dict(schema='singularity/v1', scope=value['scope'], signals=value['signals']))
    record(value['detail'], KEYS)
    for v in value['detail'].values():
        if v is not None and (type(v) is not str or not re.fullmatch(r'[a-f0-9]{64}', v)):
            raise Invalid()
    return dict(schema='singularity/v2', scope=coarse['scope'], signals=coarse['signals'], probe='web/v1', detail=dict(value['detail']))


def canonicalize(snapshot):
    s = validate(snapshot)
    values = [s['schema'], s['scope'], s['probe']] + [s['signals'][k] for k in ['platform', 'cores', 'memory', 'language', 'timezone']] + [s['detail'][k] for k in KEYS]
    values = [int(x) if type(x) is float and x.is_integer() else x for x in values]
    return json.dumps(values, separators=(',', ':'), ensure_ascii=False)


def digest(snapshot):
    return 'sg2_' + hashlib.sha256(canonicalize(snapshot).encode()).hexdigest()


def compare(a, b):
    contradictions = [k for k in ['platform', 'cores'] if a['signals'][k] is not None and b['signals'][k] is not None and a['signals'][k] != b['signals'][k]]
    comparable = [k for k in KEYS if a['detail'][k] is not None and b['detail'][k] is not None]
    supporting = [k for k in comparable if a['detail'][k] == b['detail'][k]]
    contradictions += [k for k in comparable if a['detail'][k] != b['detail'][k]]
    coarse_known = all(s['signals'][k] is not None for s in [a, b] for k in ['platform', 'cores'])
    return dict(policy=POLICY, similarity=len(supporting) / 3, coverage=len(comparable) / 3,
                comparableDetails=comparable, supportingDetails=supporting, contradictions=contradictions,
                qualifies=coarse_known and not contradictions and len(supporting) >= 2)


def sufficient(snapshot):
    return compare(snapshot, snapshot)['qualifies']


def match(snapshot, candidates):
    if type(candidates) is not list:
        raise Invalid()
    if len(candidates) > 256:
        raise Invalid('LIMIT_EXCEEDED')
    observation = validate(snapshot)
    ids, ranking = set(), []
    for c in candidates:
        record(c, ['id', 'snapshot'])
        identifier(c['id'])
        if c['id'] in ids:
            raise Invalid('DUPLICATE_ID')
        ids.add(c['id'])
        other = validate(c['snapshot'])
        if other['scope'] != observation['scope']:
            raise Invalid('SCOPE_MISMATCH')
        ranking.append(dict(id=c['id'], **compare(observation, other)))
    def result(status, reason, candidate=None):
        return dict(policy=POLICY, status=status, candidateId=candidate, reason=reason, candidates=ranking, omissions=[])
    if not sufficient(observation):
        return result('abstain', 'insufficient-detail')
    if not candidates:
        return result('unmatched', 'no-candidates')
    eligible = [c for c in ranking if c['qualifies']]
    if len(eligible) > 1:
        return result('abstain', 'ambiguous-candidates')
    if any(not c['qualifies'] and not c['contradictions'] for c in ranking):
        return result('abstain', 'insufficient-candidate-evidence')
    return result('matched', 'supported-candidate', eligible[0]['id']) if eligible else result('unmatched', 'no-candidate-qualified')
