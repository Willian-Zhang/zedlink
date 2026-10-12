# ZedLink

<p align="center">
  <strong>Secure remote control for agent conversations hosted in Zed.</strong><br>
  Continue the same native Zed Agent, Codex, Claude Code, or other ACP conversation from a phone, tablet, or desktop browser while its runtime, tools, permissions, and project context remain inside Zed.
</p>

<p align="center">
  <code>Linux host</code> · <code>Private HTTPS</code> · <code>Installable PWA</code> · <code>SwiftUI source</code> · <code>Android source</code> · <code>Apache-2.0</code>
</p>

![ZedLink desktop conversation showing live Agent activity and parallel agents](assets/screenshots/desktop-conversation.png)

> [!IMPORTANT]
> ZedLink is working development software built against pinned Zed revision `76659a55a8c10ed355a070f8764a0b1733e3c115`. It currently requires the maintained [`tjnull/zed`](https://github.com/tjnull/zed/tree/zedlink/native-agent-remote-control) fork and is not a Marketplace extension. A physical iPhone Safari client has completed a same-thread round trip over trusted Tailscale HTTPS.

## Distribution status

ZedLink cannot currently be published as a stock Zed Gallery extension. Zed's supported extension API does not expose existing native Agent threads, native Agent settings, approvals, or cancellation, and Zed's current publishing policy no longer accepts new slash-command or agent-server extensions. The native integration therefore lives as a focused Zed source branch while the gateway and clients live in this repository.

The intended public path is:

1. submit the native bridge and supported API surface to Zed through its normal core contribution process;
2. keep the gateway and clients independently buildable and reviewable here;
3. create a Gallery package only after Zed exposes an accepted extension capability that can preserve the same native thread.

See [Publishing and upstream readiness](wiki/Publishing-and-Upstream.md) for the source-grounded audit, blockers, and release checklist. Do not install an `extension.toml` from an unofficial package claiming to provide the current native-thread integration.

## What it does

ZedLink exposes only the root Agent threads you explicitly enable with `/remote-control`. Prompts from a paired client enter the selected thread's normal execution path and appear in the desktop Agent Panel. Responses, reasoning, tools, approvals, errors, cancellation, and filesystem state remain attached to that same conversation.

Zed keeps the configured model, provider credentials, tools, MCP servers, permissions, and Agent runtime. ZedLink does not run a second model client or provide a generic remote shell.

| Capability | Current support |
| --- | --- |
| Existing native Agent threads | Expose, list, resume, stream, and stop |
| ACP agents | Existing Codex, Claude Code, OpenCode, Copilot, Cursor, and other Zed-hosted ACP threads |
| Multiple Zed targets | Save several gateways and switch among explicitly configured patched Zed instances without mixing thread state |
| New sessions | Create in the allowed project with the native Zed Agent or a configured ACP agent |
| Session management | Rename an exposed session or stop remote exposure while the native desktop thread remains open |
| Live activity | Indexed long-history paging plus real-time responses, inline thinking, tool calls, terminal output, failures, retries, approvals, and parallel agents |
| Project context | Browse and search files, attach context, review syntax-highlighted code and diffs |
| Private access | Device pairing over Tailscale, routed VPNs, or trusted HTTPS profiles |
| Clients | Responsive browser/PWA, SwiftUI source, and Jetpack Compose source |

```text
Browser or app ── authenticated private HTTPS ── ZedLink gateway
                                                        │
                                                 local Unix socket
                                                        │
                                                        ▼
                                               selected Zed-hosted thread
                                               using its existing runtime
```

Zed must remain open while a remote conversation is active. Model credentials never leave the workstation.

## Interface

<table>
  <tr>
    <td width="38%"><img src="assets/screenshots/mobile-conversation.png" alt="ZedLink mobile conversation"></td>
    <td width="62%"><img src="assets/screenshots/code-review.png" alt="ZedLink syntax highlighted code review"></td>
  </tr>
  <tr>
    <td align="center"><strong>Mobile conversation</strong></td>
    <td align="center"><strong>Searchable code review</strong></td>
  </tr>
</table>

The responsive browser client can be installed as a home-screen app. It includes session controls, reconnect diagnostics, paginated long conversations, inline expandable reasoning, tool output, code and diff review, file context, approvals, and cancellation.

## Quick start

1. Install Tailscale on the workstation and client, sign both in to the same tailnet, and enable MagicDNS plus HTTPS certificates in the [Tailscale DNS admin page](https://login.tailscale.com/admin/dns).
2. Open this repository in Zed and trust the worktree.
3. Press `Ctrl+Shift+P`, run **task: spawn**, then choose **ZedLink: Set up this project**. ZedLink detects the private address and hostname and can create the certificate files for you.
4. Open **ZedLink — Patched Zed** from the Linux application menu.
5. In the desired root Agent or ACP conversation, select `/remote-control`.
6. Run **ZedLink: Start gateway**, followed by **ZedLink: Pair a device**. Choose a live browser QR page or a QR rendered directly in Zed's terminal. Dedicated **Pair in browser** and **Pair in terminal** tasks are also available.
7. Open or scan the trusted private HTTPS address, pair, select the exposed session, and send a message.

If Tailscale or HTTPS is not ready, run **ZedLink: Set up / renew Tailscale HTTPS**. It checks sign-in state, the private IP, MagicDNS hostname, certificate hostname, matching private key, and expiration, then gives a specific recovery step. Tailscale setup also enables a user-level renewal timer: ZedLink checks twice daily, renews inside the final 30 days, validates the replacement, and live-reloads a running gateway without clearing sessions or pairings.

For requirements, first build details, TLS setup, provider configuration, and recovery steps, use the project guide below.

## Project guide

| Guide | Contents |
| --- | --- |
| [Wiki home](wiki/README.md) | Documentation index and recommended reading order |
| [Installation and setup](wiki/Installation-and-Setup.md) | Requirements, patched Zed installation, tasks, launcher, and native Settings |
| [Connections and networking](wiki/Connections-and-Networking.md) | Tailscale, NetBird, WireGuard, ZeroTier, Twingate, Headscale, Cloudflare, SSH, and multiple profiles |
| [Running and pairing](wiki/Running-and-Pairing.md) | Exposing a thread, starting the gateway, pairing browsers, PWA installation, notifications, and first round trip |
| [Everyday use](wiki/Everyday-Use.md) | Normal startup, connection management, paired devices, and task reference |
| [Troubleshooting](wiki/Troubleshooting.md) | Missing commands, wrong Zed build, model and image errors, TLS, DNS, reconnects, and uncertain delivery |
| [Security](wiki/Security.md) | Trust boundaries, explicit exposure, pairing, TLS, permissions, and credential handling |
| [Development and testing](wiki/Development-and-Testing.md) | Builds, protocol tests, pinned source, fork layout, and contribution path |
| [Publishing and upstream readiness](wiki/Publishing-and-Upstream.md) | Zed Gallery eligibility, upstream core path, licensing, and public-release checklist |
| [Roadmap and validation](wiki/Roadmap-and-Validation.md) | Native parity gaps, completed evidence, and current limitations |

## Native Zed settings

Patched Zed includes a native **ZedLink** Settings page for bridge startup, gateway status and lifecycle, pairing and selective device revocation, project scope, remote permissions, connection profiles, provider-specific fields, TLS paths, activation, and connection checks.

<p align="center">
  <img src="assets/screenshots/zed-settings.png" width="760" alt="Native ZedLink connection provider settings in patched Zed">
</p>

<p align="center"><sub>Native patched Zed Settings using generic example paths and a Tailscale profile.</sub></p>

## Upstreaming to Zed

The native integration is maintained on the public [`tjnull/zed:zedlink/native-agent-remote-control`](https://github.com/tjnull/zed/tree/zedlink/native-agent-remote-control) branch. Zed asks larger features and Extension API changes to begin with maintainer discussion, so the repository includes a [source-grounded upstream proposal](wiki/Zed-Upstream-Proposal.md) and [publishing audit](wiki/Publishing-and-Upstream.md) for review before a core pull request.

The proposal keeps the product boundary explicit: Zed owns the Agent runtime and native thread; the separately authenticated gateway owns remote transport and device pairing.

## Source layout

- `gateway/` — authenticated HTTPS/WebSocket gateway and browser/PWA client.
- `protocol-core/` — versioned protocol types and deterministic behavior.
- `tools/` — setup, pairing, diagnostics, route management, and tests.
- `patches/` — reviewable patch matching the maintained Zed fork branch.
- `ios/` — native SwiftUI client source.
- `android/` — native Jetpack Compose client source.
- `zed-source/` — ignored local checkout of `tjnull/zed:zedlink/native-agent-remote-control` used for builds.

Fresh setup clones the maintained fork as `origin` and records `zed-industries/zed` as `upstream`. The full Zed checkout and build artifacts are never committed to this repository.

## Build and verify

```sh
# Build or update patched Zed and the gateway
bash tools/install_linux.sh

# Install tasks and run guided setup
bash tools/setup_zed_ide.sh

# Run static checks and deterministic protocol tests
bash tools/check_linux.sh

# Run the authenticated HTTPS/WebSocket browser fixture
python3 tools/test_gateway_transport.py
```

Browser fixture results do not substitute for real native Zed testing. See [Roadmap and validation](wiki/Roadmap-and-Validation.md) for the tested same-thread, cancellation, approval, replay, and physical phone evidence.

## Security summary

- A private VPN route does not grant application access; every browser must pair.
- TLS is required, including over private networks.
- The gateway rejects wildcard and public listener addresses.
- Only explicitly exposed threads are visible remotely.
- Zed remains authoritative for tools, permissions, approvals, and Agent execution.
- Device secrets, model credentials, and routine transcript data are excluded from logs.

Read the complete [security model](wiki/Security.md) before exposing a route beyond a private network.

Security reports should use GitHub's private vulnerability reporting flow described in [SECURITY.md](SECURITY.md). Development contributions should follow [CONTRIBUTING.md](CONTRIBUTING.md) and the [upstream readiness guide](wiki/Publishing-and-Upstream.md).

## Current status

The browser/PWA and Linux-hosted patched Zed path are the most complete implementation. The SwiftUI and Android sources are present, while signed native distribution, broader physical-device coverage, supervised background startup, and several desktop Agent parity controls remain ongoing work.

See [Roadmap and validation](wiki/Roadmap-and-Validation.md) for exact passed, unavailable, and incomplete tests.

## License

ZedLink is licensed under the [Apache License 2.0](LICENSE). The separately maintained Zed fork retains Zed's upstream licensing and contribution requirements.
