import { CORE_BUCKETS, MEMORY_BUCKETS, validateScope, validateSnapshot } from './schema.js';
import { SCHEMA, SingularityError, type Platform, type Snapshot } from './types.js';

/** An injectable adapter for tests or an existing collection pipeline. No hardware IDs. */
export interface Environment {
  readonly userAgent?: unknown;
  readonly platform?: unknown;
  readonly hardwareConcurrency?: unknown;
  readonly deviceMemory?: unknown;
  readonly language?: unknown;
  readonly timezone?: unknown;
}
export interface CollectOptions { readonly scope: string; readonly environment?: Environment }
function safeRead(get: () => unknown): unknown { try { return get(); } catch { return undefined; } }
function text(value: unknown, max: number): string | null {
  return typeof value === 'string' && value.length <= max && value.length > 0 ? value : null;
}
function platformFamily(ua: unknown, platform: unknown): Platform | null {
  const source = `${text(ua, 512) ?? ''} ${text(platform, 64) ?? ''}`.toLowerCase();
  if (/android/.test(source)) return 'android';
  if (/iphone|ipad|ipod/.test(source)) return 'ios';
  if (/cros|chrome os/.test(source)) return 'chromeos';
  if (/windows|win32|win64/.test(source)) return 'windows';
  if (/macintosh|macintel|mac os|macos/.test(source)) return 'macos';
  if (/linux/.test(source)) return 'linux';
  return null;
}
function bucket(value: unknown, bins: readonly number[]): number | null {
  if (typeof value !== 'number' || !Number.isFinite(value) || value <= 0 || value > 4096) return null;
  // Floor to powers of two; observed resource limits remain browser-dependent.
  let result = bins[0] ?? 1;
  for (const bin of bins) if (bin <= value) result = bin;
  return result;
}
function browserEnvironment(): Environment {
  if (typeof window === 'undefined' || typeof navigator === 'undefined') {
    throw new SingularityError('BROWSER_UNAVAILABLE', 'collect requires a browser or an explicit environment adapter');
  }
  const nav = navigator as Navigator & { deviceMemory?: unknown };
  return {
    userAgent: safeRead(() => nav.userAgent), platform: safeRead(() => nav.platform),
    hardwareConcurrency: safeRead(() => nav.hardwareConcurrency), deviceMemory: safeRead(() => nav.deviceMemory),
    language: safeRead(() => nav.language), timezone: safeRead(() => Intl.DateTimeFormat().resolvedOptions().timeZone),
  };
}
/** Synchronous, bounded set of reads; no timers, workers, prompts, storage or network. */
export function collect(options: CollectOptions): Snapshot {
  if (!options || typeof options !== 'object') throw new SingularityError('INVALID_INPUT', 'Expected collection options');
  const scope = validateScope(options.scope);
  const env = options.environment ?? browserEnvironment();
  const read = (key: keyof Environment): unknown => safeRead(() => env[key]);
  const language = text(read('language'), 64)?.toLowerCase().split('-')[0] ?? null;
  const timezone = text(read('timezone'), 80);
  return validateSnapshot({ schema: SCHEMA, scope, signals: {
    platform: platformFamily(read('userAgent'), read('platform')),
    cores: bucket(read('hardwareConcurrency'), CORE_BUCKETS), memory: bucket(read('deviceMemory'), MEMORY_BUCKETS),
    language: language && /^[a-z]{2,8}$/.test(language) ? language : null,
    timezone: timezone && /^[A-Za-z0-9_+/-]{1,80}$/.test(timezone) ? timezone : null,
  } });
}
