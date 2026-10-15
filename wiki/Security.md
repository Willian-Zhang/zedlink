# Security

[← Wiki home](README.md)

ZedLink is remote control for a live development environment. Treat a paired client as sensitive access even when the route is private.

## Trust boundaries

- **Private route:** limits network reachability but does not authorize the application.
- **TLS:** authenticates and encrypts the configured HTTPS origin.
- **Pairing:** gives one client a revocable gateway credential.
- **Gateway identity:** prevents silently treating another gateway as the saved one.
- **Explicit exposure:** limits visibility to selected conversations.
- **Remote permissions:** limit files, attachments, terminals, Git, approvals, debugger controls, and settings.
- **Native Zed:** remains authoritative for Agent state, tool execution, approval choices, and cancellation.

ZedLink does not provide a generic remote shell and does not send model credentials to clients.

## Safe deployment checklist

1. Bind the gateway only to the intended private listener; wildcard and public binds are rejected.
2. Use a certificate trusted by each client and matching the saved hostname.
3. Compare the HTTPS origin and gateway identity before pairing.
4. Keep pairing links and codes private. They are temporary credentials.
5. Enable only the remote permissions needed for the current work.
6. Expose only the intended project and conversation.
7. Revoke lost, retired, or unfamiliar devices immediately.
8. Keep patched Zed, the gateway, and clients updated together.
9. Review logs and screenshots before sharing them publicly.

## Secret storage and logging

Certificates, private keys, pairing state, device credentials, model keys, and local configuration belong outside this repository. The project ignores common secret, build, and local-state paths, and `tools/check_public_release.py` scans the public working tree for high-risk patterns.

Routine logs must not include:

- model/API keys or authorization headers;
- pairing links, one-time codes, or device tokens;
- private-key material;
- full transcripts or sensitive tool arguments;
- private hostnames, IP addresses, gateway identities, or personal paths.

Run this before publishing a commit:

```sh
python3 tools/check_public_release.py
```

That check covers the working tree. Git history and commit metadata need a separate review because deleting a value later does not remove the earlier object.

## Tailscale certificate privacy

Tailscale HTTPS certificate issuance records the requested DNS name in public Certificate Transparency logs. Rename a workstation whose hostname reveals personal or confidential information before requesting its first certificate.

MagicDNS and VPN membership do not replace pairing. Do not disable certificate verification to work around a route or certificate error.

## Approvals and uncertain delivery

Approval responses are checked against the exact gateway, instance, epoch, thread, and native request. Stale responses are rejected. ZedLink does not automatically retry an uncertain message, command, terminal input, or approval.

Inspect authoritative desktop state before retrying an operation that may already have executed.

## Revoke access

Open **Settings → ZedLink → Paired Devices**, select the client, and revoke it. For a lost device, also remove its private-network access through the relevant provider. Revocation does not require changing model credentials because clients never receive them.

## Report a vulnerability

Follow [SECURITY.md](../SECURITY.md). Use a private GitHub Security Advisory and omit production credentials or transcript data. Do not open a public issue containing a live pairing link, token, private key, or private deployment identity.
