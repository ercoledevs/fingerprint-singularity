import { SCHEMA, SingularityError, type Snapshot, type Signals } from './types.js';

export const LIMITS = Object.freeze({ candidates: 256, scope: 128, candidateId: 128, snapshotJson: 2048, timezone: 80 });
export const CORE_BUCKETS: readonly number[] = Object.freeze([1, 2, 4, 8, 16, 32, 64]);
export const MEMORY_BUCKETS: readonly number[] = Object.freeze([0.25, 0.5, 1, 2, 4, 8, 16, 32, 64]);
const platforms = ['windows', 'macos', 'ios', 'android', 'linux', 'chromeos'];

/** Reject accessors and unknown keys. JSON text must pass parseSnapshot's size gate. */
export function record(value: unknown, keys: readonly string[], name: string): Record<string, unknown> {
  if (value === null || typeof value !== 'object' || Array.isArray(value)) invalid(name);
  const prototype: unknown = Object.getPrototypeOf(value);
  if (prototype !== Object.prototype && prototype !== null) invalid(name);
  const descriptors = Object.getOwnPropertyDescriptors(value);
  const actualKeys = Reflect.ownKeys(descriptors);
  if (actualKeys.length !== keys.length || actualKeys.some(key => typeof key !== 'string' || !keys.includes(key))) invalid(name);
  const result: Record<string, unknown> = Object.create(null) as Record<string, unknown>;
  for (const key of keys) {
    const descriptor = descriptors[key];
    if (!descriptor || !('value' in descriptor)) invalid(name);
    result[key] = descriptor.value;
  }
  return result;
}
export function invalid(name: string): never {
  throw new SingularityError('INVALID_INPUT', `Invalid ${name}`);
}
export function validateScope(value: unknown): string {
  if (typeof value !== 'string' || value.length < 1 || value.length > LIMITS.scope || !/^[A-Za-z0-9._:/-]+$/.test(value)) invalid('scope');
  return value;
}
export function validateId(value: unknown): string {
  if (typeof value !== 'string' || value.length < 1 || value.length > LIMITS.candidateId || !/^[A-Za-z0-9._:-]+$/.test(value)) invalid('candidate ID');
  return value;
}
export function validateSnapshot(value: unknown): Snapshot {
  const outer = record(value, ['schema', 'scope', 'signals'], 'snapshot shape');
  if (outer.schema !== SCHEMA) throw new SingularityError('INCOMPATIBLE_SCHEMA', `Expected ${SCHEMA}`);
  const scope = validateScope(outer.scope);
  const fields = record(outer.signals, ['platform', 'cores', 'memory', 'language', 'timezone'], 'signal shape');
  if (fields.platform !== null && (typeof fields.platform !== 'string' || !platforms.includes(fields.platform))) invalid('platform');
  for (const [key, buckets] of [['cores', CORE_BUCKETS], ['memory', MEMORY_BUCKETS]] as const) {
    const v = fields[key];
    if (v !== null && (typeof v !== 'number' || !buckets.includes(v))) invalid(key);
  }
  if (fields.language !== null && (typeof fields.language !== 'string' || !/^[a-z]{2,8}$/.test(fields.language))) invalid('language');
  if (fields.timezone !== null && (typeof fields.timezone !== 'string' || fields.timezone.length > LIMITS.timezone || !/^[A-Za-z0-9_+/-]{1,80}$/.test(fields.timezone))) invalid('timezone');
  // Reconstruct a plain snapshot: no unknown properties or caller-owned objects escape.
  return { schema: SCHEMA, scope, signals: { platform: fields.platform, cores: fields.cores, memory: fields.memory, language: fields.language, timezone: fields.timezone } as Signals };
}
export function sameScope(a: Snapshot, b: Snapshot): void {
  if (a.scope !== b.scope) throw new SingularityError('SCOPE_MISMATCH', 'Snapshots belong to different application scopes');
}
/** Bounded JSON transport entry point. Do not JSON.parse unbounded network bodies. */
export function parseSnapshot(json: string): Snapshot {
  if (typeof json !== 'string') invalid('snapshot JSON');
  if (json.length > LIMITS.snapshotJson) throw new SingularityError('LIMIT_EXCEEDED', 'Snapshot JSON exceeds 2048 UTF-16 code units');
  let value: unknown;
  try { value = JSON.parse(json) as unknown; } catch { return invalid('snapshot JSON'); }
  return validateSnapshot(value);
}
