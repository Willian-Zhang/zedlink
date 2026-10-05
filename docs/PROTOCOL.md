# ZedLink protocol v1 — proposed contract

Status: design specification, not an existing Zed API. Reconcile the contract with verified native behavior before freezing it. Unsupported operations must be absent from advertised capabilities and return a typed error.

## Envelope

Requests use a version, request ID, method, and params. Responses echo request ID and contain either result or error, never both. Events have instance_id, epoch, thread_id where applicable, seq, type, and payload.

```json
{
  "version": 1,
  "request_id": "unique-client-request-id",
  "method": "thread.send",
  "params": {
    "instance_id": "instance-id",
    "thread_id": "existing-native-thread-id",
    "text": "Explain the function without changing files."
  }
}
```

Identifiers in this example are illustrative. Establish their encoding from the adapter. Send credentials in an authenticated channel/header, not query strings or message text. Enforce documented message size limits before allocation.

## Operations

| Method | Minimum parameters | Result |
| --- | --- | --- |
| instance.info | instance_id | Identity, epoch, protocol version, capabilities, safe compatibility metadata |
| thread.list | instance_id, optional cursor | Exposed threads, project/worktree metadata, execution state |
| thread.create | instance_id, epoch, optional title, request_id | Create and explicitly expose a native Zed Agent thread in the configured project using its current model |
| thread.commands | instance_id, epoch, thread_id | Runtime-advertised Agent/MCP/native commands for an exposed thread |
| thread.snapshot | instance_id, thread_id | Transcript, revision/cursor, turn state, pending approvals |
| thread.subscribe | instance_id, thread_id, optional epoch/after_seq | Consistent snapshot plus future events, or replay |
| thread.send | instance_id, thread_id, text, request_id | Accepted message identity and accepted/queued state |
| request.status | original request_id, instance_id | Known submission result or explicitly unknown status |
| thread.cancel | instance_id, thread_id, expected_turn_id | Native cancellation accepted, already finished, or stale turn |
| approval.respond | instance_id, thread_id, approval_id, decision | Resolved or already-resolved/expired status |
| changes.snapshot | instance_id, thread_id | Scoped read-only diff, revision, truncation metadata if supported |
| device.revoke | device_id | Revoked status; administrative authorization required |

Gateway pairing and administrative APIs are separate from agent methods. Remote devices must not receive administrative revocation powers by default. The desktop CLI can manage pairing/exposure and revoke devices.

## State/events

At minimum map message creation/deltas/completion, thread changes, tool start/update/completion, approval requested/resolved, and turn completion/failure to actual native state. Include stable message/tool/turn IDs where Zed provides them, or document adapter-generated lifetimes.

Represent disconnect/unavailable as transport state, not agent completion. Accepted, queued, running, waiting for approval, completed, failed, and cancelled must retain distinct meanings.

If a desktop edit cannot be represented incrementally, emit a resync-required event and retrieve a snapshot. Do not append stale deltas to edited content.

## Snapshot/replay consistency

1. Snapshot and subscription must share an application-state serialization boundary.
2. Return a snapshot reflecting all events through seq N; deliver subsequent events after N.
3. If replay is available within the same epoch, deliver ordered events greater than after_seq.
4. If the epoch changed or history was evicted, return RESYNC_REQUIRED and a new consistent snapshot.
5. Clients deduplicate by epoch/seq and message identity. They must detect sequence gaps.
6. Each subscription is authorization-scoped. Do not leak events from hidden threads or other devices' administrative state.

The provisional pinned adapter keeps `entries_markdown` as a 64 KiB prefix for compatibility and also returns `activity_entries_markdown`, a bounded 256 KiB tail, plus `activity_truncated`. The tail lets a client display the currently streaming native reasoning and tool state when an older long transcript has exhausted the compatibility snapshot budget. It is an activity projection, not transcript pagination; clients must not merge it into the authoritative conversation by array index.

Bound replay memory and slow-client output queues. If a consumer falls behind, terminate or request resync rather than growing without limit.

## Submission idempotency

Store request identity and a payload digest at the component performing authoritative acceptance. Define a retention window and maximum count; select and test actual values before release.

- Same authenticated device, instance, request ID, and payload returns the original accepted result.
- Same request ID with changed payload returns REQUEST_ID_CONFLICT.
- A client-side timeout does not prove failure. Query request.status; do not create a new request ID automatically.
- After instance/ledger restart, unknown delivery must remain unknown until the native transcript/message correlation resolves it. Never claim exactly-once execution beyond the implemented persistence boundary.
- Gateway restart must not discard acceptance knowledge held in the running Zed adapter.

The agent may internally issue multiple model requests per turn for tools. Assert one submitted user message/native turn, not one HTTP call for the entire task.

`thread.create` also requires a stable request ID. The gateway scopes it to the authenticated device. A same-ID retry with the same optional title returns `creating` until Zed's native session exists, then returns the same stable `thread_id`; a changed title is a request conflict. The operation has no project, agent, model, endpoint, or credential override. It always uses the gateway's configured project and Zed's native Agent with its current model, then treats the paired user's create action as explicit exposure of that new thread.

The pinned Zed adapter rejects unknown leading slash commands. For a runtime-advertised native command such as `/compact`, it calls `ThreadView::send_content` with native-command mode, matching the desktop path that invokes `AcpThread::send_command`. Any trailing text is queued as a follow-up prompt, as in the desktop composer. Agent and MCP commands stay on the ordinary prompt path with their arguments. Local composer actions such as `/remote-control` and feedback are excluded from `thread.commands`; they require desktop UI context and cannot be used to toggle remote exposure from a phone. Skill completions insert editor mentions and are not covered by this command operation.

## Cancellation and approval races

Use expected_turn_id so a delayed cancel cannot cancel a new turn. Cancellation cannot undo completed filesystem/tool effects.

Resolve approvals atomically through Zed's normal permission path. Desktop and mobile share the same pending request. First valid resolution wins. Replays, stale request IDs, and decisions for a different tool invocation cannot grant permission.

Allowed decisions in the MVP are approve-once and deny. Additional native choices require separately advertised capabilities and exact semantic mapping.

## Errors

Define structured codes including UNAUTHENTICATED, FORBIDDEN, INSTANCE_UNAVAILABLE, THREAD_NOT_FOUND, THREAD_NOT_EXPOSED, UNSUPPORTED_CAPABILITY, VERSION_MISMATCH, INVALID_REQUEST, REQUEST_ID_CONFLICT, DELIVERY_UNKNOWN, RESYNC_REQUIRED, STALE_TURN, APPROVAL_EXPIRED, APPROVAL_ALREADY_RESOLVED, PAYLOAD_TOO_LARGE, RATE_LIMITED, and INTERNAL_ERROR.

Error details must not expose secrets, hidden project names, unrelated file paths, or transcripts. Use correlation IDs for sanitized diagnostics.

## Pairing contract

- Verify server identity before transmitting a pairing secret.
- Pairing secret is single-use, short-lived, and rate-limited.
- Issue a revocable device credential; store in iOS Keychain.
- Use proven cryptographic libraries and constant-time comparisons where applicable.
- Revocation invalidates requests and closes established streams promptly.
- TLS verification is required in release builds; no silent insecure fallback.

The chosen TLS/trust bootstrap and administrative command surface must be documented with commands verified against the actual implementation.

## Route-independent session identity

Connection profile ID/network category are client configuration, not native thread identifiers or proof of a VPN state. Expose a stable authenticated gateway identity for route reconciliation and pairing. Each running Zed instance retains its own identity/epoch.

On provider/endpoint switching, verify server identity and credential scope, reconcile uncertain submissions, then replay/snapshot. Do not create a new conversation or resend a prompt merely because a route changed. Redirects must not forward credentials to another origin. See NETWORKING.md for approved alternative endpoints and proxy authentication.
