import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createHash } from 'node:crypto';
import { collect, canonicalize, digest, compare, match, parseSnapshot, validateSnapshot, SCHEMA, POLICY, LIMITS, SingularityError } from '../dist/index.js';
import { snapshot, environment, candidate } from './fixtures.mjs';

const error = code => e => e instanceof SingularityError && e.code === code;
test('canonical v1 wire tuple and SHA-256 golden vector', async () => {
  const wire = '["singularity/v1","example.test","linux",8,8,"en","UTC"]';
  assert.equal(canonicalize(snapshot()), wire);
  // Independently implemented oracle, not the library's own Web Crypto path.
  assert.equal(await digest(snapshot()), 'sg1_' + createHash('sha256').update(wire).digest('hex'));
  const a = snapshot();
  const reversed = { signals: Object.fromEntries(Object.entries(a.signals).reverse()), scope: a.scope, schema: a.schema };
  assert.equal(await digest(reversed), await digest(a));
  assert.notEqual(await digest(snapshot({}, 'another.test')), await digest(a));
});
test('scope and schema rejection is fail-closed', () => {
  assert.throws(() => compare(snapshot(), snapshot({}, 'other')), error('SCOPE_MISMATCH'));
  assert.throws(() => match(snapshot(), [{ id: 'wrong', snapshot: snapshot({}, 'other') }]), error('SCOPE_MISMATCH'));
  assert.throws(() => validateSnapshot({ ...snapshot(), schema: 'singularity/v2' }), error('INCOMPATIBLE_SCHEMA'));
});
test('display/browser/OS version changes cannot enter observation material', async () => {
  const base = collect({ scope: 'example.test', environment });
  const changed = { ...environment, userAgent: 'Mozilla/5.0 (X11; Linux x86_64) Firefox/999.0' };
  for (const field of ['screen', 'width', 'height', 'devicePixelRatio', 'maxTouchPoints', 'canvas', 'webgl', 'audio', 'fonts', 'storage']) {
    Object.defineProperty(changed, field, { get() { throw new Error(`Forbidden read: ${field}`); } });
  }
  assert.equal(await digest(collect({ scope: 'example.test', environment: changed })), await digest(base));
  for (const pair of [
    ['Windows NT 10.0; Win64; x64 Chrome/1', 'Windows NT 99.0; Win64; x64 Edg/900'],
    ['Macintosh; Intel Mac OS X 10_15_7 Version/17.0 Safari', 'Macintosh; Intel Mac OS X 99_1 Version/99.0 Safari'],
    ['Android 12 Chrome/1', 'Android 99 Chrome/900'],
  ]) {
    const samples = pair.map(userAgent => collect({ scope: 'example.test', environment: { ...environment, userAgent, platform: '' } }));
    assert.equal(await digest(samples[0]), await digest(samples[1]));
  }
});
test('blocked getters and unknown/invalid observations become null, not identifying sentinels', () => {
  const env = { userAgent: 'unrecognized', language: '<invalid>', timezone: 'bad zone', hardwareConcurrency: NaN };
  Object.defineProperty(env, 'deviceMemory', { get() { throw Error('blocked'); } });
  const s = collect({ scope: 'test', environment: env });
  assert.deepEqual(s.signals, { platform: null, cores: null, memory: null, language: null, timezone: null });
  assert.equal(match(s, [{ id: 'empty', snapshot: s }]).status, 'abstain');
});
test('collector requires explicit scope and browser or adapter; package can import in Node', () => {
  assert.throws(() => collect({ scope: '' }), error('INVALID_INPUT'));
  assert.throws(() => collect({ scope: 'test' }), error('BROWSER_UNAVAILABLE'));
  assert.equal(collect({ scope: 'test', environment: { hardwareConcurrency: 12, deviceMemory: 6 } }).signals.cores, 8);
});
test('policy constants and exact comparison are fixed v1 contract', () => {
  assert.deepEqual(POLICY, { version: 'envelope/v1', minSimilarity: .75, minCoverage: .75, minFamilies: 3, minOmittedFamilies: 2, minMargin: .15 });
  const pair = compare(snapshot(), snapshot());
  assert.equal(pair.similarity, 1);
  assert.equal(pair.coverage, 1);
  assert.equal(pair.qualifies, true);
});
test('envelope is satisfiable for a fully observed singleton', () => {
  const result = match(snapshot(), [candidate()]);
  assert.equal(result.status, 'matched');
  assert.equal(result.candidateId, 'known');
  assert.equal(result.omissions.length, 3);
  assert.ok(result.omissions.every(o => o.passes && o.margin === null && o.comparableFamilies.length === 2));
});
for (const [field, value] of [['memory', 4], ['language', 'it'], ['timezone', 'Europe/Rome']]) {
  test(`one weak change (${field}) can preserve candidate ID while snapshot digest changes`, async () => {
    const changed = snapshot({ [field]: value });
    assert.notEqual(await digest(changed), await digest(snapshot()));
    const result = match(changed, [candidate()]);
    assert.equal(result.status, 'matched');
    assert.equal(result.candidateId, 'known');
  });
}
test('base threshold is inclusive, but cannot bypass omission threshold', () => {
  const s = snapshot({ cores: 4 });
  assert.equal(compare(snapshot(), s).similarity, .75);
  assert.equal(compare(snapshot(), s).qualifies, true);
  const result = match(snapshot(), [{ id: 'previous', snapshot: s }]);
  assert.equal(result.reason, 'unstable-under-omission');
  assert.equal(result.omissions.find(o => o.omitted === 'platform').similarity, .6);
  assert.equal(compare(snapshot(), snapshot({ cores: 4, memory: 4 })).qualifies, false);
});
test('memory missing is tolerated; cores missing defeats reduced coverage', () => {
  assert.equal(match(snapshot({ memory: null }), [candidate()]).status, 'matched');
  assert.equal(compare(snapshot({ cores: null }), snapshot()).coverage, .75);
  assert.equal(match(snapshot({ cores: null }), [candidate()]).reason, 'insufficient-observation');
  assert.equal(match(snapshot({ cores: null, memory: null }), [candidate()]).reason, 'insufficient-observation');
});
test('null/null earns no similarity, and missingness is not a contradiction', () => {
  const pair = compare(snapshot({ platform: null }), snapshot({ platform: null }));
  assert.equal(pair.similarity, 5 / 8);
  assert.deepEqual(pair.contradictions, []);
  assert.equal(pair.qualifies, false);
});
test('platform contradiction vetoes full comparison', () => {
  const pair = compare(snapshot(), snapshot({ platform: 'windows' }));
  assert.deepEqual(pair.contradictions, ['platform']);
  assert.equal(match(snapshot(), [candidate('windows', { platform: 'windows' })]).status, 'unmatched');
});
test('equivalent candidates never resolve by ID or input order', () => {
  for (const list of [[candidate('a'), candidate('b')], [candidate('b'), candidate('a')]]) {
    const result = match(snapshot(), list);
    assert.equal(result.status, 'abstain');
    assert.equal(result.reason, 'ambiguous-candidates');
    assert.equal(result.candidateId, null);
  }
});
test('margin boundary on this discrete policy: .125 fails, weakest passing omission is 1/6', () => {
  assert.equal(match(snapshot(), [candidate('a'), candidate('b', { memory: 4 })]).reason, 'ambiguous-candidates');
  const result = match(snapshot(), [candidate('a'), candidate('b', { memory: 4, language: 'it' })]);
  assert.equal(result.status, 'matched');
  assert.ok(Math.abs(result.omissions.find(o => o.omitted === 'locale').margin - 1 / 6) < 1e-12);
});
for (const [name, differences, omitted] of [
  ['initially below threshold', { cores: 4, memory: 4 }, 'compute'],
  ['initially sparse', { cores: null, memory: null }, 'compute'],
  ['initially platform-vetoed', { platform: 'windows' }, 'platform'],
]) {
  test(`omission reconsiders ${name} competitors`, () => {
    const a = [candidate('winner'), candidate('rival', differences)];
    const first = match(snapshot(), a), second = match(snapshot(), [...a].reverse());
    // Per-candidate diagnostics follow caller order; the decision and omission checks do not.
    assert.deepEqual({ ...first, candidates: [] }, { ...second, candidates: [] });
    assert.deepEqual(first.candidates, [...second.candidates].reverse());
    assert.equal(first.reason, 'unstable-under-omission');
    const report = first.omissions.find(o => o.omitted === omitted);
    assert.equal(report.runnerUpId, 'rival');
    assert.equal(report.margin, 0);
    assert.equal(report.passes, false);
  });
}
test('empty list, sparse candidate, and disproven candidates have distinct outcomes', () => {
  assert.equal(match(snapshot(), []).reason, 'no-candidates');
  assert.equal(match(snapshot(), [candidate('sparse', { cores: null, memory: null })]).reason, 'insufficient-candidate-evidence');
  assert.equal(match(snapshot(), [candidate('other', { cores: 4, memory: 4, language: 'it' })]).reason, 'no-candidate-qualified');
});
test('strict validation rejects duplicate IDs and validates every candidate before a decision', () => {
  assert.throws(() => match(snapshot(), [candidate('a'), candidate('a', { memory: 4 })]), error('DUPLICATE_ID'));
  assert.throws(() => match(snapshot(), [candidate(), { id: 'bad', snapshot: { ...snapshot(), extra: true } }]), error('INVALID_INPUT'));
  assert.throws(() => match(snapshot(), Array(2)), error('INVALID_INPUT'));
  assert.throws(() => match(snapshot(), [{ id: '<script>', snapshot: snapshot() }]), error('INVALID_INPUT'));
});
test('candidate cap rejects before examining candidates, never truncates', () => {
  const oversized = Array(LIMITS.candidates + 1);
  Object.defineProperty(oversized, '0', { get() { throw new Error('Should not read'); } });
  assert.throws(() => match(snapshot(), oversized), error('LIMIT_EXCEEDED'));
  const max = Array.from({ length: LIMITS.candidates }, (_, i) => candidate(`id-${i}`));
  assert.equal(match(snapshot(), max).status, 'abstain');
});
test('custom array iterators cannot hide rivals or enlarge the candidate set', () => {
  const contenders = [candidate('a'), candidate('b')];
  contenders[Symbol.iterator] = function* () { yield this[0]; };
  const ambiguous = match(snapshot(), contenders);
  assert.equal(ambiguous.status, 'abstain');
  assert.equal(ambiguous.candidates.length, 2);
  const single = [candidate('actual')];
  single[Symbol.iterator] = function* () { throw Error('Iterator must not execute'); };
  assert.equal(match(snapshot(), single).candidateId, 'actual');
  const hiddenInvalid = [candidate(), { id: 'bad', snapshot: null }];
  hiddenInvalid[Symbol.iterator] = function* () { yield this[0]; };
  assert.throws(() => match(snapshot(), hiddenInvalid), error('INVALID_INPUT'));
});
test('array element accessors and inherited elements cannot fabricate candidates', () => {
  const withGetter = [candidate()];
  Object.defineProperty(withGetter, '0', { get() { throw Error('Getter must not execute'); } });
  assert.throws(() => match(snapshot(), withGetter), error('INVALID_INPUT'));
  const inherited = Array(1);
  Object.setPrototypeOf(inherited, { 0: candidate() });
  assert.throws(() => match(snapshot(), inherited), error('INVALID_INPUT'));
});
test('bounded JSON entry validates transported snapshots', () => {
  assert.deepEqual(parseSnapshot(JSON.stringify(snapshot())), snapshot());
  assert.throws(() => parseSnapshot(' '.repeat(LIMITS.snapshotJson + 1)), error('LIMIT_EXCEEDED'));
  for (const json of ['null', '[1]', '{', '{"__proto__":{}}']) assert.throws(() => parseSnapshot(json), error('INVALID_INPUT'));
});
test('unknown keys, accessors, prototypes, invalid buckets and oversized values reject', () => {
  const accessor = { ...snapshot() };
  Object.defineProperty(accessor, 'scope', { get() { throw new Error('Accessor must not run'); } });
  assert.throws(() => validateSnapshot(accessor), error('INVALID_INPUT'));
  for (const value of [
    { ...snapshot(), extra: true }, Object.assign(Object.create({ inherited: true }), snapshot()),
    snapshot({ cores: NaN }), snapshot({ cores: 7 }), snapshot({ memory: -1 }),
    snapshot({ language: 'en-US' }), snapshot({ timezone: 'x'.repeat(81) }), snapshot({}, 'x'.repeat(129)),
  ]) assert.throws(() => validateSnapshot(value), error('INVALID_INPUT'));
});
test('matching and canonicalization never mutate candidates or depend on wall-clock time', async () => {
  const source = snapshot(); Object.freeze(source.signals); Object.freeze(source);
  const list = Object.freeze([Object.freeze({ id: 'a', snapshot: source })]);
  const before = JSON.stringify(list);
  assert.equal(match(source, list).status, 'matched');
  assert.equal(match(source, list).status, 'matched');
  await digest(source);
  assert.equal(JSON.stringify(list), before);
});
test('identical coarse observations from distinct physical devices collide by construction', async () => {
  const deviceA = snapshot(), deviceB = snapshot();
  assert.equal(await digest(deviceA), await digest(deviceB));
  // More hash bits cannot fix equal input. A match is not authentication.
  assert.equal(match(deviceA, [{ id: 'deviceB', snapshot: deviceB }]).status, 'matched');
  assert.equal(match(deviceA, [{ id: 'deviceA', snapshot: deviceA }, { id: 'deviceB', snapshot: deviceB }]).status, 'abstain');
});
test('all null-field combinations cannot manufacture evidence or an equivalent-candidate winner', () => {
  const keys = Object.keys(snapshot().signals);
  for (let mask = 0; mask < 32; mask++) {
    const changes = Object.fromEntries(keys.filter((_, i) => mask & (1 << i)).map(k => [k, null]));
    const observed = snapshot(changes);
    const result = match(observed, [{ id: 'a', snapshot: observed }, { id: 'b', snapshot: observed }]);
    assert.notEqual(result.status, 'matched');
    const c = compare(observed, observed);
    assert.ok(c.similarity <= c.coverage);
  }
});
