import { DETAIL_KEYS, validateDetailedSnapshot, type DetailedCandidate, type DetailedSnapshot, type DetailKey } from './detailed-schema.js';
import { LIMITS, record, validateId } from './schema.js';
import { SingularityError } from './types.js';

export const DETAILED_POLICY = Object.freeze({version: 'support/v2', minDetails: 2} as const);
export interface DetailedComparison {
  readonly policy: 'support/v2';
  /** Descriptive signal agreement and availability, not a calibrated identity probability. */
  readonly similarity: number;
  readonly coverage: number;
  readonly comparableDetails: readonly DetailKey[];
  readonly supportingDetails: readonly DetailKey[];
  readonly contradictions: readonly string[];
  readonly qualifies: boolean;
}
export interface DetailedMatchResult {
  readonly policy: 'support/v2';
  readonly status: 'matched' | 'unmatched' | 'abstain';
  readonly candidateId: string | null;
  readonly reason: 'supported-candidate' | 'no-candidates' | 'insufficient-detail' | 'insufficient-candidate-evidence' | 'no-candidate-qualified' | 'ambiguous-candidates';
  readonly candidates: readonly (DetailedComparison & {readonly id: string})[];
  readonly omissions: readonly never[];
}
function sameScope(a: DetailedSnapshot, b: DetailedSnapshot): void {
  if (a.scope !== b.scope) throw new SingularityError('SCOPE_MISMATCH', 'Snapshots belong to different scopes');
}
function evaluate(a: DetailedSnapshot, b: DetailedSnapshot): DetailedComparison {
  const contradictions: string[] = [];
  for (const key of ['platform', 'cores'] as const) if (a.signals[key] !== null && b.signals[key] !== null && a.signals[key] !== b.signals[key]) contradictions.push(key);
  const comparableDetails = DETAIL_KEYS.filter(k => a.detail[k] !== null && b.detail[k] !== null);
  const supportingDetails = comparableDetails.filter(k => a.detail[k] === b.detail[k]);
  contradictions.push(...comparableDetails.filter(k => a.detail[k] !== b.detail[k]));
  const coarseKnown = a.signals.platform !== null && b.signals.platform !== null && a.signals.cores !== null && b.signals.cores !== null;
  return {policy: DETAILED_POLICY.version, similarity: supportingDetails.length / 3, coverage: comparableDetails.length / 3,
    comparableDetails, supportingDetails, contradictions,
    qualifies: coarseKnown && contradictions.length === 0 && supportingDetails.length >= DETAILED_POLICY.minDetails};
}
export function compareDetailed(left: DetailedSnapshot, right: DetailedSnapshot): DetailedComparison {
  const a = validateDetailedSnapshot(left), b = validateDetailedSnapshot(right); sameScope(a, b); return evaluate(a, b);
}
export function matchDetailed(value: DetailedSnapshot, input: readonly DetailedCandidate[]): DetailedMatchResult {
  if (!Array.isArray(input)) throw new SingularityError('INVALID_INPUT', 'Candidates must be an array');
  if (input.length > LIMITS.candidates) throw new SingularityError('LIMIT_EXCEEDED', 'At most 256 candidates; no truncation');
  const observation = validateDetailedSnapshot(value), ids = new Set<string>();
  const candidates: (DetailedComparison & {id: string})[] = [];
  for (let i = 0; i < input.length; i++) {
    const d = Object.getOwnPropertyDescriptor(input, i);
    if (!d || !('value' in d)) throw new SingularityError('INVALID_INPUT', 'Candidates require own data elements');
    const entry = record(d.value, ['id', 'snapshot'], 'candidate'), id = validateId(entry.id);
    if (ids.has(id)) throw new SingularityError('DUPLICATE_ID', 'Candidate IDs must be unique');
    ids.add(id); const snapshot = validateDetailedSnapshot(entry.snapshot); sameScope(observation, snapshot);
    candidates.push({id, ...evaluate(observation, snapshot)});
  }
  const result = (status: DetailedMatchResult['status'], reason: DetailedMatchResult['reason'], candidateId: string | null = null): DetailedMatchResult =>
    ({policy: DETAILED_POLICY.version, status, candidateId, reason, candidates, omissions: []});
  if (!evaluate(observation, observation).qualifies) return result('abstain', 'insufficient-detail');
  if (candidates.length === 0) return result('unmatched', 'no-candidates');
  const eligible = candidates.filter(c => c.qualifies);
  if (eligible.length > 1) return result('abstain', 'ambiguous-candidates');
  // Incomplete compatible contenders remain possible rivals; missing values never disprove them.
  if (candidates.some(c => !c.qualifies && c.contradictions.length === 0)) return result('abstain', 'insufficient-candidate-evidence');
  return eligible[0] ? result('matched', 'supported-candidate', eligible[0].id) : result('unmatched', 'no-candidate-qualified');
}
