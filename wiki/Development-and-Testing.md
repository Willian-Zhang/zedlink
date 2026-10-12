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
