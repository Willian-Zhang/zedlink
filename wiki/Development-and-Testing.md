# Development and Testing

[← Wiki home](README.md)

## Build and test from a terminal

After building patched Zed, run `python3 tools/test_native_debugger.py` from a graphical Linux session to create an isolated project/profile and exercise saved debugger launch, DAP state, replay, pause, continue, stepping, restart, and stop. The script uses a deterministic local DAP fixture, removes its temporary files after success, and does not open or modify your normal Zed profile.

The IDE tasks call these same scripts:

```sh
# Build or update the pinned patched Zed and gateway
bash tools/install_linux.sh

# Install, configure, and add global IDE tasks
bash tools/setup_zed_ide.sh

# Run static checks and protocol tests
bash tools/check_linux.sh

# Run the synthetic HTTPS/WebSocket browser transport test
python3 tools/test_gateway_transport.py
```

The browser transport fixture does not prove native Zed integration. Native tests must use a disposable project, a real patched Zed process, and an explicitly exposed native Agent thread.

The patch is pinned to Zed revision:

```text
c66312b200d113694fca08c1d468669028a09a0e
```

The stock extension API at that revision cannot enumerate or control an existing native Agent thread, which is why ZedLink requires the narrow, reviewable source patch under `patches/`.

### Zed upstream fork and contribution path

The nested checkout follows [`tjnull/zed:zedlink/native-agent-remote-control`](https://github.com/tjnull/zed/tree/zedlink/native-agent-remote-control), based on the exact pinned revision above. Its commits separate cancellation correctness, the opt-in local Agent bridge, native failure reporting, project and Git context, search, and native ZedLink settings. The fork is the checkout's `origin`; the official [`zed-industries/zed`](https://github.com/zed-industries/zed) repository is retained as `upstream` for revision comparison and future rebases.

Zed's contribution policy requires feature work of this size to start as a GitHub Discussion unless a staff-confirmed issue already exists. It also requires the human author to understand and review all AI-assisted code, manually test Zed, retain tests and evidence, sign the CLA, and write the maintainer communication. The checkout deliberately retains Zed's README review marker until that human review is complete. Do not remove it automatically.


## GitHub Actions budget

Android and macOS workflows run **only on manual dispatch**. Pushes do not launch hosted builds. Do not dispatch either workflow without the repository owner's approval while the Actions allowance is nearly exhausted. Use local Linux static checks, browser fixtures, and isolated native terminal checks by default. SwiftUI and Compose source changes that cannot be built locally must be labeled uncompiled, rather than silently running a cloud build.

Terminal icon fonts are bundled and self-hosted. Source, subset ranges, and upstream notices live in `gateway/web/fonts/`; copies of the notices accompany the native app resources.

For the desktop terminal font and column layout, run `python3 tools/test_terminal_rendering.py`. This uses local Chromium with synthetic output and the production CSS/text renderer; it does not verify a native Zed session. The authenticated Firefox desktop/mobile fixture remains `python3 tools/test_gateway_transport.py`. No hosted Actions run is required.

The pinned base is upstream `main` at `c66312b200d113694fca08c1d468669028a09a0e` (October 12, 2026, Zed 1.25.0 development source). The fork incorporates the ACP v2 changes while preserving the native cancellation guard and bounded compaction output. The previous 1.22 stable base remains available in the fork's backup branch.

`python3 tools/test_native_agent_smoke.py` launches patched Zed with a disposable profile/project and a deterministic loopback model. It checks native streaming/replay, exact-turn cancellation, and tool denial/approval; it does not contact the user's LLM. The Zed fork's repository Actions are disabled to protect the owner's limited remaining budget; ZedLink Android/macOS workflows remain manual-only.

The merged upstream ACP v2 API also introduces standalone permission requests. ZedLink currently projects native tool-linked authorization choices; standalone ACP v2 permission requests are not yet exposed remotely. Use desktop Zed for those requests. Physical mobile validation must be repeated before treating this upstream update as release ready.

## iOS session layout verification

The current iOS source hides bottom navigation inside conversations and opens a five-view Workspace sheet (Files, Changes, Terminal, Debug, Activity). It removes the separate healthy Live header label, uses a single rounded composer, and collapses Agent edit review. These changes require rebuilding the iOS app; restarting Zed or the gateway does not update an installed app.

Xcode/simulator and physical iPhone validation of this revision have not run on the Linux workstation. Before distributing a new build, use the existing `ZedLink` Xcode scheme to check:

- Open an exposed session: bottom tabs disappear, title/back/Workspace remain accessible, and tabs return after Back.
- Open every Workspace view against a paired gateway. Verify file contents, diffs, permitted stage/unstage, configured tasks, terminal input, debugger controls, and native activity. Disabled capabilities must remain unavailable.
- Confirm a selected terminal survives leaving/reopening Workspace; voice/clipboard fill editable drafts and uncertain input is not automatically retried.
- On iPhone 15 Pro, check keyboard show/hide, composer safe area, large text, VoiceOver, landscape, and busy/offline states. Approvals must stay visible and exact-turn Stop must target the active native turn.

No hosted Actions build was dispatched for this layout change. Local syntax parsing cannot establish SwiftUI type checking or rendered layout correctness.

The expanded [iOS end-to-end guide](iOS-End-to-End-Testing.md) includes the local Mac runner, opt-in disposable-thread UI tests, and physical-device acceptance matrix.


### Local build memory

On small workstations, keep SDKs, JDKs, and Gradle caches on a disk-backed filesystem. Check `free -h` and `df -h /tmp` first: a tmpfs consumes memory and may also exhaust swap. The Android project limits Gradle to a 1 GB Java heap and one worker and compiles Kotlin inside Gradle. Native tooling still consumes additional memory outside that heap, so avoid simultaneous native builds.

Use an existing installed JDK, Android SDK, and Gradle 8.10.2. Set `JAVA_HOME` and `ANDROID_HOME` to those installations and keep `GRADLE_USER_HOME` in a disk-backed cache outside the repository. Do not bootstrap toolchains into this checkout or RAM-backed `/tmp`. When prerequisites are missing, report compilation as NOT RUN.

Run the discovered tasks `gradle -p android --no-daemon :app:testDebugUnitTest :app:assembleDebug` once for the current changes. Run lint or instrumentation compilation when that gate is needed; device tests require a connected device or emulator and are distinct from compiling the test APK. Preserve a concise result record and only the APK needed for device testing, then clean disposable outputs. An interrupted build does not establish that lint or device tests passed.


### Native notification and input acceptance checks

Use a disposable project and isolated test pairing on both platforms. Rebuild the current source with an installed toolchain before testing. Do not use the owner's active project.

1. Run iOS `NotificationResponseQueueTests` in the generated ZedLink scheme; run Android `NotificationReceiptsTest` and `AppearanceTest` on a device/emulator. Compiling the test APK is separate from running it.
2. Enable local approval alerts. Create an approval in the selected disposable session, terminate the phone app, and reopen through the alert. Confirm session navigation waits for connection restoration.
3. Approve/deny once, then reopen the same alert. Confirm there is no second native response. Resolve another approval on desktop before opening its phone alert; confirm the stale request is rejected. Repeat with a restarted Zed epoch and changed workspace.
4. Interrupt the private route while opening an alert. Confirm no automatic response or route failover occurs. Reconnect and explicitly review current requests. Test lock-screen authentication and permitted watch mirroring separately.
5. Deny camera permission and use Paste pairing link. Share a pairing link into Android; verify it opens a draft and requires Test HTTPS followed by Pair and save. Reject duplicate fields, HTTP destinations, and wrong gateway identities.
6. Deny microphone permission, then retry after permitting it. Dictate editable text; switch sessions and background the app mid-dictation. Confirm no stale text reaches another draft and capture stops. Check on-device support and the explicit device-service fallback separately.
7. Check light/dark themes, large text, keyboard visibility and terminal layout on a small phone, including Android 16. Confirm notification status clearly says native push is not configured.

These device checks are pending. The source includes the recovery tests; no new hosted build is authorized by this checklist.


### Android send-race checks

With a delayed response in an isolated gateway fixture, send from session A and switch to B before the response arrives. Verify B's draft and delivery state remain unchanged. Repeat by editing the draft or context attachments in A while sending; accepted delivery must preserve those new edits. Interrupt delivery, then explicitly choose Retry original request: it must reuse the same request ID and refuse a changed gateway/workspace/instance/epoch/thread. Repeated taps must not launch a second concurrent retry. These latest runtime tests remain NOT RUN.
