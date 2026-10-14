import {test} from 'node:test';
import assert from 'node:assert/strict';
import {collectResilient, collectDetailed, continuityCode, digestResilient, normalizeGPU, compareResilient, matchResilient, validateResilientSnapshot, parseResilientSnapshot, compareDetailed} from '../dist/index.js';

const environment = {userAgent:'AppleWebKit/537.36 Chrome/145.0', platform:'MacIntel', hardwareConcurrency:8, deviceMemory:8, language:'en-US', timezone:'UTC'};
const sample = () => ({schema:'singularity/v3', probe:'web/v2', engine:'blink', scope:'test', signals:{platform:'macos',cores:8,memory:8,language:'en',timezone:'UTC'},detail:{gpu:'a'.repeat(64),fonts:'b'.repeat(64),canvas:'c'.repeat(64)}});
const candidate = (id, snapshot=sample()) => ({id,snapshot});
test('recognized GPU wrappers normalize without merging distinct model suffixes', () => {
  for (const [wrapper, plain] of [
    ['ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)', 'Apple M3 Pro'],
    ['ANGLE Metal Renderer: Apple M3 Pro', 'Apple M3 Pro'],
    ['NVIDIA GeForce RTX3060', 'NVIDIA GeForce RTX 3060'],
    ['AMD Radeon RX6600', 'AMD Radeon RX 6600'],
    ['Intel Arc A770', 'Intel Arc A770 Graphics'],
    ['ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 (0x00002504) Direct3D11 vs_5_0 ps_5_0, D3D11)', 'GeForce RTX 3060/PCIe/SSE2'],
    ['ANGLE (Intel, Intel(R) UHD Graphics 630 (0x00003E92) Direct3D11 vs_5_0 ps_5_0, D3D11)', 'Intel UHD Graphics 630'],
    ['ANGLE (AMD, AMD Radeon Pro 5500M, OpenGL 4.1)', 'AMD Radeon Pro 5500M OpenGL Engine'],
  ]) {
    assert.ok(normalizeGPU(wrapper)); assert.equal(normalizeGPU(wrapper), normalizeGPU(plain));
  }
  const distinct = ['Apple M3','Apple M3 Pro','Apple M3 Max','NVIDIA GeForce RTX 3060','NVIDIA GeForce RTX 3060 Ti','NVIDIA GeForce RTX 3060 Laptop GPU','AMD Radeon RX 7900 XT','AMD Radeon RX 7900 XTX'];
  assert.equal(new Set(distinct.map(normalizeGPU)).size, distinct.length);
  for (const value of [null, 'Apple GPU','ANGLE','Intel Iris Xe Graphics','SwiftShader','Mesa Unknown','VMware NVIDIA GeForce RTX 3060','NVIDIA GeForce RTX 3060 unrecognized suffix', 'a'.repeat(513)]) assert.equal(normalizeGPU(value), null);
});
test('continuity code regenerates across wrapper, canvas and incidental drift without storage', async () => {
  const options = {scope:'test',environment,probes:{gpu:()=>'Apple M3 Pro',fonts:()=>'101001',canvas:()=>'engine-a'}};
  const a = await collectResilient(options);
  const b = await collectResilient({...options,environment:{...environment,userAgent:'AppleWebKit/605.1.15 Version/26.0 Safari/605.1.15',language:'it',timezone:'Europe/Rome',deviceMemory:undefined},probes:{...options.probes,gpu:()=>'ANGLE (Apple, ANGLE Metal Renderer: Apple M3 Pro, Unspecified Version)',canvas:()=>'engine-b'}});
  assert.equal(await continuityCode(a), await continuityCode(b));
  assert.match(await continuityCode(a), /^sc1_[a-f0-9]{64}$/);
  assert.notEqual(await digestResilient(a), await digestResilient(b));
  assert.equal(matchResilient(b, [candidate('known',a)]).candidateId, 'known');
  assert.deepEqual(compareResilient(a,b).differences, ['canvas']);
  assert.ok(!JSON.stringify(a).includes('Apple'));
  const oldA=await collectDetailed(options), oldB=await collectDetailed({...options,probes:{...options.probes,canvas:()=>'engine-b'}});
  assert.equal(compareDetailed(oldA,oldB).qualifies, false);
});
test('code projection is fixed, scoped and fails closed on missing structural evidence', async () => {
  const a=sample(), code=await continuityCode(a);
  for(const field of ['gpu','fonts']) {
    const b=sample(); b.detail[field]=null; assert.equal(await continuityCode(b), null);
    b.detail[field]='d'.repeat(64); assert.notEqual(await continuityCode(b), code);
  }
  for(const field of ['platform','cores']) { const b=sample(); b.signals[field]=null; assert.equal(await continuityCode(b),null); }
  assert.notEqual(await continuityCode({...a,scope:'other'}),code);
  assert.equal(await continuityCode({...a,detail:{...a.detail,canvas:null}}),code);
});
test('font family is required; missing evidence, clones and sparse contenders do not become confidence', () => {
  for(let mask=0;mask<8;mask++) {
    const s=sample(); ['gpu','fonts','canvas'].forEach((k,i)=>{if(mask&(1<<i))s.detail[k]=null;});
    assert.equal(compareResilient(s,s).qualifies, s.detail.fonts!==null && (s.detail.gpu!==null||s.detail.canvas!==null));
  }
  const masked=sample();masked.detail.gpu=null;
  const otherEngine=structuredClone(masked);otherEngine.engine='webkit';otherEngine.detail.canvas='d'.repeat(64);
  assert.equal(matchResilient(otherEngine,[candidate('old',masked)]).reason,'insufficient-candidate-evidence');
  const sparse=sample();sparse.detail.fonts=null;
  assert.equal(matchResilient(sample(),[candidate('known'),candidate('sparse',sparse)]).status,'abstain');
  assert.equal(matchResilient(sample(),[candidate('a'),candidate('b')]).reason,'ambiguous-candidates');
  // This is a collision control, not a synthetic uniqueness success.
  const sameModelFonts=sample();sameModelFonts.detail.canvas='d'.repeat(64);
  assert.equal(compareResilient(sample(),sameModelFonts).qualifies,false);
  sameModelFonts.engine='webkit';
  assert.equal(compareResilient(sample(),sameModelFonts).qualifies,true);
  sameModelFonts.engine=null;
  assert.equal(compareResilient(sample(),sameModelFonts).qualifies,false);
  for(const [section,key,value] of [['detail','gpu','d'.repeat(64)],['detail','fonts','d'.repeat(64)],['signals','cores',4],['signals','platform','windows']]) {
    const rival=sample();rival[section][key]=value;assert.equal(compareResilient(sample(),rival).qualifies,false);
  }
});
test('v3 strict validation, full candidate validation and noisy probes', async () => {
  const s=sample();assert.deepEqual(parseResilientSnapshot(JSON.stringify(s)),s);
  for(const bad of [{...s,schema:'singularity/v2'},{...s,probe:'web/v1'},{...s,extra:1},{...s,detail:{...s.detail,gpu:'raw'}}]) assert.throws(()=>validateResilientSnapshot(bad));
  assert.throws(()=>matchResilient(s,Array(257)),{code:'LIMIT_EXCEEDED'});
  assert.throws(()=>matchResilient(s,[candidate('a'),candidate('a')]),{code:'DUPLICATE_ID'});
  assert.throws(()=>matchResilient(s,[candidate('a'),candidate('b',{...s,scope:'other'})]),{code:'SCOPE_MISMATCH'});
  let n=0;
  const noisy=await collectResilient({scope:'test',environment,probes:{gpu:()=>n++?'Apple M3 Max':'Apple M3 Pro',fonts:()=>{throw Error('blocked');},canvas:()=>'x'.repeat(76801)}});
  assert.deepEqual(noisy.detail,{gpu:null,fonts:null,canvas:null});
  assert.equal(await continuityCode(noisy),null);
  assert.deepEqual((await collectResilient({scope:'test',environment})).detail,noisy.detail);
});
