# Mobile Apps

[← Wiki home](README.md)

The SwiftUI and Jetpack Compose apps are native clients for the same ZedLink gateway. They do not contain an LLM runtime or model credentials.

## Release status

| Client | Install path | Current boundary |
| --- | --- | --- |
| Browser / PWA | Open the trusted HTTPS origin; optionally add it to the home screen | Most complete and easiest path |
| iOS | Build and sign locally with macOS and Xcode | Source available; wider simulator and physical-device coverage pending |
| Android | Build a development APK with JDK 17, Android SDK, and Gradle | Source available; terminal and speech reports still need physical-device validation |

There is no documented stable App Store or Play Store release. Treat native packages as development builds.

## Build iOS

You need macOS, Xcode, XcodeGen, a signing team, and a simulator or physical device. From the repository root:

```sh
bash tools/test_ios_local.sh build
```

Open the generated `ZedLink` project/scheme in Xcode, select your team and device, then build and run. Use a disposable Zed project and test pairing for UI tests. Do not point automated tests at an active personal conversation.

Before sharing a build, verify on a physical phone:

- pairing, reconnect, and route switching;
- transcript restoration and live updates;
- keyboard and safe-area layout in portrait and landscape;
- files, changes, terminal selection/creation/input, tasks, and debugger views;
- approvals, Stop, uncertain-delivery recovery, and stale request rejection;
- image selection/annotation, clipboard, dictation, and accessibility; and
- notification behavior while foregrounded, backgrounded, and terminated.

## Build Android

Use an existing JDK 17, Android SDK, and Gradle 8.10.2. Keep caches on disk outside the repository. From the repository root:

```sh
gradle -p android --no-daemon :app:testDebugUnitTest :app:assembleDebug :app:lintDebug
```

The debug APK is written to:

```text
android/app/build/outputs/apk/debug/app-debug.apk
```

Install it on a disposable test device:

```sh
adb install -r android/app/build/outputs/apk/debug/app-debug.apk
```

Android rejects an update signed by a different key. Uninstalling clears app data and requires pairing again.

Every Android UI change must increment version/build metadata. When reporting a problem, copy **Settings → Help & about → Version, build, and interface revision**. The current source declares version **0.2.14 (16)** and interface revision **2026.10.23.2**; that identifies source metadata, not a verified installed APK.

## Pairing

1. Keep patched Zed and the gateway running.
2. Connect the phone to the configured private route.
3. Verify the gateway HTTPS origin loads without a certificate warning.
4. Expose the intended conversation with `/remote-control` in desktop Zed.
5. In **Connections → Add**, scan or paste the pairing link.
6. Test HTTPS, compare the gateway identity, then pair and save.

Camera scanning must produce a reviewable connection draft before a network request. If scanning returns to Sessions, use **Paste pairing link**, record the app version, and include the exact route type in the issue.

## Workspace and terminal behavior

Both native apps expose capability-gated Files, Changes, Terminal, Tasks, Debug, and Activity views. Files are listed one entry per row and stay inside the exposed worktree.

The terminal selects or creates native Zed project terminals. Mobile input remains editable and visible before Return, then the authoritative Zed terminal refresh confirms delivery. Switch terminals by tapping the title. The native PTY is resized to the visible phone grid before subsequent commands so new directory listings fit the screen more naturally.

Terminal output is a bounded styled snapshot. Full-screen terminal applications, mouse input, exact cursor projection, and every custom font glyph are not established as fully supported.

## Dictation and clipboard

Dictation fills an editable draft and never sends automatically. Android provides the device speech popup and an explicit in-app path. Microphone permission alone does not guarantee that the installed speech service can record or transcribe; Android's global microphone control, speech-provider permission, language support, and provider health also matter.

An Android physical-device report of **unable to record audio** remains unresolved. Capture the exact popup text, Android version, device, speech provider, and app metadata. Test both the device popup and in-app option without exposing private transcript content.

Image paste and selection open an annotation review with freehand drawing, Undo, and Clear. Text clipboard actions show a preview. Neither path automatically submits content.

## Notifications and Apple Watch

iOS and Android local Agent alerts can cover approvals, request failures, observed native turn completion or cancellation, pending input, and context compaction while each app receives updates. Android source 0.2.14 (16) adds adaptive Material 3 navigation and a compact composer; the preceding update added loaded-conversation search and an unread count when following is paused. Apple Watch can mirror eligible iPhone notifications through the operating system.

To check mirroring:

1. enable ZedLink notifications on iPhone;
2. open **Settings → Notifications** in ZedLink and schedule the test notification;
3. lock the iPhone and keep the paired watch unlocked and on your wrist; and
4. check **Watch app → Notifications → ZedLink** if it remains on the phone.

The operating system chooses whether an alert appears on iPhone or Watch. ZedLink does not include a dedicated watch app. APNs and FCM background push are not configured, so native local alerts cannot be relied on after the app is suspended or terminated.

## Device test report

Include:

- app version, build, and interface revision;
- phone model and OS version;
- gateway and patched-Zed revisions without private addresses;
- exact steps, expected result, and actual result;
- whether the same action works in the phone browser; and
- a redacted screenshot or exact error text.

Remove pairing codes, device tokens, private hostnames, IP addresses, certificate details, project names, and transcript content before posting.
