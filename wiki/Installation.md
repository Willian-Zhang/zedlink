# Installation

[← Wiki home](README.md)

This guide installs the Linux host components: the maintained patched Zed build, the local gateway, and Zed tasks. Pairing comes later.

## Requirements

- A Linux workstation supported by Zed.
- Git, Python 3, Rust, and Cargo.
- The [Zed Linux build dependencies](https://github.com/zed-industries/zed/blob/c66312b200d113694fca08c1d468669028a09a0e/docs/src/development/linux.md).
- A model already working in desktop Zed.
- A private route that can carry trusted HTTPS. Tailscale with MagicDNS is the recommended first setup.
- Enough disk space for a Zed source checkout and build artifacts.

The first Zed build can take a while. ZedLink does not download model weights or copy model credentials.

## 1. Clone the repository

```sh
git clone https://github.com/tjnull/zedlink.git
cd zedlink
```

Do not place secrets, certificates, or a Zed source checkout inside the repository. Generated state belongs under the private paths selected by setup.

## 2. Run guided setup

```sh
bash tools/setup_zed_ide.sh
```

The guided flow can:

1. create or update the ignored `zed-source/` checkout from the maintained Zed fork;
2. build patched Zed and the Rust gateway;
3. save the selected project and private connection profile;
4. install global Zed tasks without replacing unrelated tasks; and
5. install the **ZedLink — Patched Zed** application launcher.

For an unattended update after configuration:

```sh
bash tools/setup_zed_ide.sh --yes
```

Run `bash tools/setup_zed_ide.sh --help` before using skip options. The installer preserves an existing valid configuration and does not modify Zed's model provider, endpoint, name, or credentials.

## 3. Use the Zed task picker

Open this repository in Zed, press `Ctrl+Shift+P`, choose **task: spawn**, and search for `ZedLink`.

The main setup tasks are:

| Task | Purpose |
| --- | --- |
| **ZedLink: Set up this project** | Configure the worktree currently open in patched Zed |
| **ZedLink: Guided setup / update** | Run the complete installer interactively |
| **ZedLink: Install / build** | Update and build patched Zed and the gateway |
| **ZedLink: Configure** | Change project, route, TLS, or profile settings |
| **ZedLink: Diagnose setup** | Print a read-only health report |
| **ZedLink: Repair setup** | Restore managed settings, tasks, launcher, and private directories |
| **ZedLink: Status** | Show build, bridge, gateway, route, and device state |

If the tasks are missing, confirm that the ZedLink repository is the open worktree and rerun guided setup.

## 4. Launch the correct Zed build

Open **ZedLink — Patched Zed** from the application menu. The official Zed release and the patched development build are separate applications.

| Application | Typical executable | ZedLink native bridge |
| --- | --- | --- |
| Official Zed | `~/.local/zed.app/libexec/zed-editor` | No |
| ZedLink patched Zed | `zed-source/target/debug/zed` | Yes |

If the launcher is missing, run **ZedLink: Install patched Zed launcher**. You can also run **ZedLink: Start patched Zed** from the task picker.

## 5. Verify the installation

Run **ZedLink: Status**, then **ZedLink: Diagnose setup**. Confirm that:

- the pinned patched Zed executable exists;
- the gateway executable exists;
- the project and private state directory are the intended paths;
- the native socket and connection profile are recognized; and
- no certificate or key is stored inside the repository.

Continue with [Configuration](Configuration.md).

## Updating

Pull the repository, then rerun guided setup:

```sh
git pull --ff-only
bash tools/setup_zed_ide.sh --yes
```

Finish active Agent work before restarting patched Zed. Restart the gateway after a web or gateway change. Rebuild and reinstall native mobile apps separately; a gateway update cannot update an APK or iOS app.

## Removing local integration

Use the manager's explicit removal actions rather than deleting configuration piecemeal:

```sh
python3 tools/zedlink_manager.py remove-launcher
python3 tools/zedlink_manager.py remove-cli
bash tools/setup_zed_ide.sh --remove-global-tasks
```

Review saved device, route, and private state before deleting it. Removing the ignored `zed-source/` directory only recovers build space; the next install must clone and compile Zed again.
