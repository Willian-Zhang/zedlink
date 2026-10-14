# Codex instructions for ZedLink

## Goal and scope

Build a Zed integration, local gateway, and native SwiftUI client that control the same existing native Zed Agent thread from an iPhone. Reuse the configured local LLM. Do not replace the agent runtime or add an independent model client.

Read README.md, docs/ARCHITECTURE.md, docs/BUILD_PLAN.md, docs/PROTOCOL.md, docs/IOS_APP.md, docs/NETWORKING.md, and docs/TEST_PLAN.md before implementation.

## Source grounding

- Pin the Zed revision and record exact inspected symbols and files.
- Verify extension feasibility by working code or inspected supported APIs; documentation resemblance is insufficient.
- Prefer an extension; use a minimal source patch/API addition only where verified gaps require it.
- ACP external-agent integration is not evidence of access to an existing native thread.
- Never invent existing methods, paths, settings, build targets, Xcode schemes, or successful results.
- Preserve existing instructions and unrelated user modifications. A nested Zed checkout retains its own AGENTS.md rules.

## Implementation rules

- Use narrow adapters around the same submission, execution, cancellation, and permission paths as the desktop.
- Respect application-thread scheduling and entity lifetimes. Network handlers must not mutate UI/agent entities from arbitrary threads.
- Distinguish instance identity, persisted conversation identity, and event epoch.
- Never duplicate a turn because of reconnection. Unknown delivery must remain unknown until reconciled.
- Retain native queueing and approval behavior. No blanket mobile auto-approval.
- The agent remains running if the phone disconnects. Closing Zed makes its instance unavailable.
- Remote controls apply only to explicitly exposed projects/threads.
- Use authenticated TLS plus device pairing. VPN reachability is not application authorization. Support Tailscale, WireGuard, other routed VPNs, local HTTPS, and custom HTTPS through profile-based routing; do not assume control over third-party VPN apps.
- Never include model keys, device secrets, pairing secrets, full transcripts, or sensitive tool arguments in routine logs.
- Do not introduce a generic remote shell endpoint.
- Keep UI mocks clearly labeled and never use them as evidence of native integration.

## Work sequence

Follow the BUILD_PLAN gates. Continue independent work when an environment prerequisite is missing, but do not mark dependent work complete. Maintain docs/VALIDATION_REPORT.md with actual commands, results, unavailable capabilities, and next steps.

Create implementation scripts and CI only after discovering real build/test commands. Keep phase completion reviewable through focused diffs and reproducible evidence. Do not publish, upload to an App Store, or send external messages as part of this build.

## Testing

Use disposable projects and isolated Zed profiles/configuration. Do not read or edit unrelated real projects to test functionality. Test mocked transport separately from real Zed behavior. Required gates include permissions, replay/idempotency, and a physical phone round trip.

If macOS, signing, a physical iPhone, the actual local model, or native Zed source is unavailable, report the exact unperformed tests and deliver useful work that can be verified in the current environment.

## Completion

Working mobile UI alone is not completion. A demonstrated shared native Zed thread, authoritative state assertions, exact reproducible commands, and accurate limitations are required. Distinguish implementation complete, tests passed, and release ready.

## UI and network requirements

Follow IOS_APP.md for modern native controls, readable chat, simple onboarding, accessibility, and truthful status. Follow NETWORKING.md for profile identity, TLS, VPN/service prerequisites, proxy trust boundaries, and provider-independent recovery. Embedded VPN engines are optional later work requiring verified entitlement/API feasibility. Never silently fall back from a private route to a public endpoint.


## Android test versions

Increment Android versionCode and versionName for each APK-affecting update, and update UI_REVISION when the interface changes, so the owner can identify each test build.

## GitHub Actions budget

The owner's Actions allowance is nearly exhausted and there is no budget for overages. Keep Android/macOS workflows manual-only. Do not dispatch hosted builds, re-enable automatic triggers, or launch cloud validation without explicit owner approval. Use local verification; report native app compilation as NOT RUN when the local toolchain is unavailable.


## Local build memory

This workstation has 16 GB RAM and `/tmp` is a RAM-backed tmpfs. Do not download or bootstrap SDKs, JDKs, Gradle distributions, or dependency caches inside this repository or `/tmp`. Use an existing system toolchain and a disk-backed cache outside the project. If the required tools are unavailable, report the missing prerequisite rather than automatically downloading a toolchain. Check `free -h` and `df -h /tmp` before native builds. Run one native build at a time; retain the Android 1 GB heap limit, one worker, and in-process Kotlin compilation. Do not increase build memory or start overlapping build processes while the workstation is under memory pressure. Preserve concise test results, then remove disposable build artifacts when they are no longer needed.
