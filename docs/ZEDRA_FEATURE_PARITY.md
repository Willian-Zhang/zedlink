# Zedra-inspired iOS direction

Status: implementation map based on public Zedra commit `809a12dee561175af93379d34599e2511a1ccf64` and its MIT license. ZedLink adopts compatible mobile interaction patterns while retaining its own name, visual identity, SwiftUI implementation, private HTTPS transport, and same-native-Zed-thread architecture. No Zedra artwork or branding is included.

## Product boundary

Zedra is a general remote developer workspace backed by its own desktop daemon and terminal sessions. ZedLink is a control surface for explicitly exposed native Zed Agent conversations. The local model, context, tools, permissions, MCP connections, and execution remain in Zed.

This difference controls feature scope:

- ZedLink may show terminal commands and output produced by native Zed tools.
- ZedLink does not add an unrestricted remote shell.
- File, search, and Git data must come from separately advertised, project-scoped read-only adapter capabilities.
- Agent creation or archived-session restoration must use verified native Zed paths before appearing in the app.
- Push and lock-screen activity require a separate background delivery design and are not implied by foreground polling.

## Feature map

| Zedra pattern | ZedLink implementation | State |
| --- | --- | --- |
| QR pairing | Camera scanner, clipboard pairing link, verified gateway identity, Keychain credential | Implemented |
| Reconnect after pairing | Preferred profile restoration, foreground identity verification, native reconciliation | Implemented; simulator build pending |
| Agent/session dashboard | Searchable exposed native threads with live working/ready state | Implemented; runtime visual check pending |
| Compact OLED workspace | Flat near-black surfaces, subtle rules, dense monospace metadata, semantic status color | Implemented; simulator visual check pending |
| Agent chat | Persistent composer, Markdown, code blocks, delivery state, Stop, per-thread draft | Implemented; live native iPhone check pending |
| Reasoning/activity | Separate bounded recent native activity projection, auto-visible live panel | Implemented in adapter, browser, and SwiftUI; physical app check pending |
| Terminal activity | Expandable cards for native Zed tool command/output projections | Implemented from available native Markdown |
| Approvals | Exact pending tool label/input displayed; decisions remain in desktop Zed | Display implemented; remote decision disabled pending paired race validation |
| Agent commands | Runtime-discovered native/agent/MCP slash command picker | Implemented; simulator/live app check pending |
| Markdown preview | Native attributed Markdown plus fenced code surfaces | Implemented for conversation/activity content |
| File browser and fuzzy search | Requires scoped adapter operations and pagination | Not implemented |
| Code editor and Add to Chat | Requires safe project file reads, stable selection references, and mention mapping | Not implemented |
| Git status and unified diff | Current native projection exposes limited file content; structured diff capability required | Not implemented |
| Direct terminal/TUI | Conflicts with ZedLink's no-generic-shell boundary | Intentionally excluded |
| Launch/resume arbitrary agents | Existing exposed native Zed threads only | Not implemented |
| Image paste/upload | Requires bounded attachment protocol and native Zed message mapping | Not implemented |
| Push notifications | Requires background service/APNs design | Deferred |
| Dynamic Island/Live Activity | Requires ActivityKit target plus a truthful background update source | Deferred |
| P2P QUIC/relay | ZedLink uses saved HTTPS profiles over Tailscale, WireGuard, LAN, or a custom trusted proxy | Different architecture |

## Implemented iOS slice

The SwiftUI client now includes:

- automatic preferred-profile reconnect;
- searchable exposed-session dashboard;
- OLED dark default with System and Light choices;
- flat message, tool, activity, and approval surfaces;
- native Markdown and horizontally scrollable code blocks;
- Zed-published reasoning separated from final response text;
- active-turn snapshot refresh even when no event delta is emitted;
- expandable native tool/terminal output cards;
- detailed pending approval inspection;
- runtime slash command discovery and searchable picker;
- per-thread draft persistence;
- successful-send cleanup so uncertain recovery controls appear only after an actual uncertain delivery;
- unit tests for reasoning and tool projection parsing.

## Next adapter gates

1. Define paged, project-scoped `workspace.files`, `workspace.search`, and `workspace.read` contracts with canonical path containment and bounded payloads.
2. Implement structured `changes.snapshot` through Zed's project/repository state, with stable file identities and truncation metadata.
3. Validate `approval.respond` through an authenticated paired gateway against simultaneous desktop/mobile decisions, then advertise it and add Approve once/Deny controls.
4. Add an attachment contract only if the native Zed thread supports the same image/message path used by desktop.
5. Decide whether push requires a self-hosted companion service or stays out of the private foreground MVP.

Each capability remains absent from the UI until its real adapter path and tests pass.
