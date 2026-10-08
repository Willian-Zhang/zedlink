# Running and Pairing

[← Wiki home](README.md)

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

After setup, open **ZedLink — Patched Zed** from the Linux application menu. The dedicated square ZedLink icon launches the configured project directly in the patched `Zed Dev` build, so ordinary Zed does not need to be opened first.

If the launcher is missing, run **ZedLink: Install patched Zed launcher** once from the task picker. You can always use **ZedLink: Start patched Zed** as the terminal-backed fallback.

This opens another Zed window using the patched binary. It runs as a separate **Zed Dev** instance while continuing to read your normal Zed settings, including the configured local model. The ordinary Zed window installed by `curl -f https://zed.dev/install.sh | sh` remains the official release and is not modified.

The two windows are different applications:

| Window | Executable | `/remote-control` |
| --- | --- | --- |
| Ordinary Zed | `~/.local/zed.app/libexec/zed-editor` | unavailable |
| Zed Dev for ZedLink | `zed-source/target/debug/zed` | available |

Always open the Agent panel and choose `/remote-control` in the **Zed Dev** window. Neither the launcher nor the task can add the command to an official Zed window that is already running.

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

A private pairing page opens on the Zed computer. It supports these paths:

- **New browser:** select **Pair a new browser**, scan the QR, or copy the secure pairing link.
- **Phone, Windows PC, or another Linux computer:** scan the QR or select **Copy secure pairing link** and open it in the destination browser through a private channel.
- **Already-installed iPhone home-screen app:** keep the ZedLink app open. Do not scan the QR because iOS sends camera links to the default browser. Compare the HTTPS address and Gateway ID shown on both screens, type the displayed 10-digit code into the installed app, check **I checked this gateway**, and select **Connect ZedLink**.

Confirm Tailscale or your routed VPN is connected on the destination device and that the HTTPS page has no certificate warning. The link, QR, and 10-digit code expire after five minutes and work once. Keep them private.

The native iOS app has its own scanner under **Connections → + → Scan workstation QR**. A valid scan verifies the HTTPS identity and then pairs automatically, or reuses the existing Keychain credential when that Gateway ID is already trusted. Each reachable HTTPS address is saved separately, so Tailscale, local HTTPS, WireGuard, and proxy routes to the same gateway can coexist and be switched without another scan. Removing one route keeps the credential while another saved route still uses it. The Connections screen also lists every Zed instance advertised by the active gateway and switches the native target directly.

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
4. Open ZedLink from its new icon.
5. If the installed app asks to pair, run **ZedLink: Pair a device** on the Zed computer. Leave the installed app open and manually enter the 10-digit code; scanning the QR opens the default iOS browser instead of the installed app.

iOS may keep browser and home-screen credentials in separate website-data containers, particularly when the site was installed from a third-party browser. Pairing the installed app once is expected in that case. Its credential then remains scoped to the same trusted HTTPS origin and can be revoked independently.

On Android Chrome:

1. Open the trusted ZedLink HTTPS address.
2. Open **Settings** inside ZedLink and tap **Install ZedLink** when available, or use Chrome's **Install app** menu item.
3. Launch ZedLink from the home screen.

On desktop Chrome, Chromium, or Edge, use the install icon in the address bar or the browser's **Install ZedLink** menu item. Desktop Firefox has the same ZedLink features in a normal tab but should be bookmarked or pinned.

On a wide desktop window, ZedLink uses the full browser width. The Sessions column grows enough to show two-line thread names. The square **Z** mark in the top-left corner hides or restores Sessions; on a phone it switches between the selected conversation and Sessions. That choice and the last selected exposed thread are saved in the browser. When no saved selection exists, ZedLink opens the first exposed session automatically instead of leaving an empty “Choose a session” screen. Tool cards start collapsed; select **Read tool output** only when you need command output or file content.

The header reports three separate facts: the selected native thread's current model, this browser app's notification subscription, and the route to the gateway/desktop Zed. **Zed · Live** means the authenticated browser WebSocket is receiving updates from the gateway and the patched desktop Zed process. It does not claim that the configured model server is healthy. The model label turns amber for a native retry and red with **request failed** when the selected thread reports an error. The same error appears inline in the conversation and in Sessions. Notification state is scoped to the exact HTTPS origin and browser app; `https://HOSTNAME:PORT` and a raw IP address are different browser identities.

The installed web app still requires the private route, gateway, and patched Zed to be online.

### Enable session notifications

ZedLink uses standards-based Web Push for the browser app. This covers desktop Chrome, Edge, Firefox, supported Android browsers, and the ZedLink website installed on an iPhone or iPad Home Screen. On iOS and iPadOS, open the installed Home Screen app before enabling notifications; a normal browser tab does not expose Web Push there.

1. Pair the browser or installed web app.
2. Open **Settings**.
3. Under **This device**, select **Enable notifications** and accept the system prompt.
4. Select **Send test** to verify delivery through that browser's push service.

ZedLink then sends a generic notification when an exposed session finishes, fails, or needs approval. Lock-screen text never contains the prompt, reply, error details, tool arguments, output, project name, or model credentials. Selecting the notification opens the corresponding exposed session. Disabling notifications removes the subscription from the private gateway and the browser. Revoking the paired device also removes its subscriptions.

If the header says **Notifications · Off**, browser permission alone is not an active ZedLink subscription. Open Settings from the same trusted HTTPS hostname or installed app and use **Enable notifications**. ZedLink bounds the browser and gateway checks, so a failed service worker or route changes to **Unavailable** instead of remaining on **Checking** indefinitely.

The gateway needs outbound HTTPS access to the browser's Apple, Google, or Mozilla push service. It does not open an inbound public port and does not make the ZedLink gateway public. Notifications stop when the gateway or patched Zed is closed.

The native SwiftUI and Android packages require separate APNs and Firebase credentials, signing, and physical-device validation for native background delivery. Those native channels are not enabled yet; install the ZedLink website for the implemented cross-platform notification path.

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

Live reasoning and tool progress appear inside the conversation after the current transcript. While Zed is working, the activity entry expands and updates in place with reasoning, commands, terminal output, and file content published by the native thread. When the turn finishes, it condenses to a **Turn activity** row; select **View** to reopen it. The corresponding thinking blocks and tool cards also remain at their native positions in the transcript.

When the native Zed Agent uses its `spawn_agent` tool, ZedLink shows a **Parallel agents** section in the same conversation. Every child appears concurrently with its native status and recent transcript. Active children expand automatically; completed children condense and remain reviewable. A child that is waiting for permission shows its own scoped approval controls, and **Stop agent** cancels that exact child turn without cancelling its siblings or parent. Exposing a parent grants access only to children referenced by that parent. Zed decides when to create subagents and keeps their model, tools, context, and execution inside its native runtime; ZedLink does not run a second orchestrator. The pinned Zed revision supports one level of child agents.

Sessions that are running show an animated three-bar **Working** indicator in the Sessions list. The list reconciles with native Zed every two seconds while a conversation is open, while the selected conversation continues to receive immediate WebSocket updates. Browsers that request reduced motion receive a static activity indicator.

ZedLink reports five health layers separately: the browser's network, the HTTPS gateway, desktop Zed, live updates, and the selected native Agent. Open **Connections** on a phone to see each one. An Idle thread means no turn is currently running; it does not prove that the configured model endpoint is reachable. If Zed's last native turn failed, the session changes to **Request failed** and the same native error appears inline in the conversation. Native model retries show the current attempt and next retry delay. The error clears when Zed starts a later turn.

The square control at the bottom right of the composer shows an up arrow while the thread is ready to receive a message. When the native snapshot reports an exact active turn, it changes to a red Stop square. Selecting it sends a guarded cancellation for that Zed instance, event epoch, thread, and turn, then returns to Send when the thread becomes idle. The separate thread-header Stop button has been removed so the control stays beside the text field on phones and desktop browsers.

Open **Settings** from the gear beside Sessions or the phone's Settings tab. For the selected exposed thread, ZedLink displays the actual model reported by native Zed and lets you change the native Agent profile and model-thinking toggle while the thread is idle. These controls call Zed's thread settings paths; they do not store model credentials in the browser. Model selection remains in desktop Zed for now. **Sign out** appears once in Settings and removes this device's saved browser credential; use the desktop paired-device task when the server-side device record must also be revoked.

### Codex, Claude Code, and other external agents

Zed integrates external agents through the [Agent Client Protocol](https://zed.dev/docs/ai/external-agents). Start or open the agent from Zed's Agent Panel, then run `/remote-control` in that root conversation just as you would for the native Zed Agent. ZedLink reports the agent's real display name in Sessions, the conversation header, composer, replies, and runtime status. The shared ACP thread paths carry transcript updates, prompts, runtime slash commands, cancellation, tool approvals, project context, and Git review through the same desktop conversation.

External-agent configuration remains owned by that agent. For example, Codex or Claude Code controls its own sign-in, model selection, modes, and native configuration. ZedLink shows this boundary in Settings and disables the Zed-only profile and thinking controls. The browser's **New** action still creates a native Zed Agent thread because the inspected creation path does not expose an external-agent selector. Create a new Codex or Claude Code thread in desktop Zed, then expose it. Terminal threads remain excluded because ZedLink does not provide a remote shell.

The compact composer grows only as you type. Select **+** for native slash commands, **Project file**, or **Upload file**. Project file opens the selected exposed thread's configured worktree in a read-only Context panel; **Attach** sends the canonical project path through Zed's normal file-mention path. The Files panel can filter paths or search for text inside eligible project files. A result opens the real file at the matching line. Code previews wrap by default, include line numbers and local syntax coloring, and can expand into a full-screen review view with its own text search and optional unwrapped layout. Browser uploads are limited to eight files and 1 MiB each. Text, JSON, XML, PNG, JPEG, and WebP are mapped to native Agent content blocks. Image understanding still depends on the model selected inside Zed. If the selected checkpoint lacks vision support, ZedLink shows Zed's exact native failure inline above the composer. Uploaded bytes stay in the current tab until the send is accepted and are not written to browser storage.

The Context panel's **Changes** tab reads status and unified diffs from Zed's native repository object. Loaded diffs wrap by default, color added/removed/hunk lines, support text search, and use the same full-screen reviewer. Stage and Unstage require the exact displayed repository revision and a stable request ID, so a stale view or retry cannot silently apply to different changes. ZedLink does not expose commit, checkout, reset, push, pull, arbitrary filesystem access, or a terminal endpoint. Those actions remain in desktop Zed or can be performed by the native Agent under Zed's normal tool permissions.

Pending native tool requests appear inline with the choices Zed actually supplies. Fetch and filesystem requests keep their scope selector; terminal requests can select remembered command patterns; one-time and remembered Allow/Deny choices remain distinct; and action prompts such as Save, Discard, or Keep use their native labels. ZedLink sends the exact option ID, dropdown index, and selected pattern indexes through Zed's normal authorization path. The operation is guarded by instance, event epoch, thread, turn, and tool-call identity. The first desktop or remote decision wins; stale controls expire and never grant permission. ZedLink never auto-approves a tool.

Structured ACP elicitation forms and the Agent edit-review **Keep All / Reject All** bar are separate from tool authorization. They currently remain desktop-only and are listed in the roadmap rather than being presented as working remote approval controls.

Assistant Markdown renders headings, lists, quotes, links, fenced code with language labels and copy controls, and horizontally scrollable tables. Terminal output and file content use dedicated copyable tool sections. Native image output is currently represented by Zed's snapshot as the text `Image`, so graphical output parity still requires a future structured outbound attachment projection; the browser does not invent or fetch missing image data. Text, Markdown tables, ASCII charts, and chart source in fenced blocks remain readable.

Conversation spacing follows modern chat clients: short user prompts use a content-sized surface aligned to the right, long prompts wrap at a bounded readable width, and assistant responses remain open on the page. User prompts have no repeated header row or full-width border. Their compact copy icon appears on hover, keyboard focus, or touch layouts and retains an accessible label.

Long conversations may show “Older conversation omitted here” beneath the thread title. This is quiet status text rather than a popup. The full history remains in desktop Zed, while a separate recent-activity window keeps current reasoning and tool progress visible in the browser.
