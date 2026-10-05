# ZedLink

Use your phone to continue an **existing native Zed Agent conversation** running on your computer.

ZedLink keeps the model, tools, MCP servers, permissions, project context, and Agent runtime inside Zed. Your phone connects to a private gateway and controls the same conversation shown in Zed's Agent panel.

> **Development status:** ZedLink works through a pinned, patched build of Zed on Linux. It is not currently a Zed Marketplace extension. A physical iPhone Safari browser has completed a same-thread prompt round trip over Tailscale. See [Validation and limitations](#validation-and-limitations).

## Start here

There are four parts:

1. **Patched Zed** adds the `/remote-control` command to a native Agent thread.
2. **ZedLink gateway** provides the private HTTPS connection used by your phone.
3. **Tailscale or another private route** lets the phone reach your computer.
4. **Phone browser** displays and controls the exposed Zed conversation.

A native SwiftUI client also lives under `ios/`. Its current OLED workspace revision is under active validation; Safari remains the verified physical-iPhone client.

```text
iPhone browser ── private HTTPS through Tailscale ── ZedLink gateway
                                                       │
                                                  local socket
                                                       │
                                                       ▼
                                             native Zed Agent thread
                                             using your existing model
```

Zed must remain open while you use the conversation remotely. The model does not run in the browser, and model credentials are never copied to the phone.

## Before you begin

You need:

- A Linux computer with this repository.
- Your model already working in normal Zed.
- Rust, Cargo, Git, Python 3, and the [Zed Linux build dependencies](https://github.com/zed-industries/zed/blob/76659a55a8c10ed355a070f8764a0b1733e3c115/docs/src/development/linux.md).
- Tailscale connected on both the computer and phone, or another private network route.
- A trusted TLS certificate for the hostname the phone will open.
- Python's `qrcode` package for the easiest phone pairing flow.

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
- **ZedLink: Pair phone**
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
| Phone HTTPS origin | The trusted hostname your phone opens, with the same port | `https://computer.example-tailnet.ts.net:44679` |
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

It stores paths and network settings. It does not store your model API key or copy model credentials to the phone.

### Tailscale values

Find the computer's Tailscale IPv4 address with:

```sh
tailscale ip -4
```

Use that address for **Gateway bind address**, followed by port `44679`.

The phone URL must use a hostname covered by a certificate trusted by Safari. Do not use the raw Tailscale IP as the HTTPS URL. Tailscale documents certificate creation in [Set up HTTPS certificates](https://tailscale.com/docs/how-to/set-up-https-certificates). Certificate issuance publishes the hostname in public Certificate Transparency logs, and file certificates must be renewed.

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
2. Open the conversation you want on your phone.
3. Click the Agent message composer.
4. Type `/remote-control`.
5. Select **Remote Control** from the command suggestions.

Zed should display:

```text
Thread exposed to ZedLink locally.
```

Only explicitly exposed threads appear on the phone. Run `/remote-control` again to stop exposing that thread.

After restarting patched Zed, expose the desired thread again.

### 4. Start the gateway

Return to any Zed window with the global tasks:

1. Open `Ctrl+Shift+P`.
2. Run **task: spawn**.
3. Select **ZedLink: Start gateway**.
4. Leave its terminal running.

The gateway must remain running while the phone is connected. It binds only to the private address saved during configuration.

Run **ZedLink: Status** again. The native socket and gateway admin should now report online.

### 5. Pair the phone

Run **ZedLink: Pair phone**.

A private pairing page and QR code open on the computer.

1. Confirm Tailscale is connected on the iPhone.
2. Scan the QR code with the iPhone camera.
3. Open the link in Safari.
4. Confirm there is no certificate warning.
5. Allow the one-time pairing to complete.

The QR code expires after five minutes and works once. Keep it private.

Pairing is saved in normal Safari storage. Refreshing the page or opening a second normal tab should not require another code. Private Browsing may not preserve the pairing.

### 6. Send a test message

On the phone:

1. Select the exposed conversation.
2. Send a harmless message such as:

   ```text
   Reply with: ZedLink is connected.
   ```

3. Confirm the message and reply appear in Safari.
4. Confirm the same message and reply appear in the desktop Zed Agent panel.

That matching conversation is the key end-to-end check.

While Zed is generating, the browser opens a **Zed is working** panel above the composer. It updates once per second with reasoning, plans, and tool state that the native Zed thread exposes. Tap **Hide** to reduce it to one line. ZedLink cannot reveal reasoning that the selected model or provider does not publish to Zed.

Long conversations may show “Older conversation omitted here” beneath the thread title. This is quiet status text rather than a popup. The full history remains in desktop Zed, while a separate recent-activity window keeps current reasoning and tool progress visible in the browser.

## Everyday use

After first-time setup:

1. Start patched Zed with **ZedLink: Start patched Zed**.
2. Open the desired Agent conversation.
3. Run `/remote-control` in that thread.
4. Start the gateway with **ZedLink: Start gateway**.
5. Open the saved ZedLink URL on the paired phone.

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

Closing the gateway terminal stops phone access. Closing patched Zed makes the native thread unavailable. Neither action deletes the conversation or pairing records.

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

### The phone asks to pair again

Use normal Safari rather than Private Browsing. Pairing is scoped to the exact HTTPS origin, including its hostname and port. Changing either creates a different browser origin.

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

The stock extension API at that revision cannot enumerate or control an existing native Agent thread. [FEASIBILITY.md](docs/FEASIBILITY.md) records the inspected APIs and why the narrow Zed source patch is required.

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

Exact commands, evidence, unavailable tests, and current limitations are recorded in [VALIDATION_REPORT.md](docs/VALIDATION_REPORT.md).

## Documentation

- [Architecture](docs/ARCHITECTURE.md)
- [Build plan](docs/BUILD_PLAN.md)
- [Browser behavior and pairing](docs/BROWSER.md)
- [Extension feasibility and IDE integration](docs/EXTENSION_INTEGRATION.md)
- [Gateway operation](docs/GATEWAY.md)
- [Networking and TLS](docs/NETWORKING.md)
- [Protocol](docs/PROTOCOL.md)
- [Test plan](docs/TEST_PLAN.md)
- [Validation report](docs/VALIDATION_REPORT.md)
- [Deferred native iPhone application](docs/IOS_APP.md)
- [Zedra-inspired iOS feature map](docs/ZEDRA_FEATURE_PARITY.md)
