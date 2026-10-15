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

Android source includes larger/smaller text controls and an expand action that hides workspace tabs. The latest terminal-layout correction is on `test/android-terminal-emulator`, version **0.2.8 (10)**, interface revision **2026.10.14.11**. It uses the activity window instead of a full-screen dialog to handle keyboard insets, places a labeled Command draft above output, and hides workspace tabs while typing in Terminal. Draft text appears immediately in that editor; remote terminal output echoes it only after submission. That correction has **not** passed emulator or physical-device validation. Check the branch and build metadata before testing.

When terminal delivery is unknown, check the terminal in desktop Zed before acknowledging the uncertainty. Recovery does not automatically resend the command. Output is a bounded styled snapshot, not a complete terminal emulator; remote resize and full-screen terminal application fidelity are not established.

## Dictation and clipboard

The microphone is intended to fill an editable session or terminal draft. It never automatically sends a message or executes a command. Android source offers the phone's speech popup and an explicit in-app recognition path. In-app recognition uses an on-device engine when available; other speech services may process audio online, as explained before capture. Microphone permission alone does not establish speech-service availability.

An Android tester reported **unable to record audio** in the phone's speech popup even with ZedLink microphone permission enabled. The cause and a working device workaround remain unverified. Try the explicitly offered in-app path in a build that contains it, and check the speech provider's own microphone permission and Android's microphone-access control. These paths may share a provider. See [troubleshooting](Troubleshooting.md#android-dictation-cannot-record-audio).

Remote Clipboard uses explicit preview, Copy/Paste and desktop transfer actions. Enable its desktop permission first; inserting text fills a draft and does not submit it.

## Notifications and recovery

Native local alerts depend on the app receiving session updates. APNs/FCM background delivery is not configured; do not rely on native alerts while the app is suspended or terminated. The installed web app has a separate Web Push path with its own permissions and validation requirements.

Reconnect restores the selected gateway/target and reconciles authoritative thread state. Unknown delivery remains unknown until reconciled. Reconnecting does not expose a closed thread or restart a stopped workstation.

## Test and report issues

Include the app version/build, interface revision, Android/iOS version, device model, exact action, and whether it also fails in the phone browser. Share screenshots or error text with pairing codes, tokens and private deployment details removed.

The Android workflow is manual-only. Its optional emulator test uses Android 16/API 36 and a disposable, unpaired workspace fixture to check software-keyboard/input visibility and capture a labeled screenshot. This tests layout, not a real native gateway round trip or Samsung speech capture. The October 14, 2026 attempt was blocked by hosted-run availability before any job steps ran. No APK, emulator result or screenshot was produced by that attempt.

See [validation](Roadmap-and-Validation.md) and [development and testing](Development-and-Testing.md) for the remaining gates.
