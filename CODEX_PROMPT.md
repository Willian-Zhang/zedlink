# Paste this into Codex

Build ZedLink using the implementation and acceptance documents in this repository.

I want an installable Zed extension and a modern native SwiftUI iPhone application to remotely control my existing native Zed Agent conversations. Zed is already connected to my local LLM. Keep that provider, model configuration, context, tools, MCP connections, permissions, and agent runtime inside Zed.

Read AGENTS.md and the linked documents in README.md. Inspect the actual Zed source and pin its revision before selecting integration points. First prove that supported extension APIs can enumerate an existing native thread, submit a prompt through its normal execution path, observe streamed updates, cancel a turn, and resolve a pending approval. If an essential API is missing, document exact source-grounded gaps and implement the smallest required Zed API addition/source patch. Do not substitute a separate CLI agent, UI automation, remote desktop, or direct model chat.

Proceed through docs/BUILD_PLAN.md. The first functioning milestone is a terminal test client sending one prompt to a thread already created in desktop Zed, with the response visible on both surfaces. Do not build the finished iOS app against an unproven adapter.

Implement versioned IPC and an authenticated HTTPS/WebSocket gateway accessible through saved profiles for Tailscale, WireGuard, other routed VPNs, local HTTPS, and custom HTTPS reverse proxies/tunnels. Follow docs/PROTOCOL.md for instance identity, capabilities, snapshots, replay, idempotency, uncertain delivery, approval races, and cancellation. Bind privately and pair/revoke devices explicitly. Model credentials must never reach the phone.

After the real adapter passes its tests, implement the SwiftUI client described in docs/IOS_APP.md and docs/NETWORKING.md. Implement a modern, accessible native interface with simple provider-specific onboarding, saved connection profiles, clear status, and connection diagnostics. Use existing OS VPN clients by default; embedded tunnel support is a separate optional phase. Include pairing, project/thread list, streaming conversation, composer, tool cards, approval controls, cancellation, diff inspection where supported, and accurate reconnect status. MVP foreground operation is sufficient; push/background operation is deferred.

Run docs/TEST_PLAN.md in layers: deterministic protocol tests, a deterministic local model fixture connected through real Zed, a real local LLM project task, simulator tests, and physical iPhone tests on Wi-Fi and cellular with Tailscale, WireGuard, and available additional VPN/custom HTTPS profiles. Include provider switching, DNS/route/TLS failures, accessibility, and UI layout checks. Record actual commands and evidence in docs/VALIDATION_REPORT.md. Clearly mark unavailable tests. Never claim integration or completion based solely on a mocked backend or UI screenshots.

Continue autonomously through the available phases. When a prerequisite blocks one phase, finish useful independent work and explain the exact dependency. Deliver implementation, setup/build/test scripts grounded in the actual checkout, compatibility notes, a working same-thread demonstration, and an honest validation report.

Central acceptance criterion: a prompt submitted from my iPhone executes in an existing native Zed Agent thread through my current local LLM, appears in the desktop Agent Panel, and yields matching conversation, tool, approval, and filesystem state.
