# iOS redesign and end-to-end testing

[← Wiki home](README.md)

## What changed

Conversations hide the main navigation row and use an opaque flat header with Back, title/status, Workspace and session actions. The composer, message surfaces, workspace tabs and settings lists use flat styling. Workspace includes Files, Changes, Terminal, Debug, and Activity. Reading older messages pauses following; **Latest** appears in a separate row below the transcript so it does not cover messages. Errors appear in the session/workspace. Approval actions disable while disconnected or submitting.

Light mode uses adaptive text/accent colors; the terminal preserves a black surface for the native terminal's ANSI palette. The prompt has no keyboard Done toolbar. **Connections → Workspaces** selects a configured Zed target. iOS and Android render paragraphs, headings, nested bullet/numbered lists, block quotes, fenced code and aligned Markdown tables as separate blocks. Wide tables scroll horizontally inside the transcript; cells wrap within their columns. Unfinished fenced code remains visible during streaming. These renderers cover these Markdown constructs; they are not complete CommonMark implementations.

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
| Session → Back → session | Main navigation disappears in chat and returns at Sessions; flat header and Workspace stay usable; unsent image/file attachments remain attached |
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
| Markdown formatting | Paragraphs stay separate; nested lists retain markers and indentation; tables show headers, rows and aligned cells; fenced code does not become list/table content |
| Scroll up / Latest | Latest occupies its own row below the transcript and never floats over message text |
| Notification permission and test | Settings shows the actual permission status; Enable reports the actual error; test notification has no approval actions |

Test Wi-Fi, cellular/Tailscale, background/return, and gateway restart separately. Record build revision, device/OS, route, expected effects, and actual results. Native APNs/background delivery is not configured without Apple credentials. Current native alerts are local while updates are received; use **Settings → Open browser for background push setup** for the existing browser push path. Watches may mirror supported phone notifications according to OS settings.

In Settings, use **Enable local approval alerts**, then **Send test notification**. The test schedules a harmless alert after three seconds. Check Notification Center and Focus settings if a banner is hidden. If permission is denied, use **Open iPhone notification settings**; repeated permission requests cannot override a denial. Scheduling failures now appear in Settings rather than being silently discarded. See [Apple's notification authorization reference](https://developer.apple.com/documentation/usernotifications/unnotificationsettings/authorizationstatus). This test validates local delivery only; it does not test gateway approvals, watch mirroring or suspended-app push.

## Approval forms and review controls

The native iOS client now submits the dropdown value it actually displays, applies schema defaults, validates required fields, finite numbers, integer values, numeric bounds and string lengths, and offers multiple choices for enumerated arrays. Android uses the same form rules. Optional untouched fields are omitted. These controls cover the advertised primitive fields; they are not a complete JSON Schema implementation. Nested objects and unsupported input types require desktop Zed.

Submission is blocked while a response is in flight, scoped to gateway/profile, workspace, instance, epoch, conversation and request. Approve/Decline still use Zed's existing permission and elicitation paths. There is no automatic approval or automatic retry of an uncertain response.

On iOS, expanded subagent messages use the same Markdown/tool/thinking renderer as the main conversation. File previews cache line splitting and syntax highlighting for the current content; searches cache matching line IDs. Find has Previous/Next and a position indicator. The review menu offers Jump to line and, for unified diffs, Jump to file. Diff reads poll Zed's existing loading/ready response and discard results after workspace/revision changes. Caching has been inspected in source; device performance has not been measured.

Known connectivity errors now explain the likely next step and offer Reconnect or Open Connections. Identity/certificate failures never bypass TLS verification. Routine delivery text moves into the session menu; unknown delivery and offline status remain visible.

Dictation Stop ends audio capture and allows final recognition results to arrive before cleanup, with a three-second timeout. Preparing/listening/finishing states are visible and labeled; Reduced Motion suppresses the waveform animation. Speech stays in an editable draft and is never submitted automatically. See Apple's [`endAudio()` reference](https://developer.apple.com/documentation/speech/sfspeechaudiobufferrecognitionrequest/endaudio%28%29).

Before distribution, test these additions with a disposable project:

- Submit an untouched required dropdown, optional blank field, false boolean, multi-choice array and invalid/out-of-range number; compare the values received by the native agent.
- Tap Submit/Decline repeatedly, decide the same request on desktop, and switch connections while a response is pending. Confirm only the intended request is resolved and no old form state appears in the new session.
- Expand a running subagent with lists, tables, tool output and thinking. Compare its published content and progress with desktop Zed.
- Review a large permitted file and multi-file diff: Previous/Next wraps, match counts reset on new searches, Jump to line/file scrolls correctly, and a deleted file has the correct name.
- Speak a final word immediately before pressing Stop. Verify it reaches the editable draft; test permissions, cancellation, manual edits, backgrounding and unsupported on-device languages separately.
- Disconnect network/VPN, use an invalid hostname/certificate, revoke pairing, close Zed and remove exposure. Confirm accurate guidance without replaying a prompt or weakening verification.

## Validation limitations

Local Linux checks cover Swift syntax, shell syntax, public working-tree checks, and the disposable gateway/browser transport fixture. They do not compile SwiftUI or run iOS XCTest. The Sessions revision also passed a hosted Mac simulator build, 25 unit tests and the isolated Sessions UI test ([Actions results](https://github.com/tjnull/zedlink/actions/runs/38340097403)). Android passed compilation, 14 unit tests and lint ([Actions results](https://github.com/tjnull/zedlink/actions/runs/38340102231)). The physical-device and native-agent acceptance checks above remain required before distribution.


## Sessions redesign

Sessions now uses a compact workstation/workspace selector, search by session or agent name, All / Needs attention / Running / Pinned filters, and flat grouped rows. Rows identify the native agent and distinguish approval/input requests, retries, failed idle turns, generating turns, ready and unknown state. Unknown does not become Working. Opening a conversation still hides the main navigation.

Approval/input counts use the existing `thread.approvals` and `thread.elicitations` reads, cached for five seconds while the native session list is open. Unsupported counts remain unknown, not fabricated zeroes. All reads are scoped to the current connection, workspace, instance and epoch. Pins persist locally by gateway/workspace/conversation; New activity means a change observed during this client run, not an unread transcript count or an invented server timestamp. The browser retains its visible sidebar and uses the same filters, grouping and status vocabulary. Android stops following the transcript when the user scrolls back and offers Latest in a separate row.

The manual **iOS build and Sessions preview** workflow compiles Debug for an isolated iPhone simulator, runs native unit tests and `SessionsPreviewUITests`, and captures both appearances. `--zedlink-demo` is Debug-only, bypasses gateway/model access, disables opening the sample conversations and labels the screen DEMO PREVIEW. It does not load a user's desktop Zed project. Screenshots prove simulator presentation only.

### Simulator preview

![Sessions in dark appearance](https://raw.githubusercontent.com/tjnull/zedlink/main/assets/screenshots/ios-sessions-dark.png)

[Light appearance](https://raw.githubusercontent.com/tjnull/zedlink/main/assets/screenshots/ios-sessions-light.png) · [Capture provenance](https://github.com/tjnull/zedlink/blob/main/assets/screenshots/README.md)

These images are from the successful **589b158** build. Its disabled sample rows appear dimmed; real sessions are enabled. The subsequent preview-only correction (**0bcc0f3**) is pushed but its capture job was refused by GitHub account billing/spending limits before any steps ran. No new build or screenshot of that correction is claimed.

Additional acceptance checks:

- Verify agent names against Zed, including Codex and Claude Code; inspect failed/retrying turns separately from ready sessions.
- Create a real pending approval and input request in an exposed disposable thread; verify counts, open the conversation and resolve only that exact request.
- Pin a session, relaunch, change private routes to the same gateway, and switch to another gateway/workspace with matching thread IDs. Pins must not leak between different gateway/workspace identities.
- Start work in a different session while viewing the list: New activity should appear only after an observed update. The first load must not mark every conversation unread.
- Disconnect the route: stop activity animation and label retained state Last known. Restore connectivity and verify authoritative reconciliation.
- On Android, read earlier output while the agent streams. Preserve the viewport; Latest explicitly resumes following and never overlays a message.

## Native Settings refactor (October 13, 2026)

Global Settings now contains device appearance, notification setup, connection/access diagnostics and Help & about. Session model/context controls live in the conversation's **Agent settings**, not global preferences. iOS Settings is extracted into `SettingsView.swift`; Android Settings into `SettingsScreen.kt`, with appearance tokens in `AppTheme.kt`. Neither client configures model credentials or owns a model runtime.

Android now persists System/Dark/Light and adapts the shared app colors and file highlighting. Settings scrolls and wraps values rather than forcing endpoints into a single horizontal row. Notification setup checks the Android permission, app-level blocking and approval-channel blocking, and offers a harmless test notification and system settings link. iOS exposes permission-aware Enable/Test/Disable controls. Both distinguish local delivery from unconfigured native background push.

Diagnostics shows observed connection state and the selected workspace's advertised file, terminal, debugger and clipboard access. Disconnected retained access is labeled Last known; absent information is Unknown. Access permissions remain configured in desktop Zed. Version/build comes from app metadata rather than a fixed runtime label.

Android removal requires confirmation describing the credential and all local addresses for that gateway. It is local removal, not server revocation. Removing an inactive gateway preserves the active conversation; removing the active gateway cancels its polling/event transport and clears local notifications. Appearance remains saved.

### Checks before compiling/distributing

Native compilation, simulator/emulator rendering and physical-device checks for this refactor are **NOT RUN** on the Linux development host. No hosted Actions were dispatched. Earlier successful Actions runs cover earlier revisions only.

On a Mac, use the existing `bash tools/test_ios_local.sh build` and explicit disposable simulator commands described above. Android's existing manual workflow uses `gradle -p android --no-daemon testDebugUnitTest assembleDebug lintDebug`; run it locally with the configured SDK/toolchain. Hosted validation requires separate owner approval.

Use isolated profiles and disposable projects:

1. Open Settings with no connection, a connected gateway and a disconnected gateway. Inspect Unknown versus Last known access; verify different workspace permissions are not mixed.
2. Switch System/Dark/Light, relaunch, and change the system theme. Check Settings, session rows, conversation Markdown, approvals, files and terminal readability with large text and landscape. Native terminal colors supplied by Zed retain their original styling.
3. Grant/deny notification permission, block the app and approval channel in Android Settings, then return. Status and available actions must reflect the OS. Test notifications must contain no approval actions or private content.
4. Open Agent settings in an idle native session, change an advertised model, and compare with desktop Zed. Offline, generating, unknown and in-flight states must not permit model changes. Switch workspace/connection during a read/update and verify no stale settings appear.
5. Cancel removal and confirm all profiles remain. Remove an inactive gateway and ensure the current conversation continues. Confirm active removal removes all linked local addresses and retains the appearance preference; pair again explicitly.
6. Scroll Settings on a small device with large text. Reach all controls without endpoint overflow or navigation obscuring content.

APNs/FCM delivery, watch mirroring, actual approval notifications and physical same-thread round trips remain separate acceptance gates.

## Native Connections refactor (October 13, 2026)

Connections now separates **Saved connections**, the selected connection's **Workspaces**, and **Add connection**. Tap a saved row for connect/reconnect, editing, address/identity details and removal. Rows show the user-selected route category and observed state only for the active profile; other saved profiles are not labeled online without a check. Route selection does not control another VPN app.

Pairing is a dedicated screen: Scan QR or Paste pairing link, check HTTPS and expected gateway identity, then explicitly Pair and save. Scanning no longer automatically submits a pairing code. Advanced identity fields expand on demand. A credential for an already paired gateway can be reused for an explicitly added address after verifying that address's gateway identity. Editing a saved address cannot change its gateway identity.

Pairing drafts survive tab navigation and scanner cancellation/failure in memory. Codes are masked, never logged or saved to preferences, and cleared after a successful save. They do not survive process termination. A successful pair saves access even when desktop Zed is unavailable; inspect the saved connection's diagnostic rather than pairing repeatedly.

Android now persists profile IDs and route categories and retains multiple addresses for one gateway. Existing profiles without IDs load with a deterministic legacy ID; the previous active-gateway preference remains a migration fallback. Active selection is saved by profile ID, while credentials and workspace preference remain gateway-scoped. Reconnect selects the chosen address rather than silently keeping the prior endpoint. Android currently accepts gateway origin addresses only, with no proxy path prefix; unsupported prefixed addresses are rejected explicitly.

Removing a saved connection removes only that profile/address. Other addresses retain the shared gateway credential; the last address removes its local credential. The Settings **Remove local access** action still removes all addresses and the credential for that gateway, with its own confirmation. Neither action revokes the remote device record or stops desktop Zed.

Connection attempts and reads discard obsolete results after route/workspace changes. Repeated attempts are blocked while connecting or pairing. iOS retains uncertain sends when explicitly switching addresses of the same gateway and does not resubmit them automatically. This does not establish physical recovery or native runtime validation for the new revision.

### Additional device acceptance

1. Pair in a disposable profile, then add a second private address for the same gateway. Verify both rows remain, share authorization, and select the intended endpoint after relaunch.
2. Edit one address/name/route category, check identity and save. Verify another gateway's certificate/identity never receives the saved credential. Test HTTPS failure, DNS failure, revoked pairing and unavailable desktop Zed separately.
3. Enter a draft, close Add connection, switch tabs and reopen. Cancel camera scanning and paste an invalid link. Verify draft values remain and no pairing request is sent merely by scanning/testing.
4. Double-tap Connect/Test/Pair; switch/reconnect after a slow response and remove access during an outstanding connection attempt. Confirm old responses cannot restore a removed connection or populate a different workspace.
5. Remove one of two addresses and reconnect through the other. Remove the last address and verify pairing is required. Cancel both removal confirmations and verify no profiles/credentials change.
6. Inspect small screens, landscape, large text, both appearances, VoiceOver/TalkBack and keyboard in pairing/details screens. Reach Back/Close and every input without overflow.
7. Interrupt connectivity during a pending prompt, explicitly change private routes to the same gateway, and reconcile the original request. Confirm one native turn and no automatic duplicate send. Test gateway/Zed restarts separately.

Local Kotlin policy/regression tests pass (18 tests total, including four new connection tests); Swift and changed Kotlin syntax checks pass. Native iOS/Android compilation, updated XCTest, camera/scanner, migration/credential storage and physical route switching are **NOT RUN** on this Linux host. No hosted Actions were dispatched.

Also verify a Zed restart between pages: Android must discard the old indexed transcript before reading the new epoch. An explicit retry must remain bound to its original gateway/workspace/instance/epoch/thread and original context paths; it must not submit to a newly restarted instance. This source guard is not a completed native idempotency test.


## Exposure recovery and native errors (2026-10-14)

Rebuild the native clients before testing these source changes. Use a disposable project and an explicitly exposed test conversation, not a real work transcript.

1. Open that session on iOS. Stop its exposure from desktop Zed. The client must stop displaying it as current and show the unavailable/exposure message.
2. Re-expose the same desktop conversation. Without changing the iOS navigation destination, its current transcript must reload. Confirm the persisted thread ID, instance ID and epoch match; no prompt should be resent.
3. Kill and relaunch the iOS app, reconnect and select that session. The newest transcript page must be visible initially. While following, streamed text and thinking updates must remain visible; manually scrolling upward must pause following, and Latest must resume it.
4. Using a deterministic local test model in an isolated Zed profile, return a context-limit failure and then a model-connection failure. Both mobile clients must display the native title/message even if the gateway remains reachable. Refresh and load earlier history: the current failure must remain visible until the authoritative snapshot clears it.
5. Enable local notifications. A non-retrying native failure must produce a generic Review alert while snapshots are received, without exposing the error text, transcript or tool arguments in the notification. Repeated identical snapshots must not repeatedly alert; after recovery the old alert must be removed. Tapping Review must open the matching exposed conversation and must not submit/retry/approve anything.

APNs/FCM are still unconfigured. Local failure alerts cannot promise delivery while the OS suspends or terminates the app. Browser Web Push is a separate channel.

### Android QR recovery

Use a disposable emulator or test app installation. `CameraNavigationRecoveryTest` checks that the Connections/Add screen survives activity recreation; `NativeAgentErrorTest` exercises Android's real JSON decoder. Neither proves physical camera delivery or HTTPS pairing.

On a physical Android device: Add a connection, launch Scan, rotate the device while scanning, then scan a freshly generated workstation QR. The Add screen must remain open with the endpoint and expected gateway filled. Test HTTPS, then explicitly Pair and save. Relaunch and confirm the saved profile connects. Also test camera denial, cancellation, invalid/expired QR, activity recreation with Don't keep activities enabled, and a revoked credential. Do not store one-use codes in saved-instance state or logs.

Local Android Gradle/SDK and Apple toolchains are unavailable on the Linux workstation; these native gates remain NOT RUN until executed on their respective toolchains/devices.

### Android camera stutter follow-up

QR result and camera-permission launchers now register unconditionally in MainActivity; the callback imports the result into the ViewModel and explicitly opens Connections/Add after recreation. A private PairingCaptureActivity uses the library capture theme and portrait orientation, with orientation/screen-size configuration handling; options lock orientation and prohibit barcode image files. Scan-in-progress is restored as a boolean, blocking duplicate launches. Successful scans never pair or transmit a saved credential automatically; users must verify HTTPS and choose Pair and save. Null/denied/invalid results reopen the pairing form with visible feedback.

CameraNavigationRecoveryTest also feeds results parsed by the real ScanContract into the activity callback after recreation and checks that HTTPS verification remains required, plus cancellation feedback. These are callback fixtures, not a physical camera/ActivityResultRegistry round trip; all remain NOT RUN here.

If the host is pingable but pairing still fails, open the exact gateway HTTPS URL on the phone, or run `curl --max-time 10 https://<gateway-host>:<port>/v1/gateway` in Termux. Do not use `-k` or disable TLS verification. Ping does not test the gateway port, HTTPS certificate, device authorization or camera lifecycle. Do not share QR codes, one-use codes or tokens in diagnostics.
