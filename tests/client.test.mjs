import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createAgent} from '../client/agent.js';

test('network adapter defaults to v2 and explicitly supports legacy without storage access', async t => {
  Object.defineProperty(globalThis, 'window', {configurable: true, value: {}});
  t.after(() => { delete globalThis.window; });
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    requests.push(JSON.parse(options.body));
    assert.equal(options.credentials, 'omit');
    return {ok: true, json: async () => ({eventId:'evt_test'})};
  });
  const options = {publicKey:'pk_'+'a'.repeat(32),endpoint:'https://identity.example.com'};
  await createAgent(options).identify({requestId:'request-detailed'});
  await createAgent({...options,mode:'legacy'}).identify({requestId:'request-legacy'});
  assert.equal(requests[0].snapshot.schema, 'singularity/v2');
  assert.equal(requests[0].requestId, 'request-detailed');
  assert.equal(requests[1].snapshot.schema, 'singularity/v1');
  assert.equal(requests[1].requestId, 'request-legacy');
  assert.ok(requests.every(r => r.remember === false && r.token === null));
  assert.throws(() => createAgent({...options,mode:'unknown'}), /collection mode/);
});
