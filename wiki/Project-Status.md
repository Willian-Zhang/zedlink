# Project Status and Validation

[← Wiki home](README.md)

ZedLink is public development software. Shared protocol support does not prove that every browser, native app, route, or device behaves the same.

## Current client status

| Area | Status |
| --- | --- |
| Linux host and browser/PWA | Most complete path; authenticated gateway fixtures and isolated native Zed tests exist |
| Same-thread remote control | Demonstrated for explicitly exposed native Agent threads; Zed remains authoritative |
| iPhone Safari | A physical same-thread round trip over trusted Tailscale HTTPS has been recorded |
| iOS native app | Source implemented; signing and broader simulator/physical-device validation remain pending |
| Android native app | Source and development build metadata implemented; current terminal input/layout and speech fixes need fresh device validation |
| Background native notifications | APNs/FCM are not configured; local alerts depend on received snapshots |
| Apple Watch | iPhone notification mirroring is supported by OS behavior; no dedicated watch app |
| App-store releases | No stable App Store or Play Store release documented |

## Verified behavior

- explicit desktop exposure through `/remote-control`;
- same-thread browser prompting and streamed native transcript updates;
- authenticated pairing and persistent normal-browser authorization;
- same-request replay/deduplication and native cancellation in isolated fixtures;
- `/compact` through the native command path;
- live reasoning, tool activity, errors, and approvals in bounded snapshots;
- scoped project files, search, changes, terminals, tasks, and debugger bridge tests;
- configured ACP agent discovery and browser fixture coverage;
- multiple named Zed targets without cross-target failover; and
- Web Push registration/service-worker behavior in deterministic tests.

## Remaining release gates

- signed native app distribution;
- fresh iOS and Android compilation for the current source;
- physical-device terminal, keyboard, dictation, camera, image annotation, and notification tests;
- APNs/FCM background delivery;
- a real external Codex or Claude Code end-to-end conversation for every advertised control;
- a physical test switching between two simultaneously running patched Zed instances;
- live certificate-renewal/reload validation near an actual renewal window;
- broader VPN/provider/browser/device coverage;
- complete rich tool and image-output parity; and
- Git history privacy cleanup and final public release audit.

## Deliberate boundaries

ZedLink does not include a generic remote shell, blanket mobile auto-approval, direct model credentials, automatic uncertain-send retries, public fallback routes, or access to unexposed projects and conversations.

## Interpreting test claims

- **Implemented** means source exists.
- **Compiled** means a relevant toolchain produced an artifact.
- **Tests passed** names the exact local or device checks that ran.
- **Device verified** requires the stated physical-device round trip.
- **Release ready** additionally requires signing, security/privacy review, documentation, and supported distribution.

See [Development and testing](Development.md) for reproducible commands and [Mobile apps](Mobile-Apps.md) for device reporting.
