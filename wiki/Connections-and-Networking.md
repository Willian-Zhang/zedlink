# Connections and Networking

[← Wiki home](README.md)

## Configuration: what each prompt means

Guided setup runs **ZedLink: Configure**. It asks for the following values.

| Prompt | What to enter | Example |
| --- | --- | --- |
| Project to open in patched Zed | The full path of the project whose Agent thread you want to control; this is required | `/home/you/Documents/my-project` |
| Private state directory | Where ZedLink stores its socket, paired-device records, and gateway identity | `/home/you/.local/state/zedlink` |
| Gateway bind address | A private computer IP followed by `:44679` | `100.64.10.20:44679` |
| Client HTTPS origin | The trusted hostname your browser or app opens, with the same port | `https://computer.example-tailnet.ts.net:44679` |
| TLS certificate PEM path | Full path to the certificate for that hostname; detected Tailscale setups receive a durable suggested path | `/home/you/.config/zedlink/tls/computer.example-tailnet.ts.net.crt` |
| TLS private key PEM path | Full path to its private key; detected Tailscale setups receive a matching suggested path | `/home/you/.config/zedlink/tls/computer.example-tailnet.ts.net.key` |
| Existing Zed user data directory | Usually leave blank to use your normal Zed profile | press Enter |

The private key must have restricted permissions:

```sh
chmod 600 /absolute/path/to/computer.key
```

Configuration is saved privately in:

```text
~/.config/zedlink/config.json
```

It stores paths and network settings. It does not store your model API key or copy model credentials to a client.

### Tailscale values

Find the computer's Tailscale IPv4 address with:

```sh
tailscale ip -4
```

Use that address for **Gateway bind address**, followed by port `44679`.

The client URL must use a hostname covered by a certificate trusted by the browser. Do not use the raw Tailscale IP as the HTTPS URL. Tailscale documents certificate creation in [Set up HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates). Certificate issuance publishes the hostname in public Certificate Transparency logs, and file certificates must be renewed.

When the wizard detects Tailscale, it manages the suggested certificate paths instead of asking a new user to type them. If the files do not exist, it explains the public-log consequence and asks whether it should run `tailscale cert` for you. Answering **yes** stages and validates the certificate and private key under `~/.config/zedlink/tls/`; answering **no** leaves certificate management to you and stops configuration without saving partial settings.

Run **ZedLink: Set up / renew Tailscale HTTPS** at any time for a focused preflight. It distinguishes an uninstalled client, stopped daemon, signed-out client, missing MagicDNS name, disabled HTTPS certificates, Linux operator permissions, and certificate-authority rate limiting. It also validates the saved certificate hostname, key pair, permissions, and expiration. The task requests at least 30 days of remaining validity when creating or renewing a certificate.

ZedLink's automatic renewal timer performs the same checks every 12 hours. It does not contact Tailscale while a healthy certificate has more than 30 days remaining. When renewal is due, it requires the detected MagicDNS hostname to match the saved profile, stages and validates the new pair, then asks the gateway to reload all TLS listeners. The gateway validates every configured replacement before switching any listener, so an invalid file cannot partially reload a multi-route gateway.

On the iPhone:

1. Open Tailscale and connect to the same tailnet.
2. Enable **Use Tailscale DNS settings**.
3. Keep Tailscale connected while using ZedLink.

Do not bypass a Safari certificate warning. Fix the hostname, certificate, or Tailscale DNS configuration instead.

### Other connection options

Tailscale is the validated default, but ZedLink's application protocol is standard authenticated HTTPS and WebSocket traffic. It can travel over another private network or a carefully configured HTTPS frontend without changing the native Zed Agent integration.

The practical choices are:

| Route | When to choose it | Present state |
| --- | --- | --- |
| **NetBird** | A cross-platform, optionally self-hosted WireGuard mesh alternative | Gateway preset and discovery implemented; installed here but currently disconnected and not physically tested |
| **WireGuard** | You want to manage peers, routes, and DNS yourself | Gateway preset implemented; physical route not tested |
| **ZeroTier** | You prefer a private virtual-LAN model | Gateway preset implemented; provider not installed or tested here |
| **Twingate** | A team needs identity-based access to a private ZedLink resource | Private-resource preset implemented; connector path not tested |
| **Headscale** | You want a self-hosted control plane with Tailscale clients | Tailscale-compatible preset implemented; custom control server not tested |
| **Cloudflare Tunnel + Access** | Browsers need access without a device VPN | Loopback listener and safe template implemented; external tunnel and Access policy not configured |
| **SSH reverse tunnel + your VPS** | You want a self-controlled browser route without a device VPN | Loopback listener and Caddy/SSH template implemented; no VPS route tested |
| **Local LAN HTTPS** | Remote access is unnecessary | Works through generic configuration when DNS and TLS are configured correctly |

Direct SSH port forwarding is reasonable for a desktop browser, but it is not a good primary iPhone Safari route and does not remove TLS hostname validation. ZedLink will not expose a generic SSH shell.

The gateway can now keep Tailscale active while adding NetBird, WireGuard, ZeroTier, Twingate, Headscale, a loopback Cloudflare/SSH frontend, or another private HTTPS listener. Keep the working Tailscale route while validating alternatives.

The connection profiles enforce the same pairing and TLS boundaries for every provider. No provider other than Tailscale should be treated as validated until its same-thread, TLS, pairing, WebSocket, reconnect, cancellation, and approval tests are recorded.

#### Configure more than one connection

ZedLink now supports up to 16 enabled private or loopback TLS listeners sharing the same gateway identity, paired devices, native Zed socket, and Agent state. Existing one-route configurations migrate automatically when read; the working Tailscale route is retained.

Changing a route does not create a new gateway. Keep the same private state directory: it owns the stable Gateway ID and server-side paired-device records. The iOS and Android clients key their encrypted credential to that Gateway ID, so **Save new address and reconnect** first verifies the new HTTPS endpoint and then reuses the existing credential. A changed or missing Gateway ID is rejected before any credential is sent.

Web storage is isolated by HTTPS origin. A browser paired at `https://host-a:44679` cannot read the credential stored by `https://host-b:44679`, even when both addresses reach the same gateway. The Connections screen lists the gateway's configured origins; use one stable certificate-valid hostname across network changes when possible. A new browser hostname or port requires pairing again by design.

From Zed:

1. Press `Ctrl+Shift+P` and select **task: spawn**.
2. Run **ZedLink: Manage connections**.
3. Select **Add route** and choose NetBird, WireGuard, ZeroTier, Twingate, Headscale, Cloudflare, SSH reverse, SSH local, LAN, or custom HTTPS.
4. Enter the private listener address, trusted client origin, and certificate files requested by the wizard.
5. Run **ZedLink: Restart gateway** so listener changes take effect.
6. Run **ZedLink: Check connections** to verify trusted HTTPS and the stable gateway identity.
7. Run **ZedLink: Pair a device** and choose the origin reachable from that device.

The route manager can also enable or disable a route, make it the default pairing origin, remove it, or regenerate a frontend template. A route definition starts a gateway listener; it does not sign into a VPN provider, create an external account, alter firewall rules, or publish a tunnel.

Direct private-network routes require an address on that network and a hostname whose certificate is trusted by the client:

- **NetBird:** connect the workstation and client to the same NetBird network, then use the workstation's NetBird IP and a certificate-valid DNS name.
- **WireGuard:** configure peer routes and DNS outside ZedLink, then use the workstation's routed WireGuard address.
- **ZeroTier:** authorize both members on the same network and use the workstation's managed private address.
- **Twingate:** place the chosen private listener behind a Twingate Connector and define its HTTPS hostname and port as a Resource.
- **Headscale:** connect official Tailscale clients to the custom control server and configure the resulting private address as a Tailscale-compatible route.
- **LAN:** use a private LAN address and trusted local hostname. A raw-IP certificate warning is not acceptable.

Proxy routes bind only to `127.0.0.1` or `::1`:

- **Cloudflare Tunnel + Access:** the route manager writes `~/.local/state/zedlink/frontends/ROUTE_ID/cloudflared.yml`. Create a named tunnel and Access self-hosted application, replace the tunnel UUID and credentials path, and run `cloudflared tunnel --config PATH run`. Certificate verification remains enabled between `cloudflared` and ZedLink.
- **SSH reverse + VPS/Caddy:** the manager writes a private Caddyfile containing the TLS upstream configuration and a hardened reverse-forward command template. Install it on the user-controlled VPS, keep the forwarded port bound to VPS loopback, and run the outbound SSH connection from the Zed workstation.
- **Direct SSH:** the manager writes client instructions for a local forward. The desktop client must map the certificate hostname to loopback and open that exact HTTPS hostname. This remains unsuitable as the primary iPhone Safari route.

Cloudflare and the VPS terminate the client-facing TLS session and can see application plaintext. Their authentication is an additional layer; every browser must still pair with ZedLink. Pairing credentials are scoped to an HTTPS origin, so a browser paired through Tailscale must pair separately through a Cloudflare or VPS hostname.
## Multiple Zed targets

A gateway can load a private target manifest containing up to 16 named probe sockets. The default setup creates one target. Run **ZedLink: Manage Zed targets** to add or remove another isolated patched Zed instance, then restart the gateway. Each target must use its own private probe directory and patched Zed profile. Target labels and availability are visible to paired devices; local socket paths are never returned.
