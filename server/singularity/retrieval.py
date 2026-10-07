"""Retrieve every potentially relevant anchor before the inference pool limit.

Inputs are validated snapshots. Only permanent support/v2 contradictions may
be removed here; missing values remain possible rivals, never agreements.
The legacy omission policy must keep its original, unpartitioned pool.
"""
from itertools import combinations


DETAIL_KEYS = ('gpu', 'fonts', 'canvas')
DETAIL_SUBSETS = tuple(combinations(DETAIL_KEYS, 2)) + (DETAIL_KEYS,)
INDEX_NAMES = {keys: 'v2_candidates_' + '_'.join(keys) for keys in DETAIL_SUBSETS}
INDEXES = {
    INDEX_NAMES[keys]: [('project', 1), ('snapshot.signals.platform', 1), ('snapshot.signals.cores', 1)]
    + [('snapshot.detail.' + key, 1) for key in keys] + [('expiresAt', 1)]
    for keys in DETAIL_SUBSETS
}
INDEX_PARTIAL_FILTER = {'anchor': True, 'snapshot.schema': 'singularity/v2'}


def anchor_filter(project, snapshot, at):
    query = {'project': project, 'snapshot.schema': snapshot['schema'],
             'anchor': True, 'expiresAt': {'$gt': at}}
    if snapshot['schema'] == 'singularity/v2':
        for section, keys in [('signals', ('platform', 'cores')), ('detail', DETAIL_KEYS)]:
            for key in keys:
                value = snapshot[section][key]
                if value is not None:
                    # Mongo null equality also includes absent fields. Never filter
                    # for presence: an incomplete compatible rival blocks a winner.
                    query[f'snapshot.{section}.{key}'] = {'$in': [value, None]}
    return query


def index_for(snapshot):
    """Choose a bounded lookup for a sufficient, validated v2 observation.

Every indexed field before expiry is constrained. A separate index for each
available pair avoids scanning an expired backlog behind an unknown third field.
"""
    available = tuple(key for key in DETAIL_KEYS if snapshot['detail'][key] is not None)
    return INDEX_NAMES[available]
