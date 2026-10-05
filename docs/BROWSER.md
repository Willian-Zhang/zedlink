# Browser access

Status: a browser interface is embedded in the ZedLink gateway. It passed both a paired, headless Firefox test against a synthetic probe and a paired headless Firefox prompt into a real exposed native Zed thread over disposable localhost HTTPS. A remote Tailscale device and Moshi route are still NOT RUN.

The page at `/` uses the existing gateway and native Zed probe. It has no model API or separate agent. It lists only threads exposed in desktop Zed with `/remote-control`, renders native snapshots as plain readable text, polls native events for updates, and sends through `thread.send`. It keeps a stable request ID for a retry and never resends automatically after a timeout or page reload. The native send receipt remains provisional; the UI says so. Cancellation, mobile approval, diffs, and attachments stay unavailable until their native adapter paths pass live checks.

## Open and pair

1. Start the patched Zed build with its private probe, then expose the desired native Agent thread using `/remote-control` in that desktop thread.
2. Build and start the gateway using [GATEWAY.md](GATEWAY.md). Open its **verified HTTPS** address in a browser. The page is served by the gateway on the same origin as its API.
3. On the workstation, run `zedlink-gateway admin STATE_DIR devices` to read the stable `gateway_id`, then `zedlink-gateway admin STATE_DIR pair-code` to issue a one-use code. Keep both off shared logs.
4. Enter the expected gateway ID, one-use code, and browser name on the page. The page checks the ID before transmitting the code. Browser TLS validation must already have succeeded; do not bypass a certificate warning.
5. Select an exposed thread. A page reload restores the tab's device token and rechecks Zed identity. If a send was uncertain, the page queries `request.status` and keeps it uncertain. It does not create a fresh send.

The device token lives in browser `sessionStorage`, scoped to the gateway origin and current tab session. Full transcripts and pairing codes are not stored there. “Forget this browser token” removes the local copy; run `zedlink-gateway admin STATE_DIR revoke DEVICE_ID` to revoke it on the workstation. Avoid untrusted browser extensions and shared browser profiles. The page uses a restrictive Content Security Policy, no third-party scripts, no cross-origin API calls, and text-only transcript rendering to limit script injection.

## Tailscale HTTPS

This host has a running Tailscale client. A disposable test confirmed that the gateway can bind its Tailscale IPv4 address and answer a locally originated TLS request there. A real Tailscale certificate was then issued with the user's approval, as recorded below. Use a **tailnet DNS hostname** with a certificate trusted by the browser. Tailscale documents `tailscale cert --cert-file=... --key-file=... HOSTNAME` after MagicDNS and tailnet HTTPS are enabled. Certificate issuance publishes the hostname in Certificate Transparency and file certificates require renewal; review those implications before issuing one. See [Tailscale HTTPS setup](https://tailscale.com/docs/how-to/set-up-https-certificates) and the [cert CLI reference](https://tailscale.com/docs/reference/tailscale-cli?tab=zsh).

Example after obtaining a valid certificate and confirming your host's values:

```sh
tailscale ip -4
chmod 600 /ABSOLUTE/PATH/tailnet.key
./gateway/target/debug/zedlink-gateway serve \
  TAILSCALE_IPV4:44679 \
  /ABSOLUTE/PATH/tailnet.crt \
  /ABSOLUTE/PATH/tailnet.key \
  /ABSOLUTE/PATH/probe/zedlink.sock \
  /ABSOLUTE/PATH/private-gateway-state
```

Visit `https://HOSTNAME:44679/` from a device connected to the same tailnet. Tailnet policy must allow that device to reach the host's port. The gateway rejects wildcard/public bind addresses and still requires its own paired device credential. A self-signed fixture certificate is only for local automated tests; a real browser must verify its production certificate and hostname. No `tailscale serve`, Funnel, firewall, router, or tailnet policy change is made by ZedLink. [Tailscale Serve](https://tailscale.com/docs/features/tailscale-serve) is a separate optional proxy route; it terminates browser TLS and has its own trust boundary.

## Moshi

Moshi documents [Browser Preview](https://getmoshi.app/docs/browser-preview) for host web servers forwarded into its in-app browser over an SSH session. This host has `moshi`/`moshi-hook` version 0.3.27 installed. In an isolated single-port test, its scanner discovered a disposable plain-HTTP control but **did not discover ZedLink's HTTPS listener**, even with the disposable certificate passed through `SSL_CERT_FILE`. This does not test a newer Moshi version or every HTTPS trust configuration; it means this installed Browser Preview cannot currently be claimed as a working route. Moshi's published [agent support tiers](https://getmoshi.app/docs/hooks) do not list native Zed Agent threads as a Chat View integration. Installing its generic agent hooks or driving a CLI agent would not meet ZedLink's same-native-thread requirement. ZedLink therefore uses the browser page and its own pairing/HTTPS gateway; no Moshi daemon or hooks were installed or modified.

## Validation boundary

`python3 tools/test_gateway_transport.py` runs a local HTTPS fixture and a headless Firefox browser. It checks the page headers, gateway-ID mismatch before pairing, pairing, synthetic thread selection, safe text rendering of an HTML-like transcript entry, one send, same-ID retry, reload without duplicate send, and revocation. The browser test accepts its **disposable self-signed localhost certificate only inside the test process**. It is not a real Zed/model or Tailscale-phone test. See [VALIDATION_REPORT.md](VALIDATION_REPORT.md).

`python3 tools/test_tailnet_bind.py` uses a disposable synthetic probe and certificate to request `/v1/gateway` on the host's own Tailscale IPv4 address. It tests local interface binding, not another tailnet device, DNS, a production certificate, or mobile access.

`python3 tools/test_moshi_discovery.py` uses an isolated `XDG_CONFIG_HOME` and an exact scan port. It leaves the user's Moshi configuration untouched. It verifies a plain-HTTP control is found and reports whether the installed Moshi discovers ZedLink HTTPS. The current result is `false` for HTTPS, so direct browser access over Tailscale remains the usable intended route once its certificate and real native-thread tests pass.

A separate live desktop test used the exposed disposable thread, paired a fresh headless Firefox profile to the loopback gateway, sent one harmless browser prompt, observed exactly one new native user entry and one assistant entry, and confirmed same-ID retry added no duplicate. The browser's certificate exception was confined to the disposable localhost test profile; this is not a trusted-certificate iPhone or tailnet result. The browser device credential was revoked afterward. The desktop user's visual confirmation applied to the earlier terminal-to-gateway prompt; the browser result was checked through the native snapshot.

On 2026-10-04 the installed `moshi-hook` had updated to 0.4.16. Repeating the same isolated discovery test still found the plain-HTTP control and did not discover the disposable ZedLink HTTPS listener; `global_moshi_config_changed` remained `false`. The workstation's Tailscale backend was running, but no live ZedLink gateway or exposed native thread was listening during this check. This is not a remote Moshi-to-native-Zed test.

The user subsequently approved and obtained a Tailscale certificate for `computer.example-tailnet.ts.net`. The gateway was bound only to `100.64.10.20:44679`; system-trusted HTTPS and native thread listing passed from that same host. An isolated Moshi 0.4.16 scan restricted to port 44679 still did not discover that trusted tailnet HTTPS listener. The first direct Safari attempt at `https://computer.example-tailnet.ts.net:44679/` returned “Server not found.” On the workstation, Tailscale DNS at `100.100.100.100` resolves the hostname to `100.64.10.20`, public DNS at `1.1.1.1` returns no A record, and trusted HTTPS at that name returns the pairing page. Phone DNS or route diagnosis is pending; a remote Moshi Browser Preview result is not claimed.
