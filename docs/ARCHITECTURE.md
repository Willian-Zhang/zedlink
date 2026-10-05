# Architecture and feasibility

Status: proposed full product design; a pinned patched-Zed local same-thread send/snapshot has been verified. A private TLS gateway and its browser have now sent prompts to the same exposed, desktop-created native thread over disposable localhost HTTPS. The iPhone client builds and launches in a hosted simulator, but has not connected to the real gateway/Zed thread. Remote Tailscale, Moshi, physical phone, and release permissions gates remain unverified.

## Components

| Component | Owns | Does not own |
| --- | --- | --- |
| Native Zed Agent | Conversation, model calls, execution, tools, permissions, project context | Mobile transport |
| ZedLink adapter | Narrow mapping to native operations/events; exposure policy | A second agent loop |
| Gateway | TLS, device authorization, IPC connection, transport/recovery | Model configuration or arbitrary shell execution |
| SwiftUI client | Presentation, input, Keychain credential, local reconnect state | Authoritative agent state |

Phone to gateway uses authenticated HTTPS/WSS over an approved route (Tailscale, WireGuard, another routed VPN, local network, or custom HTTPS service). Gateway to Zed uses a restricted local IPC channel, preferably a Unix-domain socket. If the source offers a better supported transport, document the choice and preserve equivalent boundaries.

## Feasibility gate

Inspect and record exact source files, symbols, visibility, and supported extension access for:

1. Instance/project/worktree discovery.
2. Native thread identifier, registry, persistence, and loading.
3. Desktop submission, queueing, streaming, and cancellation.
4. Permission creation, pending-request ownership, and resolution.
5. Transcript changes, message edits, tool output, and diff ownership.
6. Application-context scheduling and cross-thread dispatch.

Produce a capability matrix with supported / source patch needed / unavailable and evidence for each. Attempt a tiny real-Zed proof before choosing the final packaging.

An extension that can launch a process is insufficient unless it can also safely control native thread entities. ACP support for external agents does not establish native-thread attachment.

## Packaging choices

- Preferred: extension plus companion gateway if supported APIs satisfy the contract.
- Fallback: narrow Zed API addition, with an extension using that addition.
- Last practical option: pinned fork with an opt-in integrated adapter.

Describe installation honestly. An extension depending on a patched build is not a stock-Zed extension. Avoid a broad agent refactor or independent harness.

## Thread model

An application restart creates a new instance ID and event epoch. Persisted thread IDs may survive, but replay sequence numbers must not cross epochs. Treat display titles and file paths as metadata, never primary identifiers.

Run all adapter mutations through Zed's appropriate application context and normal action path. Hold weak references where needed; return explicit unavailable errors when entities close. Snapshot creation and event subscription need a common serialization boundary.

Only explicitly exposed threads are remotely discoverable. A paired device may create a new native thread only when `thread.create` is advertised; creation itself explicitly exposes that new thread and fixes it to the gateway's configured project plus Zed's native Agent and current model. Opening archived or unloaded threads requires a separate deliberate capability and must preserve Zed's native restore behavior.

## Trust and data

- Explicitly enable the adapter and exposure policy.
- Restrict socket directory/files to the user and authenticate/discover the intended instance safely.
- Default gateway binding to a selected private interface or loopback behind a controlled proxy; never wildcard by default.
- Pair devices over a verified server identity using short-lived single-use secrets.
- Store revocable device credentials in Keychain; store server verifier material securely.
- Check authorization per operation and subscription. Revocation closes existing authorized streams.
- Bound uploads, events, tool output, queues, replay buffers, and connection counts.
- No transcript/secret logging by default. Diagnostic collection is explicit and sanitized.
- File/diff access is scoped to exposed project/worktree roots; reject traversal and symlink escapes.
- No generic command execution endpoint; normal agent tools retain native permissions.

## Deferred work

Push notifications, background continuous connectivity, App Store publication, image uploads, archived-thread restoration, and hunk-level acceptance can follow the proven MVP. None may be advertised as implemented prematurely.

## Connection service separation

See NETWORKING.md. Gateway/thread identity is independent of route category. Support multiple saved connection profiles; do not duplicate agent state for a new route. TLS plus device authorization remains mandatory on every route. Proxy TLS termination changes the trust boundary. External iOS VPN clients are the default; an embedded packet tunnel requires separate verified feasibility and entitlements.
