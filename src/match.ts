import { LIMITS, record, sameScope, validateId, validateSnapshot } from './schema.js';
import { POLICY_VERSION, SingularityError, type Candidate, type CandidateComparison, type Comparison,
  type Contribution, type Family, type MatchReason, type MatchResult, type OmissionCheck, type Signal, type Snapshot } from './types.js';

export const POLICY = Object.freeze({ version: POLICY_VERSION, minSimilarity: 0.75, minCoverage: 0.75, minFamilies: 3, minOmittedFamilies: 2, minMargin: 0.15 });
const families: readonly Family[] = Object.freeze(['platform', 'compute', 'locale']);
const fields: readonly Readonly<{ key: Signal; family: Family; weight: number }>[] = Object.freeze([
  Object.freeze({ key: 'platform' as const, family: 'platform' as const, weight: 3 }),
  Object.freeze({ key: 'cores' as const, family: 'compute' as const, weight: 2 }),
  Object.freeze({ key: 'memory' as const, family: 'compute' as const, weight: 1 }),
  Object.freeze({ key: 'language' as const, family: 'locale' as const, weight: 1 }),
  Object.freeze({ key: 'timezone' as const, family: 'locale' as const, weight: 1 }),
]);

function evaluate(a: Snapshot, b: Snapshot, omitted?: Family): Comparison {
  let total = 0, equal = 0, comparable = 0;
  const seen = new Set<Family>();
  const contradictions: Signal[] = [];
  const contributions: Contribution[] = [];
  for (const { key, family, weight } of fields) {
    if (family === omitted) continue;
    total += weight;
    const left = a.signals[key], right = b.signals[key];
    const state = left === null || right === null ? 'missing' : left === right ? 'equal' : 'different';
    contributions.push({ signal: key, family, weight, state });
    if (state !== 'missing') { comparable += weight; seen.add(family); }
    if (state === 'equal') equal += weight;
    if (key === 'platform' && state === 'different') contradictions.push(key);
  }
  const similarity = equal / total, coverage = comparable / total;
  const comparableFamilies = families.filter(f => seen.has(f));
  return { policy: POLICY_VERSION, similarity, coverage, comparableFamilies, contradictions, contributions,
    qualifies: contradictions.length === 0 && similarity >= POLICY.minSimilarity && coverage >= POLICY.minCoverage
      && comparableFamilies.length >= (omitted ? POLICY.minOmittedFamilies : POLICY.minFamilies) };
}
/** Pairwise qualification alone is insufficient for a match: use match for ambiguity/omission checks. */
export function compare(left: Snapshot, right: Snapshot): Comparison {
  const a = validateSnapshot(left), b = validateSnapshot(right);
  sameScope(a, b);
  return evaluate(a, b);
}
function assess(observation: Snapshot, candidates: readonly Candidate[], omitted?: Family): CandidateComparison[] {
  return candidates.map(c => ({ id: c.id, ...evaluate(observation, c.snapshot, omitted) }));
}
function best(ranking: readonly CandidateComparison[], accept: (c: CandidateComparison) => boolean): CandidateComparison | undefined {
  let selected: CandidateComparison | undefined;
  for (const c of ranking) if (accept(c) && (!selected || c.similarity > selected.similarity ||
    (c.similarity === selected.similarity && c.id < selected.id))) selected = c;
  // Lexical tie selection only makes diagnostics repeatable; the margin rejects tied winners.
  return selected;
}
function runnerUp(ranking: readonly CandidateComparison[], id: string): CandidateComparison | undefined {
  // Even candidates below evidence/score floors can compete and block a margin.
  return best(ranking, c => c.id !== id && c.contradictions.length === 0);
}
function marginPass(winner: CandidateComparison, runner: CandidateComparison | undefined): boolean {
  return runner === undefined || winner.similarity - runner.similarity >= POLICY.minMargin;
}
export function match(snapshot: Snapshot, input: readonly Candidate[]): MatchResult {
  if (!Array.isArray(input)) throw new SingularityError('INVALID_INPUT', 'Candidates must be an array');
  const count = input.length;
  if (count > LIMITS.candidates) throw new SingularityError('LIMIT_EXCEEDED', 'At most 256 candidates; refusing to truncate contenders');
  const observation = validateSnapshot(snapshot);
  const ids = new Set<string>();
  const candidates: Candidate[] = [];
  // Validate every contender before returning any decision. Copy, never mutate caller state.
  for (let index = 0; index < count; index++) {
    // Never trust a custom iterator or execute an element getter. Every indexed contender counts.
    const descriptor = Object.getOwnPropertyDescriptor(input, index);
    if (!descriptor || !('value' in descriptor)) throw new SingularityError('INVALID_INPUT', 'Candidates require own data elements; no holes or accessors');
    const entry = record(descriptor.value, ['id', 'snapshot'], 'candidate');
    const id = validateId(entry.id);
    if (ids.has(id)) throw new SingularityError('DUPLICATE_ID', 'Candidate IDs must be unique');
    ids.add(id);
    const candidate = validateSnapshot(entry.snapshot);
    sameScope(observation, candidate);
    candidates.push({ id, snapshot: candidate });
  }
  const ranking = assess(observation, candidates);
  const result = (status: MatchResult['status'], reason: MatchReason, candidateId: string | null = null, omissions: OmissionCheck[] = []): MatchResult =>
    ({ policy: POLICY_VERSION, status, candidateId, reason, candidates: ranking, omissions });
  if (candidates.length === 0) return result('unmatched', 'no-candidates');
  if (!evaluate(observation, observation).qualifies || families.some(f => !evaluate(observation, observation, f).qualifies)) {
    return result('abstain', 'insufficient-observation');
  }
  const winner = best(ranking, c => c.qualifies);
  if (!winner) {
    const uncertain = ranking.some(c => c.contradictions.length === 0 &&
      (c.coverage < POLICY.minCoverage || c.comparableFamilies.length < POLICY.minFamilies));
    return result(uncertain ? 'abstain' : 'unmatched', uncertain ? 'insufficient-candidate-evidence' : 'no-candidate-qualified');
  }
  if (!marginPass(winner, runnerUp(ranking, winner.id))) return result('abstain', 'ambiguous-candidates');
  const omissions = families.map((omitted): OmissionCheck => {
    // Reconsider ALL candidates. Omitting platform also removes its contradiction veto.
    const reduced = assess(observation, candidates, omitted);
    const selected = reduced.find(c => c.id === winner.id)!;
    const runner = runnerUp(reduced, winner.id);
    return { omitted, passes: selected.qualifies && marginPass(selected, runner), candidateId: winner.id,
      runnerUpId: runner?.id ?? null, margin: runner ? selected.similarity - runner.similarity : null,
      similarity: selected.similarity, coverage: selected.coverage, comparableFamilies: selected.comparableFamilies };
  });
  if (omissions.some(o => !o.passes)) return result('abstain', 'unstable-under-omission', null, omissions);
  return result('matched', 'stable-candidate', winner.id, omissions);
}
