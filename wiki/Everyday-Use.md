# Everyday Use

[← Wiki home](README.md)

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
| **ZedLink: Status** | Shows configuration, build, launcher, socket, and gateway status |
| **ZedLink: Install patched Zed launcher** | Adds **ZedLink — Patched Zed** to the Linux application menu |
| **ZedLink: Manage connections** | Adds, enables, disables, selects, removes, or generates templates for gateway routes |
| **ZedLink: Check connections** | Verifies trusted HTTPS and stable gateway identity through every enabled route |
| **ZedLink: Restart gateway** | Gracefully reloads the enabled listener configuration without changing pairings or gateway identity |
| **ZedLink: Stop gateway** | Gracefully closes all gateway listeners while leaving saved state intact |
| **ZedLink: Paired devices** | Lists browsers allowed to connect |
| **ZedLink: Revoke device** | Removes a browser's access |
| **ZedLink: Configure** | Changes the project, route, TLS paths, or Zed profile |
| **ZedLink: Rebuild patched Zed** | Rebuilds the pinned patch and gateway |
| **ZedLink: Guided setup / update** | Runs the complete guided workflow again |

**ZedLink: Pair a device** opens the private pairing page without focusing a task terminal. Its temporary task tab closes after success and remains visible only when pairing fails. The `/bin/sh -i -c 'python3'` line shown by older task definitions was Zed's task wrapper; a blank cursor after “finished successfully” did not mean Python was still running. Run **ZedLink: Guided setup / update** once to refresh an older global task definition.

Closing the gateway terminal stops remote browser access. Closing patched Zed makes the native thread unavailable. Neither action deletes the conversation or pairing records.
