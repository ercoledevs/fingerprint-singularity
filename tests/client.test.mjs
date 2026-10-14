import {test} from 'node:test';
import assert from 'node:assert/strict';
import {createAgent} from '../client/agent.js';

test('network adapter defaults to v3 and explicitly supports v2 and legacy without storage access', async t => {
  Object.defineProperty(globalThis, 'window', {configurable: true, value: {}});
  t.after(() => { delete globalThis.window; });
  const requests = [];
  t.mock.method(globalThis, 'fetch', async (_url, options) => {
    requests.push(JSON.parse(options.body));
    assert.equal(options.credentials, 'omit');
    return {ok: true, json: async () => ({eventId:'evt_test'})};
  });
  const options = {publicKey:'pk_'+'a'.repeat(32),endpoint:'https://identity.example.com'};
  await createAgent(options).identify({requestId:'request-detailed',linkedId:'order:123',tags:{flow:'checkout'}});
  await createAgent({...options,mode:'legacy'}).identify({requestId:'request-legacy'});
  assert.equal(requests[0].snapshot.schema, 'singularity/v3');
  assert.equal(requests[0].requestId, 'request-detailed');
  assert.equal(requests[0].linkedId, 'order:123');
  assert.deepEqual(requests[0].tags, {flow:'checkout'});
  assert.equal(requests[1].linkedId, undefined);
  assert.equal(requests[1].snapshot.schema, 'singularity/v1');
  assert.equal(requests[1].requestId, 'request-legacy');
  await createAgent({...options,mode:'detailed'}).identify();
  assert.equal(requests[2].snapshot.schema, 'singularity/v2');
  assert.ok(requests.every(r => r.remember === false && r.token === null));
  assert.throws(() => createAgent({...options,mode:'unknown'}), /collection mode/);
});
