import { collect } from './collect.js';
import { canvasProbe, fontsProbe, gpuProbe, hash, readStable, type DetailedCollectOptions } from './detailed.js';
import { RESILIENT_SCHEMA, RESILIENT_PROBE_REVISION, RESILIENT_DETAIL_KEYS, validateResilientSnapshot, type ResilientSnapshot, type ResilientDetailKey, type RenderingEngine } from './resilient-schema.js';

export type ResilientCollectOptions = DetailedCollectOptions;
function renderingEngine(options: ResilientCollectOptions): RenderingEngine | null {
  try {
    const ua: unknown = options.environment ? options.environment.userAgent : navigator.userAgent;
    if (typeof ua !== 'string' || ua.length > 512) return null;
    // iOS browser brands usually share WebKit. Do not treat brands as engines.
    if (/iPhone|iPad|iPod/.test(ua) && /AppleWebKit\//.test(ua)) return 'webkit';
    if (/Chrome\/|Chromium\//.test(ua) && /AppleWebKit\//.test(ua)) return 'blink';
    if (/Gecko\/\d/.test(ua) && /Firefox\//.test(ua)) return 'gecko';
    if (/AppleWebKit\//.test(ua) && /Version\/.*Safari\//.test(ua)) return 'webkit';
  } catch { /* Unknown context cannot justify rendering tolerance. */ }
  return null;
}
// Immutable web/v2 panel. All font bits form ONE evidence family, not 64 votes.
const FONT_NAMES = Object.freeze([
  'Arial', 'Arial Black', 'Calibri', 'Cambria', 'Candara', 'Comic Sans MS', 'Consolas', 'Courier New',
  'Georgia', 'Helvetica', 'Impact', 'Menlo', 'Monaco', 'Segoe UI', 'Times New Roman', 'Verdana',
  'Aptos', 'Aptos Display', 'Bahnschrift', 'Book Antiqua', 'Bookman Old Style', 'Century Gothic', 'Corbel', 'Franklin Gothic Medium',
  'Garamond', 'Lucida Console', 'Lucida Sans Unicode', 'Palatino Linotype', 'Segoe UI Variable', 'Tahoma', 'Trebuchet MS', 'Yu Gothic',
  'American Typewriter', 'Avenir', 'Avenir Next', 'Baskerville', 'Bodoni 72', 'Chalkboard', 'Didot', 'Futura',
  'Gill Sans', 'Helvetica Neue', 'Hoefler Text', 'Optima', 'Palatino', 'Papyrus', 'Rockwell', 'SF Pro Text',
  'DejaVu Sans', 'DejaVu Serif', 'Liberation Sans', 'Liberation Mono', 'Noto Sans', 'Noto Serif', 'Ubuntu', 'Cantarell',
  'Adobe Caslon Pro', 'Myriad Pro', 'Minion Pro', 'Source Code Pro', 'Fira Code', 'JetBrains Mono', 'Roboto', 'Droid Sans',
]);

/** Conservative model allowlist. Unknown, masked and software renderers stay null. */
export function normalizeGPU(value: unknown): string | null {
  if (typeof value !== 'string' || value.length > 512) return null;
  let model = value.trim().toLowerCase().replace(/[®™]/g, '').replace(/\((?:r|tm)\)/g, '').replace(/\s+/g, ' ');
  if (/swiftshader|llvmpipe|softpipe|software|virgl|virtualbox|vmware/.test(model)) return null;
  if (/^angle\s*\(/.test(model)) {
    const wrapper = /^angle\s*\([^,]+,\s*(.+),\s*(?:unspecified version|d3d11|d3d12|opengl[^,]*|vulkan[^,]*|metal[^,]*)\)$/.exec(model);
    if (!wrapper) return null;
    model = wrapper[1]!;
  }
  model = model.replace(/^angle metal renderer:\s*/, '')
    .replace(/\s*\(0x[0-9a-f]+\)/g, '')
    .replace(/\s+direct3d(?:11|12)(?:\s+vs_\d+_\d+\s+ps_\d+_\d+)?$/, '')
    .replace(/\s+opengl engine$/, '').replace(/\/pcie\/sse2$/, '').trim().replace(/\s+/g, ' ');
  if (/^geforce /.test(model)) model = 'nvidia ' + model;
  model = model.replace(/^(nvidia geforce (?:gtx|rtx|gt|mx)) ?(\d)/, '$1 $2')
    .replace(/^(amd radeon rx) ?(\d)/, '$1 $2')
    .replace(/^(intel arc [ab]\d{3}m?) graphics$/, '$1');
  const recognized = [
    /^apple m[1-9]\d*(?: pro| max| ultra)?$/,
    /^nvidia geforce (?:gtx|rtx|gt|mx) ?\d{3,4}(?: ti| super| laptop gpu| mobile)*$/,
    /^nvidia (?:quadro|rtx) [a-z]?\d{3,4}(?: ada generation| laptop gpu)?$/,
    /^amd radeon (?:rx ?\d{3,4}(?: xt| xtx| gre|m|s)*|pro [a-z]?\d{3,4}[a-z]?|vega \d{1,2})$/,
    /^intel (?:uhd|hd) graphics \d{3,4}$/,
    /^intel iris (?:plus|pro) graphics \d{3,4}$/,
    /^intel arc [ab]\d{3}(?:m)?(?: graphics)?$/,
  ];
  return recognized.some(pattern => pattern.test(model)) ? model : null;
}

/** Storage-free local collection; no screens, browser versions, network or permission prompts. */
export async function collectResilient(options: ResilientCollectOptions): Promise<ResilientSnapshot> {
  const coarse = collect(options);
  let probes = options.probes ?? {};
  let frame: HTMLIFrameElement | undefined;
  const raw: Record<ResilientDetailKey, string | null> = {gpu: null, fonts: null, canvas: null};
  try {
    if (!options.probes && !options.environment) {
      frame = document.createElement('iframe');
      frame.hidden = true; frame.style.display = 'none';
      frame.setAttribute('aria-hidden', 'true'); frame.setAttribute('sandbox', 'allow-same-origin');
      document.documentElement.appendChild(frame);
      const doc = frame.contentDocument;
      if (doc) probes = {gpu: () => gpuProbe(doc), fonts: () => fontsProbe(doc, FONT_NAMES), canvas: () => canvasProbe(doc)};
    }
    for (const key of RESILIENT_DETAIL_KEYS) {
      try { raw[key] = readStable(probes[key], key === 'canvas' ? 76800 : 512); } catch { /* unavailable */ }
    }
  } catch { /* No isolated DOM: no detailed evidence. */ }
  finally { frame?.remove(); }
  raw.gpu = normalizeGPU(raw.gpu);
  const detail: Record<ResilientDetailKey, string | null> = {gpu: null, fonts: null, canvas: null};
  for (const key of RESILIENT_DETAIL_KEYS) if (raw[key] !== null) {
    detail[key] = await hash(JSON.stringify([RESILIENT_PROBE_REVISION, coarse.scope, key, raw[key]]));
  }
  return validateResilientSnapshot({...coarse, schema: RESILIENT_SCHEMA, probe: RESILIENT_PROBE_REVISION, engine: renderingEngine(options), detail});
}

export function canonicalizeResilient(value: ResilientSnapshot): string {
  const s = validateResilientSnapshot(value), c = s.signals;
  return JSON.stringify([s.schema, s.scope, s.probe, s.engine, c.platform, c.cores, c.memory, c.language, c.timezone,
    s.detail.gpu, s.detail.fonts, s.detail.canvas]);
}

export async function digestResilient(snapshot: ResilientSnapshot): Promise<string> {
  return 'sg3_' + await hash(canonicalizeResilient(snapshot));
}

/** Repeatable scoped profile code, not a unique hardware ID or authentication credential.
 * Excludes rendering, language, timezone and memory. Never substitutes a weaker projection.
 */
export async function continuityCode(value: ResilientSnapshot): Promise<string | null> {
  const s = validateResilientSnapshot(value), c = s.signals;
  if (c.platform === null || c.cores === null || s.detail.gpu === null || s.detail.fonts === null) return null;
  return 'sc1_' + await hash(JSON.stringify(['continuity/v1', s.scope, s.probe, c.platform, c.cores, s.detail.gpu, s.detail.fonts]));
}
