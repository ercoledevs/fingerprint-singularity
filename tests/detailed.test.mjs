import { test } from 'node:test';
import assert from 'node:assert/strict';
import { collectDetailed, digestDetailed, canonicalizeDetailed, validateDetailedSnapshot, parseDetailedSnapshot, compareDetailed, matchDetailed } from '../dist/index.js';
const environment={platform:'MacIntel',hardwareConcurrency:8,deviceMemory:8,language:'en-US',timezone:'UTC'};
const sample=()=>({schema:'singularity/v2',scope:'test',probe:'web/v1',signals:{platform:'macos',cores:8,memory:8,language:'en',timezone:'UTC'},detail:{gpu:'a'.repeat(64),fonts:'b'.repeat(64),canvas:'c'.repeat(64)}});
const candidate=(id,s=sample())=>({id,snapshot:s});
const err=code=>e=>e.code===code;
test('detail collection hashes stable probes by scope; exceptions, noise and oversized data are null',async()=>{
 let n=0;const calls={gpu:0,fonts:0,canvas:0};
 const probes={gpu:()=>{calls.gpu++;return 'GPU model';},fonts:()=>{calls.fonts++;return '10101';},canvas:()=>{calls.canvas++;return 'pixels';}};
 const s=await collectDetailed({scope:'test',environment,probes});
 assert.deepEqual(calls,{gpu:2,fonts:2,canvas:2});
 assert.ok(Object.values(s.detail).every(x=>/^[a-f0-9]{64}$/.test(x)));
 assert.ok(!JSON.stringify(s).includes('GPU model'));
 const other=await collectDetailed({scope:'other',environment,probes});assert.notEqual(s.detail.gpu,other.detail.gpu);
 const blocked=await collectDetailed({scope:'test',environment,probes:{gpu:()=>{throw Error('blocked');},fonts:()=>String(n++),canvas:()=> 'x'.repeat(76801)}});
 assert.deepEqual(blocked.detail,{gpu:null,fonts:null,canvas:null});assert.equal(matchDetailed(blocked,[]).reason,'insufficient-detail');
 assert.deepEqual((await collectDetailed({scope:'test',environment})).detail,blocked.detail);
});
test('v2 canonical data includes immutable probe revision and round-trips',async()=>{
 const s=sample();assert.deepEqual(parseDetailedSnapshot(JSON.stringify(s)),s);
 assert.match(await digestDetailed(s),/^sg2_[a-f0-9]{64}$/);assert.ok(canonicalizeDetailed(s).includes('web/v1'));
 const changed=sample();changed.detail.canvas='d'.repeat(64);assert.notEqual(await digestDetailed(changed),await digestDetailed(s));
});
test('strict detailed agreement separates nearby coarse profiles and retains locale/memory drift',()=>{
 const s=sample(),rival=sample();rival.detail.gpu='d'.repeat(64);
 assert.equal(matchDetailed(s,[candidate('other',rival)]).status,'unmatched');
 const drift=sample();drift.signals.memory=null;drift.signals.language='it';drift.signals.timezone='Europe/Rome';
 assert.equal(matchDetailed(drift,[candidate('known')]).candidateId,'known');
 const rendererChange=sample();rendererChange.detail.canvas='e'.repeat(64);
 assert.equal(matchDetailed(rendererChange,[candidate('known')]).status,'unmatched');
});
test('two details suffice; one or contradictory detail does not; missing rivals still block',()=>{
 const two=sample();two.detail.canvas=null;assert.equal(matchDetailed(two,[candidate('a')]).candidateId,'a');
 const one=sample();one.detail.canvas=null;one.detail.fonts=null;
 assert.equal(matchDetailed(one,[candidate('a')]).reason,'insufficient-detail');
 assert.equal(matchDetailed(sample(),[candidate('a'),candidate('b',one)]).reason,'insufficient-candidate-evidence');
 const conflict=sample();conflict.detail.canvas='d'.repeat(64);assert.equal(compareDetailed(sample(),conflict).qualifies,false);
});
test('duplicates abstain; known structural conflicts stay excluded; result is permutation invariant',()=>{
 assert.equal(matchDetailed(sample(),[candidate('a'),candidate('b')]).reason,'ambiguous-candidates');
 const other=sample();other.signals.platform='windows';
 const list=[candidate('a'),candidate('b',other)];
 assert.equal(matchDetailed(sample(),list).candidateId,'a');
 assert.deepEqual({...matchDetailed(sample(),list),candidates:[]},{...matchDetailed(sample(),list.reverse()),candidates:[]});
});
test('all detail availability masks enforce a two-signal floor',()=>{
 for(let mask=0;mask<8;mask++){
  const s=sample();['gpu','fonts','canvas'].forEach((k,i)=>{if(mask&(1<<i))s.detail[k]=null;});
  const count=Object.values(s.detail).filter(x=>x!==null).length;
  assert.equal(compareDetailed(s,s).qualifies,count>=2);
 }
});
test('full-evidence clones remain indistinguishable without a possession token',()=>{
 assert.equal(matchDetailed(sample(),[candidate('other-physical-device')]).status,'matched');
 assert.equal(matchDetailed(sample(),[candidate('device-a'),candidate('device-b')]).status,'abstain');
});
test('strict v2 transport validation, schema isolation and complete candidate checking',()=>{
 const s=sample();
 for(const bad of [{...s,extra:1},{...s,probe:'web/v2'},{...s,detail:{...s.detail,gpu:'raw-gpu'}},{...s,detail:{...s.detail,extra:1}}])assert.throws(()=>validateDetailedSnapshot(bad));
 assert.throws(()=>parseDetailedSnapshot(' '.repeat(4097)),err('LIMIT_EXCEEDED'));
 assert.throws(()=>matchDetailed(s,[candidate('a'),candidate('a')]),err('DUPLICATE_ID'));
 assert.throws(()=>matchDetailed(s,Array(2)),err('INVALID_INPUT'));
 assert.throws(()=>matchDetailed(s,Array(257)),err('LIMIT_EXCEEDED'));
 const list=[candidate('a'),candidate('b')];list[Symbol.iterator]=function*(){yield this[0];};assert.equal(matchDetailed(s,list).status,'abstain');
 const mixed={schema:'singularity/v1',scope:s.scope,signals:s.signals};assert.throws(()=>matchDetailed(s,[candidate('old',mixed)]));
 assert.throws(()=>matchDetailed(s,[candidate('other',{...s,scope:'elsewhere'})]),err('SCOPE_MISMATCH'));
 Object.defineProperty(s.detail,'gpu',{get(){throw Error('Getter must not execute');}});assert.throws(()=>validateDetailedSnapshot(s),err('INVALID_INPUT'));
});
