# Troubleshooting

[← Wiki home](README.md)

## Troubleshooting

### “Setup: not configured”

Run:

```text
Ctrl+Shift+P → task: spawn → ZedLink: Configure
```

### ZedLink tasks do not appear

For the first run, open the ZedLink repository itself so Zed loads [the project tasks](../.zed/tasks.json). Then run **ZedLink: Guided setup** to install global tasks.

From a terminal, reinstall only the global tasks with:

```sh
bash tools/setup_zed_ide.sh --yes --skip-build --skip-config
```

### `/remote-control` does not appear

You are probably in ordinary Zed. The official installer does not contain the source patch.

1. Run **ZedLink: Status** and confirm `Patched Zed bridge: online (separate dev-channel instance)`.
2. Find the separate **Zed Dev** window for the configured project.
3. Open its Agent panel with `Ctrl+Shift+P`, search for **agent: toggle focus**, and run it.
4. Click the Agent composer, type `/remote-control`, and select **Remote Control**.

If Status says the bridge is offline, run **ZedLink: Start patched Zed** again. The launcher sets a separate `dev` release channel so it cannot forward the request back to ordinary Zed's `stable` instance socket.

### The gateway will not start

Run **ZedLink: Status** first. The patched bridge must be online before the gateway starts. If another old gateway already owns the configured port, stop that old ZedLink task or process and run **ZedLink: Start gateway** again. A ready result says `Gateway admin: online`.

### Patched Zed shows the wrong model

ZedLink uses the profile loaded by that Zed window. It does not act as a model.

1. Stop the patched window.
2. Run **ZedLink: Configure**.
3. Check **Existing Zed user data directory**.
4. Start patched Zed again.
5. Confirm the model selector before exposing a thread.

If you removed the official Zed installation, your settings normally remain in
`~/.config/zed/settings.json` and the patched dev-channel build continues to read
that file. Run these checks before re-entering any model configuration:

```sh
python3 tools/zedlink_manager.py status
zed --help
```

`ZedLink: Set up this project` installs a guarded `~/.local/bin/zed` command for
the patched build. With it, `zed` opens the configured ZedLink project, `zed .`
opens the current directory, and `zed path/to/file` opens a file. The installer
refuses to overwrite an unrelated command or symbolic link. Refresh it with
`python3 tools/zedlink_manager.py install-cli`; remove only the managed command
with `python3 tools/zedlink_manager.py remove-cli`.

The model selector proves which model Zed selected, while **Idle** only means no
turn is running. A reachable `/v1/models` endpoint can still stall during text
generation. When a turn remains on Generating, inspect Zed's error panel and the
model server itself before changing the saved model ID or credential.

### “image input requires a supported vision checkpoint”

This message comes from the model server used by native Zed. It means the current Agent request contains an image, but the selected checkpoint/server does not support image input. ZedLink does not select a different model and cannot make a text-only checkpoint understand images.

An image already stored earlier in the conversation is sent again as part of that thread's history. In that case, later text-only prompts such as “Please resume this” repeat the error even though the new prompt has no attachment.

For a text-only local model:

1. Wait for the native thread to become Idle.
2. In ZedLink, select **Rewind before image** in the inline error.
3. Read the removal count and confirm. This removes the first image message and every later conversation item from the same native Zed thread; it cannot be undone from ZedLink.
4. Send a text-only description of what you want to continue.

If the recovery button is unavailable, restart the updated patched **Zed Dev**, expose the thread again with `/remote-control`, or create a fresh text-only native Agent thread. ZedLink blocks a newly selected image when Zed explicitly reports that the current model does not support images. Some custom providers can report incomplete capability metadata, so the model server remains authoritative.

To use images, select a genuinely vision-capable checkpoint in Zed and configure its model server for image input according to that server's documentation. A `--vision` flag cannot add vision capability to a text-only checkpoint.

### Which Zed should I open?

Remote control requires the patched **Zed Dev** build. Keep the ordinary installed Zed for normal work if desired, but `/remote-control` exists only in the patched window.

The reliable launch path is:

1. Open your Linux application menu.
2. Search for **ZedLink — Patched Zed** and open it.
3. Confirm the window title or application identity says **Zed Dev**.
4. Run **ZedLink: Status**. It must say `Patched Zed bridge: online (separate dev-channel instance)`.
5. In that same window's Agent composer, type `/remote-control`. Seeing that command and its exposure toast is the final confirmation.

The application launcher is installed at `~/.local/share/applications/dev.zed.Zed-Dev.desktop`. It uses Zed's real dev-channel application ID, which keeps the patched window distinct from official Zed in the dock and application switcher. Run `python3 tools/zedlink_manager.py remove-launcher` if you want to remove it.

The menu launcher detaches Zed from the desktop activation process and records startup output privately at `~/.local/state/zedlink/patched-zed-launcher.log`. If the window does not appear, inspect that file and run **ZedLink: Status**. Re-running **ZedLink: Install patched Zed launcher** safely refreshes the entry after moving or updating this repository.

On this workstation the patched executable and managed command are:

```text
Patched:   /home/you/Documents/projects/zedlink/zed-source/target/debug/zed
Command:   /home/you/.local/bin/zed
```

After ZedLink installs the managed command, both `zed` and **ZedLink — Patched
Zed** start the patched dev-channel build. If an official Zed installer later
replaces `~/.local/bin/zed`, run `python3 tools/zedlink_manager.py install-cli`;
the ownership check will explain the conflict instead of silently replacing it.

### The browser says Zed is unavailable

Check, in order:

1. Patched Zed is still open.
2. The desired thread was exposed with `/remote-control`.
3. **ZedLink: Status** reports the native socket online.
4. The gateway terminal is still running.

The Sessions screen keeps **+ New** visible while Zed is unavailable, but disables it until the patched bridge reconnects. After starting patched Zed, refresh Sessions; the control enables when `thread.create` is advertised.

### Safari says server not found

1. Connect Tailscale on the iPhone.
2. Enable **Use Tailscale DNS settings**.
3. Confirm the phone is on the same tailnet.
4. Reopen the exact configured HTTPS hostname and port.

### Safari displays a certificate warning

Do not continue through the warning. Confirm:

- the URL hostname matches the certificate,
- the certificate is current,
- the gateway is using the matching certificate and key,
- the phone's date and time are correct.

### A browser asks to pair again

Use a normal browser window rather than private or incognito mode. Pairing is scoped to the exact HTTPS origin, including its hostname and port. Changing either creates a different browser origin. Browser policies that clear site data on exit also remove the saved credential.

Open **Connections → Saved addresses** and return to the hostname previously used by that browser. iOS and Android native clients can instead edit or scan the new address and choose **Save new address and reconnect**; they verify that it reports the same Gateway ID before retrieving the existing Keychain or encrypted credential. If the Gateway ID changed, check that the workstation is still using the original ZedLink private state directory.

### The conversation stops updating on a phone

Refresh once to load the latest web build, then reopen the thread. Open **Connections** to identify the failing layer. **Gateway unavailable** points to the phone route, TLS service, or gateway process. **Zed unavailable** means the gateway is reachable but its private native socket is not. **Live updates: Reconnecting** or **Timed out · polling** means HTTPS reconciliation continues while the WebSocket reconnects with bounded backoff. ZedLink reconnects when Safari or Chrome returns to the foreground. If it remains offline, confirm Tailscale is connected and run **ZedLink: Status** on the workstation.

### ZedLink says Idle while the local model is offline

Idle describes the native thread's execution state. The model is contacted only when Zed runs a turn, so ZedLink does not invent a background model-health result. After a native request fails, the browser shows **Request failed** with Zed's native error and preserves it while the thread is idle. Restore the configured model endpoint, then send or retry through Zed's normal Agent path. A later native retry is shown as **Retrying** with its attempt and delay.

### A message may have been sent during a disconnect

ZedLink does not automatically submit a second copy. Recovery controls appear only when delivery is uncertain. **Try again safely** reuses the same request ID so the gateway can deduplicate it.


## Remove the global Zed tasks

This removes only task labels beginning with `ZedLink:` and preserves unrelated tasks:

```sh
cd /home/you/Documents/projects/zedlink
bash tools/setup_zed_ide.sh --remove-global-tasks
```
