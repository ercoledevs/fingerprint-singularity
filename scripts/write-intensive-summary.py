"""Publish aggregate evidence in the public CI summary without raw observations."""
import json
import os
from pathlib import Path

root = Path('artifacts/intensive-v04')
report = json.loads((root / 'browsers.json').read_text())
def percent(rate):
    value = rate['percent']
    return 'N/A' if value is None else f'{value:.4f}% ({rate["numerator"]}/{rate["denominator"]})'

lines = ['## Paired public SDK results', '',
         f'Host: {report["environment"]["platform"]}/{report["environment"]["arch"]}. Completed paired observations: {report["totalPairedObservations"]}. One host; real cross-device uniqueness is not measurable.', '',
         '| Browser | Build | SDK | Stable observation digest | sc1 availability | Stable available sc1 | Collector p95 |',
         '| --- | --- | --- | --- | --- | --- | --- |']
for browser in report['browsers']:
    if browser['status'] != 'PASS':
        lines.append(f'| {browser["name"]} | FAIL | — | — | — | — | — |')
        continue
    for version, data in browser['versions'].items():
        all_data = data['all']; code = all_data['continuityCode']
        lines.append(f'| {browser["name"]} | {browser["version"]} | {version} | {percent(all_data["digest"]["conditionalRepeatability"])} | {percent(code["availability"]) if code else "N/A"} | {percent(code["conditionalRepeatability"]) if code else "N/A"} | {all_data["collect"]["p95Ms"]:.4f} ms |')
lines += ['', 'Persistent profile, verified site-data clearing, persistent restarts, nonpersistent incognito contexts and empty-cache fresh normal profiles. In-place HTTP cache eviction is proven only for Chromium. No population accuracy estimate.', '', '### Visitor matcher replay', '',
          '| SDK | Assigned visits | Same-host pair continuity |', '| --- | --- | --- |']
for version, data in report['matchReplay'].items():
    metrics = data['metrics']
    lines.append(f'| {version} | {percent(metrics["availability"])} | {percent(metrics["sameDeviceLinkYield"])} |')
synthetic = json.loads((root / 'synthetic.json').read_text())
lines += ['', f'Synthetic evaluation: {synthetic["policyObservations"]} policy-visits across {synthetic["cohorts"]} replayed cohorts. These are finite-class simulations, not independently measured physical devices.', '', 'Full evidence is retained in the workflow artifact.']
text = '\n'.join(lines) + '\n'
if os.environ.get('GITHUB_STEP_SUMMARY'):
    with Path(os.environ['GITHUB_STEP_SUMMARY']).open('a') as stream:
        stream.write(text)
    aggregate = []
    for browser in report['browsers']:
        if browser['status'] != 'PASS':
            aggregate.append(dict(browser=browser['name'], status=browser['status']))
            continue
        for version, data in browser['versions'].items():
            values = data['all']; code = values['continuityCode']
            aggregate.append(dict(browser=browser['name'], build=browser['version'], sdk=version,
                                  digest=values['digest']['conditionalRepeatability'],
                                  codeAvailability=code['availability'] if code else None,
                                  codeStability=code['conditionalRepeatability'] if code else None,
                                  collectP95Ms=values['collect']['p95Ms']))
    print('::notice title=Intensive SDK aggregate::' + json.dumps(dict(pairedObservations=report['totalPairedObservations'],
          physicalHosts=1, uniqueness=None, browsers=aggregate, matchReplay=report['matchReplay']), separators=(',', ':')))
else:
    print(text)
