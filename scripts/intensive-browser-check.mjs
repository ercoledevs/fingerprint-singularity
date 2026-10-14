// Exact published SDKs; persistent profiles and incognito contexts are distinct.
import {chromium,firefox,webkit} from 'playwright';
import {createServer} from 'node:http';
import {readFile,mkdir,mkdtemp,rm,writeFile} from 'node:fs/promises';
import {resolve,sep} from 'node:path';
import {tmpdir} from 'node:os';
import {performance} from 'node:perf_hooks';
import {repeatability,labeledMetrics,rate} from './evidence-metrics.mjs';

const out=resolve(process.env.INTENSIVE_OUT||'artifacts/intensive-v04');
const vendor=resolve('artifacts/intensive-v04/vendor');
const old=await import(new URL('../artifacts/intensive-v04/vendor/0.3.0/dist/index.js',import.meta.url));
const current=await import(new URL('../artifacts/intensive-v04/vendor/0.4.0/dist/index.js',import.meta.url));
const samples=Number(process.env.INTENSIVE_SAMPLES||250);
if(!Number.isInteger(samples)||samples<20||samples>1000||samples%10) throw Error('Samples must be 20–1000 and divisible by ten');
const selected=(process.env.BROWSERS||'chromium,firefox,webkit').split(',');
const engines={chromium:{engine:chromium},firefox:{engine:firefox},webkit:{engine:webkit},chrome:{engine:chromium,channel:'chrome'}};
const report={schema:'singularity-intensive-browser/v1',source:'one-host-empirical',
  environment:{platform:process.platform,arch:process.arch,node:process.version},
  sdks:JSON.parse(await readFile('artifacts/intensive-v04/sdk-provenance.json','utf8')),
  physicalHosts:1,samplesPerArm:samples,browsers:[],crossBrowser:[],uniqueness:null,
  limitations:['One host cannot measure cross-device uniqueness.','Incognito uses Playwright nonpersistent contexts, not branded privacy UI.',
    'Firefox/WebKit in-place HTTP cache eviction is not claimed; fresh persistent profiles provide empty caches.',
    'Viewport changes are not a physical display replacement. No longitudinal OS/browser upgrades.']};
let hits=0;
const server=createServer(async(req,res)=>{
  try {
    const path=new URL(req.url,'http://localhost').pathname;
    if(path==='/') {res.writeHead(200,{'Content-Type':'text/html','Cache-Control':'no-store'}).end('<!doctype html><html><body>SDK test</body></html>');return;}
    if(path==='/cache-probe') {res.writeHead(200,{'Content-Type':'application/json','Cache-Control':'public,max-age=3600'}).end(JSON.stringify({hit:++hits}));return;}
    const match=/^\/(0\.3\.0|0\.4\.0)\/dist\/([a-z-]+\.js)$/.exec(path);
    if(!match) {res.writeHead(404).end();return;}
    const file=resolve(vendor,match[1],'dist',match[2]);
    if(!file.startsWith(vendor+sep)) throw Error('Invalid path');
    res.writeHead(200,{'Content-Type':'text/javascript','Cache-Control':'public,max-age=3600'}).end(await readFile(file));
  } catch {res.writeHead(404).end();}
});
await new Promise(yes=>server.listen(0,'127.0.0.1',yes));
const url=`http://127.0.0.1:${server.address().port}`;
const raw=[];
function quantiles(values) {
  const a=[...values].sort((x,y)=>x-y);
  return {count:a.length,p50Ms:a[Math.floor(a.length*.5)]??null,p95Ms:a[Math.floor(a.length*.95)]??null,p99Ms:a[Math.floor(a.length*.99)]??null};
}
async function preparePage(context) {
  const external=[], errors=[];
  context.on('request',r=>{if(!r.url().startsWith(url+'/'))external.push(r.url());});
  const page=await context.newPage();page.on('pageerror',e=>errors.push(e.message));
  await page.goto(url);
  return {page,external,errors};
}
async function collect(page,count,scenario,contextId,name) {
  const rows=await page.evaluate(async({count,scenario,contextId,name})=>{
    const old=await import('/0.3.0/dist/index.js'), current=await import('/0.4.0/dist/index.js'), rows=[];
    for(let i=0;i<count;i++) {
      const pair={browser:name,scenario,contextId,repeat:i,device:'host'};
      for(const version of i%2?['0.4.0','0.3.0']:['0.3.0','0.4.0']) {
        const api=version==='0.3.0'?old:current,start=performance.now();
        const snapshot=await (version==='0.3.0'?api.collectDetailed:api.collectResilient)({scope:'intensive-v04'});
        const collectMs=performance.now()-start, hashStart=performance.now();
        const digest=await (version==='0.3.0'?api.digestDetailed:api.digestResilient)(snapshot);
        const digestMs=performance.now()-hashStart,codeStart=performance.now();
        const code=version==='0.4.0'?await api.continuityCode(snapshot):null;
        pair[version]={snapshot,digest,code,collectMs,digestMs,codeMs:version==='0.4.0'?performance.now()-codeStart:null};
      }
      if(document.querySelectorAll('iframe').length) throw Error('Collector iframe leaked');
      rows.push(pair);
    }
    return rows;
  },{count,scenario,contextId,name});
  raw.push(...rows);return rows;
}
async function clearSite(page,context) {
  await page.evaluate(async()=>{
    localStorage.clear();sessionStorage.clear();
    for(const key of await caches.keys()) await caches.delete(key);
    for(const registration of await navigator.serviceWorker.getRegistrations()) await registration.unregister();
    const databases=await indexedDB.databases();
    await Promise.all(databases.map(db=>new Promise((yes,no)=>{const request=indexedDB.deleteDatabase(db.name);request.onsuccess=yes;request.onerror=no;request.onblocked=()=>no(Error('IndexedDB deletion blocked'));})));
  });
  await context.clearCookies();
  const state=await page.evaluate(async()=>({local:localStorage.length,session:sessionStorage.length,
    caches:(await caches.keys()).length,databases:(await indexedDB.databases()).length,cookies:document.cookie}));
  if(state.local||state.session||state.caches||state.databases||state.cookies) throw Error('Site data not empty');
}
function summarize(rows,baseline,version) {
  const values=rows.map(r=>r[version]);
  return {observations:rows.length,digest:repeatability(values.map(v=>v.digest),baseline[version].digest),
    continuityCode:version==='0.4.0'?repeatability(values.map(v=>v.code),baseline[version].code):null,
    detailAvailability:Object.fromEntries(['gpu','fonts','canvas'].map(k=>[k,rate(values.filter(v=>v.snapshot.detail[k]!==null).length,values.length)])),
    collect:quantiles(values.map(v=>v.collectMs)),digestTime:quantiles(values.map(v=>v.digestMs)),
    codeTime:version==='0.4.0'?quantiles(values.map(v=>v.codeMs)):null};
}
try {
  for(const name of selected) {
    const config=engines[name];if(!config) throw Error('Unknown browser '+name);
    const profile=await mkdtemp(resolve(tmpdir(),'singularity-intensive-'));
    let persistent, browser;
    const options={locale:'en-US',timezoneId:'UTC',viewport:{width:1280,height:800},deviceScaleFactor:1};
    const allExternal=[],allErrors=[],cacheChecks=[];
    const start=raw.length;
    try {
      persistent=await config.engine.launchPersistentContext(profile,{...options,channel:config.channel,timeout:20000});
      const version=persistent.browser().version();
      let prepared=await preparePage(persistent);allExternal.push(prepared.external);allErrors.push(prepared.errors);
      await collect(prepared.page,samples,'persistent-baseline','normal-0',name);
      const baseline=raw[start];
      for(let clear=0;clear<10;clear++) {
        const seeded=await prepared.page.evaluate(async()=>{
          const result={};
          for(const [key,fn] of Object.entries({local:()=>localStorage.setItem('test','x'),session:()=>sessionStorage.setItem('test','x'),
            cookie:()=>{document.cookie='test=x;path=/';},cache:async()=>{await (await caches.open('test')).put('/test',new Response('x'));},
            indexedDB:()=>new Promise((yes,no)=>{const q=indexedDB.open('test',1);q.onupgradeneeded=()=>q.result.createObjectStore('test');q.onsuccess=()=>{q.result.close();yes();};q.onerror=no;})})) {
            try {await fn();result[key]='seeded';} catch(e) {result[key]=e.name||'unavailable';}
          }
          return result;
        });
        const warm=await prepared.page.evaluate(async()=>[(await (await fetch('/cache-probe')).json()).hit,(await (await fetch('/cache-probe')).json()).hit]);
        await clearSite(prepared.page,persistent);
        if(config.engine===chromium) {
          const cdp=await persistent.newCDPSession(prepared.page);
          await cdp.send('Network.clearBrowserCache');await cdp.detach();
          const after=await prepared.page.evaluate(async()=>(await (await fetch('/cache-probe')).json()).hit);
          cacheChecks.push({warmCacheProven:warm[0]===warm[1],clearCacheProven:after>warm[1],siteDataEmpty:true,seeded});
          if(after<=warm[1]) throw Error('HTTP cache eviction failed');
        } else cacheChecks.push({warmCacheProven:warm[0]===warm[1],clearCacheProven:null,siteDataEmpty:true,seeded});
        await prepared.page.reload();
        await collect(prepared.page,samples/10,config.engine===chromium?'http-cache-and-site-data-cleared':'site-data-cleared','clear-'+clear,name);
      }
      await persistent.close();persistent=undefined;
      for(let restart=0;restart<5;restart++) {
        persistent=await config.engine.launchPersistentContext(profile,{...options,channel:config.channel,timeout:20000});
        prepared=await preparePage(persistent);allExternal.push(prepared.external);allErrors.push(prepared.errors);
        await collect(prepared.page,samples/5,'persistent-restart','restart-'+restart,name);
        await persistent.close();persistent=undefined;
      }
      browser=await config.engine.launch({channel:config.channel,timeout:20000});
      for(let session=0;session<10;session++) {
        const context=await browser.newContext(options);
        prepared=await preparePage(context);allExternal.push(prepared.external);allErrors.push(prepared.errors);
        await collect(prepared.page,samples/10,'incognito-fresh','private-'+session,name);
        await context.close();
      }
      await browser.close();browser=undefined;
      for(let fresh=0;fresh<10;fresh++) {
        const emptyProfile=await mkdtemp(resolve(tmpdir(),'singularity-empty-profile-'));
        try {
          persistent=await config.engine.launchPersistentContext(emptyProfile,{...options,channel:config.channel,timeout:20000});
          prepared=await preparePage(persistent);allExternal.push(prepared.external);allErrors.push(prepared.errors);
          await collect(prepared.page,samples/10,'empty-cache-fresh-normal-profile','empty-'+fresh,name);
          await persistent.close();persistent=undefined;
        } finally {await persistent?.close();persistent=undefined;await rm(emptyProfile,{recursive:true,force:true});}
      }
      if(allExternal.flat().length||allErrors.flat().length) throw Error('Unexpected requests or page errors');
      const rows=raw.slice(start),scenarios=[...new Set(rows.map(r=>r.scenario))];
      report.browsers.push({name,version,status:'PASS',pairedObservations:rows.length,cacheChecks,
        versions:Object.fromEntries(['0.3.0','0.4.0'].map(v=>[v,{all:summarize(rows,baseline,v),
          scenarios:Object.fromEntries(scenarios.map(s=>[s,summarize(rows.filter(r=>r.scenario===s),baseline,v)]))}]))});
      console.log(JSON.stringify({browser:name,status:'PASS',pairedObservations:rows.length}));
    } catch(error) {
      report.browsers.push({name,status:'FAIL',error:error.message.slice(0,1800),partialObservations:raw.length-start});
      process.exitCode=1;console.log(JSON.stringify({browser:name,status:'FAIL',error:error.message.slice(0,180)}));
    } finally {await persistent?.close();await browser?.close();await rm(profile,{recursive:true,force:true});}
  }
  const representatives=report.browsers.filter(b=>b.status==='PASS').map(b=>raw.find(r=>r.browser===b.name));
  for(let i=0;i<representatives.length;i++) for(let j=i+1;j<representatives.length;j++) {
    const a=representatives[i],b=representatives[j];
    report.crossBrowser.push({pair:[a.browser,b.browser],v03:old.compareDetailed(a['0.3.0'].snapshot,b['0.3.0'].snapshot),
      v04:current.compareResilient(a['0.4.0'].snapshot,b['0.4.0'].snapshot),
      sameAvailableCode:a['0.4.0'].code!==null&&b['0.4.0'].code!==null?a['0.4.0'].code===b['0.4.0'].code:null});
  }
  const successful=new Set(report.browsers.filter(b=>b.status==='PASS').map(b=>b.name));
  const rows=raw.filter(r=>successful.has(r.browser));
  report.totalPairedObservations=rows.length;
  report.matchReplay={};
  for(const [version,api,match] of [['0.3.0',old,old.matchDetailed],['0.4.0',current,current.matchResilient]]) {
    const pool=[],replay=[],timings=[];
    for(const row of rows) {
      const at=performance.now(),decision=match(row[version].snapshot,pool);timings.push(performance.now()-at);
      let visitor=decision.candidateId;
      if(decision.status==='unmatched') {visitor='anchor-'+pool.length;pool.push({id:visitor,snapshot:row[version].snapshot});}
      replay.push({device:'host',browser:row.browser,visitor});
    }
    const metrics=labeledMetrics(replay,'visitor');
    metrics.exclusiveStableDevices=rate(0,0); // One physical host gives no exclusivity estimate.
    report.matchReplay[version]={metrics,timing:quantiles(timings),anchors:pool.length};
  }
} finally {
  await new Promise(yes=>server.close(yes));await mkdir(out,{recursive:true});
  await writeFile(resolve(out,'browsers.json'),JSON.stringify(report,null,2));
  await writeFile(resolve(out,'observations.jsonl'),raw.map(r=>JSON.stringify(r)).join('\n')+'\n');
}
console.log(JSON.stringify({out,totalPairedObservations:report.totalPairedObservations,matchReplay:report.matchReplay}));
