# Ordered build plan

Every phase must update VALIDATION_REPORT.md with code changes, exact commands, evidence, and remaining blockers. The steps below describe intended work; they are not executed results.

## Phase 0 — Environment and source

1. Read repository instructions; inventory available source and local changes.
2. Obtain authorized Zed source, pin commit, inspect build instructions and license requirements.
3. Inventory Rust/toolchain, desktop/display environment, macOS/Xcode availability, signing, iPhone, available Tailscale/WireGuard/other VPN or proxy routes, and a disposable model provider configuration.
4. Discover supported isolated profile/configuration methods. Never alter the production Zed profile as a convenience.
5. Record real build targets and commands; no guessed cargo targets or Xcode schemes.

Exit: reproducible environment inventory and pinned source identity. Missing macOS does not block Linux work, but iOS checks remain unperformed.

## Phase 1 — Source-grounded adapter proof

1. Trace ARCHITECTURE.md's capability list.
2. Create docs/FEASIBILITY.md with exact source symbols and the extension/API gap matrix.
3. Select extension, API addition, or minimal fork based on evidence.
4. Build an opt-in adapter able to list exposed loaded native threads and read one snapshot.
5. Add a small terminal client using real IPC.
6. Submit a prompt to a desktop-created thread through the verified native path.
7. Stream the response back while the Agent Panel updates.

Exit: same instance/thread identity and authoritative state show one prompt and one native turn visible on both surfaces. A mock adapter does not pass.

## Phase 2 — State and operation semantics

1. Implement PROTOCOL.md envelopes, capability negotiation, and typed errors.
2. Implement consistent snapshots, event subscriptions, epoch/revision tracking, and bounded replay.
3. Add idempotent prompt acceptance, native queueing, and status reconciliation.
4. Add cancellation and exact pending-approval resolution.
5. Handle entity closure, multiple threads/instances, and restarts.
6. Implement supported diff snapshots with worktree/root confinement, or mark capability unavailable.
7. Test against real Zed and a deterministic local model fixture.

Exit: same-thread, permissions, concurrency, reconnect, and duplicate-request tests pass before mobile development.

## Phase 3 — Gateway and device authorization

1. Implement authenticated HTTPS/WSS and secure local IPC discovery.
2. Choose provider-independent HTTPS identity/trust bootstrap for tailnet, WireGuard/private VPN, LAN, and custom proxy endpoints.
3. Add single-use pairing, credential issuance, listing, rotation/revocation, limits, and timeouts.
4. Scope operations/subscriptions to exposed instances/threads.
5. Add sanitized diagnostics and bounded buffers.
6. Test with the terminal client across the actual gateway.
7. Implement NETWORKING.md profile/identity/diagnostic semantics, and test available VPN/proxy paths. External tunnels are user-managed by default.
8. Create verified startup/service instructions for the selected workstation platform.

Exit: unauthorized/revoked devices cannot access state or operations; a paired terminal client controls real native Zed over private TLS.

## Phase 4 — SwiftUI client

1. Select a deployment target based on the development/device environment and document it.
2. Implement a transport/state library with unit-testable reducers and no direct model client.
3. Implement guided profile onboarding, pairing and Keychain storage; validate server identity.
4. Implement instances/projects/threads, transcript, composer, tool cards, approvals, and cancel.
5. Implement optimistic input state separately from authoritative acceptance and execution state.
6. Implement reconnect/snapshot recovery and stale/unknown indicators.
7. Implement read-only diff review when the gateway capability exists.
8. Verify IOS_APP.md native design, accessibility, small/large device layouts, large text, keyboard, dark/light presentation, long tool arguments, and simulator workflows.

Exit: simulator drives the real gateway and Zed; a mocked preview is not integration evidence.

## Phase 5 — Physical end-to-end validation

1. Create the disposable project in TEST_PLAN.md.
2. Connect actual local LLM through Zed; never copy its key into the app.
3. Pair a physical iPhone, attach to the desktop-created thread, and complete the benign repair task.
4. Verify matching transcript, tool state, approvals, diff, and tests.
5. Repeat reconnect cases over Wi-Fi and cellular through actual Tailscale and WireGuard profiles; test available other VPN and custom HTTPS routes. Include provider switch, route/DNS failure, server identity changes, and private/public failover boundaries.
6. Inspect controlled call counters or egress to confirm model calls originate only in Zed.
7. Capture sanitized demonstration and authoritative assertions.

Exit: physical same-thread proof and completed validation report. Missing device/model access means this gate is blocked, not passed.

## Phase 6 — Reproducible delivery

1. Add setup/build/test scripts using commands actually verified in the checkout.
2. Add Linux and macOS CI where feasible; physical iPhone checks remain a separate manual gate.
3. Package the extension/API patch or fork, gateway, and iOS project.
4. Document compatibility, installation, rollback/unpairing, restart semantics, and limitations.
5. Update README from specification status to actual implementation status only where supported by evidence.

Exit: another developer can reproduce supported build/test steps, and all release claims match executed evidence.

## Progress checklist

- [ ] Phase 0: source and environment
- [ ] Phase 1: real native-thread proof
- [ ] Phase 2: state, permissions, recovery
- [ ] Phase 3: authenticated gateway
- [ ] Phase 4: SwiftUI/simulator
- [ ] Phase 5: physical iPhone/local LLM
- [ ] Phase 6: reproducible delivery

## Optional phase 7 — Embedded tunnel research

Only after external-client profiles pass, investigate in-app WireGuard with verified Network Extension entitlements, library licensing, signing, lifecycle, and iOS conflict handling. Do not assume a supported embedded Tailscale interface. Document feasibility and defer if unavailable; do not block the standard profile-based product on this research.
