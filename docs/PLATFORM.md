# Platform and API

The platform adds server-side decisions, retained events, project configuration, a Vue console and a standalone CLI to the TypeScript core.

## Identifiers and assignments

| Field | Role |
|---|---|
| `eventId` | Random ID of a recorded request |
| `digest` | Server-recomputed SHA-256 of the validated observation tuple |
| `continuityCode` | Repeatable scoped v3 model/font profile code, or `null` |
| `visitorId` | Project-scoped assigned visitor, or `null` when unassigned |
| `history` | First and previous retained visits for the assigned visitor |
| `origin`, `linkedId`, `tags` | Recorded request origin and optional application metadata |
| `method` | How the assignment was made |
| `reason` | Machine-readable explanation |
| `decision` | Policy, retrieved candidate count and omission checks; optional comparison |
| `expiresAt` | Retention deadline |

Methods are `provisional` (a new inferred candidate), `inferred` (a qualifying existing candidate), `enrolled` (fresh explicit browser enrollment), `remembered` (valid possession token), and `unassigned`.

Inferred assignments use `support/v3` for resilient observations, `support/v2` for detailed observations or the unchanged `envelope/v1` policy for legacy observations. Agreement scores describe evidence, not identity probabilities. Browser enrollment establishes token possession; it does not authenticate a person. Keep authentication and authorization separate from visitor IDs. See [resilient observations and upgrading](RESILIENT.md).

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

Attach application context without changing fingerprint matching:

```js
const event = await agent.identify({
  linkedId: 'order:123',
  tags: { flow: 'checkout', environment: 'production' },
});
console.log(event.continuityCode, event.history?.previousSeenAt);
```

`linkedId` allows 1–128 letters, digits or `._:@/-`. Tags are a flat object with at most 16 entries: keys contain 1–32 letters, digits, `_` or `-`, and values are strings of at most 256 characters. The total request still must fit within 8 KiB. Metadata is visible in protected event search and never contributes to matching. Do not put secrets in these fields.

History contains `visitorFound`, `firstSeenAt` and `previousSeenAt`. It reflects retained events at identification time, not lifetime activity. A new assigned visitor has the current event's timestamp as `firstSeenAt`; an unassigned event has null timestamps. Previous means before this accepted event. The stored response freezes history for idempotent retries.

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

The response always contains an event ID for an accepted request. Sparse observations, ambiguous candidates and candidate overflow can leave `visitorId` unassigned. All schemas retain coarse platform, core bucket, memory bucket, base language and timezone. Detailed snapshots add `probe: "web/v1"` and `detail: {gpu, fonts, canvas}`, each a nullable scope-specific SHA-256 hash. Resilient snapshots use `probe: "web/v2"` and add nullable `engine` context. Screen dimensions, browser version strings, raw IP addresses, full page URLs and page content are not collected. The request Origin is recorded separately. Rendering details may change when browsers or drivers are updated. The JSON request above shows the legacy format; the new agent supplies resilient snapshots by default.

Added response fields are optional when replaying old stored responses. For v1/v2 observations, `continuityCode` is `null`. Clearing storage does not delete retained server events; deleting a visitor does not change the mathematical code generated from an unchanged profile.

## Administration

All administration endpoints require an unexpired `sg_admin` cookie. Login is `POST /api/admin/login` with `username` and `password`. It returns a CSRF token; send it as `X-CSRF-Token` on mutations. The cookie is HttpOnly, SameSite Strict, and Secure for HTTPS deployments. Logout revokes the session.

| Endpoint | Purpose |
|---|---|
| `GET /api/admin/session` | Session status and CSRF token |
| `GET/POST /api/admin/projects` | List/create projects |
| `PUT/DELETE /api/admin/projects/{project}` | Update/delete a project |
| `GET /api/admin/projects/{project}/events` | Filtered event search |
| `GET /api/admin/projects/{project}/events/{event}` | Detailed event and decision |
| `POST /api/admin/projects/{project}/server-key` | Create/rotate a backend secret, shown once |
| `DELETE /api/admin/projects/{project}/server-key` | Revoke backend access |
| `POST /api/admin/projects/{project}/visitors/{visitor}/revoke` | Revoke browser continuity |
| `DELETE /api/admin/projects/{project}/visitors/{visitor}` | Delete associated events and redact contender references |

Search supports the same filters described in the [CLI reference](CLI.md). Credentials and token hashes never appear in event search responses. The built-in demo project cannot be deleted; its visitors can be removed individually.

## Backend event verification

Create a server key in **Projects** and keep it only in your backend configuration. A project has one active key; rotation immediately invalidates the previous key. Only its keyed hash is stored. Project responses expose `serverKeyConfigured`, never the hash. The key grants retained event access for that project, not administration. Admin cookies and public keys cannot replace it.

| Endpoint | Purpose |
| --- | --- |
| `GET /api/server/projects/{project}/events/{event}` | Retrieve a retained event |
| `POST /api/server/projects/{project}/events/{event}/verify` | Check freshness, origin, assignment and prior consumption |

Pass `Authorization: Bearer sk_REPLACE_WITH_SERVER_KEY`. Responses use `Cache-Control: no-store`. Example on your trusted Python backend:

```python
import os
import httpx

response = httpx.post(
    f"https://identity.example.com/api/server/projects/{project}/events/{event_id}/verify",
    headers={"Authorization": "Bearer " + os.environ["SINGULARITY_SERVER_KEY"]},
    json={
        "expectedOrigin": "https://shop.example",
        "maxAgeSeconds": 300,
        "requireVisitor": True,
        "consume": True,
    },
    timeout=10,
)
response.raise_for_status()
verification = response.json()
if not verification["verified"]:
    raise ValueError("Event is not eligible for this operation")
```

`expectedOrigin` is required and must be an exact HTTP(S) origin. `maxAgeSeconds` is an integer from 1 to 3,600, default 300. Future-dated events fail freshness. `requireVisitor` defaults to true; set it false when an unassigned but recorded event is acceptable. `consume` defaults to false. A verified consuming call durably marks the event as used; concurrent calls can consume it only once. A failed verification does not consume it. Subsequent verification reports `verified: false` and `checks.unused: false`. `consumed` describes consumption by this call. Reads remain available until retention or deletion.

This is event provenance and replay control, not device attestation. The server checks its stored record; a client can fabricate observations and a non-browser caller can forge Origin. Validate your own business context using protected event retrieval and your authenticated application session. Consumption and your business operation are not one transaction: after a lost response, inspect `consumedAt` and reconcile using your own operation record instead of blindly executing again.

Key changes and consumption are written to the independent recovery ledger before Mongo mutation. Restore replays them, so an older database backup cannot revive revoked keys or consumed events when the current recovery state is retained. Rotating `SINGULARITY_SECRET`, including during supported restore, invalidates all existing server keys; create fresh keys for your integrations afterward. `serverKeyConfigured` only indicates a stored hash, not whether an old key survived secret rotation.

## Storage and operating limits

One MongoDB document atomically stores an event, its decision, idempotency record and any newly created candidate. Inferred matches do not rewrite candidate observations. Token revocation and deletion can remove credential material or redact deleted visitor references from retained decisions.

This release is designed for a small self-hosted instance:

- One API worker, enforced with a lock on its shared state volume. Writes wait at most two seconds for the global atomic write lock, then return `429` under prolonged contention. Admission remains bounded at 32 requests.
- At most 32 projects, 120 identification requests/minute/project and 10,000 accepted events/day/project.
- At most 256 complete active compatible candidates for inference, partitioned by schema. V2/v3 retrieval excludes policy contradictions before that limit and retains missing evidence; v1 keeps its complete legacy pool. A 257th compatible candidate causes abstention rather than a truncated comparison. Explicit enrollment is capped at 512 active candidates across schemas. See [v3 retrieval](RESILIENT.md#matching-and-retrieval) and [v2 retrieval](DETAILED.md#candidate-retrieval).
- Backend event access is limited to 240 requests/minute in one instance-wide bucket, including failed credentials.
- An 8 KiB body cap, 10-second total body deadline, 32 active requests, bounded Mongo connection pool and query deadlines.
- Retention of 1–90 days, default 30. Query-time expiry applies immediately; Mongo TTL cleans up expired documents asynchronously. Increasing retention never restores expired data.

The candidate limit bounds comparisons, not real-world recognition coverage. Track the unassigned proportion for your workload before expanding deployment. The included synthetic performance checks are engineering measurements; they are not a measured identification-accuracy score.
