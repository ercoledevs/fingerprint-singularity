import { match, canonicalize, digest, matchDetailed, canonicalizeDetailed, digestDetailed } from '../dist/index.js';
import { readFileSync } from 'node:fs';
const cases = JSON.parse(readFileSync(0, 'utf8'));
const results = [];
for (const c of cases) {
  try {
    const detailed = c.snapshot?.schema === 'singularity/v2';
    results.push(c.op === 'digest' ? {canonical: (detailed ? canonicalizeDetailed : canonicalize)(c.snapshot),
      digest: await (detailed ? digestDetailed : digest)(c.snapshot)} : (detailed ? matchDetailed : match)(c.snapshot, c.candidates));
  }
  catch (e) { results.push({error: e.code}); }
}
process.stdout.write(JSON.stringify(results));
