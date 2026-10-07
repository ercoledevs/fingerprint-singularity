<script setup>
import { ref, computed, onMounted } from 'vue';
import { collect } from '../../src/collect.ts';
import { collectDetailed } from '../../src/detailed.ts';

const tab = ref('Live demo'), busy = ref(false), error = ref(''), notice = ref('');
const config = ref(null), user = ref(null), csrf = ref(''), username = ref('admin'), password = ref('');
const result = ref(null), observation = ref(null), remember = ref(false);
const collectionMode = ref('detailed');
const projects = ref([]), project = ref('demo'), events = ref([]), next = ref(null), selected = ref(null);
const filters = ref({prefix: '', method: '', platform: '', after: '', before: ''});
const form = ref({name: '', origins: location.origin, retentionDays: 30, enrollment: true});
const editing = ref(null);
const browserOrigin = location.origin;
const activeProject = computed(() => projects.value.find(p => p._id === project.value));
const snippet = computed(() => `<script type="module">\nimport { createAgent } from "${location.origin}/sdk/agent.js";\nconst agent = createAgent({ publicKey: "${activeProject.value?.publicKey || config.value?.publicKey || 'YOUR_PUBLIC_KEY'}" });\nconst event = await agent.identify();\nconsole.log(event.eventId, event.visitorId);\n<` + '/script>');
const tokenKey = () => `singularity:${location.origin}:${config.value.publicKey}`;
const methodLabel = {provisional: 'New inferred visitor', inferred: 'Inferred visitor', enrolled: 'Remembered browser enrolled', remembered: 'Remembered browser', unassigned: 'Unassigned event'};
const explanations = {
  'candidate-overflow': 'The active candidate set exceeds the comparison limit. This event was saved without assigning a visitor.',
  'ambiguous-candidates': 'Several visitors have similar observations. This event was saved without choosing between them.',
  'unstable-under-omission': 'The match changes when one signal family is removed. This event remains unassigned.',
  'insufficient-observation': 'This browser did not provide enough observations for an assignment.',
  'insufficient-detail': 'This browser did not expose enough stable detail for an assignment. The event is saved without choosing a visitor.',
  'supported-candidate': 'One compatible candidate agrees on at least two available detailed signals, with no observed conflict.',
  'insufficient-candidate-evidence': 'The available candidate evidence is incomplete.',
  'stable-candidate': 'The candidate passed agreement, margin and signal-family omission checks.',
  'no-candidates': 'A new provisional visitor was created from this observation.',
  'no-candidate-qualified': 'No candidate qualified. A new provisional visitor was created.',
  'explicit-enrollment': 'A fresh browser identity was created with an optional possession token.',
  'possession-token': 'A valid token links this event to the browser enrollment.'
};
async function api(path, options = {}) {
  const response = await fetch('/api' + path, {credentials: 'same-origin', ...options, headers: {'Content-Type': 'application/json', 'X-CSRF-Token': csrf.value, ...options.headers}});
  let data; try { data = await response.json(); } catch { throw new Error('The server is unavailable. Try again shortly.'); }
  if (!response.ok) {
    if (response.status === 401) user.value = null;
    throw new Error(typeof data.detail === 'string' ? data.detail : 'Check the entered values and try again.');
  }
  return data;
}
async function action(fn) { busy.value = true; error.value = ''; notice.value = ''; try { await fn(); } catch (e) { error.value = e.message; } finally { busy.value = false; } }
async function loadProjects() { projects.value = await api('/admin/projects'); if (!projects.value.some(p => p._id === project.value)) project.value = 'demo'; }
async function loadEvents(cursor = null) {
  const params = new URLSearchParams({limit: '25'});
  for (const [key, val] of Object.entries(filters.value)) if (val) params.set(key, ['after', 'before'].includes(key) ? new Date(val).toISOString() : val);
  if (cursor) params.set('cursor', cursor);
  const data = await api(`/admin/projects/${project.value}/events?${params}`);
  events.value = data.items; next.value = data.nextCursor; selected.value = null;
}
function navigate(value) { tab.value = value; if (user.value && value === 'Activity') action(() => loadEvents()); }
async function identify() {
  await action(async () => {
    observation.value = collectionMode.value === 'detailed' ? await collectDetailed({scope: config.value.publicKey}) : collect({scope: config.value.publicKey});
    let token = null;
    if (remember.value) { try { token = localStorage.getItem(tokenKey()); } catch { throw new Error('Browser storage is unavailable. Turn off Remember this browser to continue.'); } }
    result.value = await api(`/v1/identify/${config.value.publicKey}`, {method: 'POST', body: JSON.stringify({snapshot: observation.value, requestId: crypto.randomUUID(), remember: remember.value, token})});
    if (result.value.token) { try { localStorage.setItem(tokenKey(), result.value.token); } catch { notice.value = 'Event saved, but this browser could not save its continuity token.'; } }
  });
}
function forget() { try { localStorage.removeItem(tokenKey()); notice.value = 'Local token removed. Server history remains until deletion or retention expiry.'; } catch { error.value = 'Browser storage is unavailable.'; } remember.value = false; }
async function login() { await action(async () => { const data = await api('/admin/login', {method: 'POST', body: JSON.stringify({username: username.value, password: password.value})}); password.value = ''; user.value = data.username; csrf.value = data.csrf; await loadProjects(); await loadEvents(); }); }
async function logout() { await action(async () => { await api('/admin/logout', {method: 'POST'}); user.value = null; events.value = []; selected.value = null; }); }
async function saveProject() { await action(async () => {
  const data = {...form.value, origins: form.value.origins.split(/\n|,/).map(s => s.trim()).filter(Boolean)};
  const p = await api(editing.value ? `/admin/projects/${editing.value}` : '/admin/projects', {method: editing.value ? 'PUT' : 'POST', body: JSON.stringify(data)});
  await loadProjects(); project.value = p._id; editing.value = null; form.value = {name: '', origins: location.origin, retentionDays: 30, enrollment: true}; notice.value = 'Project saved. Copy its snippet from Integration.';
}); }
function edit(p) { editing.value = p._id; form.value = {name: p.name, origins: p.origins.join('\n'), retentionDays: p.retentionDays, enrollment: p.enrollment}; }
async function removeProject(p) { if (!confirm(`Delete project “${p.name}” and all its visitor and event data? This cannot be undone.`)) return; await action(async () => { await api(`/admin/projects/${p._id}`, {method: 'DELETE'}); await loadProjects(); notice.value = 'Project and its data deleted.'; }); }
async function visitorAction(kind) {
  const visitor = selected.value.visitorId;
  const message = kind === 'revoke' ? `Revoke the remembered-browser token for ${visitor}? Event history remains.` : `Delete ${visitor} and all associated events in this project? This cannot be undone.`;
  if (!confirm(message)) return;
  await action(async () => { await api(`/admin/projects/${project.value}/visitors/${visitor}${kind === 'revoke' ? '/revoke' : ''}`, {method: kind === 'revoke' ? 'POST' : 'DELETE'}); await loadEvents(); notice.value = kind === 'revoke' ? 'Token revoked. History retained.' : 'Visitor and associated events deleted.'; });
}
async function copy(text) { try { await navigator.clipboard.writeText(text); notice.value = 'Copied to clipboard.'; } catch { error.value = 'Clipboard unavailable. Select and copy the text manually.'; } }
const formatTime = value => new Date(value).toLocaleString();
onMounted(async () => { await action(async () => { config.value = await api('/config'); try { const s = await api('/admin/session'); user.value = s.username; csrf.value = s.csrf; await loadProjects(); } catch { /* A signed-out console is expected. */ } }); });
</script>

<template>
  <div class="shell">
    <aside class="sidebar">
      <a class="brand" href="#" @click.prevent="navigate('Live demo')"><span class="mark">◎</span><span>singularity<small>IDENTIFICATION PLATFORM</small></span></a>
      <div class="workspace"><span class="avatar">S</span><div>Your workspace<small>Self-hosted instance</small></div><span class="dot"></span></div>
      <p class="nav-label">CONSOLE</p>
      <nav aria-label="Main navigation"><button v-for="(item, i) in ['Live demo', 'Activity', 'Projects', 'Integration']" :key="item" :class="{active: tab === item}" @click="navigate(item)"><span aria-hidden="true">{{ ['◉', '▤', '▦', '⌘'][i] }}</span>{{ item }}<span v-if="tab === item" class="nav-arrow">→</span></button></nav>
      <div class="sidebar-bottom"><span class="small-pill">v0.3 · SELF-HOSTED</span><p>Your infrastructure.<br>Your observations.</p><button v-if="user" class="text-button" @click="logout" :disabled="busy">Sign out · {{ user }}</button><button v-else class="text-button" @click="navigate('Activity')">Open backoffice →</button></div>
    </aside>
    <main>
      <header><span>Workspace <span class="slash">/</span> {{ tab }}</span><span class="status"><i></i>{{ config ? 'API connected' : 'Connecting…' }}</span></header>
      <div class="content">
        <div v-if="error" class="alert error" role="alert"><strong>Something needs attention.</strong> {{ error }}<button aria-label="Dismiss error" @click="error = ''">×</button></div>
        <div v-if="notice" class="alert success" role="status">{{ notice }}<button aria-label="Dismiss notification" @click="notice = ''">×</button></div>
        <template v-if="tab === 'Live demo'">
          <div class="page-heading"><div><p class="eyebrow">OBSERVE. RECOGNIZE. UNDERSTAND.</p><h1>Every visit tells a story.</h1><p>See the identifiers and evidence behind a browser visit, in real time.</p></div><span class="outline-pill">LIVE DEMO</span></div>
          <div class="demo-grid">
            <section class="panel identity-card">
              <div class="section-title"><h2>Your browser identity</h2><span class="badge">{{ result ? methodLabel[result.method] : 'Ready to identify' }}</span></div>
              <div class="identity-art" aria-hidden="true"><div class="orbit o1"></div><div class="orbit o2"></div><div class="orbit o3"></div><span>◎</span><b class="node n1"></b><b class="node n2"></b><b class="node n3"></b></div>
              <p class="eyebrow">{{ result?.method === 'remembered' || result?.method === 'enrolled' ? 'REMEMBERED BROWSER ID' : 'INFERRED VISITOR ID' }}</p>
              <div class="primary-id" data-testid="visitor-id">{{ result ? (result.visitorId || 'Unassigned') : 'Waiting for your first event' }}</div>
              <p class="identity-description">{{ result ? explanations[result.reason] : 'Run identification to collect browser observations and receive a server decision.' }}</p>
              <div class="demo-controls"><button class="primary" @click="identify" :disabled="busy || !config">{{ busy ? 'Identifying…' : result ? 'Identify again' : 'Identify this browser' }} <span aria-hidden="true">↗</span></button><button class="secondary" @click="forget" :disabled="!config || busy">Forget local token</button></div>
              <label>Collection mode<select aria-label="Collection mode" v-model="collectionMode" :disabled="busy"><option value="detailed">Detailed · GPU, fonts and canvas</option><option value="legacy">Legacy · coarse observations only</option></select></label>
              <label class="check"><input type="checkbox" v-model="remember">Remember this browser</label><p class="hint">Optional local token for continuity. Separate browsers and private contexts keep separate storage. Losing the token ends possession-based continuity.</p>
            </section>
            <section class="panel event-card"><div class="section-title"><h2>Event details</h2><span class="tiny-label">SERVER RESPONSE</span></div>
              <dl><dt>Event ID <button v-if="result" class="copy" aria-label="Copy event ID" @click="copy(result.eventId)">Copy</button></dt><dd data-testid="event-id">{{ result?.eventId || '—' }}</dd><dt>Observation digest</dt><dd class="digest">{{ result?.digest || '—' }}</dd><dt>Assignment method</dt><dd>{{ result ? methodLabel[result.method] : '—' }}</dd><dt>Decision reason</dt><dd>{{ result?.reason || '—' }}</dd><dt>Retained until</dt><dd>{{ result ? formatTime(result.expiresAt) : '—' }}</dd></dl>
              <div class="info-box"><strong>Three identifiers, three roles.</strong><p>Event IDs identify requests. Digests describe observations. Visitor IDs connect assigned events; inferred assignments are estimates.</p></div>
            </section>
          </div>
          <section class="panel observations"><div class="section-title"><div><h2>Browser observations</h2><p class="hint">Display dimensions are excluded. Rendering details can change with browser, driver or font updates.</p></div><span class="tiny-label">{{ observation?.schema || 'READY TO COLLECT' }}</span></div><div class="signals"><div v-for="key in ['platform', 'cores', 'memory', 'language', 'timezone']" :key="key"><span>{{ key }}</span><strong>{{ observation?.signals[key] ?? 'Not observed' }}</strong></div></div><div v-if="observation?.detail" class="signals detail-signals"><div v-for="key in ['gpu', 'fonts', 'canvas']" :key="key"><span>{{ key }}</span><strong :title="observation.detail[key] || ''">{{ observation.detail[key] ? observation.detail[key].slice(0, 16) + '…' : 'Unavailable or unstable' }}</strong></div></div><p v-if="observation?.detail" class="hint">Detailed evidence stays scope-specific. Missing or unstable probes never count as agreement.</p></section>
          <div class="footer-note"><span>◎</span> Original observations. Explainable decisions. Hosted by you.</div>
        </template>
        <template v-else-if="!user && tab !== 'Integration'">
          <div class="page-heading"><div><p class="eyebrow">INTERNAL BACKOFFICE</p><h1>Your data, in focus.</h1><p>Sign in to explore events and manage your projects.</p></div></div>
          <form class="panel login-card" @submit.prevent="login"><h2>Welcome back</h2><label>Username<input v-model="username" autocomplete="username" required></label><label>Password<input v-model="password" type="password" autocomplete="current-password" required></label><button class="primary" :disabled="busy">{{ busy ? 'Signing in…' : 'Sign in' }}</button><p class="hint">Use the credentials generated during server setup. Sessions expire after eight hours.</p></form>
        </template>
        <template v-else-if="tab === 'Activity'">
          <div class="page-heading"><div><p class="eyebrow">EVENT EXPLORER</p><h1>Activity, with context.</h1><p>Search observations, inspect decisions, and follow a visitor’s events.</p></div><button class="secondary" @click="action(() => loadEvents())" :disabled="busy">Refresh ↻</button></div>
          <form class="panel filters" @submit.prevent="action(() => loadEvents())"><label>Project<select v-model="project"><option v-for="p in projects" :value="p._id" :key="p._id">{{ p.name }}</option></select></label><label class="wide">ID prefix<input v-model="filters.prefix" placeholder="evt_, vis_, sg1_ or sg2_…"></label><label>Method<select v-model="filters.method"><option value="">All methods</option><option v-for="(label, key) in methodLabel" :value="key" :key="key">{{ label }}</option></select></label><label>Platform<select v-model="filters.platform"><option value="">All platforms</option><option v-for="p in ['macos','windows','linux','ios','android','chromeos']" :key="p">{{ p }}</option></select></label><label>From (local time)<input type="datetime-local" v-model="filters.after"></label><label>Until (exclusive)<input type="datetime-local" v-model="filters.before"></label><button class="primary" :disabled="busy">Search</button></form>
          <section class="panel"><div class="section-title"><h2>Events <span class="count">{{ events.length }} on this page</span></h2><span class="tiny-label">NEWEST FIRST</span></div><div class="table-scroll"><table><thead><tr><th>Time</th><th>Event ID</th><th>Visitor ID</th><th>Method</th><th>Platform</th></tr></thead><tbody><tr v-for="e in events" :key="e._id"><td>{{ formatTime(e.createdAt) }}</td><td><button class="id-link" @click="selected = e">{{ e._id }}</button></td><td class="mono">{{ e.visitorId || 'Unassigned' }}</td><td><span class="badge">{{ e.method }}</span></td><td>{{ e.snapshot.signals.platform || 'Unknown' }}</td></tr></tbody></table></div><div v-if="!events.length" class="empty"><span>⌕</span><h3>No events here yet</h3><p>Run the live demo or adjust your filters to see activity.</p></div><button v-if="next" class="secondary pagination" @click="action(() => loadEvents(next))" :disabled="busy">Next 25 events →</button></section>
          <section v-if="selected" class="panel event-inspector" aria-label="Event inspector"><div class="section-title"><h2>Event inspector</h2><button class="secondary" @click="selected = null">Close</button></div><p class="mono">{{ selected._id }}</p><p>{{ explanations[selected.reason] }}</p><dl><dt>Visitor assignment</dt><dd>{{ methodLabel[selected.method] }} · {{ selected.visitorId || 'Unassigned' }}</dd><dt>Retention deadline</dt><dd>{{ formatTime(selected.expiresAt) }}</dd></dl><pre>{{ JSON.stringify(selected, null, 2) }}</pre><div v-if="selected.visitorId" class="demo-controls"><button class="secondary" @click="visitorAction('revoke')" :disabled="busy">Revoke browser token</button><button class="danger" @click="visitorAction('delete')" :disabled="busy">Delete visitor and events</button></div></section>
        </template>
        <template v-else-if="tab === 'Projects'">
          <div class="page-heading"><div><p class="eyebrow">WORKSPACE SETTINGS</p><h1>A home for every project.</h1><p>Set allowed origins, data retention, and browser enrollment.</p></div></div>
          <div class="project-grid"><section class="panel"><div class="section-title"><h2>Your projects</h2><span class="count">{{ projects.length }} / 32</span></div><article v-for="p in projects" :key="p._id" class="project-item"><div><h3>{{ p.name }}</h3><code>{{ p.publicKey }}</code><p>{{ p.origins.join(', ') }}</p><small>{{ p.retentionDays }} days · Enrollment {{ p.enrollment ? 'enabled' : 'disabled' }}</small></div><div class="demo-controls"><button class="secondary" @click="edit(p)">Edit</button><button v-if="p._id !== 'demo'" class="danger" @click="removeProject(p)" :disabled="busy">Delete</button></div></article></section>
          <form class="panel project-form" @submit.prevent="saveProject"><h2>{{ editing ? 'Edit project' : 'Create project' }}</h2><label>Project name<input v-model="form.name" required maxlength="80" placeholder="My application"></label><label>Allowed origins<textarea v-model="form.origins" rows="3" required placeholder="https://app.example.com"></textarea></label><p class="hint">One exact origin per line. Remote sites require HTTPS. Public keys identify projects; they are not authentication secrets.</p><label>Retention (days)<input type="number" v-model.number="form.retentionDays" min="1" max="90" required></label><label class="check"><input type="checkbox" v-model="form.enrollment">Allow explicit browser enrollment</label><button class="primary" :disabled="busy">{{ editing ? 'Save changes' : 'Create project' }}</button><button v-if="editing" type="button" class="secondary" @click="editing = null; form = {name:'', origins:browserOrigin, retentionDays:30, enrollment:true}">Cancel editing</button></form></div>
        </template>
        <template v-else>
          <div class="page-heading"><div><p class="eyebrow">DEVELOPER QUICKSTART</p><h1>From snippet to first event.</h1><p>Add the agent to your site or explore the same data from your terminal.</p></div></div>
          <section class="panel integration"><div class="section-title"><h2>1. Choose your project</h2><select v-if="user" v-model="project" aria-label="Integration project"><option v-for="p in projects" :key="p._id" :value="p._id">{{ p.name }}</option></select></div><p>Allow your site’s exact origin in Projects, then add this module to your application.</p><h2>2. Identify a browser</h2><pre>{{ snippet }}</pre><button class="secondary" @click="copy(snippet)">Copy integration snippet</button><p class="hint">The default agent stores no token. Opt in with <code>agent.identify({ remember: true })</code>. Use HTTPS in production.</p><h2>3. Explore from your terminal</h2><pre>pipx install ./server
singularity login --url https://identity.example.com
singularity projects
singularity events --project demo --method inferred --platform macos
singularity --json events --project demo --prefix evt_ --limit 100</pre><p>Use <code>--after</code>, <code>--before</code>, <code>--visitor</code>, <code>--digest</code>, and <code>--cursor</code> to narrow results. The CLI uses the same protected API and can run with the headless server.</p></section>
        </template>
      </div>
    </main>
  </div>
</template>
