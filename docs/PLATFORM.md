# Platform and API

The platform adds server-side decisions, retained events, project configuration, a Vue console and a standalone CLI to the TypeScript core.

## Identifiers and assignments

| Field | Role |
|---|---|
| `eventId` | Random ID of a recorded request |
| `digest` | Server-recomputed SHA-256 of the validated observation tuple |
| `visitorId` | Project-scoped assigned visitor, or `null` when unassigned |
| `method` | How the assignment was made |
| `reason` | Machine-readable explanation |
| `decision` | Policy, candidate count and omission checks; optional comparison |
| `expiresAt` | Retention deadline |

Methods are `provisional` (a new inferred candidate), `inferred` (a qualifying existing candidate), `enrolled` (fresh explicit browser enrollment), `remembered` (valid possession token), and `unassigned`.

Inferred assignments use `support/v2` for detailed observations or the unchanged `envelope/v1` policy for legacy observations. Agreement scores describe evidence, not identity probabilities. Browser enrollment establishes token possession; it does not authenticate a person. Keep authentication and authorization separate from visitor IDs. See [detailed observations and upgrading](DETAILED.md).

## Browser integration

Create a project in the backoffice and allow your site's exact origin. The full web deployment serves a JavaScript agent:

```html
<script type="module">
import { createAgent } from 'https://identity.example.com/sdk/agent.js';
const agent = createAgent({ publicKey: 'pk_REPLACE_WITH_PROJECT_KEY' });
const event = await agent.identify();
console.log(event.eventId, event.visitorId);
</script>
```

When installed from the repository's npm tarball, import `createAgent` from `fingerprint-singularity/client` and pass `endpoint: 'https://identity.example.com'`. The headless deployment serves APIs only; use the package client in your application bundle.

The default call does not store a token. To request browser-local continuity explicitly:

```js
const event = await agent.identify({ remember: true });
agent.forget(); // Removes this site's local token; does not delete server history.
```

Fresh enrollment creates its own visitor ID instead of binding a token to an inferred match. Tokens are project scoped, expire with the enrollment, and can be revoked in the console. Only a keyed hash is stored on the server. Different origins, browser profiles, browser products and private contexts have separate storage. No hidden cross-browser communication is performed.

Use the same `requestId` when retrying the **same input** after a connection failure. Successful retries within retention return the recorded event. Reusing an active request ID with different input returns `409`. An expired record awaiting TTL cleanup returns `410`; use a new ID for a new event. Retention also ends the idempotency window.

## Identification endpoint

`POST /api/v1/identify/{publicKey}` with JSON:

```json
{
  "snapshot": {
    "schema": "singularity/v1",
    "scope": "pk_REPLACE_WITH_PROJECT_KEY",
    "signals": {"platform":"macos","cores":8,"memory":8,"language":"en","timezone":"Europe/Rome"}
  },
  "requestId": "a-random-unique-request-id",
  "remember": false,
  "token": null
}
```

The scope must equal the project public key. Unknown properties and invalid bucket values are rejected. Include the allowed `Origin` header when calling from your own server. A public key and origin allowlist are integration controls, not authentication for an arbitrary HTTP caller. Browser-supplied observations can be fabricated.

The response always contains an event ID for an accepted request. Sparse observations, ambiguous candidates and candidate overflow can leave `visitorId` unassigned. Both schemas retain coarse platform, core bucket, memory bucket, base language and timezone. Detailed snapshots add `probe: "web/v1"` and `detail: {gpu, fonts, canvas}`, each a nullable scope-specific SHA-256 hash. Screen dimensions, browser version strings, raw IP addresses, URLs and page content are not recorded. Rendering details may change when browsers or drivers are updated. The JSON request above shows the legacy format; the new agent supplies detailed snapshots by default.

## Administration

All administration endpoints require an unexpired `sg_admin` cookie. Login is `POST /api/admin/login` with `username` and `password`. It returns a CSRF token; send it as `X-CSRF-Token` on mutations. The cookie is HttpOnly, SameSite Strict, and Secure for HTTPS deployments. Logout revokes the session.

| Endpoint | Purpose |
|---|---|
| `GET /api/admin/session` | Session status and CSRF token |
| `GET/POST /api/admin/projects` | List/create projects |
| `PUT/DELETE /api/admin/projects/{project}` | Update/delete a project |
| `GET /api/admin/projects/{project}/events` | Filtered event search |
| `GET /api/admin/projects/{project}/events/{event}` | Detailed event and decision |
| `POST /api/admin/projects/{project}/visitors/{visitor}/revoke` | Revoke browser continuity |
| `DELETE /api/admin/projects/{project}/visitors/{visitor}` | Delete associated events and redact contender references |

Search supports the same filters described in the [CLI reference](CLI.md). Credentials and token hashes never appear in event search responses. The built-in demo project cannot be deleted; its visitors can be removed individually.

## Storage and operating limits

One MongoDB document atomically stores an event, its decision, idempotency record and any newly created candidate. Inferred matches do not rewrite candidate observations. Token revocation and deletion can remove credential material or redact deleted visitor references from retained decisions.

This release is designed for a small self-hosted instance:

- One API worker, enforced with a lock on its shared state volume. Writes wait at most two seconds for the global atomic write lock, then return `429` under prolonged contention. Admission remains bounded at 32 requests.
- At most 32 projects, 120 identification requests/minute/project and 10,000 accepted events/day/project.
- At most 256 complete active compatible candidates for inference, partitioned by schema and additionally by platform for v2. A 257th compatible candidate causes abstention rather than a truncated comparison. Explicit enrollment is capped at 512 active candidates across schemas.
- An 8 KiB body cap, 10-second total body deadline, 32 active requests, bounded Mongo connection pool and query deadlines.
- Retention of 1–90 days, default 30. Query-time expiry applies immediately; Mongo TTL cleans up expired documents asynchronously. Increasing retention never restores expired data.

The candidate limit bounds comparisons, not real-world recognition coverage. Track the unassigned proportion for your workload before expanding deployment. The included synthetic performance checks are engineering measurements; they are not a measured identification-accuracy score.
