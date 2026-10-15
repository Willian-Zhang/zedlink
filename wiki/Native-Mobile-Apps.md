# Native Mobile Apps

[← Wiki home](README.md)

The iOS and Android apps are native companions to desktop Zed. They use the same HTTPS gateway, explicitly exposed conversations, configured agents, and native permissions as the browser. They do not run a separate LLM.

## Pick an installation path

| Client | Requirements | Validation boundary |
| --- | --- | --- |
| Browser / PWA | Trusted HTTPS and device pairing; install to the home screen if desired | Most complete path; browser tests do not prove native app behavior |
| iOS | macOS, Xcode, signing and the SwiftUI source | Follow the [iOS build/device guide](iOS-End-to-End-Testing.md); wider physical-device coverage remains pending |
| Android | JDK 17, Android SDK 35, Gradle 8.10.2 and the Compose source | Development builds; current keyboard and speech issues still require device verification |

There is no stable App Store or Play Store release documented here. Use the [browser pairing guide](Running-and-Pairing.md) if you do not want to compile an app.

## Build Android

With the required tools already installed, from the repository root:

```sh
gradle -p android --no-daemon testDebugUnitTest assembleDebug lintDebug
```

The debug APK is written to `android/app/build/outputs/apk/debug/app-debug.apk`. Install it on a disposable test device with ADB:

```sh
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Use a compatible existing installation/signing key; Android will reject an update signed by a different key. Uninstalling removes local app data and requires pairing again. Gateway updates do not update native apps.

Check **Settings → Help & about** for the app version, build number and interface revision when reporting problems. “Latest APK” is insufficient to identify a build. Android changes increment the version/build; use the metadata shown by the installed app, rather than an APK filename.

## Connect to the same Zed conversation

1. Keep patched desktop Zed and the gateway running.
2. Verify trusted HTTPS from the phone on the configured private route.
3. Explicitly expose the intended conversation in desktop Zed with `/remote-control`.
4. In the native app's Connections screen, scan or paste the trusted pairing link, or enter the HTTPS address, gateway identity and one-time code.
5. Verify the gateway identity, pair, and select the exposed session.

Both devices must have network access to the gateway. Ping alone does not prove HTTPS connectivity or certificate trust. Each native app and browser installation pairs independently.

## Files and terminal

In Android source, Workspace contains Files, Changes, Terminal, Tasks and Debug. Files offers folders, breadcrumbs, text previews, wrap and find. Reading and attaching files require the corresponding desktop capabilities. Unsupported/binary files and partial previews have separate states; partial previews cannot be attached as complete files.

Terminal controls address an existing terminal in the exposed Zed workspace. Enable **View Project Terminals** and **Send Terminal Input** separately on desktop. Type a command or reply in the editable command field, review it, then press Enter. Esc, Tab, Ctrl C and arrows use the same guarded input path. Draft typing does not stream directly to the shell in the native clients.

Android source includes larger/smaller text controls and an expand action that hides workspace tabs. The latest terminal update is on `test/android-terminal-emulator`, version **0.2.12 (14)**, interface revision **2026.10.14.15**. It uses the activity window instead of a full-screen dialog to handle keyboard insets, removes the separate Command draft box, and renders the editable command and cursor inline after the terminal output. The reviewed line still uses guarded acknowledged submission on Enter; refreshed native output remains authoritative. Workspace tabs hide while typing. This correction has **not** passed emulator or physical-device validation. Check the branch and build metadata before testing.

When terminal delivery is unknown, check the terminal in desktop Zed before acknowledging the uncertainty. Recovery does not automatically resend the command. With an updated bridge, iOS and Android resize the same native PTY to the visible phone grid before later commands run. This makes shell-generated directory columns fit the phone and read top-to-bottom. Previously emitted desktop-width output is not rewritten. Output remains a bounded styled snapshot rather than a complete terminal emulator; full-screen terminal application fidelity is not established.

Both native composers expose image selection, and phone clipboard paste is available from the + menu. Selected or pasted images open a review screen with freehand annotation, Undo, and Clear before attachment. The native attachment permission, selected model support, 1 MiB image limit, and eight-item message limit still apply.

## Dictation and clipboard

The microphone is intended to fill an editable session or terminal draft. It never automatically sends a message or executes a command. Android source offers the phone's speech popup and an explicit in-app recognition path. In-app recognition uses an on-device engine when available; other speech services may process audio online, as explained before capture. Microphone permission alone does not establish speech-service availability.

An Android tester reported **unable to record audio** in the phone's speech popup even with ZedLink microphone permission enabled. The cause and a working device workaround remain unverified. Try the explicitly offered in-app path in a build that contains it, and check the speech provider's own microphone permission and Android's microphone-access control. These paths may share a provider. See [troubleshooting](Troubleshooting.md#android-dictation-cannot-record-audio).

Remote Clipboard uses explicit preview, Copy/Paste and desktop transfer actions. Enable its desktop permission first; inserting text fills a draft and does not submit it.

## Notifications and recovery

With the updated patched Zed bridge, iOS reads native Agent phases for responding, preparing/running a tool, waiting for approval, and compacting context. The conversation shows the current phase and places its progress wheel beside Stop; session rows distinguish compaction from ordinary work. The transcript uses a fast event/snapshot path while slower session-control refreshes run separately.

Enabled iOS local Agent alerts include approvals, request failures, and an observed compaction start. Apple Watch users can receive these through Apple's iPhone notification mirroring. In iOS **Settings → Notifications**, choose **Test Apple Watch in 10 seconds**, then lock the iPhone and keep the paired watch unlocked and on your wrist. Apple sends the notification to either the phone or watch according to device state; check **Watch app → Notifications → ZedLink** if it stays on the phone.

See Apple's documentation for [notification forwarding](https://developer.apple.com/documentation/watchos-apps/taking-advantage-of-notification-forwarding) and [Apple Watch notification settings](https://support.apple.com/guide/watch/change-notification-settings-apd9b833c9f3/watchos).

Native local alerts depend on the app receiving session updates. APNs/FCM background delivery is not configured; do not rely on native alerts while the app is suspended or terminated. The installed web app has a separate Web Push path with its own permissions and validation requirements.

Reconnect restores the selected gateway/target and reconciles authoritative thread state. Unknown delivery remains unknown until reconciled. Reconnecting does not expose a closed thread or restart a stopped workstation.

## Test and report issues

Include the app version/build, interface revision, Android/iOS version, device model, exact action, and whether it also fails in the phone browser. Share screenshots or error text with pairing codes, tokens and private deployment details removed.

The Android workflow is manual-only. Its optional emulator test uses Android 16/API 36 and a disposable, unpaired workspace fixture to check software-keyboard/input visibility and capture a labeled screenshot. This tests layout, not a real native gateway round trip or Samsung speech capture. The October 14, 2026 attempt was blocked by hosted-run availability before any job steps ran. No APK, emulator result or screenshot was produced by that attempt.

See [validation](Roadmap-and-Validation.md) and [development and testing](Development-and-Testing.md) for the remaining gates.

### Readable directory listings

Android's inline terminal input leaves more space for output, and the voice/special-key row appears while typing. **Browse project files** opens the scoped folder/file reader with one entry per row. This browser starts from the exposed project, not necessarily the shell's current directory. For a shell listing, **Terminal tools → List files one per line** prepares `ls -1F` at the terminal prompt: one entry per line, with a `/` suffix for directories. Review and press Enter to execute it; the action does not overwrite an existing draft or run automatically. Raw output keeps native colors and line breaks; **Wrap long lines / Keep original columns** controls presentation. Existing multi-column output is not converted into inferred filenames. Device rendering for this change remains pending.

### Create and switch terminals

Updated iOS/Android source includes **New terminal** (+) in the Terminal toolbar and in the empty state. Creation needs a rebuilt gateway and patched Zed advertising `terminal.create`, plus **View Project Terminals**, **Send Terminal Input**, and an exposed session. The configured shell starts in that project; the phone cannot specify a command, environment or arbitrary working directory. After creation the app selects the returned terminal. Tap its title to switch among existing terminals; switching does not close the other shells.

Creation uses a saved scoped request ID. If it times out, tapping New terminal again checks the same request without creating a duplicate. The picker is disabled while creation is in progress. Older bridges show instructions to open a terminal on desktop instead. The adapter passes a Rust check; native runtime and mobile build/device verification for creation remain pending because the capped full Zed build did not complete.
