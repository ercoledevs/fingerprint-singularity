export const SCHEMA = 'singularity/v1' as const;
export const POLICY_VERSION = 'envelope/v1' as const;
export type Platform = 'windows' | 'macos' | 'ios' | 'android' | 'linux' | 'chromeos';
export type Family = 'platform' | 'compute' | 'locale';
export interface Signals {
  readonly platform: Platform | null;
  readonly cores: number | null;
  readonly memory: number | null;
  readonly language: string | null;
  readonly timezone: string | null;
}
export type Signal = keyof Signals;
export interface Snapshot {
  readonly schema: typeof SCHEMA;
  /** Application namespace, not a secret or an access-control boundary. */
  readonly scope: string;
  readonly signals: Signals;
}
export interface Candidate { readonly id: string; readonly snapshot: Snapshot }
export interface Contribution {
  readonly signal: Signal;
  readonly family: Family;
  readonly weight: number;
  readonly state: 'equal' | 'different' | 'missing';
}
export interface Comparison {
  readonly policy: typeof POLICY_VERSION;
  /** Heuristic agreement, never an identity probability. Missing values earn zero. */
  readonly similarity: number;
  readonly coverage: number;
  readonly comparableFamilies: readonly Family[];
  readonly contradictions: readonly Signal[];
  readonly contributions: readonly Contribution[];
  readonly qualifies: boolean;
}
export interface CandidateComparison extends Comparison { readonly id: string }
export interface OmissionCheck {
  readonly omitted: Family;
  readonly passes: boolean;
  readonly candidateId: string;
  readonly runnerUpId: string | null;
  readonly margin: number | null;
  readonly similarity: number;
  readonly coverage: number;
  readonly comparableFamilies: readonly Family[];
}
export type MatchReason = 'stable-candidate' | 'no-candidates' | 'insufficient-observation'
  | 'insufficient-candidate-evidence' | 'no-candidate-qualified' | 'ambiguous-candidates'
  | 'unstable-under-omission';
export interface MatchResult {
  readonly policy: typeof POLICY_VERSION;
  readonly status: 'matched' | 'unmatched' | 'abstain';
  readonly candidateId: string | null;
  readonly reason: MatchReason;
  readonly candidates: readonly CandidateComparison[];
  readonly omissions: readonly OmissionCheck[];
}
export type ErrorCode = 'INVALID_INPUT' | 'INCOMPATIBLE_SCHEMA' | 'SCOPE_MISMATCH'
  | 'LIMIT_EXCEEDED' | 'DUPLICATE_ID' | 'BROWSER_UNAVAILABLE' | 'CRYPTO_UNAVAILABLE';
export class SingularityError extends Error {
  constructor(public readonly code: ErrorCode, message: string) {
    super(message);
    this.name = 'SingularityError';
  }
}
