# Modern SwiftUI app specification

Brand: ZedLink. Tagline: Your Zed agent, wherever you are.

Status: product/build specification. An initial native SwiftUI application now exists in `ios/`, compiled with Xcode 16.4, and launched on a hosted iPhone 16 Pro simulator. The UI and transport have not been tested against a live exposed Zed thread from an iPhone; the requirements below remain the acceptance target. Preserve the real native Zed thread and local LLM architecture.

## Design principles

Make checking progress, sending a prompt, and resolving an approval possible with few taps. Favor native SwiftUI navigation and controls, clear hierarchy, readable chat, and meaningful status over decorative dashboards.

Use system typography, SF Symbols, semantic colors, consistent spacing and rounded cards. Apply current platform materials to navigation/controls with availability checks and native fallbacks. Keep message content/code surfaces high-contrast and readable; do not turn every card into translucent glass.

Support light/dark appearances, Dynamic Type, VoiceOver, Reduce Motion/Reduce Transparency, landscape, safe areas, and keyboard avoidance. Primary touch targets should be at least 44 by 44 points. Never rely only on color. Use subtle haptics for meaningful acknowledgement, not every streamed token.

## Navigation and primary tasks

Use a native tab structure: Sessions, Connections, Settings. Sessions groups threads by exposed host/project, with a host switcher and search. A connection card shows a friendly host name, route label, reachability/authorization state, and a one-tap Connect action.

The conversation screen shows project/thread name, a compact connection indicator, transcript, and a persistent composer. Tool details and changes open in sheets or dedicated views. A prominent pending approval card remains accessible without overwhelming the chat.

Expose Running, Queued, Waiting for approval, Completed, Failed, Offline, Reconnecting, and Stale as distinct states. “Live” requires successful authenticated state reconciliation.

## Onboarding

Follow NETWORKING.md. Choose connection type, enter/scan endpoint, verify identity, pair, and select a project. Show only essential fields initially; put certificates, custom prefixes, timeouts, and alternative routes in Advanced.

Provide a connection test with plain-language result and Retry. Display provider prerequisites without asking for model keys, Tailscale admin tokens, or WireGuard private keys.

Returning users can open their last thread with one tap after connection/reconciliation. A saved session is not assumed to remain online.

## Conversation and composer

- Render streaming Markdown, syntax-highlighted code, copy controls, and collapsible tool cards.
- Maintain stable message identities and scroll position. Follow new output only when at the bottom; otherwise show a jump-to-latest button.
- Allow multiline prompts, draft persistence, send, native queue indication, and cancel of the identified active turn.
- Show Sending, Accepted, Queued, and Delivery unknown separately. Keep draft until acknowledged; avoid automatic resubmission after uncertain delivery.
- Preserve desktop-originated messages, edits, approval decisions, and tool updates.
- Disable stale approval/cancel controls after disconnection until authoritative state returns.
- Keep read-only code/diff inspection available when supported. Show file names and changed lines; clearly indicate truncated diffs.
- Provide accessible labels and announcements for completed turns/pending approvals without announcing every streamed token.
- Attachments and native diff acceptance are capability-gated optional features, not decorative nonfunctional buttons.

## Approval experience

Show the exact pending operation, target, and relevant arguments with expandable full content. Never hide decisive command/path information behind truncated text alone. Offer clearly labeled Approve once and Deny. Require the authoritative approval ID; show already resolved if desktop acted first. Do not support blanket auto-approval.

## Connections

Implement saved profiles for Tailscale, WireGuard, Other VPN, Local network, and Custom HTTPS as described in NETWORKING.md. The route category is explanatory; HTTPS/WSS and server/device authorization are consistent across categories.

Keep profile state and thread state separate. Switching route should reauthenticate/reconcile the same gateway/thread if identities match, without spawning a new agent. Switching host must not forward credentials to the previous/next host.

Offer provider setup help, endpoint editing, test connection, forget/unpair, and sanitized diagnostics. Never claim to toggle another app's tunnel through an unverified API.

## Implementation structure

Separate typed protocol models, profile repository, transport, credential vault, reconnect coordinator, state reducers, and SwiftUI views. Use an appropriate observable model for the chosen deployment target; avoid UI/network coupling and main-thread blocking. Use structured concurrency and cancellation of obsolete connection tasks.

One authoritative reducer applies snapshots/events. A single coordinator owns connection lifetimes, pending request reconciliation, path changes, and replay. Profile edits invalidate stale connection tasks. Mocks are only for clearly labeled previews/unit tests.

Store device credentials in Keychain; minimize local transcript caching and document it. Never store model keys. Forgetting a profile removes its locally owned credential reference without deleting credentials still used by explicitly linked profiles; remote revocation is a separate authenticated operation.

## Foreground lifecycle

Foreground activation verifies network, server identity, authorization, capabilities, pending request state, and snapshot/replay. Background suspension is expected; show reconciling state on return. Do not promise a continuously running background WebSocket. APNs/lock-screen controls are deferred.

## UI acceptance

Test small and large iPhones, light/dark, large accessibility text, landscape, keyboard interaction, code blocks, long tool arguments, empty/loading/error states, and reduce-motion settings. Capture simulator screenshots for inspection, with mock/real environments labeled.

Use accessibility identifiers for pairing, profile controls, thread selection, composer, send, approval buttons, cancel, reconnect, and change viewer.

Validate at least one simulator flow against real gateway/Zed; fixtures alone do not pass integration. Physical Wi-Fi/cellular and provider switching requirements are in TEST_PLAN.md.

## Primary design references

- https://developer.apple.com/design/human-interface-guidelines
- https://developer.apple.com/design/human-interface-guidelines/accessibility
- https://developer.apple.com/design/human-interface-guidelines/materials

Confirm API availability against actual Xcode/deployment versions; do not require a particular new material API merely to look modern.
