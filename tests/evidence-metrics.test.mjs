import {test} from 'node:test';
import assert from 'node:assert/strict';
import {repeatability, labeledMetrics} from '../scripts/evidence-metrics.mjs';

test('missing codes cannot produce perfect repeatability', () => {
  const result=repeatability([null,null],null);
  assert.equal(result.availability.percent,0);
  assert.equal(result.conditionalRepeatability.percent,null);
  assert.equal(result.endToEndContinuity.percent,0);
  assert.equal(repeatability(['x',null,'x'],'x').endToEndContinuity.percent,200/3);
});
test('cloned devices and abstention are separate from stable identity', () => {
  const rows=[{device:'a',id:'x'},{device:'a',id:'x'},{device:'b',id:'x'},{device:'b',id:'x'}];
  const result=labeledMetrics(rows,'id');
  assert.equal(result.sameDeviceLinkYield.percent,100);
  assert.equal(result.falseLinks,4);
  assert.equal(result.exclusiveStableDevices.percent,0);
  assert.equal(result.linkPrecision.percent,100/3);
  const missing=labeledMetrics(rows.map(r=>({...r,id:null})),'id');
  assert.equal(missing.availability.percent,0);
  assert.equal(missing.linkPrecision.percent,null);
});
