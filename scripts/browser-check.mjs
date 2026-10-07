import { chromium, firefox, webkit } from 'playwright';
import assert from 'node:assert/strict';
import { mkdir, writeFile } from 'node:fs/promises';
import { startServer } from './serve.mjs';
import { match } from '../dist/index.js';

const local = await startServer();
const report = { browsers: [], crossBrowser: [], note: 'Same host, automated browser builds; not longitudinal accuracy or physical-monitor validation. Raw observations stay in local memory only.' };
const observations = [];
await mkdir('artifacts', { recursive: true });
try {
  for (const [name, engine] of Object.entries({ chromium, firefox, webkit })) {
    let browser;
    try {
      browser = await engine.launch({ headless: true, timeout: 20000 });
      const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: 'en-US', timezoneId: 'Europe/Rome' });
      const page = await context.newPage();
      const external = [], errors = [];
      page.on('request', r => { if (!r.url().startsWith(local.url + '/')) external.push(r.url()); });
      page.on('pageerror', e => errors.push(e.message));
      await page.goto(local.url);
      await page.waitForFunction(() => document.querySelector('#fingerprint')?.textContent.startsWith('sg1_'));
      const initial = await page.evaluate(async () => {
        const api = await import('/dist/index.js');
        const snapshot = api.collect({ scope: 'browser-check' });
        return { snapshot, digest: await api.digest(snapshot) };
      });
      await page.setViewportSize({ width: 390, height: 844 });
      const checks = await page.evaluate(async () => {
        const api = await import('/dist/index.js');
        const forbidden = [];
        for (const name of ['screen', 'localStorage', 'sessionStorage']) {
          Object.defineProperty(window, name, { configurable: true, get() { forbidden.push(name); throw Error('Forbidden read'); } });
        }
        const originalFetch = window.fetch;
        window.fetch = () => { forbidden.push('fetch'); throw Error('Unexpected fetch'); };
        try {
          const observed = api.collect({ scope: 'browser-check' });
          const hash = await api.digest(observed);
          const fixture = { schema: api.SCHEMA, scope: 'fixture', signals: { platform: 'linux', cores: 8, memory: 8, language: 'en', timezone: 'UTC' } };
          const equal = api.match(fixture, [{ id: 'known', snapshot: fixture }]);
          const ambiguous = api.match(fixture, [{ id: 'a', snapshot: fixture }, { id: 'b', snapshot: fixture }]);
          const candidates = Array.from({ length: 256 }, (_, i) => ({ id: `id-${i}`, snapshot: i === 0 ? fixture : { ...fixture, signals: { ...fixture.signals, platform: 'windows', cores: 2, memory: 2, language: 'it' } } }));
          const measure = fn => {
            for (let i = 0; i < 20; i++) fn();
            const t = [];
            for (let i = 0; i < 100; i++) { const start = performance.now(); fn(); t.push(performance.now() - start); }
            t.sort((a, b) => a - b);
            return { medianMs: t[50], p95Ms: t[95], maxMs: t[99] };
          };
          return { hash, singleton: equal.status, ambiguous: ambiguous.status, forbidden,
            collection: measure(() => api.collect({ scope: 'browser-check' })),
            matchAtCap: measure(() => api.match(fixture, candidates)),
            performanceHeapAvailable: typeof performance.memory?.usedJSHeapSize === 'number' };
        } finally { window.fetch = originalFetch; }
      });
      assert.equal(checks.hash, initial.digest, `${name}: viewport invariance`);
      assert.equal(checks.singleton, 'matched'); assert.equal(checks.ambiguous, 'abstain');
      assert.deepEqual(checks.forbidden, []); assert.deepEqual(external, []); assert.deepEqual(errors, []);
      assert.ok(checks.collection.p95Ms < 10, `${name}: collection budget`);
      assert.ok(checks.matchAtCap.p95Ms < 50, `${name}: match budget`);
      await page.click('#resample');
      await page.waitForFunction(() => document.querySelector('#status')?.textContent !== 'Inizializzazione');
      if (name === 'chromium') await page.screenshot({ path: 'artifacts/demo-mobile.png', fullPage: true });
      observations.push({ name, snapshot: initial.snapshot });
      report.browsers.push({ name, version: browser.version(), status: 'PASS', checks: { ...checks, hash: undefined }, viewport: ['1280x800', '390x844'], memoryNote: 'No portable browser peak-allocation API; memory bounded structurally, Node retained heap measured separately.' });
    } catch (e) { report.browsers.push({ name, status: 'FAIL', error: e.message }); process.exitCode = 1; }
    finally { await browser?.close(); }
  }
  for (const a of observations) for (const b of observations) if (a.name < b.name) {
    const result = match(a.snapshot, [{ id: b.name, snapshot: b.snapshot }]);
    report.crossBrowser.push({ pair: `${a.name}/${b.name}`, status: result.status, reason: result.reason });
  }
} finally { await local.close(); }
await writeFile('artifacts/browsers.json', JSON.stringify(report, null, 2));
console.log(JSON.stringify(report, null, 2));
