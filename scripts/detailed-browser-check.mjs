// Real browser probes on one physical host. Isolated contexts are not extra devices.
import {chromium, firefox, webkit} from 'playwright';
import assert from 'node:assert/strict';
import {mkdir, writeFile} from 'node:fs/promises';
import {startServer} from './serve.mjs';
import {compareDetailed} from '../dist/index.js';

const local = await startServer();
const report = {source: 'one-host-browser-execution', browsers: [], crossBrowser: [],
  note: 'Ephemeral automation contexts, not independent devices or a population accuracy measurement.'};
const snapshots = [];
const selected = (process.env.BROWSERS || 'chromium,firefox,webkit').split(',');
try {
  for (const [name, engine] of Object.entries({chromium, firefox, webkit})) {
    if (!selected.includes(name)) continue;
    let browser;
    try {
      browser = await engine.launch({timeout: 20000});
      const observations = [], elapsed = [], requests = [];
      for (let index = 0; index < 4; index++) {
        const context = await browser.newContext({locale: 'en-US', timezoneId: 'UTC', deviceScaleFactor: index % 2 + 1});
        const page = await context.newPage();
        await page.route('**/*', async route => {
          const url = route.request().url();
          if (/\.woff2(?:\?|$)/.test(url) || !url.startsWith(local.url + '/')) {
            requests.push(url); await route.abort();
          } else await route.continue();
        });
        await page.goto(local.url);
        await page.evaluate(() => import('/dist/index.js'));
        for (const width of [1280, 390]) {
          await page.setViewportSize({width, height: 844});
          const batch = await page.evaluate(async () => {
            const api = await import('/dist/index.js');
            const rows = [], times = [];
            const before = document.querySelectorAll('iframe').length;
            for (let n = 0; n < 25; n++) {
              const start = performance.now();
              const snapshot = await api.collectDetailed({scope: 'detailed-browser-check'});
              times.push(performance.now() - start);
              rows.push({snapshot, digest: await api.digestDetailed(snapshot)});
            }
            if (document.querySelectorAll('iframe').length !== before) throw Error('Probe iframe leaked');
            return {rows, times};
          });
          observations.push(...batch.rows); elapsed.push(...batch.times);
        }
        // Host CSS must not initiate a font download or poison the local probes.
        const poisoning = await page.evaluate(async () => {
          const api = await import('/dist/index.js');
          const original = await api.collectDetailed({scope: 'detailed-browser-check'});
          const style = document.createElement('style');
          style.textContent = '@font-face{font-family:Arial;src:url(/remote.woff2)}@font-face{font-family:Consolas;src:url(/remote2.woff2)}';
          document.head.append(style);
          const remote = await api.collectDetailed({scope: 'detailed-browser-check'});
          style.textContent = '@font-face{font-family:Arial;src:local("Courier New")}';
          await document.fonts.load('17px Arial');
          const local = await api.collectDetailed({scope: 'detailed-browser-check'});
          style.remove();
          const create = document.createElement;
          document.createElement = function(tag, ...rest) {
            if (tag === 'iframe') throw Error('DOM isolation blocked');
            return create.call(this, tag, ...rest);
          };
          let blocked;
          try { blocked = await api.collectDetailed({scope: 'detailed-browser-check'}); }
          finally { document.createElement = create; }
          return {original, remote, local, blocked, frames: document.querySelectorAll('iframe').length};
        });
        assert.deepEqual(poisoning.original, poisoning.remote, `${name}: page web fonts`);
        assert.deepEqual(poisoning.original, poisoning.local, `${name}: page local font aliases`);
        assert.deepEqual(poisoning.blocked.detail, {gpu: null, fonts: null, canvas: null});
        assert.equal(poisoning.frames, 0);
        await page.reload();
        const reloaded = await page.evaluate(async () => (await import('/dist/index.js')).collectDetailed({scope: 'detailed-browser-check'}));
        assert.deepEqual(reloaded, poisoning.original, `${name}: reload`);
        await context.close();
      }
      assert.deepEqual(requests, [], `${name}: unexpected network request`);
      assert.equal(new Set(observations.map(r => r.digest)).size, 1, `${name}: same-engine/context/viewport/DPR stability`);
      elapsed.sort((a,b) => a-b);
      snapshots.push({name, snapshot: observations[0].snapshot});
      report.browsers.push({name, version: browser.version(), status: 'PASS', collections: observations.length,
        distinctDigests: 1, available: Object.fromEntries(Object.entries(observations[0].snapshot.detail).map(([k,v]) => [k,v !== null])),
        timings: {medianMs: elapsed[Math.floor(elapsed.length / 2)], p95Ms: elapsed[Math.floor(elapsed.length * .95)], maxMs: elapsed.at(-1)},
        checks: ['viewport/DPR/reload/isolated-context stability', 'host font isolation', 'no external/font requests', 'blocked DOM => null', 'no iframe leaks']});
    } catch (e) {
      report.browsers.push({name, status: 'FAIL', error: e.message}); process.exitCode = 1;
      // Keep failures visible in public CI annotations as well as archived evidence.
      const message = e.message.replaceAll('%', '%25').replaceAll('\r', '%0D').replaceAll('\n', '%0A');
      console.error(`::error title=Detailed browser ${name}::${message}`);
    }
    finally { await browser?.close(); }
  }
  for (const a of snapshots) for (const b of snapshots) if (a.name < b.name) {
    report.crossBrowser.push({pair: `${a.name}/${b.name}`, ...compareDetailed(a.snapshot, b.snapshot)});
  }
} finally { await local.close(); }
await mkdir('artifacts/improvement-v03', {recursive: true});
await writeFile('artifacts/improvement-v03/browsers.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
