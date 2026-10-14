import { match, canonicalize, digest, matchDetailed, canonicalizeDetailed, digestDetailed, matchResilient, canonicalizeResilient, digestResilient, continuityCode } from '../dist/index.js';
import { readFileSync } from 'node:fs';
const cases = JSON.parse(readFileSync(0, 'utf8'));
const results = [];
for (const c of cases) {
  try {
    const resilient = c.snapshot?.schema === 'singularity/v3';
    if (c.op === 'code') { results.push(await continuityCode(c.snapshot)); continue; }
    const detailed = c.snapshot?.schema === 'singularity/v2';
    results.push(c.op === 'digest' ? {canonical: (resilient ? canonicalizeResilient : detailed ? canonicalizeDetailed : canonicalize)(c.snapshot),
      digest: await (resilient ? digestResilient : detailed ? digestDetailed : digest)(c.snapshot)} : (resilient ? matchResilient : detailed ? matchDetailed : match)(c.snapshot, c.candidates));
  }
  catch (e) { results.push({error: e.code}); }
}
process.stdout.write(JSON.stringify(results));
