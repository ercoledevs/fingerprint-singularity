import { SCHEMA } from '../dist/index.js';
export function snapshot(changes = {}, scope = 'example.test') {
  return { schema: SCHEMA, scope, signals: { platform: 'linux', cores: 8, memory: 8, language: 'en', timezone: 'UTC', ...changes } };
}
export const environment = Object.freeze({ userAgent: 'Mozilla/5.0 (X11; Linux x86_64) Chrome/123.0.0.0', platform: 'Linux x86_64', hardwareConcurrency: 8, deviceMemory: 8, language: 'en-US', timezone: 'UTC' });
export const candidate = (id = 'known', changes = {}) => ({ id, snapshot: snapshot(changes) });
