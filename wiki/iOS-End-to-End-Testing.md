# iOS redesign and end-to-end testing

[← Wiki home](README.md)

## What changed

Conversations hide the app tabs and use a compact title/status, a rounded composer, expandable edit review, and a Workspace sheet with Files, Changes, Terminal, Debug, and Activity. Reading older messages pauses following; **Latest** returns to streamed output. Errors appear in the session/workspace. Approval actions disable while disconnected or submitting.

Files support filename filtering, native project-content search, and searching inside the selected file. The code/diff viewer supports line numbers, wrapping, colored added/deleted lines, copying, expansion, and partial-content notices. Workspace requests load the visible page's catalogs.

Use **+ → Attach photo / Paste image** for images. Images are converted to JPEG, resized, and limited to 1 MiB; total attachments are limited to eight. A model that advertises no image support disables image input. Attached files/images can be removed from the composer. **Session actions → Agent settings** opens the advertised model selector without leaving the conversation.

A submitted request freezes its text, paths, and image payload for retries with the same request ID. Only identity metadata is persisted for uncertain delivery; a relaunched app must reconcile and inspect desktop Zed rather than replay an unavailable payload. Late diff/search/model/terminal responses are checked against connection/session scope.

## Build on a Mac

The local runner reuses the `ZedLink` scheme and XcodeGen specification used by the existing macOS workflow. It never dispatches Actions.

```sh
bash tools/test_ios_local.sh build
xcrun simctl list devices available
bash tools/test_ios_local.sh unit 'platform=iOS Simulator,id=<disposable simulator UUID>'
```

Install Xcode with the iOS 17 SDK or newer and XcodeGen first; the app requires iOS 17 or newer. The runner prints its derived-data directory. The unsigned simulator app is under `Build/Products/Debug-iphonesimulator/ZedLink.app`. Install it on your selected disposable simulator:

```sh
xcrun simctl install '<simulator UUID>' '<derived-data directory>/Build/Products/Debug-iphonesimulator/ZedLink.app'
xcrun simctl launch '<simulator UUID>' dev.zedlink.app
```

For the physical iPhone, open the generated `ios/ZedLink.xcodeproj`, select your development team and connected iPhone, and Run the `ZedLink` scheme. Signing is required; simulator artifacts cannot install on a phone. Keep hosted workflows idle while the Actions budget is constrained.

Before the first device test, confirm that the phone can reach the gateway's trusted HTTPS hostname, pair this installation, and explicitly expose the disposable thread in desktop Zed. Grant local-network access when requested; microphone/speech and camera permissions are needed only for dictation and QR scanning. Test a clean install separately from an upgrade that should retain existing connection profiles.

## Pair a disposable native session

1. Use a separate Zed user-data directory and a new project. Do not use a personal running workspace. The patched binary supports `--user-data-dir` as used by the existing native fixture scripts.
2. Configure that isolated profile's model and ZedLink state/project settings. Enable only the controls being tested and configure a separate trusted HTTPS gateway route. Do not overwrite the normal gateway/profile.
3. Put a source file containing a known search string in the disposable project. Add a harmless Git change, a configured task, and debugger scenario if testing those controls.
4. Create an Agent thread in that project and expose it with `/remote-control`. Record its exact thread ID for test selection.
5. Pair the fresh simulator/app using that gateway's QR or short code. Confirm HTTPS identity and that the disposable thread is listed.

Existing [running and pairing](Running-and-Pairing.md) instructions explain gateway setup. A simulator and a physical phone must each be able to reach and trust the chosen HTTPS route; never disable TLS verification.

## Automated session UI checks

After manually pairing the disposable simulator, run:

```sh
ZEDLINK_E2E_THREAD_ID='<exact disposable thread ID>' \
ZEDLINK_E2E_SEARCH_TEXT='<known project string>' \
bash tools/test_ios_local.sh session 'platform=iOS Simulator,id=<simulator UUID>'
```

The tests check hidden/restored tab navigation, workspace views, keyboard dismissal, native project search, file viewing, and capture screenshots in the Xcode test results. No project is chosen implicitly. Tests skip without explicit fixture identity; **skipped tests do not count as validation**.

To also send one harmless prompt to that same test thread, add `ZEDLINK_E2E_ALLOW_SEND=1`. The optional test asks the configured Zed model for an exact marker and waits for it in the app. Inspect desktop Zed to verify one user message and the corresponding answer in the exact same native thread; a screenshot alone does not prove shared-thread behavior.

The runner forwards test variables with Apple's documented [`TEST_RUNNER_` convention](https://developer.apple.com/documentation/xcode/environment-variable-reference). No pairing secret or model key is supplied through test variables.

## Physical-device acceptance

| Check | Expected result |
| --- | --- |
| Session → Back → session | Tabs hide in chat and restore at Sessions; title and Workspace stay usable; unsent image/file attachments remain attached |
| iPhone 15 Pro keyboard, landscape, large text | Composer and approval controls remain reachable; Send/Stop/Workspace dismiss input focus |
| Long streaming thread | Scroll up without being pulled down; Latest resumes following; earlier-history loading preserves readable content |
| Files/search/diff | Search finds the expected source and line; viewer opens real file content; Wrap/Expand/Find work; partial results are labeled |
| Exact approvals | Approve/Deny affects only the pending native request; repeated taps are blocked; a desktop decision is reconciled |
| Connection interruption | Stale controls disable and errors remain visible; return/background recovery reconciles without a second prompt; retry retains the original text, files and images |
| Switch connections/targets during a read | Old file/diff/search/terminal responses do not populate the new session |
| Terminal/task/debugger | Enable each permission separately; run a harmless command/task in the disposable project; compare output and DAP state with desktop Zed |
| Images/model settings | Image becomes a removable draft attachment; unsupported models disable images; model changes occur in Zed |
| Voice/clipboard | Text remains editable before submission; pasting into terminal draft does not execute automatically |
| VoiceOver/Reduce Motion/light mode | Navigation and actions have readable labels and usable controls; streaming does not require animation |

Test Wi-Fi, cellular/Tailscale, background/return, and gateway restart separately. Record build revision, device/OS, route, expected effects, and actual results. Native APNs/background delivery is not configured without Apple credentials. Current native alerts are local while updates are received; use **Settings → Open browser for background push setup** for the existing browser push path. Watches may mirror supported phone notifications according to OS settings.

## Current evidence

Local Linux checks cover Swift syntax, shell syntax, public working-tree checks, and the disposable gateway/browser transport fixture. They do not compile SwiftUI or run iOS XCTest. This revision still requires a Mac build and the simulator/physical-device checks above before being considered validated for distribution.
