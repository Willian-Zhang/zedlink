# Installation and Setup

[← Wiki home](README.md)

## Why `zed-source/` is on the workstation but not GitHub

`zed-source/` is a generated local checkout of the maintained [`tjnull/zed`](https://github.com/tjnull/zed/tree/zedlink/native-agent-remote-control) fork on branch `zedlink/native-agent-remote-control`. That branch is based on the pinned official Zed revision and contains the native ZedLink integration. The installer builds the patched `zed` executable under `zed-source/target/`, keeps `tjnull/zed` as `origin`, and records `zed-industries/zed` as `upstream`.

The directory is intentionally ignored by the ZedLink repository and is never copied into `tjnull/zedlink`. The reviewable [source patch](../patches/zed-1.22.0-local-probe.patch) mirrors the fork changes for auditing and compatibility checks. If `zed-source/` is missing, the installer recreates it directly from the fork branch.

Keep it while using or rebuilding patched Zed. It can be deleted to recover disk space only after closing Zed Dev and accepting that the next **ZedLink: Install / build** will clone and compile Zed again. Deleting it is not required before committing or pushing ZedLink changes.


## Before you begin

You need:

- A Linux computer with this repository.
- Your model already working in normal Zed.
- Rust, Cargo, Git, Python 3, and the [Zed Linux build dependencies](https://github.com/zed-industries/zed/blob/76659a55a8c10ed355a070f8764a0b1733e3c115/docs/src/development/linux.md).
- Tailscale connected on both the Zed computer and client device, or another private network route.
- HTTPS enabled for the tailnet. ZedLink can request and store the matching Tailscale certificate files during setup.
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
- **ZedLink: Guided setup / update**
- **ZedLink: Install / build**
- **ZedLink: Configure**
- **ZedLink: Set up / renew Tailscale HTTPS**
- **ZedLink: Diagnose setup**
- **ZedLink: Repair setup**
- **ZedLink: Install patched Zed launcher**
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

### If this is your first time using Tailscale

1. [Install Tailscale on Linux](https://tailscale.com/docs/install/linux), then run `sudo tailscale up` and finish sign-in in the browser.
2. Install Tailscale on the phone or other client and sign in to the same tailnet.
3. Open the [Tailscale DNS admin page](https://login.tailscale.com/admin/dns). Enable **MagicDNS**, then enable **HTTPS Certificates**. An Owner, Admin, or Network admin must perform this tailnet-level step.
4. Read and accept Tailscale's certificate-transparency notice. The workstation's machine name and tailnet DNS suffix become visible in public Certificate Transparency logs, so rename the machine first if its current name is sensitive.
5. In Zed, run **ZedLink: Set up / renew Tailscale HTTPS**. ZedLink checks that the client is installed, signed in, and has a private address and MagicDNS hostname. It then offers to request the certificate and key into `~/.config/zedlink/tls/`.
6. Run **ZedLink: Set up this project**. The wizard now manages the detected Tailscale certificate paths instead of asking you to type them.

If certificate creation reports a Linux permission error, delegate Tailscale CLI operations to your account with:

```sh
sudo tailscale set --operator="$USER"
```

Then rerun **ZedLink: Set up / renew Tailscale HTTPS**. ZedLink validates the hostname, matching public key, private-key permissions, and expiration before replacing an existing certificate.

For a Tailscale profile, normal project setup installs a private systemd user timer automatically. It checks twice daily with up to one hour of randomized delay and requests a new certificate only when fewer than 30 days remain. A replacement is generated in a private staging directory, fully validated, moved into place, and reloaded by the running gateway without changing its identity, paired devices, or native sessions. If the gateway is offline, it reads the renewed files at its next start.

Open **Settings → ZedLink → Tailscale HTTPS** to inspect renewal status, open Tailscale's DNS/HTTPS administration page, enable or disable the timer, or run a check immediately. The equivalent Zed tasks are **Enable automatic certificate renewal**, **Certificate renewal status**, and **Check certificate renewal now**.

Automatic renewal requires the current Linux user to be permitted to run `tailscale cert`. The timer records failures in the systemd user journal and retries at its next scheduled check. It never changes a connection profile when the detected MagicDNS identity differs from the saved hostname.

### Configure ZedLink in Zed Settings

The patched Zed build now has a native **ZedLink** Settings page. Open it with `Ctrl+,`, then select **ZedLink** in the left sidebar. It contains:

<p align="center">
  <img src="../assets/screenshots/zed-settings.png" width="760" alt="Native ZedLink connection provider settings in patched Zed">
</p>

<p align="center"><sub>Native patched Zed Settings using generic example paths and a Tailscale connection profile.</sub></p>

- **Enable ZedLink** — starts the private local bridge whenever patched Zed starts.
- **Private State Directory** — normally `~/.local/state/zedlink` written as a full absolute path.
- **Project Root** — the project whose Agent threads may be exposed.
- **Start Gateway on Launch** — starts the saved private HTTPS gateway with patched Zed.
- **ZedLink Manager** — the installer-managed path used to load connection and TLS profiles.
- **Gateway Control** — automatically shows the gateway, native bridge, active route, paired-device count, project scope, and patched-Zed readiness as inline status rows. Refresh, start, restart, stop, and diagnostics remain on the same page instead of opening a status popup.
- **Paired Devices** — opens the private pairing page, lists authorized browsers and installed web apps, and revokes one selected device after confirmation.
- **Remote Permissions** — separate controls for new sessions, attachments, project browsing, Git changes, approval decisions, and Agent settings.

Open **Connection Providers** at the top of the ZedLink page to manage the private route used by browsers and apps. The subpage supports Tailscale, NetBird, WireGuard, ZeroTier, Twingate, Headscale, Cloudflare Tunnel + Access, SSH reverse tunnels, direct SSH forwarding, local LAN HTTPS, and custom private HTTPS.

The **Connection Provider** dropdown displays the provider saved for the selected profile. Choosing another provider updates the fields and instructions beneath it: private network profiles show their routed listener and trusted client origin, while Cloudflare and reverse SSH profiles show the required loopback origin and origin TLS hostname. Hidden proxy-only values are not retained when a direct provider is saved.

To add or update a connection:

1. Enter a short lowercase **Profile ID**, such as `tailscale` or `wireguard-home`.
2. Choose its **Provider**.
3. Choose **Detect Provider Defaults** for Tailscale, Headscale, NetBird, Cloudflare, or SSH. For other providers, enter the private listener address supplied by that network.
4. Review the trusted client HTTPS origin and certificate paths.
5. Choose **Save & Activate**. ZedLink validates the private bind, URL, port, certificate, key permissions, and proxy rules before saving and restarting the gateway.
6. Choose **Check Connection**. ZedLink makes a trusted HTTPS request to the saved endpoint and confirms that it reports this installation's gateway identity.

To switch back to a saved profile, enter its ID and choose **Select Existing Connection**. Invalid or disabled profiles are rejected without replacing the working primary route. Provider applications such as Tailscale, NetBird, WireGuard, ZeroTier, and Twingate still own their device authentication, routing, and DNS; ZedLink configures only its authenticated HTTPS listener on the resulting private route.

The check runs from the Zed workstation. A passing result confirms the local provider route, certificate trust, HTTPS listener, and gateway identity from that machine. It cannot prove that a phone or another computer is signed into the provider or can resolve and route to the host; open the same HTTPS origin on that device for the final client-side check.

**ZedLink: Set up this project** fills these settings automatically when the Zed settings file is strict JSON. It enables automatic gateway startup and uses permissive remote controls for the explicitly exposed thread by default. Later setup runs preserve permission switches you turned off. If the file contains JSON comments, setup preserves it and asks you to enter the values on the ZedLink page instead of deleting your comments. Restart patched Zed after changing these fields.

Run **ZedLink: Diagnose setup** for one health report covering the patched binary, native settings, project and state paths, TLS profiles, local bridge, gateway, and paired-device count. Run **ZedLink: Repair setup** to restore native settings, global tasks, launchers, private directories, and gateway startup. Repair never changes Zed's model provider, model name, endpoint, or credentials.

The task picker remains the bootstrap and maintenance surface for first-time setup, compiling the source patch, repairing files, installing launchers, and advanced interactive connection management. Normal gateway control, connection checks, pairing, and device revocation are available from ZedLink Settings.

The downloaded Zed from `zed.dev` cannot show this page or `/remote-control`, because the stock extension API cannot add a settings page or control an existing native Agent thread. Open **ZedLink — Patched Zed** from the operating system application menu. Once Zed accepts the native patch upstream or ships an equivalent API, this separate build can be removed.

`/remote-control` still selects the individual conversation that becomes visible. Enabling ZedLink does not expose every Agent conversation.

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
