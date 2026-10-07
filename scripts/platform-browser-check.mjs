// Deployed-stack acceptance, run by CI against an isolated Compose installation.
import { chromium, firefox, webkit } from 'playwright';
import assert from 'node:assert/strict';
import { readFile, mkdir } from 'node:fs/promises';
const base = process.env.PLATFORM_URL || 'http://localhost:8080';
const password = (await readFile('.admin-password', 'utf8')).trim();
await mkdir('artifacts/platform', {recursive: true});
for (const [name, engine] of Object.entries({chromium, firefox, webkit})) {
  const browser = await engine.launch();
  const page = await browser.newPage({viewport: {width: 1365, height: 1000}});
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  async function identify(buttonName) {
    const [response] = await Promise.all([
      page.waitForResponse(r => r.request().method() === 'POST' && r.url().includes('/api/v1/identify/')),
      page.getByRole('button', {name: buttonName, exact: true}).click(),
    ]);
    const data = await response.json();
    // CI uses disposable browser profiles; never print tokens or credentials.
    console.log(JSON.stringify({engine: name, status: response.status(), method: data.method,
      reason: data.reason, signals: response.request().postDataJSON().snapshot.signals}));
    assert.equal(response.status(), 200, typeof data.detail === 'string' ? data.detail : 'Identification response');
    return data;
  }
  await page.goto(base);
  await identify('Identify this browser');
  await page.getByRole('button', {name: 'Identify again', exact: true}).waitFor();
  assert.match(await page.getByTestId('event-id').innerText(), /^evt_/);
  await page.getByLabel('Remember this browser', {exact: true}).check();
  const enrollment = await identify('Identify again');
  assert.equal(enrollment.method, 'enrolled', enrollment.reason);
  await page.getByText('explicit-enrollment', {exact: true}).waitFor();
  const visitor = await page.getByTestId('visitor-id').innerText();
  const remembered = await identify('Identify again');
  assert.equal(remembered.method, 'remembered', remembered.reason);
  await page.getByText('possession-token', {exact: true}).waitFor();
  assert.equal(await page.getByTestId('visitor-id').innerText(), visitor);
  await page.screenshot({path: `artifacts/platform/${name}-desktop.png`, fullPage: true});
  await page.getByRole('button', {name: 'Activity', exact: true}).click();
  await page.getByLabel('Password', {exact: true}).fill(password);
  await page.getByRole('button', {name: 'Sign in', exact: true}).click();
  await page.getByRole('heading', {name: 'Activity, with context.'}).waitFor();
  await page.getByLabel('ID prefix', {exact: true}).fill('vis_' + visitor.slice(4, 12));
  await page.getByRole('button', {name: 'Search', exact: true}).click();
  await page.waitForFunction(() => document.querySelectorAll('tbody tr').length > 0);
  await page.locator('tbody .id-link').first().click();
  await page.getByRole('heading', {name: 'Event inspector', exact: true}).waitFor();
  await page.getByRole('button', {name: 'Close', exact: true}).click();
  await page.getByLabel('ID prefix', {exact: true}).fill('INVALID');
  await page.getByRole('button', {name: 'Search', exact: true}).click();
  await page.getByRole('alert').waitFor();
  await page.getByRole('button', {name: 'Dismiss error', exact: true}).click();
  await page.getByRole('button', {name: 'Projects', exact: true}).click();
  await page.getByLabel('Project name', {exact: true}).fill('Browser test ' + name);
  await page.getByLabel('Allowed origins', {exact: true}).fill(base);
  await page.getByRole('button', {name: 'Create project', exact: true}).click();
  await page.getByRole('status').filter({hasText: 'Project saved. Copy its snippet from Integration.'}).waitFor();
  await page.getByRole('button', {name: 'Integration', exact: true}).click();
  await page.getByRole('heading', {name: '2. Identify a browser', exact: true}).waitFor();
  // Exercise the delivered SDK with a project created through the real GUI.
  const snippet = await page.locator('.integration pre').first().innerText();
  const publicKey = snippet.match(/publicKey: "(pk_[a-f0-9]+)"/)[1];
  const sdk = await page.evaluate(async ({base, publicKey}) => {
    const {createAgent} = await import(base + '/sdk/agent.js');
    return createAgent({publicKey}).identify();
  }, {base, publicKey});
  assert.match(sdk.eventId, /^evt_/);
  await page.getByRole('button', {name: 'Live demo', exact: true}).click();
  await page.setViewportSize({width: 390, height: 844});
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth), true);
  await page.getByRole('button', {name: 'Identify again', exact: true}).focus();
  await page.keyboard.press('Enter');
  await page.getByText('possession-token', {exact: true}).waitFor();
  await page.screenshot({path: `artifacts/platform/${name}-mobile.png`, fullPage: true});
  assert.deepEqual(errors, []);
  await browser.close();
  console.log(`PASS ${name}: live events, enrollment/continuity, admin, filters/error, project, SDK, mobile/keyboard`);
}
