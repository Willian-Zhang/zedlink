# ZedLink

Your Zed agent, wherever you are.

## What this package contains

This project contains a transport-independent Rust protocol core, an opt-in native Zed probe, a private HTTPS/WebSocket gateway, and a browser interface served by that gateway. The patched Zed build adds `/remote-control` to the native Agent composer. A terminal prompt reached an existing desktop native thread through the local probe, with matching user and assistant entries. The browser passed a paired local transport fixture against a synthetic probe. The gateway reached a real isolated Zed instance over its private socket; no thread was exposed during that gateway check, so a gateway/browser same-thread prompt has not passed. The send receipt and event feed remain provisional. There is no installable extension or iOS application yet. Approval resolution, provider-side cancellation, simulator, physical-device, VPN-route, and independently verified local-model tests have not passed. The pinned stock extension API cannot control an existing native Agent thread or register a native composer command; see [docs/FEASIBILITY.md](docs/FEASIBILITY.md) and [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md).

ZedLink will let an iPhone attach to an existing native Zed Agent thread while the desktop retains its local LLM configuration and agent runtime. Desktop and phone must control the same underlying thread.

On this Linux checkout, `tools/check_linux.sh` runs the verified source, protocol, and gateway checks. `python3 tools/test_gateway_transport.py` runs a separate local TLS fixture and requires loopback access. See [docs/GATEWAY.md](docs/GATEWAY.md) for the development gateway setup.

## Start here

1. Extract this package into the project root where Codex will work. Preserve any existing AGENTS.md; merge relevant guidance instead of overwriting it.
2. Use the pinned local `zed-source/` checkout at `76659a55a8c10ed355a070f8764a0b1733e3c115`, or apply the [source patch](patches/zed-1.22.0-local-probe.patch) to that exact public revision. The nested checkout is ignored by the package root.
3. Paste [CODEX_PROMPT.md](CODEX_PROMPT.md) into Codex.
4. Implement in the order described in [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md), with evidence recorded at every gate.
5. Use [docs/TEST_PLAN.md](docs/TEST_PLAN.md) as the release acceptance contract.

## Documents

| File | Purpose |
| --- | --- |
| [AGENTS.md](AGENTS.md) | Persistent Codex implementation constraints |
| [CODEX_PROMPT.md](CODEX_PROMPT.md) | Ready-to-paste starting task |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | Components, trust boundaries, feasibility gate |
| [docs/BUILD_PLAN.md](docs/BUILD_PLAN.md) | Ordered implementation steps and exit criteria |
| [docs/PROTOCOL.md](docs/PROTOCOL.md) | Proposed versioned operations and recovery semantics |
| [docs/NETWORKING.md](docs/NETWORKING.md) | VPN/service profiles, routing, trust, and provider tests |
| [docs/IOS_APP.md](docs/IOS_APP.md) | Modern native iOS experience and implementation scope |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | Deterministic, real-Zed, simulator, and physical-phone tests |
| [docs/VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md) | Honest status and evidence template |
| [docs/FEASIBILITY.md](docs/FEASIBILITY.md) | Source inspection and native API gate |
| [docs/LOCAL_PROBE.md](docs/LOCAL_PROBE.md) | Opt-in patched-Zed local probe, `/remote-control`, and observed native send and snapshot |
| [docs/GATEWAY.md](docs/GATEWAY.md) | Development gateway build, TLS setup, pairing, revocation, and limits |
| [docs/BROWSER.md](docs/BROWSER.md) | Paired browser interface, Tailscale HTTPS setup, and Moshi compatibility boundary |
| [docs/MODEL_FIXTURE.md](docs/MODEL_FIXTURE.md) | Source-grounded loopback Chat Completions fixture and its validation limits |
| [protocol-core](protocol-core) | Provisional Rust request, replay, and submission-identity rules; no Zed adapter |
| [gateway](gateway) | Private TLS/WSS gateway that forwards authorized requests to the native probe |

## Product constraints

- Target native Zed Agent threads, not a replacement CLI agent.
- Keep the current local LLM provider, model credentials, tools, MCP connections, instructions, project/worktree context, and permissions in Zed.
- No VNC, RDP, VMware UI access, screen scraping, keyboard injection, or phone-to-model chat.
- Prefer an installable extension. If essential APIs are missing, report verified gaps and implement the smallest practical Zed API addition/source patch. Do not promise stock-Zed compatibility prematurely.
- Support Tailscale, WireGuard, other routed VPNs, local HTTPS, and custom HTTPS gateways through saved connection profiles; use application-level pairing for device authorization.
- Build the real integration before the finished iOS UI.

## Central acceptance criterion

An iPhone prompt executes in an existing native Zed Agent thread through Zed's configured local LLM, appears in the desktop Agent Panel, and produces matching conversation, tool, approval, and project state.

## Environment requirements

Linux development can cover the gateway, protocol, and relevant Zed integration. Native iOS compilation and simulator validation require macOS/Xcode. Physical iPhone validation also requires provisioning/signing and a reachable workstation. Codex must discover actual supported versions, build commands, and schemes from the checkout; none are assumed here.

## Documentation references

These official pages informed the design. Recheck them against the pinned source revision:

- https://zed.dev/docs/ai/zed-agent
- https://zed.dev/docs/ai/agent-panel
- https://zed.dev/docs/extensions
- https://zed.dev/docs/extensions/agent-servers
- https://zed.dev/docs/remote-development
- https://github.com/zed-industries/zed

The documents do not establish a supported native-agent mobile API. Proposed identifiers, endpoints, modules, and operations in this package are ZedLink design choices, not existing Zed APIs.

## Revision 2 — UI and connectivity

Expanded native SwiftUI design, onboarding, accessibility, connection diagnostics, and provider-independent profiles. External iOS VPN clients are the default; embedded tunnels are a separate feasibility phase. Provider tests and modern UI acceptance are specified, not executed.
