import { match, canonicalize, digest } from '../dist/index.js';
import { readFileSync } from 'node:fs';
const cases = JSON.parse(readFileSync(0, 'utf8'));
const results = [];
for (const c of cases) {
  try { results.push(c.op === 'digest' ? {canonical: canonicalize(c.snapshot), digest: await digest(c.snapshot)} : match(c.snapshot, c.candidates)); }
  catch (e) { results.push({error: e.code}); }
}
process.stdout.write(JSON.stringify(results));
