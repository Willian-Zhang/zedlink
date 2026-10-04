# Connection profiles and VPN support

Status: implementation requirements, not executed integrations.

## Provider-independent transport

ZedLink uses authenticated HTTPS/WSS to the same native-agent gateway regardless of the network route. VPN providers supply reachability; ZedLink supplies device pairing, authorization, shared-thread state, and recovery. The local model stays configured in Zed.

The MVP uses existing iOS VPN apps/configurations. It must not pretend to start or inspect arbitrary third-party VPN tunnels. Profile labels are user selections, not proof that a particular tunnel is connected. Network path monitoring cannot by itself establish a VPN's identity or gateway reachability.

| Profile | User setup | Gateway endpoint | MVP scope |
| --- | --- | --- | --- |
| Tailscale | Enable Tailscale on phone; route to workstation or authorized subnet router | Verified tailnet HTTPS hostname, or private address with explicitly configured trust | Required |
| WireGuard | Activate configured iOS tunnel with routes/DNS to bridge | Private hostname/address reachable through peer routes | Required |
| Other VPN | Activate existing VPN that routes to bridge | HTTPS hostname/address reachable through that VPN | Required generic endpoint support |
| Local network | Join authorized LAN; configure local network permission if required | Local HTTPS hostname/address | Required |
| Custom HTTPS gateway | User configures reverse proxy/tunnel to bridge | Verified HTTPS hostname with WSS support | Required generic endpoint support; provider-specific login adapters only after validation |

A consumer VPN that only provides Internet egress does not automatically route to the home workstation. A mesh/subnet route must actually reach the bridge.

Do not require Tailscale to use WireGuard, and do not chain the two on iOS. Separate profiles support switching providers. Tailscale documents the iOS limitation of one active VPN at a time; test switching explicitly.

## Profile model

Persist profile UUID, display name, network category, HTTPS base URL, optional path prefix, server identity, credential reference, timeout/retry preferences, and optional user-approved alternative endpoints. Credentials remain in Keychain, not exportable profile JSON.

A profile is an endpoint/trust configuration, not a WireGuard peer configuration. Do not import WireGuard private keys into the standard MVP. Do not request Tailscale account keys/admin tokens.

Gateway identity must be stable across routes and distinct from a running Zed instance identity. Authenticate it during pairing. Alternate endpoints must be explicitly approved and authenticate the same gateway before credential use. Changed server identity requires user review and pairing/trust resolution.

Support multiple saved profiles/hosts now. Keep more complex aggregate multi-host dashboards optional; this replaces the prior blanket deferral of multiple remote hosts.

## Setup flow

1. Choose Tailscale, WireGuard, Other VPN, Local network, or Custom HTTPS.
2. Display a short provider-specific prerequisite, with Advanced settings collapsed.
3. Enter hostname/base URL or scan a pairing QR.
4. Show endpoint and expected server identity before transmitting pairing material.
5. Verify server trust, reachability, protocol, and capabilities; pair device.
6. Name/save the profile; select exposed Zed project/thread.
7. On later visits, one tap connects to the saved profile.

QR payloads must be versioned, bounded, short-lived where secret-bearing, and validated against allowed schemes/hosts. Never auto-connect to arbitrary unreviewed URLs, forward secrets after a cross-origin redirect, or place long-lived credentials in QR codes.

Deep links to provider apps are optional conveniences. Verify official supported schemes against the installed platform/version. If unavailable, show instructions and allow a user to switch manually. Do not invent app URLs or use undocumented Settings navigation.

## Trust and services

TLS is mandatory for every profile, including VPN/LAN. Use a valid hostname/certificate or explicitly paired pin strategy with a verified provisioning method. Connecting to a raw IP does not bypass hostname validation. Never disable certificate verification or make global App Transport Security exceptions.

Reverse proxies/tunnel services may terminate TLS and see plaintext application traffic. Document that trust boundary; do not call such a path end-to-end encrypted unless separately implemented. Keep gateway authorization independent of proxy authentication.

The user chooses and configures external services. Do not create accounts, expose a public endpoint, change routers/firewalls, or publish a tunnel automatically.

Generic custom HTTPS support is not a claim of verified integration with every service. Provider-specific SSO, service-token, or access-policy flows require documented APIs, secure credential storage, and real tests. Unsupported login flows receive a clear error, not browser cookies scraped from another app.

An optional authenticated outbound relay can be a later feature. It requires its own operator/trust/privacy model and cannot be replaced by an untrusted public WebSocket proxy.

## Routing and diagnostics

Test DNS, route availability, TLS, application authorization, protocol negotiation, gateway identity, Zed availability, then native thread attachment. Separate errors: no network, name resolution failure, endpoint timeout, TLS mismatch, pairing expired, credential revoked, protocol mismatch, bridge offline, Zed offline.

A timed-out endpoint does not prove the VPN is off. Show: “Bridge unreachable. Check your VPN connection, address, and route.” Use “VPN connected” only if supported APIs actually verify it.

Use Network framework path changes to trigger controlled revalidation, with bounded exponential retry and jitter for reliability. Avoid duplicate transports/subscriptions. Once authenticated, restore request state and snapshot/replay before displaying Live.

An alternate route must not silently broaden private access to a public service. Automatic failover is opt-in per profile and limited to approved endpoints with verified gateway identity.

## Embedded VPN — separate optional phase

Only after the normal profiles pass end-to-end tests, investigate an in-app WireGuard tunnel as a separately scoped Network Extension feature. Verify Apple entitlements, provisioning, App Store constraints, official library licensing, tunnel lifecycle, and conflict handling. A UI picker alone does not implement a VPN.

Do not promise an embedded Tailscale SDK or the ability to control the separate Tailscale app without a documented supported interface. Mark embedding deferred if feasibility is not established.

## Required validation

Run same-thread, pairing, approvals, and reconnect tests across actual Tailscale, actual WireGuard, local HTTPS, one available other VPN, and one available custom HTTPS proxy. Generic fixture tests supplement but do not replace physical provider-route tests.

If a route is unavailable, mark it NOT RUN and retain functional generic endpoint support without claiming provider validation.

## Primary references

Verify current instructions/platform behavior during implementation:

- https://tailscale.com/docs/reference/faq/other-vpns
- https://tailscale.com/docs/features/client/ios-vpn-on-demand
- https://www.wireguard.com/install/
- https://www.wireguard.com/quickstart/
- https://developer.apple.com/documentation/networkextension/packet-tunnel-provider
- https://developer.apple.com/documentation/xcode/configuring-network-extensions/
