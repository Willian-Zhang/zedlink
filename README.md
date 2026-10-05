# ZedLink

Use a phone, tablet, or desktop browser to continue an **existing native Zed Agent conversation** running on your computer.

ZedLink keeps the model, tools, MCP servers, permissions, project context, and Agent runtime inside Zed. Your browser connects to a private gateway and controls the same conversation shown in Zed's Agent panel.

> **Development status:** ZedLink works through a pinned, patched build of Zed on Linux. It is not currently a Zed Marketplace extension. A physical iPhone Safari browser has completed a same-thread prompt round trip over Tailscale. See [Validation and limitations](#validation-and-limitations).

## Start here

There are four parts:

1. **Patched Zed** adds the `/remote-control` command to a native Agent thread.
2. **ZedLink gateway** provides the private HTTPS connection used by your browser or app.
3. **Tailscale or another private route** lets the client device reach your computer.
4. **Client** displays and controls the exposed Zed conversation through a desktop browser, installable web app, SwiftUI app, or Android app.

A native SwiftUI client lives under `ios/`, and a matching Jetpack Compose client lives under `android/`. Both pass hosted builds and unit/UI or lint checks. The HTTPS browser is also an installable home-screen PWA. Safari remains the verified physical-phone client until the native packages complete signed physical-device tests.

```text
Browser or app ── private HTTPS through Tailscale ── ZedLink gateway
                                                       │
                                                  local socket
                                                       │
                                                       ▼
                                             native Zed Agent thread
                                             using your existing model
```

Zed must remain open while you use the conversation remotely. The model does not run in the browser, and model credentials are never copied to the client device.

### Why `zed-source/` is on the workstation but not GitHub

`zed-source/` is a generated local checkout of the pinned upstream Zed revision. ZedLink applies [its reviewable patch](patches/zed-1.22.0-local-probe.patch) there and builds the patched `zed` executable under `zed-source/target/`. The directory is intentionally ignored by this repository and is never pushed to ZedLink's GitHub repository. The installer recreates it from upstream Zed when it is missing.

Keep it while using or rebuilding patched Zed. It can be deleted to recover disk space only after closing Zed Dev and accepting that the next **ZedLink: Install / build** will clone and compile Zed again. Deleting it is not required before committing or pushing ZedLink changes.

## Before you begin

You need:

- A Linux computer with this repository.
- Your model already working in normal Zed.
- Rust, Cargo, Git, Python 3, and the [Zed Linux build dependencies](https://github.com/zed-industries/zed/blob/76659a55a8c10ed355a070f8764a0b1733e3c115/docs/src/development/linux.md).
- Tailscale connected on both the Zed computer and client device, or another private network route.
- A trusted TLS certificate for the hostname the client browser will open.
- Python's `qrcode` package for the easiest browser pairing flow.

The first patched Zed build can take a while. Later starts use the existing build.

## First-time setup in Zed

### 1. Open this repository

In Zed:

1. Open the **File** menu.
2. Select **Open Folder**.
3. Open:

   ```text
   /home/you/Documents/projects/zedlink
   ```

4. If Zed displays **Restricted Mode**, select **Trust and Continue**.

Trust is required because the project includes tasks that build and start local programs.

### 2. Open the Zed task picker

A Zed task is a saved command that runs in Zed's integrated terminal.

1. Press `Ctrl+Shift+P` to open the command palette.
2. Type `task: spawn`.
3. Select **task: spawn**.
4. Type `ZedLink`.

You should see tasks such as:

- **ZedLink: Set up this project**
- **ZedLink: Guided setup**
- **ZedLink: Install / build**
- **ZedLink: Configure**
- **ZedLink: Start patched Zed**
- **ZedLink: Start gateway**
- **ZedLink: Pair a device**
- **ZedLink: Status**

If no ZedLink tasks appear, make sure the ZedLink repository is the folder currently open in Zed.

### Fast setup for this workstation

The global tasks are already installed on this workstation. To configure whichever project is open in Zed:

1. Open that project in Zed.
2. Press `Ctrl+Shift+P` and select **task: spawn**.
3. Run **ZedLink: Set up this project**.

That single task uses Zed's current `$ZED_WORKTREE_ROOT`, builds the pinned Zed and gateway if needed, detects the Tailscale address and MagicDNS hostname, reuses or creates the private TLS files, saves the configuration, and installs the global management tasks. If a usable configuration already exists, it preserves the route, certificate, state, and Zed profile while changing only the selected project.

The only possible first-run question is permission to request a Tailscale certificate when no matching certificate exists. That confirmation remains because certificate issuance publishes the hostname in public Certificate Transparency logs.

### Why this uses the task picker instead of an extension settings screen

Zed's [task system](https://zed.dev/docs/tasks) is the supported GUI surface available for this workflow: global tasks appear in every project, and `$ZED_WORKTREE_ROOT` gives a task the project currently open in the editor. The inspected extension API does not provide a custom settings page, toolbar, panel, or access to existing native Agent threads. Zed's current [extension publishing prerequisites](https://zed.dev/docs/extensions/publishing/prerequisites) also say new agent-server and slash-command extension submissions are deprecated.

For those reasons, **ZedLink: Set up this project** is the closest supported one-click Zed UI today. A dedicated graphical ZedLink panel would require another native source patch inside Zed and would remain tied to pinned Zed revisions.

### 3. Guided setup for custom networking

Select **ZedLink: Guided setup**.

The task opens a terminal and asks three groups of questions:

1. Whether to build patched Zed and the gateway.
2. Whether to save the project and private network configuration.
3. Whether to install global ZedLink tasks.

Use this longer workflow when you need WireGuard, local HTTPS, a reverse proxy, a custom port, a separate Zed profile, or another non-default path. For a first custom installation, answer **yes** to all three.

The global tasks let you access ZedLink from any project later. They preserve unrelated Zed tasks and back up an existing global task file before changing it.

You can run the same guided setup from a terminal:

```sh
cd /home/you/Documents/projects/zedlink
bash tools/setup_zed_ide.sh
```

## Configuration: what each prompt means

Guided setup runs **ZedLink: Configure**. It asks for the following values.

| Prompt | What to enter | Example |
| --- | --- | --- |
| Project to open in patched Zed | The full path of the project whose Agent thread you want to control; this is required | `/home/you/Documents/my-project` |
| Private state directory | Where ZedLink stores its socket, paired-device records, and gateway identity | `/home/you/.local/state/zedlink` |
| Gateway bind address | A private computer IP followed by `:44679` | `100.64.10.20:44679` |
| Client HTTPS origin | The trusted hostname your browser or app opens, with the same port | `https://computer.example-tailnet.ts.net:44679` |
| TLS certificate PEM path | Full path to the certificate for that hostname; detected Tailscale setups receive a durable suggested path | `/home/you/.config/zedlink/tls/computer.example-tailnet.ts.net.crt` |
| TLS private key PEM path | Full path to its private key; detected Tailscale setups receive a matching suggested path | `/home/you/.config/zedlink/tls/computer.example-tailnet.ts.net.key` |
| Existing Zed user data directory | Usually leave blank to use your normal Zed profile | press Enter |

The private key must have restricted permissions:

```sh
chmod 600 /absolute/path/to/computer.key
```

Configuration is saved privately in:

```text
~/.config/zedlink/config.json
```

It stores paths and network settings. It does not store your model API key or copy model credentials to a client.

### Tailscale values

Find the computer's Tailscale IPv4 address with:

```sh
tailscale ip -4
```

Use that address for **Gateway bind address**, followed by port `44679`.

The client URL must use a hostname covered by a certificate trusted by the browser. Do not use the raw Tailscale IP as the HTTPS URL. Tailscale documents certificate creation in [Set up HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates). Certificate issuance publishes the hostname in public Certificate Transparency logs, and file certificates must be renewed.

When the wizard detects Tailscale and the suggested certificate files do not exist, it explains that public-log consequence and asks whether it should run `tailscale cert` for you. Answering **yes** creates the certificate and private key under `~/.config/zedlink/tls/`; answering **no** leaves certificate management to you and stops configuration without saving partial settings.

On the iPhone:

1. Open Tailscale and connect to the same tailnet.
2. Enable **Use Tailscale DNS settings**.
3. Keep Tailscale connected while using ZedLink.

Do not bypass a Safari certificate warning. Fix the hostname, certificate, or Tailscale DNS configuration instead.

## Start ZedLink

Complete these steps in order.

### 1. Check setup

Open `Ctrl+Shift+P` → **task: spawn** → **ZedLink: Status**.

A ready setup should report:

- the configured project,
- the gateway URL,
- patched Zed as built,
- the gateway binary as built.

If it says **Setup: not configured**, run **ZedLink: Configure**.

### 2. Start patched Zed

Run **ZedLink: Start patched Zed**.

This opens another Zed window using the patched binary. It runs as a separate **Zed Dev** instance while continuing to read your normal Zed settings, including the configured local model. The ordinary Zed window installed by `curl -f https://zed.dev/install.sh | sh` remains the official release and is not modified.

The two windows are different applications:

| Window | Executable | `/remote-control` |
| --- | --- | --- |
| Ordinary Zed | `~/.local/zed.app/libexec/zed-editor` | unavailable |
| Zed Dev for ZedLink | `zed-source/target/debug/zed` | available |

Always open the Agent panel and choose `/remote-control` in the **Zed Dev** window. Starting the task cannot add the command to an official Zed window that is already running.

If Zed reuses the ordinary window or the patched window does not appear:

1. Save your work.
2. Close other Zed windows using the same profile.
3. Run **ZedLink: Start patched Zed** again.

In the new window, verify that:

- the configured project is open,
- your expected model is selected in the Agent panel,
- the existing native Agent conversations are present.

If the window shows the wrong model, stop there and review the **Existing Zed user data directory** value. ZedLink never selects or replaces your model.

### 3. Expose one Agent thread

In the patched Zed window:

1. Open the Agent panel.
2. Open the conversation you want to access remotely.
3. Click the Agent message composer.
4. Type `/remote-control`.
5. Select **Remote Control** from the command suggestions.

Zed should display:

```text
Thread exposed to ZedLink locally.
```

Only explicitly exposed threads appear in remote clients. Run `/remote-control` again to stop exposing that thread.

After restarting patched Zed, expose the desired thread again.

You can also create a fresh native Agent session from the paired browser after the patched Zed and gateway are running. Open **Sessions**, select **+ New**, optionally enter a title, and select **Create**. ZedLink creates the session inside the configured project with Zed's native Agent and its current model, then exposes it automatically. It cannot choose another project, model, provider, or tool policy from the browser.

### 4. Start the gateway

Return to any Zed window with the global tasks:

1. Open `Ctrl+Shift+P`.
2. Run **task: spawn**.
3. Select **ZedLink: Start gateway**.
4. Leave its terminal running.

The gateway must remain running while a remote client is connected. It binds only to the private address saved during configuration.

Run **ZedLink: Status** again. The native socket and gateway admin should now report online.

### 5. Pair a browser or device

Run **ZedLink: Pair a device**.

A private pairing page opens on the Zed computer. It supports two paths:

- **Browser on the Zed computer:** select **Pair this computer's browser**.
- **Phone, Windows PC, or another Linux computer:** scan the QR or select **Copy secure pairing link** and open it in the destination browser through a private channel.

Confirm Tailscale or your routed VPN is connected on the destination device and that the HTTPS page has no certificate warning. The link, QR, and 10-digit code expire after five minutes and work once. Keep them private.

The browser name and operating system are detected automatically, such as **Firefox on Linux** or **Edge on Windows**, and can be edited before manual pairing. Pairing is saved for the exact HTTPS origin in normal browser storage. Refreshing or opening another normal tab should not require another code. Private browsing and storage-clearing policies may not preserve it.

#### Supported desktop browsers

| Client | Access | Install behavior |
| --- | --- | --- |
| Firefox on Linux or Windows | Full browser interface | Bookmark or pin the page; Firefox desktop does not install the PWA |
| Chrome or Chromium on Linux or Windows | Full browser interface | Installable from the address bar or browser menu when offered |
| Microsoft Edge on Windows | Full browser interface | Installable as an app when offered |
| Safari on iPhone or iPad | Full mobile interface | Add to Home Screen from Share |

The gateway and patched Zed currently run on the configured Linux workstation. Windows support here means a Windows browser can securely control that workstation; it does not yet make Windows a supported ZedLink gateway host.

### Install the website on the home screen

The gateway page is a standalone Progressive Web App with an OLED icon and the same Sessions, Connections, Settings, conversation, activity, tool, command, and composer layout as the native clients. Its service worker caches only the static interface. It explicitly bypasses `/v1/`, so API responses, conversations, pairing exchanges, and credentials are never stored in the offline cache.

On iPhone or iPad:

1. Open the trusted ZedLink HTTPS address in Safari.
2. Tap **Share**.
3. Tap **Add to Home Screen**.
4. Open ZedLink from its new icon. Your normal-Safari pairing should remain available for the same HTTPS origin.

On Android Chrome:

1. Open the trusted ZedLink HTTPS address.
2. Open **Settings** inside ZedLink and tap **Install ZedLink** when available, or use Chrome's **Install app** menu item.
3. Launch ZedLink from the home screen.

On desktop Chrome, Chromium, or Edge, use the install icon in the address bar or the browser's **Install ZedLink** menu item. Desktop Firefox has the same ZedLink features in a normal tab but should be bookmarked or pinned.

On a wide desktop window, ZedLink uses the full browser width. The Sessions column grows enough to show two-line thread names, and **Hide sessions** in the conversation header collapses it when you want more room for chat, reasoning, or tool output. Select **Sessions** to restore it. That choice and the last selected exposed thread are saved in the browser, so reloads and new normal tabs return to the same workspace when it is still available. Tool cards start collapsed; select **Read tool output** only when you need command output or file content.

The installed web app still requires the private route, gateway, and patched Zed to be online.

### 6. Send a test message

In the paired browser or app:

1. Select an exposed conversation, or use **+ New** on Sessions to create a native thread in the configured project.
2. Send a harmless message such as:

   ```text
   Reply with: ZedLink is connected.
   ```

3. Confirm the message and reply appear in Safari.
4. Confirm the same message and reply appear in the desktop Zed Agent panel.

That matching conversation is the key end-to-end check.

While Zed is generating, the browser receives native thread events through an authenticated WebSocket and refreshes the conversation immediately. Bounded polling remains active as recovery if a browser or network closes that stream. Returning to the tab, restoring Safari from the background, or reconnecting the network triggers an immediate snapshot reconciliation.

On a phone, live reasoning and tool progress appear as a compact activity row above the composer. Tap **View** to read the stream and **Close** to return space to the conversation. ZedLink can display only reasoning and tool state that the selected model or provider publishes to native Zed.

Long conversations may show “Older conversation omitted here” beneath the thread title. This is quiet status text rather than a popup. The full history remains in desktop Zed, while a separate recent-activity window keeps current reasoning and tool progress visible in the browser.

## Everyday use

After first-time setup:

1. Start patched Zed with **ZedLink: Start patched Zed**.
2. Open the desired Agent conversation.
3. Run `/remote-control` in that thread.
4. Start the gateway with **ZedLink: Start gateway**.
5. Open the saved ZedLink URL on any paired browser or app.

You normally do not need to pair the same browser again.

Use these tasks for management:

| Task | Purpose |
| --- | --- |
| **ZedLink: Set up this project** | Automatically configures the currently open Zed worktree using detected Tailscale settings |
| **ZedLink: Status** | Shows configuration, build, socket, and gateway status |
| **ZedLink: Paired devices** | Lists browsers allowed to connect |
| **ZedLink: Revoke device** | Removes a browser's access |
| **ZedLink: Configure** | Changes the project, route, TLS paths, or Zed profile |
| **ZedLink: Rebuild patched Zed** | Rebuilds the pinned patch and gateway |
| **ZedLink: Guided setup / update** | Runs the complete guided workflow again |

Closing the gateway terminal stops remote browser access. Closing patched Zed makes the native thread unavailable. Neither action deletes the conversation or pairing records.

## Troubleshooting

### “Setup: not configured”

Run:

```text
Ctrl+Shift+P → task: spawn → ZedLink: Configure
```

### ZedLink tasks do not appear

For the first run, open the ZedLink repository itself so Zed loads [the project tasks](.zed/tasks.json). Then run **ZedLink: Guided setup** to install global tasks.

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

### The conversation stops updating on a phone

Refresh once to load the latest web build, then reopen the thread. The connection label should become **Live with Zed**, and the thread header should change between Idle and the native running state. ZedLink reconnects when Safari or Chrome returns to the foreground. If it remains offline, confirm Tailscale is connected and run **ZedLink: Status** on the workstation.

### A message may have been sent during a disconnect

ZedLink does not automatically submit a second copy. Recovery controls appear only when delivery is uncertain. **Try again safely** reuses the same request ID so the gateway can deduplicate it.

## Remove the global Zed tasks

This removes only task labels beginning with `ZedLink:` and preserves unrelated tasks:

```sh
cd /home/you/Documents/projects/zedlink
bash tools/setup_zed_ide.sh --remove-global-tasks
```

## Security model

- A private VPN route does not grant application access by itself; the browser must also pair.
- TLS is required, including on Tailscale and local networks.
- The gateway refuses wildcard and public bind addresses.
- Only threads explicitly exposed with `/remote-control` are visible.
- Zed keeps control of tools and approvals.
- ZedLink does not provide a generic remote shell.
- Model credentials remain in Zed.

Use **ZedLink: Paired devices** regularly and revoke devices you no longer use.

## Build and test from a terminal

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
76659a55a8c10ed355a070f8764a0b1733e3c115
```

The stock extension API at that revision cannot enumerate or control an existing native Agent thread, which is why ZedLink requires the narrow, reviewable source patch under `patches/`.

## Validation and limitations

Verified:

- desktop-created native Agent thread exposed with `/remote-control`,
- terminal and gateway prompts appearing in that same native conversation,
- physical iPhone Safari prompt round trip over trusted Tailscale HTTPS,
- persistent browser pairing across refreshes and normal Safari tabs,
- request replay and same-ID deduplication,
- native cancellation in an isolated real-Zed fixture,
- browser `/compact` through the native command path,
- automatically visible live reasoning and tool activity from a bounded recent native snapshot,
- global Zed task discovery and Status execution in an already-open Zed window.

Still incomplete:

- release packaging as a stock Zed extension,
- supervised background startup and certificate renewal,
- fully structured desktop-equivalent tool arguments, output, and diffs,
- complete real approval-race validation through the paired gateway,
- broader physical-device and VPN-provider coverage.
