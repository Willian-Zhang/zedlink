# Gateway web UI

The gateway serves a local, installable browser UI. The visual shell keeps ZedLink's original neutral OLED palette, low-contrast surfaces, a compact session rail, a bounded conversation reader, and a two-row composer. It controls only the native threads exposed by desktop Zed; model calls and credentials stay in Zed.

## Build

The local build was verified with Bun 1.4.0:

```sh
cd gateway/web
bun install --frozen-lockfile
bun run build
```

`bun run build` type-checks `src/session-list.tsx` and bundles React into `ui.js`. The generated bundle is committed because the Rust gateway embeds it with `include_str!`; rebuild it after changing React source. Then build the gateway with `CARGO_BUILD_JOBS=1 CARGO_INCREMENTAL=0 cargo build --manifest-path gateway/Cargo.toml --offline -j 1` from the repository root.

The session navigator is the first React and TypeScript component. `app.js` remains the native-thread controller and owns pairing, transport, replay, permissions, and transcript behavior. It passes display-only session data and selection/pin callbacks to the React component. Keep network and native operations in that controller until their behavior is covered by the paired-browser fixture. `index.html` loads `ui.js` before `app.js`, and the service worker caches both assets under one shell version.

The session rail shows counts for All chats, Needs attention, Running, and Pinned based on the current search. It includes an expandable Project tools section for Files, Changes, Terminal, and Activity; Connection and Settings stay at the foot of the rail. Project tools require a selected exposed thread. On shorter desktop windows, the Project tools section starts collapsed so recent sessions remain visible. Outside a text field, use Ctrl+K (⌘K on macOS) to open session search; Down Arrow moves into the result list, and Escape clears a query. A filtered empty view offers a reset. Pinning only changes local browser ordering; thread selection, sending, approvals, and cancellation use the existing native-thread controller.

Search messages reads the selected or all currently exposed threads on demand through native snapshot and history pages. It displays at most 100 results and keeps no transcript index. A result opens its native thread and loads the needed history page. The reader keeps at most 192 entries in the DOM at a time, with controls to move through older loaded entries and back to the latest. The attention view links to native sessions waiting for approval or input, or reporting a failed turn. Browser-local tags and last-viewed order are scoped to a gateway target; they do not alter Zed projects or thread state.

The context button shows native Zed's reported input usage and offers `/compact` only when the selected idle native Agent advertises that command. Reading width, text size, session density, and code wrapping are browser-local preferences. The workspace opens as a compact side panel on wide desktop windows; Expand provides a wider review view. Files, changes, terminal, debug, and activity still use the selected exposed project. Unified diff review has hunk navigation when the native diff contains hunk headers. Narrow windows use the full-screen workspace view.

On the owner's Linux workstation, Bun is at `~/.bun/bin/bun`. Local build rules require dependency files and caches on disk outside this repository and `/tmp`; the local test used an external dependency directory with `gateway/web/node_modules` as an ignored symlink to it. A normal development environment can use Bun's default install location for `node_modules`.

## Verify

From the repository root:

```sh
python3 tools/test_mobile_viewport.py
python3 tools/test_gateway_transport.py
```

The gateway transport test uses a disposable loopback TLS gateway and paired Firefox profile. It covers the session list, search, pinning, thread selection, approvals, cancellation, reconnect, pairing, and revocation. The mobile viewport fixture uses synthetic content in Chromium. Neither is a physical iPhone/WebKit validation.

## Interactive local mock preview

With the gateway and `ui.js` built, run `python3 tools/preview_gateway_ui.py` from the repository root and open the printed `/preview` URL in a browser on the same workstation. That URL generates a fresh one-time pairing code and opens the current web assets against a disposable local gateway and synthetic probe. The mock supports session search, settings, context, prompt submission, and live WebSocket updates without touching a running Zed instance, real project, or model. It binds to `127.0.0.1` only and stops with Ctrl+C. A browser on another device needs a deliberate private port forward to that loopback listener.
