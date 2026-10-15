# ZedLink Wiki

This guide contains the detailed setup, operation, networking, security, development, and troubleshooting documentation for the project. Start with the browser/PWA path; native mobile apps are development builds with separate build and device-validation requirements.

## Start here

1. [Installation and setup](Installation-and-Setup.md)
2. [Connections and networking](Connections-and-Networking.md)
3. [Running and pairing](Running-and-Pairing.md)
4. [Everyday use](Everyday-Use.md)
5. [Native mobile apps](Native-Mobile-Apps.md)

## Reference

- [Agent commands](Agent-Commands.md)
- [Troubleshooting](Troubleshooting.md)
- [Security](Security.md)
- [Credits](Credits.md)
- [Development and testing](Development-and-Testing.md)
- [Publishing and upstream readiness](Publishing-and-Upstream.md)
  - [Draft Zed upstream proposal](Zed-Upstream-Proposal.md)
- [Roadmap and validation](Roadmap-and-Validation.md)

## Core design

ZedLink controls the same Zed-hosted Agent thread visible in desktop Zed. The phone and browser never receive model credentials and do not run an independent model client. The gateway accepts authenticated private HTTPS/WebSocket traffic and forwards narrow, versioned requests to the patched Zed bridge over a private local Unix socket.

Only conversations explicitly exposed with `/remote-control` are available remotely. Closing Zed makes its threads unavailable while leaving paired-device and gateway state intact.

## Device testing

- [iOS redesign and end-to-end testing](iOS-End-to-End-Testing.md) — local builds, disposable-session UI checks, and phone validation.

## Community support

Thank you to **Ringmast4r** and **diablo_rain** for testing and supporting ZedLink. See [Credits](Credits.md).

[← Project README](../README.md)
