# Agent commands

The browser, iOS and Android command pickers use the command catalog from the selected Zed thread. Type `/` or open the composer command menu, select a command, edit its arguments, then send. Descriptions, argument hints and skill warnings come from Zed. The list refreshes when opened and periodically while connected; switching connections cannot apply an old thread's catalog.

## Supported commands

| Source | Remote behavior |
| --- | --- |
| Native Zed | `/compact` follows the desktop command and queue paths. |
| Skills | Scoped names such as `/Orbit Notes:review` load the registered skill through Zed's mention loader. Additional instructions remain editable. |
| MCP | Prompts advertised by the native thread appear with their available argument hints. |
| External agents | ACP commands advertised by the selected Codex, Claude Code or other agent appear dynamically. Availability depends on that agent. |
| `/remote-control` | Explicit confirmation stops exposure of the selected conversation. The agent continues in desktop Zed. Starting exposure requires desktop Zed. |
| `/helpful` | Explicit confirmation invokes Zed's native feedback action, which shares the conversation with the Zed team. |
| `/not-helpful` | Explicit confirmation opens the native feedback form in desktop Zed; finish that form there. |

Local actions are never sent as model prompts. They require confirmation for the exact draft and connection, reject attachments and arguments, and obey native action availability and exposure permissions. Unknown slash commands are rejected. Retrying an uncertain submission preserves its request identity; reconnecting does not send it again automatically.

Native commands and local actions reject attachments. Skills, MCP prompts and ACP prompt commands follow the ordinary native content submission path and its advertised attachment capabilities.

## Native agent controls

The native apps also show advertised Zed profiles and thinking controls alongside models. Changes require a live, idle thread and its settings capability. Models that require thinking cannot disable it. External agents own their configuration and do not receive Zed-only controls.

## Limits and verification

Coverage means the commands actually advertised by the selected runtime, plus available native local actions. Zed's pinned MCP adapter filters unsupported prompt signatures, including multi-argument prompts; ZedLink does not invent missing commands. Other context mention types are a separate feature from slash commands.

An isolated native Zed profile and disposable Orbit Notes project verified skill loading, same-thread browser submission, replay, permission gating and Stop exposing. Browser transport fixtures and command-resolution tests also passed. iOS and Android UI compilation, physical-phone round trips, the owner's local GLM and each external agent's command set have **not** been tested in this Linux environment. No hosted builds were dispatched.

After upgrading, restart patched Zed and the gateway, refresh the browser, and rebuild the native apps. Use a disposable exposed conversation to check the command picker and its argument hints before testing compaction or actions.

[← Everyday use](Everyday-Use.md)

Inspected fork revision: `dc532ac8ad534619a9609af9a0b09713b9cc8020`, based on upstream `c66312b200d113694fca08c1d468669028a09a0e`.
