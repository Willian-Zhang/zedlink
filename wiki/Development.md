# Development and Testing

[← Wiki home](README.md)

## Repository layout

| Path | Purpose |
| --- | --- |
| `gateway/` | Rust gateway and browser/PWA assets |
| `protocol-core/` | Shared versioned protocol types |
| `ios/` | SwiftUI client source and tests |
| `android/` | Jetpack Compose client source and tests |
| `tools/` | Setup, management, diagnostics, fixtures, and local checks |
| `patches/` | Reviewable native Zed integration patch |
| `zed-source/` | Ignored local checkout of the maintained Zed fork |

The native integration is grounded in the maintained fork branch and pinned upstream revision recorded in the README and patch. Do not treat ACP external-agent support as proof that stock extensions can control an existing native Agent thread.

## Local Linux checks

Run from the repository root:

```sh
bash tools/check_linux.sh
python3 tools/test_gateway_transport.py
python3 tools/check_public_release.py
```

The Linux script runs format/static checks and offline protocol/gateway tests. The gateway transport fixture uses synthetic authenticated HTTPS/WebSocket traffic. It does not prove a real Zed thread, phone route, native app layout, or physical notification delivery.

For terminal presentation in a local browser fixture:

```sh
python3 tools/test_terminal_rendering.py
```

## Patched Zed verification

Use an isolated Zed profile and disposable project. Record the exact fork revision, upstream base, build command, and result. Required native assertions include:

- explicit exposure and removal with `/remote-control`;
- same-thread send, streaming, cancellation, and errors;
- request replay/idempotency across reconnects;
- native approval choices and stale-response rejection;
- scoped files, terminal, task, debugger, and settings permissions; and
- instance identity, persisted conversation identity, and event epoch changes.

Do not interrupt or repurpose an active personal Agent conversation for testing.

## Android

Before a native build, run:

```sh
free -h
df -h /tmp
```

Use the existing system JDK/SDK/Gradle and a disk-backed cache outside the repository. Keep the configured 1 GB Gradle heap, one worker, and in-process Kotlin compilation. Run one native build at a time.

```sh
gradle -p android --no-daemon :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

Compiling instrumentation tests is different from running them. Keyboard, microphone, camera, notifications, inset handling, and real gateway behavior require an emulator or physical device. Increment version/build metadata for every APK used in testing.

## iOS

On a Mac with Xcode and XcodeGen:

```sh
bash tools/test_ios_local.sh build
```

Run unit/UI tests only against disposable data. Simulator success does not establish physical-device microphone, notification, Keychain, network, safe-area, background, or Apple Watch behavior.

## GitHub Actions budget

Android and macOS workflows are manual-only. Do not dispatch hosted builds, add automatic triggers, or enable cloud validation without the repository owner's explicit approval. Report native compilation as **NOT RUN** when the local toolchain is unavailable.

## Documentation fixtures

Screenshots and demo recordings must use synthetic content from isolated fixtures. Record their generation details under `assets/screenshots/README.md` or `assets/recordings/README.md`. Review every frame for hostnames, IP addresses, usernames, paths, project data, pairing codes, tokens, and notifications before publishing.

## Public release check

Before publishing:

1. run all applicable local checks;
2. verify the maintained Zed fork revision matches the checked-in patch;
3. run `python3 tools/check_public_release.py`;
4. scan the complete Git history with a secret scanner;
5. inspect commit author metadata and deleted files for private information;
6. confirm screenshots and recordings are synthetic/redacted; and
7. keep unperformed native/device tests visible in [Project status](Project-Status.md).

The working-tree checker cannot sanitize Git history. If history contains private information, rewrite it before public release and coordinate the force push with every contributor.

## Upstream path

ZedLink currently needs native thread access that the stock extension API does not expose. See the [draft upstream proposal](Zed-Upstream-Proposal.md) for the verified API gap and a review-first contribution sequence. A decorative extension manifest would not provide same-thread submission, events, cancellation, approvals, or native settings.

## Contributing

Read [CONTRIBUTING.md](../CONTRIBUTING.md) and root [AGENTS.md](../AGENTS.md). Keep diffs focused, preserve unrelated work, document exact commands/results, and distinguish implementation, passing tests, and release readiness.
