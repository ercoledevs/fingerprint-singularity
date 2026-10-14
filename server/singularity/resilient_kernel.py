"""support/v3: font agreement with model or rendering support; rendering drift is diagnostic."""
import hashlib
import json
import re
from .kernel import Invalid, identifier, record, validate_v1

POLICY = 'support/v3'
KEYS = ['gpu', 'fonts', 'canvas']


def validate(value):
    record(value, ['schema', 'scope', 'signals', 'probe', 'engine', 'detail'])
    if value['schema'] != 'singularity/v3' or value['probe'] != 'web/v2':
        raise Invalid('INCOMPATIBLE_SCHEMA')
    if value['engine'] is not None and value['engine'] not in ('blink', 'gecko', 'webkit'):
        raise Invalid()
    coarse = validate_v1(dict(schema='singularity/v1', scope=value['scope'], signals=value['signals']))
    record(value['detail'], KEYS)
    for v in value['detail'].values():
        if v is not None and (type(v) is not str or not re.fullmatch(r'[a-f0-9]{64}', v)):
            raise Invalid()
    return dict(schema='singularity/v3', scope=coarse['scope'], signals=coarse['signals'], probe='web/v2', engine=value['engine'], detail=dict(value['detail']))


def canonicalize(snapshot):
    s = validate(snapshot)
    values = [s['schema'], s['scope'], s['probe'], s['engine']] + [s['signals'][k] for k in ['platform', 'cores', 'memory', 'language', 'timezone']] + [s['detail'][k] for k in KEYS]
    values = [int(x) if type(x) is float and x.is_integer() else x for x in values]
    return json.dumps(values, separators=(',', ':'), ensure_ascii=False)


def digest(snapshot):
    return 'sg3_' + hashlib.sha256(canonicalize(snapshot).encode()).hexdigest()


def compare(a, b):
    contradictions = [k for k in ['platform', 'cores'] if a['signals'][k] is not None and b['signals'][k] is not None and a['signals'][k] != b['signals'][k]]
    comparable = [k for k in KEYS if a['detail'][k] is not None and b['detail'][k] is not None]
    supporting = [k for k in comparable if a['detail'][k] == b['detail'][k]]
    differences = [k for k in comparable if a['detail'][k] != b['detail'][k]]
    cross_engine = a['engine'] is not None and b['engine'] is not None and a['engine'] != b['engine']
    contradictions += [k for k in differences if k != 'canvas' or not cross_engine]
    coarse_known = all(s['signals'][k] is not None for s in [a, b] for k in ['platform', 'cores'])
    return dict(policy=POLICY, similarity=len(supporting) / 3, coverage=len(comparable) / 3,
                comparableDetails=comparable, supportingDetails=supporting, contradictions=contradictions, differences=differences,
                qualifies=coarse_known and not contradictions and 'fonts' in supporting and ('gpu' in supporting or 'canvas' in supporting))


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


def continuity_code(snapshot):
    """Fixed projection; never a visitor credential or a deletion/retention bypass."""
    s = validate(snapshot)
    c, d = s['signals'], s['detail']
    if any(v is None for v in [c['platform'], c['cores'], d['gpu'], d['fonts']]):
        return None
    values = ['continuity/v1', s['scope'], s['probe'], c['platform'], c['cores'], d['gpu'], d['fonts']]
    values = [int(x) if type(x) is float and x.is_integer() else x for x in values]
    return 'sc1_' + hashlib.sha256(json.dumps(values, separators=(',', ':'), ensure_ascii=False).encode()).hexdigest()
