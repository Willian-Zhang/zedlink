# Configuration

[← Wiki home](README.md)

ZedLink needs two independent controls: a trusted network route to the gateway and explicit application authorization. A working VPN or ping does not pair a device.

## Configure patched Zed

Open `Ctrl+,` in **ZedLink — Patched Zed**, then select **ZedLink**.

![Native ZedLink settings in an isolated profile](../assets/screenshots/zed-settings.png)

The important settings are:

| Setting | Meaning |
| --- | --- |
| **Enable ZedLink** | Starts the private native bridge with patched Zed |
| **Private State Directory** | Stores local bridge state outside the repository |
| **Project Root** | Limits project operations to the selected worktree |
| **Start Gateway on Launch** | Starts the saved gateway profile with patched Zed |
| **ZedLink Manager** | Points Zed to this repository's management script |
| **Remote Permissions** | Separately enables connecting to open threads, session creation, attachments, files, Git changes, approvals, terminals, debugger actions, and Agent settings |

Permissions apply only to explicitly exposed conversations. Disable capabilities that are unnecessary for your use.

**Connect to Open Threads** (`allow_remote_attach`, off by default) lets a paired device list Agent threads already open in a configured project and expose one itself, instead of running `/remote-control` on the desktop. Zed shows a toast in that thread when a device connects. Only the desktop can turn it on. Threads in an SSH window that is still connecting are listed as waiting; connecting to one, from the phone or with `/remote-control`, exposes it once its folders load and match a configured root.

Changes to `project_root` and `project_roots` apply without restarting Zed. Removing a root stops exposing its threads immediately; turning `enabled` off empties the list. Changing `enabled` from off to on or changing `state_directory` still needs a restart.

## Recommended Tailscale setup

1. Install Tailscale on the Zed workstation and client device.
2. Sign both into the same tailnet.
3. In the Tailscale DNS admin page, enable **MagicDNS** and **HTTPS Certificates**.
4. Read the certificate-transparency notice. The requested machine hostname becomes public in Certificate Transparency logs, so rename a sensitive hostname first.
5. Run **ZedLink: Set up / renew Tailscale HTTPS**.
6. Run **ZedLink: Set up this project**.
7. Open **Settings → ZedLink → Connection Providers**, select the Tailscale profile, and choose **Check Connection**.

If certificate issuance needs permission on Linux:

```sh
sudo tailscale set --operator="$USER"
```

Then rerun certificate setup. ZedLink validates hostname coverage, matching certificate and key, private-key permissions, and expiration before activation.

### Certificate renewal

Normal Tailscale setup can install a systemd user timer. It checks twice daily with randomized delay and renews only when the certificate is near expiration. A validated replacement is moved into place and the running gateway reloads it without changing the gateway identity or paired devices.

Use **Settings → ZedLink → Tailscale HTTPS** or these tasks:

- **Enable automatic certificate renewal**
- **Certificate renewal status**
- **Check certificate renewal now**

## Connection profiles

Open **Settings → ZedLink → Connection Providers**. Each profile records a private listener, the HTTPS origin clients trust, TLS material, and provider-specific proxy rules.

Supported profiles include Tailscale, Headscale, WireGuard, NetBird, ZeroTier, Twingate, local LAN HTTPS, Cloudflare Tunnel with Access, SSH reverse tunnels, direct SSH forwarding, and custom private HTTPS.

To save a profile:

1. Enter a short lowercase profile ID.
2. Choose the provider.
3. Use **Detect Provider Defaults** where offered, or enter the private listener supplied by that network.
4. Confirm the HTTPS origin and TLS paths.
5. Choose **Save & Activate**.
6. Choose **Check Connection** and confirm the returned gateway identity.

The workstation check verifies its own route, certificate trust, listener, and gateway identity. Complete the final check on the phone by opening the same HTTPS origin there without a certificate warning.

> [!WARNING]
> Never disable TLS verification or silently fall back to a public endpoint. A self-signed certificate must be explicitly trusted on every client, or replaced with a certificate that client already trusts.

## Multiple workstations and Zed instances

Clients keep authorization and drafts separate for each paired gateway. One gateway may also advertise multiple patched Zed instances. Select the intended gateway under **Connections**, then the intended **Zed target** above Sessions.

An unavailable target remains selected and visibly unavailable. ZedLink does not reroute an uncertain send to another target.

Each patched Zed **process** needs its own private probe socket and an explicit project root. Opening another folder in a second process that inherited the first process's ZedLink settings does not create another target: the first process owns that socket, and the bridge remains scoped to the first project. Start the second process with distinct probe settings:

```sh
mkdir -p -m 700 "$HOME/.local/state/zedlink/probes/second"
ZEDLINK_PROBE_DIR="$HOME/.local/state/zedlink/probes/second" \
ZEDLINK_PROBE_PROJECT_ROOT="/absolute/path/to/second-project" \
  /path/to/patched/zed "/absolute/path/to/second-project"
```

In **ZedLink: Manage Zed targets**, add a unique target ID and label with the socket path `~/.local/state/zedlink/probes/second/zedlink.sock` expanded to its absolute path. Restart **only the gateway** to load the target list; running desktop Agent turns continue. Then open the intended Agent conversation in the second patched Zed window and run `/remote-control` there. A new target starts with zero exposed threads. On the phone or browser, select the same paired gateway and switch the **Zed target** to that project. Each target's thread selection and pending sends remain separate.

## Models and external agents

ZedLink uses the model and Agent configuration already selected in Zed. It does not store provider keys or call an LLM directly. New native Agent sessions use the current Zed model/profile. Codex, Claude Code, and other ACP agents retain their configuration in Zed.

## Configuration checks

Use these in order:

```sh
python3 tools/zedlink_manager.py status
python3 tools/zedlink_manager.py diagnose
python3 tools/zedlink_manager.py check-routes
```

For Tailscale-specific failures, use **Check Tailscale Connection** followed by **Guided Tailscale Repair**. The repair flow checks client state, MagicDNS, HTTPS certificates, active gateway identity, and renewal without changing unrelated Zed settings.

Continue with [Pairing and first run](Pairing-and-First-Run.md).
