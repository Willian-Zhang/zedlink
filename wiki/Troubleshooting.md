# Troubleshooting

[← Wiki home](README.md)

Start with the read-only checks:

```sh
python3 tools/zedlink_manager.py status
python3 tools/zedlink_manager.py diagnose
python3 tools/zedlink_manager.py check-routes
```

Record the failing layer: patched Zed, native bridge, gateway, private route, TLS, pairing, selected target, exposed thread, or client UI.

## Setup is not configured

Run **ZedLink: Configure** or:

```sh
bash tools/setup_zed_ide.sh
```

If Zed tasks are absent, open the repository as the current worktree and rerun guided setup to install global tasks.

## `/remote-control` is missing

You are using official Zed, an outdated patched build, or a profile that did not load the integration.

1. Save active work and close the incorrect window.
2. launch **ZedLink — Patched Zed**;
3. verify the intended project and Agent conversation; and
4. rebuild with **ZedLink: Install / build** if the command is still absent.

## Patched Zed shows the wrong model

Stop before sending. ZedLink does not choose the model. Check the selected Zed profile/user-data path and the model selection in desktop Zed. Repair does not change provider keys or model settings.

## Gateway will not start

Run **ZedLink: Diagnose setup** and check:

- the configured private address exists on the host;
- the port is free;
- certificate and key paths exist outside the repository;
- hostname coverage and key permissions pass validation;
- patched Zed's local socket is available; and
- the selected route has not changed identity.

Use **Restart gateway** after correcting the cause.

## Phone can ping but HTTPS times out

Ping proves only basic IP reachability. On the phone, verify:

1. the VPN is connected to the expected network;
2. MagicDNS resolves the saved hostname;
3. the gateway port is reachable;
4. the browser opens the exact `https://host:port/` origin; and
5. there is no certificate warning.

For Tailscale, run **Check Tailscale Connection** and **Guided Tailscale Repair**. Confirm MagicDNS and HTTPS Certificates are enabled for the tailnet.

## Certificate warning or self-signed certificate

Do not bypass the warning. Replace the certificate with one trusted by the device, or explicitly install and trust the intended private CA according to platform policy. Confirm the certificate hostname matches the saved origin and that the gateway is serving the expected certificate.

## Pair and save is disabled

Complete the endpoint test and identity verification first. A timeout or certificate failure prevents pairing. Generate a fresh one-time challenge after fixing connectivity; do not repeatedly submit an uncertain pairing request.

## QR scan returns to Sessions

Use **Paste pairing link** and preserve the connection draft long enough to read the error. Record app version/build/interface revision, camera permission, Android version, and whether manual paste succeeds. Never attach the live QR or code to an issue.

## Browser asks to pair again

Check whether the HTTPS origin changed, private browsing is active, site data was cleared, or the device was revoked. Pairing is scoped to the exact origin and browser storage.

## Zed or a session is unavailable

Confirm patched Zed remains open, the target selected in the client is online, and the intended conversation is still exposed. Restarting Zed ends the old instance epoch and requires exposure again. ZedLink does not fail over to another target.

## Conversation is stale or opens at the wrong position

Use **Latest**, keep the client foregrounded, and check connection status. Reopen the session after the gateway and native bridge are online. If reconnection occurred during a send, reconcile the request state before retrying.

## Context length or compaction fails

ZedLink invokes Zed's native `/compact` path. A server that advertises a larger context than it actually accepts must be corrected on the inference server. Align the advertised and enforced maximum, then start a short disposable conversation to verify it. ZedLink should display native compaction state but cannot enlarge the model server's limit.

## Image input is rejected

Check desktop attachment permission, size/count limits, file type, and whether the selected model supports image input. Remove the image or switch models in desktop Zed. ZedLink never reroutes a failed image prompt to another model.

## Terminal input is missing or layout is hard to read

1. Check the installed native app version/build/interface revision.
2. Confirm **View Project Terminals** and **Send Terminal Input** are enabled.
3. Select the correct terminal and use the keyboard button.
4. Use **List files one per line** for directory output.
5. Toggle wrap/original columns or text size.
6. Compare the phone browser and native app, then report which path fails.

An installed APK does not change when the gateway is rebuilt. Rebuild and reinstall the app for native UI fixes.

## Android dictation says it cannot record

Check ZedLink microphone permission, Android's global microphone switch, the speech provider's permission and enabled status, language support, and whether another app is using the microphone. Try both the device speech popup and the in-app recognition option. This physical-device report remains under investigation; include redacted diagnostics and exact app metadata.

## Native notifications do not arrive in the background

Foreground local alerts depend on live snapshots. APNs and FCM background push are not configured. Apple Watch can mirror an eligible iPhone notification only when iOS delivers it and the phone/watch state allows mirroring.

## Repair and reporting

Use **ZedLink: Repair setup** only after diagnostics. It restores managed integration files and settings without changing the model configuration.

When filing an issue, include commands run, redacted output, revisions, client metadata, device/OS, and the smallest reproduction. Remove all credentials, pairing material, private deployment identities, personal paths, project names, and transcript content.
