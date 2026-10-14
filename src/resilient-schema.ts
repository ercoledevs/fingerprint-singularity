import { record, validateScope, validateSnapshot } from './schema.js';
import { SCHEMA, SingularityError, type Signals } from './types.js';

export const RESILIENT_SCHEMA = 'singularity/v3' as const;
export const RESILIENT_PROBE_REVISION = 'web/v2' as const;
export const RESILIENT_DETAIL_KEYS = Object.freeze(['gpu', 'fonts', 'canvas'] as const);
export type ResilientDetailKey = typeof RESILIENT_DETAIL_KEYS[number];
export type RenderingEngine = 'blink' | 'gecko' | 'webkit';
export interface ResilientSnapshot {
  readonly schema: typeof RESILIENT_SCHEMA;
  readonly scope: string;
  readonly signals: Signals;
  readonly probe: typeof RESILIENT_PROBE_REVISION;
  /** Declared engine family, used only to interpret rendering differences. */
  readonly engine: RenderingEngine | null;
  /** Scope-separated hashes of bounded probes; unavailable/unstable observations are null. */
  readonly detail: Readonly<Record<ResilientDetailKey, string | null>>;
}
export interface ResilientCandidate { readonly id: string; readonly snapshot: ResilientSnapshot }
export function validateResilientSnapshot(value: unknown): ResilientSnapshot {
  const outer = record(value, ['schema', 'scope', 'signals', 'probe', 'engine', 'detail'], 'resilient snapshot');
  if (outer.schema !== RESILIENT_SCHEMA || outer.probe !== RESILIENT_PROBE_REVISION) {
    throw new SingularityError('INCOMPATIBLE_SCHEMA', 'Expected singularity/v3 with web/v2 probes');
  }
  const scope = validateScope(outer.scope);
  if (outer.engine !== null && !['blink', 'gecko', 'webkit'].includes(outer.engine as string)) {
    throw new SingularityError('INVALID_INPUT', 'Invalid rendering engine');
  }
  const { signals } = validateSnapshot({ schema: SCHEMA, scope, signals: outer.signals });
  const detail = record(outer.detail, [...RESILIENT_DETAIL_KEYS], 'detail');
  for (const key of RESILIENT_DETAIL_KEYS) if (detail[key] !== null &&
    (typeof detail[key] !== 'string' || !/^[a-f0-9]{64}$/.test(detail[key]))) {
    throw new SingularityError('INVALID_INPUT', 'Invalid detail hash');
  }
  return { schema: RESILIENT_SCHEMA, scope, signals, probe: RESILIENT_PROBE_REVISION, engine: outer.engine as RenderingEngine | null,
    detail: { gpu: detail.gpu as string | null, fonts: detail.fonts as string | null, canvas: detail.canvas as string | null } };
}
export function parseResilientSnapshot(json: string): ResilientSnapshot {
  if (typeof json !== 'string') throw new SingularityError('INVALID_INPUT', 'Expected JSON text');
  if (json.length > 4096) throw new SingularityError('LIMIT_EXCEEDED', 'Resilient JSON exceeds 4096 code units');
  let value: unknown;
  try { value = JSON.parse(json) as unknown; } catch { throw new SingularityError('INVALID_INPUT', 'Invalid JSON'); }
  return validateResilientSnapshot(value);
}
