import { collect, type CollectOptions } from './collect.js';
import { DETAILED_SCHEMA, PROBE_REVISION, DETAIL_KEYS, validateDetailedSnapshot, type DetailedSnapshot, type DetailKey } from './detailed-schema.js';
import { SingularityError } from './types.js';

/** Synchronous injected probes are for testing or an existing observation pipeline. */
export type DetailProbes = Readonly<Partial<Record<DetailKey, () => unknown>>>;
export interface DetailedCollectOptions extends CollectOptions { readonly probes?: DetailProbes }
const FONT_NAMES = Object.freeze(['Arial', 'Arial Black', 'Calibri', 'Cambria', 'Candara', 'Comic Sans MS', 'Consolas',
  'Courier New', 'Georgia', 'Helvetica', 'Impact', 'Menlo', 'Monaco', 'Segoe UI', 'Times New Roman', 'Verdana']);
const SAMPLE = 'mmmmmmmmmmlliWW0123456789';
async function hash(value: string): Promise<string> {
  if (typeof globalThis.crypto?.subtle?.digest !== 'function') throw new SingularityError('CRYPTO_UNAVAILABLE', 'SHA-256 requires Web Crypto');
  const bytes = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(value));
  return Array.from(new Uint8Array(bytes), b => b.toString(16).padStart(2, '0')).join('');
}
function gpuProbe(doc: Document): string | null {
  const canvas = doc.createElement('canvas');
  canvas.width = canvas.height = 1;
  const gl = canvas.getContext('webgl', { failIfMajorPerformanceCaveat: true });
  if (!gl) return null;
  try {
    const ext = gl.getExtension('WEBGL_debug_renderer_info');
    if (!ext) return null;
    const renderer: unknown = gl.getParameter(ext.UNMASKED_RENDERER_WEBGL);
    if (typeof renderer !== 'string' || renderer.length > 512) return null;
    // Do not guess a model from masked/generic/software renderers or strip driver/model distinctions.
    if (/swiftshader|llvmpipe|software|^apple gpu$|^webkit|^angle$/i.test(renderer.trim())) return null;
    return renderer.trim().toLowerCase().replace(/\s+/g, ' ') || null;
  } finally { gl.getExtension('WEBGL_lose_context')?.loseContext(); }
}
function context2d(doc: Document): CanvasRenderingContext2D | null {
  const canvas = doc.createElement('canvas');
  canvas.width = 240; canvas.height = 80;
  const ctx = canvas.getContext('2d');
  if (ctx) { ctx.direction = 'ltr'; if ('lang' in ctx) (ctx as CanvasRenderingContext2D & {lang: string}).lang = 'en'; }
  return ctx;
}
function fontsProbe(doc: Document): string | null {
  const ctx = context2d(doc); if (!ctx) return null;
  const fallbacks = ['monospace', 'sans-serif', 'serif'];
  const width = (font: string): number => { ctx.font = `72px ${font}`; return ctx.measureText(SAMPLE).width; };
  const baseline = fallbacks.map(width);
  if (baseline.some(w => !Number.isFinite(w) || w <= 0)) return null;
  const bits = FONT_NAMES.map(name => fallbacks.some((fallback, i) => width(`"${name}",${fallback}`) !== baseline[i]) ? '1' : '0').join('');
  return bits.includes('1') ? bits : null;
}
function canvasProbe(doc: Document): string | null {
  const ctx = context2d(doc); if (!ctx) return null;
  ctx.fillStyle = '#153a2b'; ctx.fillRect(0, 0, 240, 80);
  ctx.fillStyle = '#b7e49e'; ctx.fillRect(7, 9, 83, 29);
  ctx.font = '17px Arial'; ctx.textBaseline = 'alphabetic'; ctx.fillStyle = '#eb87ad';
  ctx.fillText('Singularity 0123 Ω ≠', 13, 32);
  ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = 'rgba(50,140,220,0.7)';
  ctx.beginPath(); ctx.arc(118, 42, 27, 0, Math.PI * 2); ctx.fill();
  return ctx.canvas.toDataURL('image/png');
}
function readStable(probe: (() => unknown) | undefined, maximum: number): string | null {
  try {
    const first = probe?.();
    if (typeof first !== 'string' || first.length === 0 || first.length > maximum) return null;
    return probe?.() === first ? first : null;
  } catch { return null; }
}
/** Fixed-size local probes only. No network, storage, screen dimensions or prompts. */
export async function collectDetailed(options: DetailedCollectOptions): Promise<DetailedSnapshot> {
  const coarse = collect(options);
  let probes = options.probes ?? {};
  let frame: HTMLIFrameElement | undefined;
  const raw: Record<DetailKey, string | null> = {gpu: null, fonts: null, canvas: null};
  try {
    if (!options.probes && !options.environment) {
      // A fresh about:blank document excludes host CSS and downloaded @font-face
      // definitions. No src, scripts or external resources are inserted.
      frame = document.createElement('iframe');
      frame.hidden = true;
      frame.style.display = 'none';
      frame.setAttribute('aria-hidden', 'true');
      frame.setAttribute('sandbox', 'allow-same-origin');
      document.documentElement.appendChild(frame);
      const doc = frame.contentDocument;
      if (doc) probes = {gpu: () => gpuProbe(doc), fonts: () => fontsProbe(doc), canvas: () => canvasProbe(doc)};
    }
    for (const key of DETAIL_KEYS) {
      // Access to injected properties may throw. Failure is never a matching value.
      try { raw[key] = readStable(probes[key], key === 'canvas' ? 65536 : 512); } catch { /* unavailable */ }
    }
  } catch { /* DOM isolation unavailable: keep detail null. */ }
  finally { frame?.remove(); }
  const detail: Record<DetailKey, string | null> = {gpu: null, fonts: null, canvas: null};
  for (const key of DETAIL_KEYS) {
    if (raw[key] !== null) detail[key] = await hash(JSON.stringify([PROBE_REVISION, coarse.scope, key, raw[key]]));
  }
  return validateDetailedSnapshot({...coarse, schema: DETAILED_SCHEMA, probe: PROBE_REVISION, detail});
}
export function canonicalizeDetailed(value: DetailedSnapshot): string {
  const s = validateDetailedSnapshot(value), c = s.signals;
  return JSON.stringify([s.schema, s.scope, s.probe, c.platform, c.cores, c.memory, c.language, c.timezone,
    s.detail.gpu, s.detail.fonts, s.detail.canvas]);
}
export async function digestDetailed(snapshot: DetailedSnapshot): Promise<string> {
  return 'sg2_' + await hash(canonicalizeDetailed(snapshot));
}
