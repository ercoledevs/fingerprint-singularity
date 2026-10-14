import { RESILIENT_DETAIL_KEYS, validateResilientSnapshot, type ResilientCandidate, type ResilientSnapshot, type ResilientDetailKey } from './resilient-schema.js';
import { LIMITS, record, validateId } from './schema.js';
import { SingularityError } from './types.js';

export const RESILIENT_POLICY = Object.freeze({version: 'support/v3', minDetails: 2} as const);
export interface ResilientComparison {
  readonly policy: 'support/v3';
  /** Descriptive signal agreement and availability, not a calibrated identity probability. */
  readonly similarity: number;
  readonly coverage: number;
  readonly comparableDetails: readonly ResilientDetailKey[];
  readonly supportingDetails: readonly ResilientDetailKey[];
  readonly contradictions: readonly string[];
  /** All differences, including rendering tolerated across known different engines. */
  readonly differences: readonly ResilientDetailKey[];
  readonly qualifies: boolean;
}
export interface ResilientMatchResult {
  readonly policy: 'support/v3';
  readonly status: 'matched' | 'unmatched' | 'abstain';
  readonly candidateId: string | null;
  readonly reason: 'supported-candidate' | 'no-candidates' | 'insufficient-detail' | 'insufficient-candidate-evidence' | 'no-candidate-qualified' | 'ambiguous-candidates';
  readonly candidates: readonly (ResilientComparison & {readonly id: string})[];
  readonly omissions: readonly never[];
}
function sameScope(a: ResilientSnapshot, b: ResilientSnapshot): void {
  if (a.scope !== b.scope) throw new SingularityError('SCOPE_MISMATCH', 'Snapshots belong to different scopes');
}
function evaluate(a: ResilientSnapshot, b: ResilientSnapshot): ResilientComparison {
  const contradictions: string[] = [];
  for (const key of ['platform', 'cores'] as const) if (a.signals[key] !== null && b.signals[key] !== null && a.signals[key] !== b.signals[key]) contradictions.push(key);
  const comparableDetails = RESILIENT_DETAIL_KEYS.filter(k => a.detail[k] !== null && b.detail[k] !== null);
  const supportingDetails = comparableDetails.filter(k => a.detail[k] === b.detail[k]);
  const differences = comparableDetails.filter(k => a.detail[k] !== b.detail[k]);
  const crossEngine = a.engine !== null && b.engine !== null && a.engine !== b.engine;
  contradictions.push(...differences.filter(k => k !== 'canvas' || !crossEngine));
  const coarseKnown = a.signals.platform !== null && b.signals.platform !== null && a.signals.cores !== null && b.signals.cores !== null;
  return {policy: RESILIENT_POLICY.version, similarity: supportingDetails.length / 3, coverage: comparableDetails.length / 3,
    comparableDetails, supportingDetails, contradictions, differences,
    qualifies: coarseKnown && contradictions.length === 0 && supportingDetails.includes('fonts') && (supportingDetails.includes('gpu') || supportingDetails.includes('canvas'))};
}
export function compareResilient(left: ResilientSnapshot, right: ResilientSnapshot): ResilientComparison {
  const a = validateResilientSnapshot(left), b = validateResilientSnapshot(right); sameScope(a, b); return evaluate(a, b);
}
export function matchResilient(value: ResilientSnapshot, input: readonly ResilientCandidate[]): ResilientMatchResult {
  if (!Array.isArray(input)) throw new SingularityError('INVALID_INPUT', 'Candidates must be an array');
  if (input.length > LIMITS.candidates) throw new SingularityError('LIMIT_EXCEEDED', 'At most 256 candidates; no truncation');
  const observation = validateResilientSnapshot(value), ids = new Set<string>();
  const candidates: (ResilientComparison & {id: string})[] = [];
  for (let i = 0; i < input.length; i++) {
    const d = Object.getOwnPropertyDescriptor(input, i);
    if (!d || !('value' in d)) throw new SingularityError('INVALID_INPUT', 'Candidates require own data elements');
    const entry = record(d.value, ['id', 'snapshot'], 'candidate'), id = validateId(entry.id);
    if (ids.has(id)) throw new SingularityError('DUPLICATE_ID', 'Candidate IDs must be unique');
    ids.add(id); const snapshot = validateResilientSnapshot(entry.snapshot); sameScope(observation, snapshot);
    candidates.push({id, ...evaluate(observation, snapshot)});
  }
  const result = (status: ResilientMatchResult['status'], reason: ResilientMatchResult['reason'], candidateId: string | null = null): ResilientMatchResult =>
    ({policy: RESILIENT_POLICY.version, status, candidateId, reason, candidates, omissions: []});
  if (!evaluate(observation, observation).qualifies) return result('abstain', 'insufficient-detail');
  if (candidates.length === 0) return result('unmatched', 'no-candidates');
  const eligible = candidates.filter(c => c.qualifies);
  if (eligible.length > 1) return result('abstain', 'ambiguous-candidates');
  // Incomplete compatible contenders remain possible rivals; missing values never disprove them.
  if (candidates.some(c => !c.qualifies && c.contradictions.length === 0)) return result('abstain', 'insufficient-candidate-evidence');
  return eligible[0] ? result('matched', 'supported-candidate', eligible[0].id) : result('unmatched', 'no-candidate-qualified');
}
