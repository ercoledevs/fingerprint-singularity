// Diagnostic percentages retain exact denominators; unavailable IDs are not links.
export function rate(numerator, denominator) {
  return {numerator, denominator, percent: denominator ? 100 * numerator / denominator : null};
}
export function repeatability(values, baseline) {
  const available = values.filter(v => v !== null);
  const same = baseline === null ? 0 : available.filter(v => v === baseline).length;
  return {availability:rate(available.length, values.length),
    conditionalRepeatability:rate(same, baseline === null ? 0 : available.length),
    endToEndContinuity:rate(same, values.length),
    distinctAvailableValues:new Set(available).size};
}
export function labeledMetrics(rows, field) {
  const devices = new Map(), predictions = new Map(), cells = new Map(), coveredDevices = new Map();
  let available = 0;
  for (const row of rows) {
    devices.set(row.device, (devices.get(row.device) || 0) + 1);
    const id = row[field];
    if (id === null) continue;
    available++;
    coveredDevices.set(row.device, (coveredDevices.get(row.device) || 0) + 1);
    predictions.set(id, (predictions.get(id) || 0) + 1);
    const key = JSON.stringify([row.device, id]);
    cells.set(key, (cells.get(key) || 0) + 1);
  }
  const choose = n => n * (n - 1) / 2;
  const pairs = counter => [...counter.values()].reduce((s, n) => s + choose(n), 0);
  const positive = pairs(devices), trueLinks = pairs(cells), falseLinks = pairs(predictions) - trueLinks;
  const coveredPositive = pairs(coveredDevices), negative = choose(rows.length) - positive;
  const coveredNegative = choose(available) - coveredPositive;
  let exclusive = 0;
  const owners = new Map();
  for (const row of rows) if (row[field] !== null) {
    if (!owners.has(row[field])) owners.set(row[field], new Set());
    owners.get(row[field]).add(row.device);
  }
  for (const device of devices.keys()) {
    const ids = new Set(rows.filter(r => r.device === device).map(r => r[field]));
    if (devices.get(device) > 1 && ids.size === 1 && !ids.has(null) && owners.get([...ids][0]).size === 1) exclusive++;
  }
  return {observations:rows.length, devices:devices.size, availability:rate(available, rows.length),
    sameDeviceLinkYield:rate(trueLinks, positive), linkPrecision:rate(trueLinks, trueLinks + falseLinks),
    conditionalSameDeviceStability:rate(trueLinks, coveredPositive),
    pairCoverage:rate(choose(available), choose(rows.length)),
    falseLinkRate:rate(falseLinks, coveredNegative),
    endToEndFalseLinkRate:rate(falseLinks, negative),
    falseLinks, differentDevicePairs:negative, coveredDifferentDevicePairs:coveredNegative,
    exclusiveStableDevices:rate(exclusive, devices.size)};
}
