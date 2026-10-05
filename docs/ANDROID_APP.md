# Native Android application

Status: an Android 8.0+ Jetpack Compose client exists under `android/`. It uses the same authenticated HTTPS gateway and explicitly exposed native Zed Agent threads as the iOS and browser clients. The QR-enabled debug build, unit tests, and lint passed in [hosted run 37350419429](https://github.com/tjnull/zedlink/actions/runs/37350419429). It contains no model provider or remote shell.

## Included

- OLED black, flat session/chat/connection/settings interface matching the iOS and installed web app;
- system QR scanning, pasted one-scan pairing-link parsing, and manual HTTPS origin, gateway ID, and code entry;
- Android Keystore encryption for the paired-device token;
- saved connection profile and automatic reconnect;
- exposed native thread list and conversation snapshots;
- one-second foreground activity polling while Zed is working;
- reasoning separated from final response text;
- native tool and terminal-output cards;
- pending approval inspection, with decisions retained in desktop Zed until the approval race is validated;
- runtime-discovered slash commands;
- stable request IDs, uncertain delivery display, and same-ID retry;
- guarded native turn cancellation;
- per-thread drafts.

## Build

The project requires JDK 17, Android SDK 35, and Gradle 8.10.2:

```sh
gradle -p android --no-daemon testDebugUnitTest assembleDebug lintDebug
```

The private repository workflow `.github/workflows/android-smoke.yml` runs that command and uploads `app-debug.apk` as the `zedlink-android-debug` artifact. This APK is a development build. A release keystore, Play signing, store metadata, and a physical-device release check are separate gates.

## Pair

1. Connect Android to the same Tailscale tailnet or private routed network as the workstation.
2. Start patched Zed, expose the intended native thread with `/remote-control`, and start the gateway.
3. Run **ZedLink: Pair phone** on the workstation.
4. Copy the trusted HTTPS QR link.
5. In Android ZedLink, open **Connections**, tap **Paste pairing link**, and then **Pair and connect**.
6. Check that the shown gateway identity matches the workstation before pairing.

The Android client rejects HTTP and redirects. Android must trust the certificate for the configured hostname. The device token does not grant access to threads that have not been explicitly exposed in desktop Zed.

## Remaining device tests

- install the debug APK on a physical Android phone;
- pair through the real Tailscale hostname;
- send a prompt and verify matching desktop/browser/iOS state;
- observe a real native tool turn and cancellation;
- test Wi-Fi/cellular transitions, large text, rotation, TalkBack, and process restoration;
- create a signed release build.
