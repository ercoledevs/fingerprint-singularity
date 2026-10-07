import { record, validateScope, validateSnapshot } from './schema.js';
import { SCHEMA, SingularityError, type Signals } from './types.js';

export const DETAILED_SCHEMA = 'singularity/v2' as const;
export const PROBE_REVISION = 'web/v1' as const;
export const DETAIL_KEYS = Object.freeze(['gpu', 'fonts', 'canvas'] as const);
export type DetailKey = typeof DETAIL_KEYS[number];
export interface DetailedSnapshot {
  readonly schema: typeof DETAILED_SCHEMA;
  readonly scope: string;
  readonly signals: Signals;
  readonly probe: typeof PROBE_REVISION;
  /** Scope-separated hashes of bounded probes; unavailable/unstable observations are null. */
  readonly detail: Readonly<Record<DetailKey, string | null>>;
}
export interface DetailedCandidate { readonly id: string; readonly snapshot: DetailedSnapshot }
export function validateDetailedSnapshot(value: unknown): DetailedSnapshot {
  const outer = record(value, ['schema', 'scope', 'signals', 'probe', 'detail'], 'detailed snapshot');
  if (outer.schema !== DETAILED_SCHEMA || outer.probe !== PROBE_REVISION) {
    throw new SingularityError('INCOMPATIBLE_SCHEMA', 'Expected singularity/v2 with web/v1 probes');
  }
  const scope = validateScope(outer.scope);
  const { signals } = validateSnapshot({ schema: SCHEMA, scope, signals: outer.signals });
  const detail = record(outer.detail, [...DETAIL_KEYS], 'detail');
  for (const key of DETAIL_KEYS) if (detail[key] !== null &&
    (typeof detail[key] !== 'string' || !/^[a-f0-9]{64}$/.test(detail[key]))) {
    throw new SingularityError('INVALID_INPUT', 'Invalid detail hash');
  }
  return { schema: DETAILED_SCHEMA, scope, signals, probe: PROBE_REVISION,
    detail: { gpu: detail.gpu as string | null, fonts: detail.fonts as string | null, canvas: detail.canvas as string | null } };
}
export function parseDetailedSnapshot(json: string): DetailedSnapshot {
  if (typeof json !== 'string') throw new SingularityError('INVALID_INPUT', 'Expected JSON text');
  if (json.length > 4096) throw new SingularityError('LIMIT_EXCEEDED', 'Detailed JSON exceeds 4096 code units');
  let value: unknown;
  try { value = JSON.parse(json) as unknown; } catch { throw new SingularityError('INVALID_INPUT', 'Invalid JSON'); }
  return validateDetailedSnapshot(value);
}
