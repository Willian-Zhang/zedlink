# Local gateway setup

Status: Linux development build. The TLS gateway passed a local transport fixture and a paired loopback HTTPS prompt to an exposed, desktop-created native Zed thread. One native user and assistant entry appeared; the user confirmed both on desktop. This does not establish an iPhone or remote VPN route. See VALIDATION_REPORT.md.

The gateway now serves its paired browser UI at `/`. See [BROWSER.md](BROWSER.md) for browser behavior, Tailscale certificate setup, and Moshi notes.

## Build and start

From the project root:

```sh
cd gateway
cargo build --offline
cd ..
```

Start patched Zed with `ZEDLINK_PROBE_DIR` and `ZEDLINK_PROBE_PROJECT_ROOT` as described in [LOCAL_PROBE.md](LOCAL_PROBE.md). Select `/remote-control` in a native Agent thread to expose it. The probe directory and socket must have modes 0700 and 0600.

Supply a certificate and private key whose hostname is trusted and verified by the client. The gateway does not issue certificates. Never disable TLS verification.

```sh
./gateway/target/debug/zedlink-gateway serve \
  127.0.0.1:44679 \
  /ABSOLUTE/PATH/cert.pem \
  /ABSOLUTE/PATH/key.pem \
  /ABSOLUTE/PATH/probe/zedlink.sock \
  /ABSOLUTE/PATH/private-gateway-state
```

The final directory is created with mode 0700 if absent. Its state file stores a stable gateway UUID and device-token digests with mode 0600. The private `admin.sock` lives there. Start Zed first: gateway startup checks the native socket and its parent are private. The gateway refuses wildcard and public address binds. Use a private interface address for routed VPN access or loopback behind an explicitly trusted proxy. A proxy terminating TLS sees plaintext application data.

## Pair and revoke

From the same local user account:

```sh
./gateway/target/debug/zedlink-gateway admin /ABSOLUTE/PATH/private-gateway-state pair-code
./gateway/target/debug/zedlink-gateway admin /ABSOLUTE/PATH/private-gateway-state devices
./gateway/target/debug/zedlink-gateway admin /ABSOLUTE/PATH/private-gateway-state revoke DEVICE_ID
```

`pair-code` prints a one-use 32-byte hex secret valid for five minutes and limited to five failed attempts. Do not put it in logs or URLs. After verifying the server certificate and expected gateway identity, POST `{"code":"…","device_name":"…"}` to `/v1/pair`. The response contains a device ID and bearer token. The phone must store its token in Keychain. The gateway stores only a digest. Revoked HTTP requests are denied and active WSS streams close on the next poll.

Authenticated `POST /v1/rpc` forwards version-1 JSON requests to Zed. Send the token in `Authorization: Bearer TOKEN`. The gateway scopes send and status request IDs by device before forwarding. A timeout remains uncertain; retry the exact ID or query status, and never create a fresh ID automatically.

`GET /v1/events?thread_id=...` upgrades to WSS and polls the bounded native event feed. Clients fetch snapshots for changed content and resync on `RESYNC_REQUIRED`. The gateway allows only `instance.info`, `thread.list`, `thread.snapshot`, `thread.events`, `thread.send`, and `request.status`. Experimental native cancellation and approval resolution remain unavailable remotely until live race tests pass.

## Network profiles and limits

The same HTTPS endpoint can be saved under Tailscale, WireGuard, another routed VPN, local HTTPS, or custom proxy profiles. These labels describe user-configured routes; the gateway does not start or inspect VPN clients. An alternate endpoint must verify the same gateway identity before receiving the device token. Do not silently fail over from private to public.

Run `python3 tools/test_gateway_transport.py` for the synthetic transport fixture. It checks TLS hostname rejection, unauthenticated denial, pairing reuse, device isolation, WSS revocation, and forbidden methods. See [VALIDATION_REPORT.md](VALIDATION_REPORT.md) for the separate real-Zed same-thread loopback prompt and browser check. No external route, physical phone, approval race, or provider-origin assertion has passed through this gateway.

The user approved issuing a Tailscale certificate for `computer.example-tailnet.ts.net`; Tailscale records that hostname in public Certificate Transparency. A disposable gateway using that certificate was bound to the private Tailscale IP `100.64.10.20:44679`. System-trusted HTTPS, MagicDNS, pairing, and real exposed-thread listing passed **from the workstation to its own tailnet address**. Another tailnet device and phone prompt have not yet been verified. The certificate files are in a private temporary directory, expire on 2027-01-03, and require renewal before then. This is test setup, not a persistent service installation.
