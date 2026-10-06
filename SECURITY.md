# Security Policy

ZedLink controls an IDE-hosted coding agent and handles paired-device credentials. Please report security issues privately.

## Reporting a vulnerability

Use this repository's **Security → Report a vulnerability** flow to open a private GitHub Security Advisory. Do not open a public issue containing credentials, pairing links, device tokens, certificates, private network addresses, transcripts, tool arguments, or exploit details.

Include the affected commit, operating system, connection profile type, reproduction steps, and expected impact. Replace real secrets and private addresses with clearly marked examples.

## Supported versions

ZedLink is development software without a stable release line. Security fixes target the latest `main` commit and the pinned Zed fork branch documented in the README. Older commits are not supported.

## Security boundary

- Zed remains authoritative for model access, tools, permissions, approvals, and Agent execution.
- Every browser or app must pair independently even when it can reach the private network route.
- Only explicitly exposed threads are remotely visible.
- Trusted HTTPS is required; a certificate warning is a failed connection check.
- The gateway does not provide a generic terminal or remote shell endpoint.

See the [complete security model](wiki/Security.md) before deploying ZedLink.
