// Fresh processes and contexts are repeat visits on ONE host, never extra devices.
import {chromium, firefox, webkit} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {startServer} from './serve.mjs';
import {compareDetailed, compareResilient} from '../dist/index.js';

const local = await startServer();
const report = {source:'one-host-browser-execution', browsers:[], crossBrowser:[],
  note:'Process restarts, empty ephemeral profiles, cleared storage, locale, viewport and DPR changes. No cross-device accuracy estimate.'};
const representatives=[];
try {
  for(const [name, engine] of Object.entries({chromium,firefox,webkit})) {
    if(!(process.env.BROWSERS||'chromium,firefox,webkit').split(',').includes(name)) continue;
    const rows=[], timings=[]; let browser, version;
    try {
      for(let processRun=0;processRun<2;processRun++) {
        browser=await engine.launch({timeout:20000}); version=browser.version();
        // Same DPR repeats across fresh contexts; change the order between processes.
        const scales=processRun ? [2,1,1,3] : [1,3,2,1];
        for(let i=0;i<scales.length;i++) {
          const context=await browser.newContext({deviceScaleFactor:scales[i],locale:i%2?'it-IT':'en-US',timezoneId:i%2?'Europe/Rome':'UTC'});
          const page=await context.newPage();
          const forbidden=[];
          await page.route('**/*',route=>{
            const url=route.request().url();
            if(!url.startsWith(local.url+'/') || /\.woff/.test(url)) {forbidden.push(url);return route.abort();}
            return route.continue();
          });
          await page.goto(local.url);
          await page.setViewportSize({width:i%2?390:1280,height:844});
          const batch=await page.evaluate(async()=>{
            const api=await import('/dist/index.js'), rows=[],timings=[];
            // Any accidental storage dependency must fail, even before clearing it.
            localStorage.clear();sessionStorage.clear();
            const original=Object.getOwnPropertyDescriptor(window,'localStorage');
            Object.defineProperty(window,'localStorage',{configurable:true,get(){throw Error('Unexpected storage access');}});
            try {
              for(let n=0;n<10;n++) {
                const start=performance.now(), snapshot=await api.collectResilient({scope:'resilient-browser'});
                timings.push(performance.now()-start);
                rows.push({snapshot,code:await api.continuityCode(snapshot)});
              }
            } finally {Object.defineProperty(window,'localStorage',original);}
            const before=rows[0].snapshot;
            const style=document.createElement('style');
            style.textContent='@font-face{font-family:Arial;src:url(/remote.woff2)}@font-face{font-family:JetBrains Mono;src:local("Arial")}';
            document.head.append(style);
            const poisoned=await api.collectResilient({scope:'resilient-browser'});style.remove();
            if(JSON.stringify(before)!==JSON.stringify(poisoned)) throw Error('Host font isolation failed');
            if(document.querySelectorAll('iframe').length) throw Error('Iframe leaked');
            return {rows,timings,detailed:await api.collectDetailed({scope:'resilient-browser'})};
          });
          await page.reload();
          const repeat=await page.evaluate(async()=>{const a=await import('/dist/index.js');return a.continuityCode(await a.collectResilient({scope:'resilient-browser'}));});
          assert.equal(repeat,batch.rows[0].code,'reload code');
          assert.deepEqual(forbidden,[],'no external/font requests');
          rows.push(...batch.rows);timings.push(...batch.timings);
          if(!representatives.some(r=>r.name===name)) representatives.push({name,v2:batch.detailed,v3:batch.rows[0].snapshot,code:batch.rows[0].code});
          await context.close();
        }
        await browser.close();browser=undefined;
      }
      // Missing codes are reported as unavailable, never counted as successful identity.
      const codes=rows.map(r=>r.code).filter(c=>c!==null);
      const variants=Object.fromEntries(['gpu','fonts','canvas'].map(k=>[k,new Set(rows.map(r=>r.snapshot.detail[k])).size]));
      assert.ok(new Set(codes).size<=1,`${name}: unstable available code`);
      timings.sort((a,b)=>a-b);
      report.browsers.push({name,version,status:'PASS',collections:rows.length,availableCodes:codes.length,
        distinctAvailableCodes:new Set(codes).size,detailVariants:variants,
        available:Object.fromEntries(Object.entries(rows[0].snapshot.detail).map(([k,v])=>[k,v!==null])),
        medianMs:timings[Math.floor(timings.length/2)],p95Ms:timings[Math.floor(timings.length*.95)]});
    } catch(e) {report.browsers.push({name,status:'FAIL',error:e.message});process.exitCode=1;}
    finally {await browser?.close();}
  }
  for(const a of representatives) for(const b of representatives) if(a.name<b.name) {
    report.crossBrowser.push({pair:`${a.name}/${b.name}`,v2:compareDetailed(a.v2,b.v2),v3:compareResilient(a.v3,b.v3),
      sameAvailableCode:a.code!==null&&b.code!==null?a.code===b.code:null});
  }
} finally {await local.close();}
await mkdir('artifacts/improvement-v04',{recursive:true});
await writeFile('artifacts/improvement-v04/browsers.json',JSON.stringify(report,null,2));
console.log(JSON.stringify(report,null,2));
