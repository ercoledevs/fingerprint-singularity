"""Paired, deterministic synthetic evaluation. Never a population accuracy estimate.

Run: python scripts/evaluate-detailed.py --out artifacts/improvement-v03
Uses finite shared latent hardware/font/rendering groups, not device-derived hashes.
"""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
from singularity import kernel
from singularity.evaluation import system_metrics


def feature(name, value):
    return hashlib.sha256(json.dumps(['web/v1', 'paired-sandbox', name, value], separators=(',', ':')).encode()).hexdigest()


def generate(kind, seed, count=64):
    rng = random.Random(seed)
    rows = []
    for i in range(count):
        platform = rng.choice(['macos', 'windows', 'linux', 'android']) if kind == 'diverse' else 'windows'
        cores = rng.choice([2, 4, 8, 16, 32]) if kind == 'diverse' else rng.choice([4, 8, 16])
        memory = rng.choice([2, 4, 8])
        gpu = rng.randrange(12 if kind == 'diverse' else 4)
        fonts = rng.randrange(8 if kind == 'diverse' else 4)
        signals = dict(platform=platform, cores=cores, memory=memory, language=rng.choice(['en', 'it', 'de']), timezone=rng.choice(['UTC', 'Europe/Rome']))
        if kind != 'diverse':
            signals.update(language='it', timezone='Europe/Rome', memory=rng.choice([4, 8]))
        if kind == 'clones':
            signals = dict(platform='windows', cores=8, memory=8, language='it', timezone='Europe/Rome')
            gpu = fonts = 0
        detail = dict(gpu=feature('gpu', [platform, gpu]), fonts=feature('fonts', [platform, fonts]),
                      canvas=feature('canvas', [platform, gpu % 3, fonts % 2, 'engine-a']))
        rows.append(dict(label=f'device-{i}', snapshot=dict(schema='singularity/v2', scope='paired-sandbox', probe='web/v1', signals=signals, detail=detail), latent=dict(gpu=gpu, fonts=fonts)))
    # Deliberate complete clones: the new policy must not manufacture uniqueness.
    if kind == 'office':
        for i in range(0, min(16, count), 2):
            rows[i+1]['snapshot'] = json.loads(json.dumps(rows[i]['snapshot']))
            rows[i+1]['latent'] = dict(rows[i]['latent'])
    rng.shuffle(rows)
    return rows


def mutate(device, scenario):
    s = json.loads(json.dumps(device['snapshot']))
    if scenario == 'locale-memory-drift':
        s['signals'].update(memory=None, language='fr', timezone='America/New_York')
    elif scenario == 'canvas-update':
        s['detail']['canvas'] = feature('canvas', [s['signals']['platform'], device['latent']['gpu'] % 3, device['latent']['fonts'] % 2, 'engine-b'])
    elif scenario == 'gpu-unavailable':
        s['detail']['gpu'] = None
    elif scenario == 'blocked-detail':
        s['detail'].update(gpu=None, canvas=None)
    return s


def visit_snapshot(device, scenario, visit):
    if scenario == 'sparse-first':
        return mutate(device, 'gpu-unavailable') if visit == 0 else device['snapshot']
    return mutate(device, scenario) if visit else device['snapshot']


def summarize(rows):
    owners, by_device = defaultdict(set), defaultdict(list)
    for row in rows:
        by_device[row['deviceLabel']].append(row['visitorId'])
        if row['visitorId'] is not None:
            owners[row['visitorId']].add(row['deviceLabel'])
    strict = sum(all(v is not None for v in ids) and len(set(ids)) == 1 and len(owners[ids[0]]) == 1 for ids in by_device.values())
    return dict(devices=len(by_device), visits=len(rows), assignedVisits=sum(r['visitorId'] is not None for r in rows),
                exclusiveStableDevices=strict, exclusiveStableRate=strict / len(by_device), metrics=system_metrics(rows, 'visitorId')['allPairs'])


def run(devices, scenario, policy):
    anchors, rows = [], []
    for visit in range(2):
        for device in devices:
            detailed = visit_snapshot(device, scenario, visit)
            snapshot = detailed if policy in ['support/v2', 'exact-detailed'] else {k: detailed[k] for k in ['scope', 'signals']} | {'schema': 'singularity/v1'}
            pool = [a for a in anchors if policy != 'support/v2' or a['snapshot']['signals']['platform'] == snapshot['signals']['platform']]
            visitor = None
            if policy == 'exact-detailed':
                # Evidence-only equality separates richer observations from fuzzy selection.
                visitor = 'vis_' + feature('exact-detailed', [snapshot['signals']['platform'], snapshot['signals']['cores'], snapshot['detail']])[:32]
            elif policy == 'exact-coarse':
                # Exact equality baseline, with no noisy-hash uniqueness interpretation.
                visitor = 'vis_' + kernel.digest(snapshot)[4:36]
            elif kernel.sufficient(snapshot) and len(pool) <= 256:
                decision = kernel.match(snapshot, pool)
                if decision['status'] == 'matched':
                    visitor = decision['candidateId']
                elif decision['status'] == 'unmatched':
                    visitor = 'vis_' + f'{len(anchors)+1:032x}'
                    anchors.append(dict(id=visitor, snapshot=snapshot))
            rows.append(dict(deviceLabel=device['label'], visitorId=visitor, browser='synthetic-adapter'))
    return dict(**summarize(rows), anchors=len(anchors)), rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out', type=Path, default=Path('artifacts/improvement-v03'))
    args = parser.parse_args(); args.out.mkdir(parents=True, exist_ok=True)
    reports, records = [], []
    # Fixed before evaluating outputs; no adaptive threshold fitting. Seeds not used by the v0.2 sandbox.
    for seed in [728193, 913571, 481927]:
        for kind in ['diverse', 'office', 'clones']:
            for order in range(3):
                devices = generate(kind, seed)
                random.Random(seed + order * 1777).shuffle(devices)
                for scenario in ['repeat', 'locale-memory-drift', 'canvas-update', 'gpu-unavailable', 'blocked-detail', 'sparse-first']:
                    for policy in ['envelope/v1', 'exact-coarse', 'exact-detailed', 'support/v2']:
                        result, rows = run(devices, scenario, policy)
                        reports.append(dict(seed=seed, order=order, population=kind, scenario=scenario, policy=policy, **result))
                        for i, row in enumerate(rows):
                            records.append(dict(seed=seed, order=order, population=kind, scenario=scenario, policy=policy, visit=i, **row))
    report = dict(schema='singularity-paired-sandbox/v1', source='synthetic', populationAccuracy='UNKNOWN',
                  seeds=[728193,913571,481927], arrivalOrders=3, scenarios=6, policies=4, cohorts=len(reports), visits=len(records),
                  method='Same latent devices and visits for all policies; shared finite GPU/font groups and coarser correlated rendering groups (GPU mod 3, font mod 2), deliberately cloned devices, no labels in hashes. Repeated seeds/orders/scenarios are not independent population samples.',
                  outcomes=reports)
    (args.out/'paired-results.json').write_text(json.dumps(report, indent=2))
    (args.out/'paired-observations.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    print(json.dumps({k: report[k] for k in ['cohorts','visits','populationAccuracy']}))
    for kind in ['diverse','office','clones']:
        for scenario in ['repeat','canvas-update','blocked-detail']:
            compact=[]
            for policy in ['envelope/v1','exact-coarse','exact-detailed','support/v2']:
                subset=[r for r in reports if r['population']==kind and r['scenario']==scenario and r['policy']==policy]
                compact.append(dict(policy=policy,exclusiveStableRange=[min(r['exclusiveStableRate'] for r in subset),max(r['exclusiveStableRate'] for r in subset)],assignedVisits=[r['assignedVisits'] for r in subset]))
            print(json.dumps(dict(population=kind,scenario=scenario,results=compact)))


if __name__ == '__main__':
    main()
