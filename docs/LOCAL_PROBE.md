# Local native-thread probe

Status: opt-in source patch; compiled with `cargo check -p agent_ui --offline` and included in a successful `cargo build -p zed --offline` at Zed `76659a55a8c10ed355a070f8764a0b1733e3c115`. The current build adds explicit `/remote-control` exposure in the native Agent composer. Before exposure, the isolated process returned an empty thread list and rejected a known thread snapshot with `THREAD_NOT_EXPOSED`. The user selected the command in the native Agent composer and saw its success toast; the socket then listed exactly that thread, returned its snapshot, and a local probe prompt produced one matching native user entry and a following assistant entry. Selecting the command again hid the thread and denied snapshots and sends. This probe is not the authenticated gateway or an iPhone transport.

The source change is in the ignored nested `zed-source/` checkout and is exported as [the reviewable patch](../patches/zed-1.22.0-local-probe.patch). It adds a private Unix socket inside the patched Zed process. The listener starts only when `ZEDLINK_PROBE_DIR` and `ZEDLINK_PROBE_PROJECT_ROOT` are both set to absolute paths. Zed creates or verifies a mode-0700 private directory, creates a mode-0600 socket, and can replace its own stale socket after a restart; it refuses a live or non-socket path. The project root must already exist and is canonicalized. Each process starts with no exposed threads. In a native Agent thread whose visible worktree root matches the selected project, selecting `/remote-control` toggles exposure of only that thread; selecting it again revokes access. Exposure is lost on process restart. No remote endpoint is opened.

The probe accepts one newline-delimited JSON request per connection, up to 4 KiB. Methods are `instance.info`, `thread.list`, `thread.snapshot`, `thread.events`, `thread.send`, `thread.cancel`, `request.status`, and experimental `thread.approvals` and `approval.respond`. The newest build advertises `thread.cancel` in `instance.info`; the paired gateway forwards it with native instance/epoch/thread/turn checks. Approval remains local-only. A currently running older Zed process must be restarted and its thread explicitly re-exposed to advertise the new capability. Snapshot entries are provisional Markdown projections, capped at 64 KiB. A snapshot includes a per-thread `last_sequence` and pending permission-grant metadata. `thread.events` returns sanitized event kinds after a sequence cursor from a bounded 256-event in-process buffer. It returns `RESYNC_REQUIRED` for a cursor that is too old or ahead of the current sequence. The terminal client's `watch` command polls that feed and prints event metadata. This is not a WebSocket subscription and does not yet attach stable per-entry IDs. The snapshot includes `provisional: true` so it cannot be mistaken for the finished protocol. A 16-item command queue and short socket timeouts bound local requests. Errors and event metadata do not include transcript content.

`thread.send` requires the loaded `thread_id`, current `instance_id` and `epoch` from `thread.list`, a stable `request_id`, and text of at most 3000 bytes. It enters `ThreadView::send_content` when the native thread is idle and has no queued messages, or `ThreadView::add_to_queue` while busy or already queued. It rejects a send while the desktop is still loading message contents. The local in-process ledger retains up to 256 request IDs, their exact text, and outcomes; a same-ID retry returns the previous outcome, changed text returns `REQUEST_CONFLICT`, and a stale instance or epoch returns `INSTANCE_UNAVAILABLE`. `request.status` looks up a prior send ID without resending, returns `known: false` and `outcome: unknown` when absent, and denies access after thread exposure is revoked. The absent-request result passed one live check; the known-request and revoked cases have not been tested. The idle send result is `unknown` because `send_content` schedules an asynchronous task, so this is not an authoritative accepted/complete receipt. A busy result is `queued`, not an execution guarantee. If the probe restarts, its epoch changes and old retries are rejected. There is no durable replay or automatic reconciliation yet. Prompt text remains only in process memory and the native thread; routine probe errors and logs omit it.

`thread.create` requires the current instance and epoch plus a stable request ID and an optional title of at most 128 bytes. It calls `AgentPanel::create_thread_with_options` in the workspace that owns the configured project, explicitly selecting `Agent::NativeAgent` while leaving model and work directories unset so Zed inherits the native Agent's current model and project defaults. The operation returns `creating` while Zed connects the native session, then exposes and returns its stable ACP session ID. Same-ID retries are idempotent; a changed title returns `REQUEST_CONFLICT`. The adapter retains at most 64 creation records for the life of the Zed instance. It does not accept a project path, model, agent, endpoint, prompt, or credentials from the remote client.

## Reproducible commands and observed runtime check

From the project root, the following checks have passed:

```sh
cd zed-source
RUSTUP_TOOLCHAIN=stable cargo fmt --package agent_ui -- --check
RUSTUP_TOOLCHAIN=stable cargo check -p agent_ui --offline
```

The full binary build initially stopped at the missing ALSA development package (`alsa.pc`). After the documented Linux headers were installed, `RUSTUP_TOOLCHAIN=stable cargo build -p zed` passed. The build downloaded Zed's pinned WebRTC archive through its build script. This environment's sandbox could not access the desktop display or local Unix socket, so the isolated runtime and socket client were run with permitted external access. The test did not touch the production Zed profile.

Run the patched binary with a fresh disposable project and isolated Zed profile. The source's `crates/zed/src/main.rs` defines `--user-data-dir`; this command pattern was executed with a temporary fixture:

```sh
private_parent="$(mktemp -d /tmp/zedlink-probe.XXXXXX)"
printf 'Probe parent: %s\n' "$private_parent"
fixture_root="$private_parent/fixture"
mkdir "$fixture_root"
ZEDLINK_PROBE_DIR="$private_parent/socket" \
ZEDLINK_PROBE_PROJECT_ROOT="$fixture_root" \
  ./zed-source/target/debug/zed --user-data-dir "$private_parent/profile" "$fixture_root"
```

Create or open a native Agent thread for that project in the desktop UI, type `/remote-control` in its composer, and select the **Remote Control** suggestion. The success toast says the thread is exposed locally; it does not mean that a phone is paired or connected. Then use the terminal client in another shell. Set `private_parent` there to the printed path from the first shell:

```sh
private_parent=/tmp/zedlink-probe.REPLACE_WITH_PRINTED_SUFFIX
python3 tools/zedlink_probe_client.py --socket "$private_parent/socket/zedlink.sock" list
python3 tools/zedlink_probe_client.py --socket "$private_parent/socket/zedlink.sock" snapshot THREAD_ID_FROM_LIST

# Runtime commands for that exposed thread (copy instance_id and epoch from list):
python3 tools/zedlink_probe_client.py --socket "$private_parent/socket/zedlink.sock" \
  --instance-id INSTANCE_ID --epoch EPOCH commands THREAD_ID_FROM_LIST
python3 tools/zedlink_probe_client.py --socket "$private_parent/socket/zedlink.sock" events THREAD_ID_FROM_LIST
python3 tools/zedlink_probe_client.py --socket "$private_parent/socket/zedlink.sock" watch THREAD_ID_FROM_LIST
request_id="$(python3 -c 'import uuid; print(uuid.uuid4())')"
printf 'Send request ID: %s\n' "$request_id"
python3 tools/zedlink_probe_client.py --socket "$private_parent/socket/zedlink.sock" \
  --request-id "$request_id" \
  --instance-id INSTANCE_ID_FROM_LIST --epoch EPOCH_FROM_LIST \
  send THREAD_ID_FROM_LIST 'Reply with the word hello.'
```

Record the request ID before sending and reuse it for a retry. Do not use a real project as the fixture. On 2026-10-03 the first isolated process listed native thread `312dda8b-2c50-4eda-bcd3-7e85fcd36bd7` in instance `79867c43-0197-4edd-aec7-8851082af37b`. After the user sent a desktop prompt, `thread.snapshot` for that ID contained 15 Agent entries and reported `Generating`, `truncated: false`, and `provisional: true`. The user reported that this Zed Agent was using their configured local LLM; model origin was not independently measured.

The rebuilt process restored the desktop-created thread `daebd781-e95b-44e2-9454-0b6beb279247` in a new instance and epoch. One local `thread.send` returned `unknown`; a later snapshot showed exactly one matching native user entry, a following assistant entry, and `Idle` status. A repeat with the same request ID returned `unknown` and did not add a second user entry. A changed prompt with that ID returned `REQUEST_CONFLICT`; a stale epoch returned `INSTANCE_UNAVAILABLE`. After a final guard was added and the binary rebuilt, a second harmless prompt reached that same persisted thread in a new instance and produced one user entry with `Idle` status. Retrying the earlier request with its actual previous instance/epoch returned `INSTANCE_UNAVAILABLE`.

With the `/remote-control` build, the user selected the command in the isolated native Agent composer and reported the “Thread exposed to ZedLink locally” toast. The socket then listed exactly the selected thread and snapshotted 11 entries. A harmless `thread.send` produced exactly one new native user entry and a following assistant entry; status moved from `Generating` to `Idle`. The user selected the command again and reported “ZedLink exposure stopped”; the socket list emptied and snapshots, new sends, and old request retries all returned `THREAD_NOT_EXPOSED`.

The next patched build added bounded `thread.events` polling. The user explicitly exposed two native threads, and confirmed selecting `/remote-control` in each. The known desktop thread started at sequence 9. While one local probe prompt ran, the terminal `watch` command received ordered events 10 through 27, including `status.changed`, `entry.added`, repeated `entry.updated`, and `turn.stopped`. A final snapshot returned `Idle`, 15 entries, sequence 27, and exactly one matching user entry with a following assistant entry. A future cursor returned `RESYNC_REQUIRED`. These are local IPC checks; authoritative acceptance linkage, authenticated WebSocket streaming, queueing while busy, approval, TLS, pairing, and phone behavior remain untested.

The experimental `thread.cancel` takes the current `instance_id`, `epoch`, `thread_id`, and `turn_id` reported by a snapshot. It rejects an idle or mismatched turn with `STALE_TURN` and invokes `ThreadView::cancel_generation` for a matching active turn. The first active-turn test returned `outcome: requested` and the wrapper became `Idle`, but assistant content continued to grow while event polling continued. A bridge guard now stops forwarding native events once their ACP turn is no longer current. A repeat isolated test cancelled an actively streaming turn; one in-flight update arrived, then text and event sequence stabilized for the rest of a 4.6-second observation. This is a narrow visible-state check, and provider-side cancellation and broader race coverage remain unverified. The method remains experimental and is not an advertised client capability. See [the validation report](VALIDATION_REPORT.md) for identifiers and observations.
