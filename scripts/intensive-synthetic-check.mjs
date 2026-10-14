// Shared finite latent classes, three visits, fixed seeds, unmodified public SDKs.
import {mkdir,writeFile} from 'node:fs/promises';
import {labeledMetrics} from './evidence-metrics.mjs';
const old=await import(new URL('../artifacts/intensive-v04/vendor/0.3.0/dist/index.js',import.meta.url));
const current=await import(new URL('../artifacts/intensive-v04/vendor/0.4.0/dist/index.js',import.meta.url));
const seeds=[728193,913571,481927],populations=['diverse','office','clones'];
const scenarios=['repeat','wrapper-cross-engine','private-no-state','gpu-missing-return','sparse-first','fonts-change','browser-update-same-engine','mixed-engines'];
const platforms=['macos','windows','linux'];
const models={macos:['Apple M1','Apple M1 Pro','Apple M2','Apple M2 Pro','Apple M3','Apple M3 Pro','Apple M3 Max','Apple M4'],
  windows:['NVIDIA GeForce RTX 3060','NVIDIA GeForce RTX 3070','NVIDIA GeForce RTX 3080','NVIDIA GeForce RTX 4090','AMD Radeon RX 6600','AMD Radeon RX 7900 XT','Intel UHD Graphics 630','Intel Arc A770']};
models.linux=models.windows;
const ua={blink:'AppleWebKit/537.36 Chrome/145.0',gecko:'Gecko/20100101 Firefox/140.0',webkit:'AppleWebKit/605.1.15 Version/26.0 Safari/605.1.15'};
function random(seed){let s=seed>>>0;return()=>{s=(Math.imul(s,1664525)+1013904223)>>>0;return s/4294967296;};}
function shuffled(input,seed){const rows=[...input],rng=random(seed);for(let i=rows.length-1;i>0;i--){const j=Math.floor(rng()*(i+1));[rows[i],rows[j]]=[rows[j],rows[i]];}return rows;}
function generate(kind,seed){
  const rng=random(seed),pick=n=>Math.floor(rng()*n);
  return Array.from({length:64},(_,i)=>{
    const platform=kind==='diverse'?platforms[pick(3)]:'windows';
    return {device:'device-'+i,platform,cores:kind==='diverse'?[2,4,8,16,32][pick(5)]:8,
      gpu:kind==='clones'?0:pick(kind==='diverse'?8:3),font:kind==='clones'?0:pick(kind==='diverse'?16:3),
      renderer:kind==='clones'?0:pick(kind==='diverse'?6:3)};
  });
}
async function observations(device,scenario,visit){
  let engine=scenario==='mixed-engines'?['blink','gecko','webkit'][Number(device.device.slice(7))%3]:'blink';
  const drift=scenario==='wrapper-cross-engine'&&visit>0;
  if(drift) engine=visit===1?'webkit':'gecko';
  const model=models[device.platform][device.gpu];
  let gpu=drift?`ANGLE (Vendor, ${model}, Unspecified Version)`:model;
  if(scenario==='gpu-missing-return'&&visit>0||scenario==='sparse-first'&&visit===0)gpu=null;
  const fonts=(device.font+128).toString(2)+(scenario==='fonts-change'&&visit>0?'1':'');
  const canvas=JSON.stringify([device.gpu%3,device.font%2,device.renderer,engine,scenario==='browser-update-same-engine'&&visit>0?'changed':'base']);
  const environment={userAgent:ua[engine],platform:device.platform==='macos'?'MacIntel':device.platform==='windows'?'Win32':'Linux x86_64',
    hardwareConcurrency:device.cores,deviceMemory:8,language:drift?'it-IT':'en-US',timezone:drift?'Europe/Rome':'UTC'};
  const options={scope:'intensive-synthetic',environment,probes:{gpu:()=>gpu,fonts:()=>fonts,canvas:()=>canvas}};
  return {'0.3.0':await old.collectDetailed(options),'0.4.0':await current.collectResilient(options)};
}
const reports=[];
for(const seed of seeds)for(const population of populations)for(const scenario of scenarios){
  const devices=generate(population,seed),visits=[];
  for(let visit=0;visit<3;visit++) for(const device of devices)visits.push({device:device.device,visit,snapshots:await observations(device,scenario,visit)});
  for(let order=0;order<3;order++){
    const sequence=[];
    for(let visit=0;visit<3;visit++)sequence.push(...shuffled(visits.filter(v=>v.visit===visit),seed+order*1777+visit*97));
    const result={seed,population,scenario,arrivalOrder:order,versions:{}};
    for(const [version,api,match] of [['0.3.0',old,old.matchDetailed],['0.4.0',current,current.matchResilient]]){
      const pool=[],rows=[];
      for(const row of sequence){
        const snapshot=row.snapshots[version],decision=match(snapshot,pool);let visitor=decision.candidateId;
        if(decision.status==='unmatched'){visitor='anchor-'+pool.length;pool.push({id:visitor,snapshot});}
        rows.push({device:row.device,visitor,code:version==='0.4.0'?await current.continuityCode(snapshot):null});
      }
      result.versions[version]={visitor:labeledMetrics(rows,'visitor'),continuityCode:version==='0.4.0'?labeledMetrics(rows,'code'):null,anchors:pool.length};
    }
    reports.push(result);
  }
}
function aggregate(rows,key){
  const sum=name=>rows.reduce((n,r)=>n+r[name],0);
  const pairs=rows.map(r=>r[key]),numerator=pairs.reduce((n,r)=>n+r.numerator,0),denominator=pairs.reduce((n,r)=>n+r.denominator,0);
  return {numerator,denominator,percent:denominator?100*numerator/denominator:null,
    cohortRange:[Math.min(...pairs.map(r=>r.percent).filter(v=>v!==null)),Math.max(...pairs.map(r=>r.percent).filter(v=>v!==null))]};
}
const summary=[];
for(const population of populations)for(const scenario of scenarios){
  const subset=reports.filter(r=>r.population===population&&r.scenario===scenario),row={population,scenario,versions:{}};
  for(const version of ['0.3.0','0.4.0']){
    const data=subset.map(r=>r.versions[version].visitor);
    row.versions[version]=Object.fromEntries(['availability','sameDeviceLinkYield','conditionalSameDeviceStability','linkPrecision','falseLinkRate','endToEndFalseLinkRate','exclusiveStableDevices'].map(k=>[k,aggregate(data,k)]));
    row.versions[version].falseLinks=data.reduce((n,r)=>n+r.falseLinks,0);
  }
  summary.push(row);
}
const report={source:'synthetic-finite-class-regression',physicalDeviceAccuracy:null,
  seeds,devicesPerCohort:64,visitsPerDevice:3,arrivalOrders:3,cohorts:reports.length,policyObservations:reports.length*64*3*2,
  note:'Shared finite GPU/font/rendering groups; labels never enter probes. Same designed font bits for both collectors, not measured entropy of their real font panels. Incognito/no-state is a no-op adapter control; real private contexts are tested separately. No inference of population uniqueness.',
  summary,cohortResults:reports};
await mkdir('artifacts/intensive-v04',{recursive:true});
await writeFile('artifacts/intensive-v04/synthetic.json',JSON.stringify(report,null,2));
console.log(JSON.stringify({cohorts:report.cohorts,policyObservations:report.policyObservations,summary}));
