import { validateSnapshot } from './schema.js';
import { SingularityError, type Snapshot } from './types.js';

/** Frozen v1 tuple format: scope and schema are part of the preimage. */
export function canonicalize(snapshot: Snapshot): string {
  const { schema, scope, signals: s } = validateSnapshot(snapshot);
  return JSON.stringify([schema, scope, s.platform, s.cores, s.memory, s.language, s.timezone]);
}
/** SHA-256 identifies this observation, NOT a unique physical device. Requires Web Crypto. */
export async function digest(snapshot: Snapshot): Promise<string> {
  const canonical = canonicalize(snapshot);
  if (typeof globalThis.crypto?.subtle?.digest !== 'function') {
    throw new SingularityError('CRYPTO_UNAVAILABLE', 'SHA-256 requires Web Crypto (HTTPS or localhost in browsers)');
  }
  const bytes = await globalThis.crypto.subtle.digest('SHA-256', new TextEncoder().encode(canonical));
  return `sg1_${Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('')}`;
}
