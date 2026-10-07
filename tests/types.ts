import { collect, match, digest, type Snapshot, type MatchResult } from '../dist/index.js';
const s: Snapshot = collect({ scope: 'example.test' });
const result: MatchResult = match(s, [{ id: 'known', snapshot: s }]);
const code: Promise<string> = digest(s);
void result; void code;
// @ts-expect-error Scope is required; no accidental global namespace.
collect({});
// @ts-expect-error Callers cannot substitute arbitrary schema versions.
const invalid: Snapshot = { schema: 'v2', scope: 'x', signals: s.signals };
// @ts-expect-error Snapshots expose immutable fields.
s.scope = 'other';
void invalid;
import {collectDetailed, matchDetailed, digestDetailed, type DetailedSnapshot, type DetailedMatchResult} from '../dist/index.js';
const detailed: Promise<DetailedSnapshot> = collectDetailed({scope: 'example.test'});
const detailedResult: Promise<DetailedMatchResult> = detailed.then(s => matchDetailed(s, []));
const detailedCode: Promise<string> = detailed.then(digestDetailed);
void detailedResult; void detailedCode;
