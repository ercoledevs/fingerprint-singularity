import { collect, collectDetailed } from '../dist/index.js';

/** Optional network adapter. The core library remains stateless. */
export function createAgent({ publicKey, endpoint = new URL(import.meta.url).origin, mode = 'detailed' }) {
  if (!/^pk_[a-f0-9]{32}$/.test(publicKey)) throw new TypeError('Invalid public key');
  if (!['detailed', 'legacy'].includes(mode)) throw new TypeError('Invalid collection mode');
  const base = new URL(endpoint);
  if (base.protocol !== 'https:' && !['localhost', '127.0.0.1', '[::1]'].includes(base.hostname)) throw new TypeError('Use HTTPS for remote endpoints');
  const key = `singularity:${base.origin}:${publicKey}`;
  return {
    async identify({ remember = false, requestId = crypto.randomUUID() } = {}) {
      let token = null;
      if (remember) token = localStorage.getItem(key);
      const snapshot = mode === 'detailed' ? await collectDetailed({scope: publicKey}) : collect({scope: publicKey});
      const response = await fetch(`${base.origin}/api/v1/identify/${publicKey}`, {
        method: 'POST', credentials: 'omit', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({snapshot, requestId, remember, token}),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(typeof data.detail === 'string' ? data.detail : `Identification failed (${response.status})`);
      if (remember && data.token) localStorage.setItem(key, data.token);
      return data;
    },
    forget() { localStorage.removeItem(key); },
  };
}
