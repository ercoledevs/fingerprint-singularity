"""Paired candidate-capacity regression; synthetic, never population accuracy.

Run: python scripts/evaluate-retrieval.py --out artifacts/improvement-retrieval
"""
import argparse
import copy
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random

from singularity import kernel
from singularity.detailed_kernel import compare
from singularity.evaluation import system_metrics

ORDERS = (728193, 913571, 481927)
CASES = (('grid', 'repeat'), ('grid', 'gpu-unavailable'), ('grid', 'sparse-first'), ('clones', 'repeat'))


def feature(name, value):
    return hashlib.sha256(json.dumps([name, value], separators=(',', ':')).encode()).hexdigest()


def visits(population, scenario, order):
    devices = []
    # Shared finite categories; device labels and visit numbers never enter a probe.
    for gpu in range(24):
        for fonts in range(16):
            g, f = (0, 0) if population == 'clones' else (gpu, fonts)
            snapshot = dict(schema='singularity/v2', probe='web/v1', scope='capacity-sandbox',
                signals=dict(platform='windows', cores=8, memory=8, language='en', timezone='UTC'),
                detail=dict(gpu=feature('gpu', g), fonts=feature('fonts', f), canvas=feature('canvas', [g % 3, f % 2])))
            devices.append((f'device-{gpu}-{fonts}', snapshot))
    rng = random.Random(order)
    for visit in range(2):
        rng.shuffle(devices)
        for label, snapshot in devices:
            s = copy.deepcopy(snapshot)
            if (scenario == 'gpu-unavailable' and visit == 1) or (scenario == 'sparse-first' and visit == 0):
                s['detail']['gpu'] = None
            yield label, s


def oracle(snapshot, anchors):
    """Uncapped support/v2 semantics, independent of retrieval and Mongo syntax."""
    if not kernel.sufficient(snapshot):
        return 'abstain', None
    comparisons = [(a['id'], compare(snapshot, a['snapshot'])) for a in anchors]
    eligible = [key for key, evidence in comparisons if evidence['qualifies']]
    unresolved = any(not evidence['qualifies'] and not evidence['contradictions'] for _, evidence in comparisons)
    if len(eligible) > 1 or unresolved:
        return 'abstain', None
    return ('matched', eligible[0]) if eligible else ('unmatched', None)


def summarize(rows):
    owners, devices = defaultdict(set), defaultdict(list)
    for row in rows:
        devices[row['deviceLabel']].append(row['visitorId'])
        if row['visitorId'] is not None:
            owners[row['visitorId']].add(row['deviceLabel'])
    exclusive = sum(all(key is not None for key in ids) and len(set(ids)) == 1 and len(owners[ids[0]]) == 1 for ids in devices.values())
    return dict(devices=len(devices), visits=len(rows), assignedVisits=sum(r['visitorId'] is not None for r in rows),
                exclusiveStableDevices=exclusive, exclusiveStableRate=exclusive / len(devices),
                metrics=system_metrics(rows, 'visitorId')['allPairs'])


def run(population, scenario, order, retrieval):
    anchors, rows = [], []
    for label, snapshot in visits(population, scenario, order):
        if retrieval == 'uncapped-oracle':
            status, visitor = oracle(snapshot, anchors)
        else:
            if retrieval == 'platform-only':
                pool = [a for a in anchors if a['snapshot']['signals']['platform'] == snapshot['signals']['platform']]
            elif retrieval == 'compatible':
                pool = [a for a in anchors if not compare(snapshot, a['snapshot'])['contradictions']]
            else:
                raise ValueError('Unknown retrieval mode')
            if len(pool) > 256:
                status, visitor = 'abstain', None
            else:
                result = kernel.match(snapshot, pool)
                status, visitor = result['status'], result['candidateId']
        if status == 'unmatched':
            visitor = f'vis_{len(anchors) + 1:032x}'
            anchors.append(dict(id=visitor, snapshot=snapshot))
        rows.append(dict(deviceLabel=label, visitorId=visitor, browser='synthetic-adapter', status=status))
    return dict(**summarize(rows), anchors=len(anchors)), rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('artifacts/improvement-retrieval'))
    args = parser.parse_args()
    reports = []
    for population, scenario in CASES:
        for order in ORDERS:
            paired = {}
            for retrieval in ('platform-only', 'compatible', 'uncapped-oracle'):
                result, rows = run(population, scenario, order, retrieval)
                reports.append(dict(population=population, scenario=scenario, order=order, retrieval=retrieval, **result))
                paired[retrieval] = rows
            assert paired['compatible'] == paired['uncapped-oracle']
    report = dict(schema='singularity-retrieval-evaluation/v1', source='synthetic', populationAccuracy='UNKNOWN',
        method='384 device labels, 24 shared GPU classes × 16 shared font classes; coarser correlated canvas, same platform and core bucket. Three shuffled arrival orders. Clone and missing-evidence controls. No labels in observations. Orders are not independent populations.',
        oracleParity=True, cohorts=len(reports), visits=sum(r['visits'] for r in reports), outcomes=reports)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / 'retrieval-results.json').write_text(json.dumps(report, indent=2))
    print(json.dumps({k: report[k] for k in ('cohorts', 'visits', 'oracleParity', 'populationAccuracy')}))
    for row in reports:
        if row['order'] == ORDERS[0]:
            print(json.dumps({k: row[k] for k in ('population', 'scenario', 'retrieval', 'assignedVisits', 'exclusiveStableDevices')}
                | {k: row['metrics'][k] for k in ('trueLinks', 'falseLinks')}))


if __name__ == '__main__':
    main()
