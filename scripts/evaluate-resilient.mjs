// Paired deterministic regression fixtures, NOT a sample of independent real PCs.
import {collectDetailed,collectResilient,continuityCode,matchDetailed,matchResilient} from '../dist/index.js';
import {mkdir,writeFile} from 'node:fs/promises';
import assert from 'node:assert/strict';
const environment={userAgent:'AppleWebKit/537.36 Chrome/145.0',platform:'MacIntel',hardwareConcurrency:8,deviceMemory:8,language:'en-US',timezone:'UTC'};
const models=['Apple M1','Apple M1 Pro','Apple M1 Max','Apple M2','Apple M2 Pro','Apple M2 Max','Apple M3','Apple M3 Pro'];
const cases=['unchanged','wrapper-canvas-locale-drift','gpu-missing-return','shared-model-fonts-distinct-canvas','shared-model-fonts-mixed-engines','identical-profiles','font-change'];
const outcomes=[];
function metrics(rows,key) {
  let positives=0,trueLinks=0,falseLinks=0,negatives=0;
  for(let i=0;i<rows.length;i++) for(let j=i+1;j<rows.length;j++) {
    const same=rows[i].device===rows[j].device, linked=rows[i][key]!==null&&rows[i][key]===rows[j][key];
    if(same) positives++;else negatives++;
    if(linked) {if(same) trueLinks++;else falseLinks++;}
  }
  const labels=[...new Set(rows.map(r=>r.device))];
  let exclusive=0;
  for(const label of labels) {
    const own=rows.filter(r=>r.device===label), ids=new Set(own.map(r=>r[key]));
    if(!ids.has(null)&&ids.size===1&&!rows.some(r=>r.device!==label&&ids.has(r[key]))) exclusive++;
  }
  return {visits:rows.length,devices:labels.length,assigned:rows.filter(r=>r[key]!==null).length,
    sameDevicePairs:positives,differentDevicePairs:negatives,trueLinks,falseLinks,
    linkYield:positives?trueLinks/positives:null,exclusiveStableDevices:exclusive,
    exclusiveStableDeviceRate:exclusive/labels.length};
}
for(const scenario of cases) for(const reverse of [false,true]) {
  const pools={v2:[],v3:[]},rows={v2:[],v3:[]};
  const order=Array.from({length:64},(_,i)=>i);if(reverse)order.reverse();
  for(let visit=0;visit<2;visit++) for(const device of order) {
    const identical=scenario==='identical-profiles', mixed=scenario==='shared-model-fonts-mixed-engines';
    const shared=scenario==='shared-model-fonts-distinct-canvas'||mixed;
    const model=models[identical||shared?0:device%8];
    const font=identical||shared?'101010':(Math.floor(device/8)+128).toString(2);
    const drift=visit===1&&scenario==='wrapper-canvas-locale-drift';
    const gpu=visit===1&&scenario==='gpu-missing-return'?null:drift?`ANGLE (Apple, ANGLE Metal Renderer: ${model}, Unspecified Version)`:model;
    const canvas=identical?'same-pixels':shared?`rendering-variant-${device}`:drift?'engine-b':'engine-a';
    const probes={gpu:()=>gpu,fonts:()=>visit===1&&scenario==='font-change'?font+'1':font,canvas:()=>canvas};
    const env=drift?{...environment,userAgent:'AppleWebKit/605.1.15 Version/26.0 Safari/605.1.15',language:'it-IT',timezone:'Europe/Rome',deviceMemory:undefined}:mixed&&device%2?{...environment,userAgent:'AppleWebKit/605.1.15 Version/26.0 Safari/605.1.15'}:environment;
    for(const [mode,collect,match] of [['v2',collectDetailed,matchDetailed],['v3',collectResilient,matchResilient]]) {
      const snapshot=await collect({scope:'paired-regression',environment:env,probes});
      const result=match(snapshot,pools[mode]);let id=result.candidateId;
      if(result.status==='unmatched') {id='anchor-'+pools[mode].length;pools[mode].push({id,snapshot});}
      rows[mode].push({device,visitor:id,code:mode==='v3'?await continuityCode(snapshot):null});
    }
  }
  const v2=metrics(rows.v2,'visitor'),v3=metrics(rows.v3,'visitor');
  outcomes.push({scenario,order:reverse?'reverse':'forward',v2,v3,continuityCode:metrics(rows.v3,'code')});
  if(scenario==='wrapper-canvas-locale-drift') {assert.equal(v2.trueLinks,0);assert.equal(v3.trueLinks,64);assert.equal(v3.falseLinks,0);}
  if(scenario==='unchanged') assert.deepEqual(v3,v2);
  if(scenario==='shared-model-fonts-distinct-canvas') {assert.equal(v2.falseLinks,0);assert.equal(v3.falseLinks,0);}
  // Deliberate counterexample: tolerating cross-engine rendering can merge
  // different devices with identical model/fonts before later rivals appear.
  if(scenario==='shared-model-fonts-mixed-engines') {assert.equal(v2.falseLinks,0);assert.ok(v3.falseLinks>0);}
  if(scenario==='identical-profiles') {assert.equal(v2.exclusiveStableDevices,0);assert.equal(v3.exclusiveStableDevices,0);}
}
const report={source:'synthetic-adapter-regression',note:'Designed model/font groups, not measured population entropy. Continuity codes lose canvas-only distinctions; visitor matching preserves them in a known same-engine context.',outcomes};
await mkdir('artifacts/improvement-v04',{recursive:true});
await writeFile('artifacts/improvement-v04/paired.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(outcomes.filter(r=>r.order==='forward').map(({scenario,v2,v3,continuityCode:c})=>({scenario,v2:v2.linkYield,v3:v3.linkYield,falseLinksV2:v2.falseLinks,falseLinksV3:v3.falseLinks,exclusiveV3:v3.exclusiveStableDeviceRate,availableCodes:c.assigned})),null,2));
