# Everyday Use

[← Wiki home](README.md)

## Everyday use

After first-time setup:

1. Start patched Zed with **ZedLink: Start patched Zed**.
2. Open the desired Agent conversation.
3. Run `/remote-control` in that thread.
4. Open **Settings → ZedLink → Gateway Control** and choose **Start**. The task command remains available as a fallback.
5. Open the saved ZedLink URL on any paired browser or app.

You normally do not need to pair the same browser again.

Use **Settings → ZedLink** for routine work:

| Settings page | Purpose |
| --- | --- |
| **Gateway Control** | Shows live gateway, bridge, route, device, project, and patched-Zed state inline; starts, restarts, or stops the gateway; and runs setup diagnostics |
| **Paired Devices** | Offers browser QR or terminal QR, lists authorized devices, and revokes one selected device after confirmation |
| **Connection Providers** | Selects, detects, validates, saves, activates, and checks private connection profiles |
| **Remote Permissions** | Controls session creation, attachments, project browsing, Git changes, approvals, and native Agent settings |

The task picker remains available for setup and maintenance:

| Task | Purpose |
| --- | --- |
| **ZedLink: Set up this project** | Automatically configures the currently open Zed worktree using detected Tailscale settings |
| **ZedLink: Status** | Shows configuration, build, launcher, socket, and gateway status |
| **ZedLink: Install patched Zed launcher** | Adds **ZedLink — Patched Zed** to the Linux application menu |
| **ZedLink: Manage connections** | Adds, enables, disables, selects, removes, or generates templates for gateway routes |
| **ZedLink: Manage Zed targets** | Adds or removes isolated patched Zed instances served by the paired gateway |
| **ZedLink: Check connections** | Verifies trusted HTTPS and stable gateway identity through every enabled route |
| **ZedLink: Restart gateway** | Gracefully reloads the enabled listener configuration without changing pairings or gateway identity |
| **ZedLink: Stop gateway** | Gracefully closes all gateway listeners while leaving saved state intact |
| **ZedLink: Paired devices** | Lists browsers allowed to connect |
| **ZedLink: Revoke device** | Removes a browser's access |
| **ZedLink: Configure** | Changes the project, route, TLS paths, or Zed profile |
| **ZedLink: Rebuild patched Zed** | Rebuilds the pinned patch and gateway |
| **ZedLink: Guided setup / update** | Runs the complete guided workflow again |

In desktop **Settings → ZedLink → Paired Devices**, choose **Open Browser QR** or **Show Terminal QR**. The terminal option opens a local Zed terminal and prints a one-use QR and manual code for the primary connection, valid for five minutes. It does not launch a browser. From a shell, `python3 tools/zedlink_manager.py pair-primary-terminal` does the same; `pair-terminal` lets you choose another route.

**ZedLink: Pair a device** opens the private pairing page without focusing a task terminal. Its temporary task tab closes after success and remains visible only when pairing fails. The `/bin/sh -i -c 'python3'` line shown by older task definitions was Zed's task wrapper; a blank cursor after “finished successfully” did not mean Python was still running. Run **ZedLink: Guided setup / update** once to refresh an older global task definition.

Build/install, launcher installation, full repair, and starting another patched Zed process intentionally remain tasks. They can compile for a long time, modify installation files, or create another application window, so they are poor fits for a Settings button. Runtime controls return promptly and are safe to use from Settings.

Closing the gateway terminal stops remote browser access. Closing patched Zed makes the native thread unavailable. Neither action deletes the conversation or pairing records.
## Switching Zed hosts and instances

The iPhone, Android, and browser clients keep connection state separate for each paired gateway. Choose a saved gateway from **Connections** to move between workstations. When one gateway manages multiple patched Zed instances, use the **Zed target** selector above Sessions. Drafts, selected threads, live event cursors, and uncertain sends remain scoped to that target.

An unavailable target remains selected and is shown as unavailable. ZedLink never sends its work to another target automatically.

From **+ New**, choose an agent advertised by the selected Zed project. The native Zed Agent uses its current Zed model and profile. Codex, Claude Code, and other ACP choices retain their external agent configuration in Zed.


## Terminal keyboard

Open **Context → Terminal** to use an existing terminal in the selected Zed project. Enable **View Project Terminals** and **Send Terminal Input** in desktop ZedLink settings. Those permissions are independent and apply live.

The browser offers two input modes. **Command** composes a whole command or reply before sending. Tap **Command** to switch to **Keyboard**, which sends typing directly to the selected Zed terminal. Use the shortcut row for Esc, Tab completion, Ctrl C, arrows, and Backspace. Hardware keyboards support these keys and Ctrl combinations in Keyboard mode. Enter sends a command or terminal Return; **Hide keyboard** restores the output area.

The native apps provide a command/reply field, Return, and Esc, Tab, Ctrl C, and arrow shortcuts. Android uses the Workspace Terminal tab; iOS offers a full-screen terminal from project context. Sending a shortcut first delivers any partially composed command without pressing Return. iOS includes a keyboard Hide action; Android includes a keyboard-dismiss button. Native apps currently compose text before submission; browser Keyboard mode additionally streams typing.

These controls address the existing terminal through Zed. Terminal output is a bounded text snapshot with native foreground/background colors, bold, italic, underline, and dim styles, refreshed while the terminal view is open. Color requires the updated patched Zed; older bridges remain readable as plain text. A bundled font supplies Seti, Devicons, Font Awesome, Octicons, and Material Design shell icons, while emoji use the operating system font. Other custom shell glyphs may still need additional font coverage. Browser and native controls offer wrapping for reading long output and an original-column mode for aligned terminal grids. Cursor position and remote resize are not projected, so full-screen editors and other terminal UIs do not have full emulator fidelity. Do not use this as evidence that every interactive terminal program is supported.


## Read parallel agents

Parallel agents appear as compact rows with their native status and activity count. Open a row to read that child in its own view; the main conversation stays in place. Browser readers keep the same panel and unchanged transcript rows during polling. Native apps use a separate reader with the same Markdown and tool-output renderer as the conversation.

Use **Load earlier activity** to page backward through the child transcript, and **Latest** to resume following updates after reading older content. Child approvals remain scoped to their owning agent: native readers show those approvals, and the browser's **Review approval** returns to the approval controls. **Continue agent** prepares an editable follow-up in the parent prompt; it does not automatically submit it. **Stop agent** appears only for a cancellable native turn and does not stop the parent or other children.

An updated patched Zed bridge is needed for child history offsets and paging. Older bridges show a truncation notice. After rebuilding, let active work finish before restarting patched Zed; restart the gateway to serve its rebuilt browser assets, and rebuild the mobile apps. No running agent is restarted automatically by this change.

Child-history bridge verified at fork revision `56cc1e513670e8a516be795baeb9367f6710e02b`. Native app compilation and physical-device verification remain pending.


Completed children leave the active conversation rows automatically. Open **Session actions → Agent history** in the native apps, or **+ → Agent history** in the browser, to read them again. Pending approvals stay visible even if a child no longer reports an active turn. Finishing does not close a child reader you deliberately opened. History is scoped to the selected conversation and the runtime's advertised child list.

## Native app build status

A gateway update does not update an installed APK or iOS app. Check app version/build and interface revision when testing. Android terminal keyboard visibility and speech popup recording have unresolved physical-device reports; the latest activity-window keyboard fix is awaiting validation. See [Native mobile apps](Native-Mobile-Apps.md) for build commands, branch/version details and known limitations.
