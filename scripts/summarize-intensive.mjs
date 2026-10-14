// Merge successful paired runs from one host; retain every failed attempt.
import {readFile,writeFile} from 'node:fs/promises';
import {labeledMetrics,rate} from './evidence-metrics.mjs';
const old=await import(new URL('../artifacts/intensive-v04/vendor/0.3.0/dist/index.js',import.meta.url));
const current=await import(new URL('../artifacts/intensive-v04/vendor/0.4.0/dist/index.js',import.meta.url));
const inputs=process.argv.slice(2);
if(!inputs.length)throw Error('Provide evidence directories from the same physical host');
const browsers=new Map(),samples=new Map(),failures=[];
for(const path of inputs){
  const report=JSON.parse(await readFile(path+'/browsers.json','utf8'));
  const records=(await readFile(path+'/observations.jsonl','utf8')).trim().split('\n').filter(Boolean).map(s=>JSON.parse(s));
  for(const browser of report.browsers){
    if(browser.status!=='PASS'){failures.push({input:path,...browser});continue;}
    if(browsers.has(browser.name))throw Error('Duplicate successful browser: '+browser.name);
    browsers.set(browser.name,browser);samples.set(browser.name,records.filter(r=>r.browser===browser.name));
  }
}
const rows=[...samples.values()].flat(),versions={};
const choose=n=>n*(n-1)/2;
for(const [version,match] of [['0.3.0',old.matchDetailed],['0.4.0',current.matchResilient]]){
  const pool=[],replay=[];
  for(const row of rows){
    const snapshot=row[version].snapshot,decision=match(snapshot,pool);let visitor=decision.candidateId;
    if(decision.status==='unmatched'){visitor='anchor-'+pool.length;pool.push({id:visitor,snapshot});}
    replay.push({device:'host',browser:row.browser,visitor,code:row[version].code});
  }
  const metrics=labeledMetrics(replay,'visitor');metrics.exclusiveStableDevices=rate(0,0);
  const perBrowser=Object.fromEntries([...browsers.keys()].map(name=>{
    const m=labeledMetrics(replay.filter(r=>r.browser===name),'visitor');m.exclusiveStableDevices=rate(0,0);return[name,m];
  }));
  const count=(field,predicate)=>{
    const total=new Map(),byBrowser=new Map();
    for(const r of replay.filter(predicate)){
      const key=field?r[field]:'all',cell=JSON.stringify([key,r.browser]);
      total.set(key,(total.get(key)||0)+1);byBrowser.set(cell,(byBrowser.get(cell)||0)+1);
    }
    return [...total.values()].reduce((s,n)=>s+choose(n),0)-[...byBrowser.values()].reduce((s,n)=>s+choose(n),0);
  };
  const all=count(null,()=>true),covered=count(null,r=>r.visitor!==null),linked=count('visitor',r=>r.visitor!==null);
  versions[version]={visitorReplay:metrics,perBrowser,anchors:pool.length,
    crossBrowserStability:rate(linked,all),conditionalCrossBrowserStability:rate(linked,covered),
    crossBrowserPairCoverage:rate(covered,all),
    continuityCode:version==='0.4.0'?{...labeledMetrics(replay,'code'),exclusiveStableDevices:rate(0,0)}:null};
}
const report={source:'one-host-paired-empirical',physicalHosts:1,totalPairedObservations:rows.length,
  datasetOrder:[...browsers.keys()],failedAttempts:failures,uniqueness:null,browsers:[...browsers.values()],versions,
  note:'Matching replay uses the exact public SDKs, not HTTP/Mongo. Replay order is explicit; null assignments and failed runs are retained in their proper denominators. Incognito context and fresh profile repetitions do not become separate devices.'};
await writeFile('artifacts/intensive-v04/combined-macos.json',JSON.stringify(report,null,2));
console.log(JSON.stringify({totalPairedObservations:rows.length,versions}));
