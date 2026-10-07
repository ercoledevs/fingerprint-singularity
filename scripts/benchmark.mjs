import { performance } from 'node:perf_hooks';
import { mkdir, writeFile } from 'node:fs/promises';
import { collect, match, LIMITS } from '../dist/index.js';
import { environment, snapshot, candidate } from '../tests/fixtures.mjs';

// Local regression budgets, not a promise for arbitrary hardware or a benchmark against competitors.
const budgets = { collectP95Ms: 10, matchAtCapP95Ms: 50, retainedHeapBytes: 32 * 1024 * 1024, jsonCodeUnits: 2048, candidates: 256 };
function sample(fn, iterations = 200) {
  for (let i = 0; i < 40; i++) fn();
  const times = [];
  for (let i = 0; i < iterations; i++) { const start = performance.now(); fn(); times.push(performance.now() - start); }
  times.sort((a, b) => a - b);
  return { medianMs: times[Math.floor(times.length * .5)], p95Ms: times[Math.floor(times.length * .95)], maxMs: times.at(-1) };
}
const observation = snapshot();
const scaling = [1, 16, 64, LIMITS.candidates].map(count => {
  const candidates = Array.from({ length: count }, (_, i) => candidate(`id-${i}`));
  return { count, ...sample(() => match(observation, candidates)) };
});
const cap = Array.from({ length: LIMITS.candidates }, (_, i) => i === 0 ? candidate('winner') : candidate(`other-${i}`, { platform: 'windows', cores: 2, memory: 2, language: 'it' }));
const fullEnvelope = sample(() => match(observation, cap));
const ambiguous = scaling.at(-1);
const collection = sample(() => collect({ scope: 'bench', environment }));
global.gc?.();
const before = process.memoryUsage().heapUsed;
for (let i = 0; i < 500; i++) match(observation, cap);
const beforeGc = process.memoryUsage().heapUsed - before;
global.gc?.();
const retainedHeap = process.memoryUsage().heapUsed - before;
const oversized = Array(LIMITS.candidates + 1);
const earlyReject = sample(() => { try { match(observation, oversized); throw Error('Expected rejection'); } catch (e) { if (e.code !== 'LIMIT_EXCEEDED') throw e; } });
const pass = collection.p95Ms < budgets.collectP95Ms && Math.max(ambiguous.p95Ms, fullEnvelope.p95Ms) < budgets.matchAtCapP95Ms && retainedHeap < budgets.retainedHeapBytes;
const result = { status: pass ? 'PASS' : 'FAIL', runtime: process.version, budgets, collectionAdapter: collection, scaling, fullEnvelopeAtCap: fullEnvelope, earlyReject, observedHeapDeltaBeforeGc: beforeGc, retainedHeapAfterGc: retainedHeap, note: 'Adapter collection here; browser collection measured separately. Heap deltas are noisy observations, not peak allocations. Fixed 5 signals, 3 omissions, max 256 contenders bound work. No population or competitor accuracy measurements.' };
await mkdir('artifacts', { recursive: true });
await writeFile('artifacts/benchmark.json', JSON.stringify(result, null, 2));
console.log(JSON.stringify(result, null, 2));
if (!pass) process.exitCode = 1;
