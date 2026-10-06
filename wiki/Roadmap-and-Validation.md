# Roadmap and Validation

[← Wiki home](README.md)

## Native Agent parity roadmap

ZedLink intentionally exposes a smaller remote surface than desktop Zed. The following native features remain candidates for carefully scoped bridge methods and browser controls.

| Native Zed feature | ZedLink status | Next useful step |
| --- | --- | --- |
| Model selection, mode, fast mode, and thinking effort | Current model is visible; profile and basic thinking can be changed | Add capability-gated native selectors with authoritative snapshots |
| Queued messages and steering | Native queue behavior is preserved but the queue is not manageable remotely | List, reorder, remove, and steer queued prompts without duplicating turns |
| Edit, regenerate, rewind, and checkpoints | Image-error rewind exists; general history controls do not | Expose native checkpoint IDs and guarded restore actions |
| Thread history and management | Exposed threads can be listed; sessions can be created in the configured project | Add rename, archive, delete, pagination, and project/worktree selection |
| External ACP agents | Existing root ACP threads can be exposed, identified, streamed, prompted, stopped, and approved | Add capability-tested external-agent creation when Zed exposes a stable agent-selection API |
| Rich tool interaction | Thinking, tools, terminal output, approvals, and child agents render inline | Add structured elicitation forms, interactive terminal input, and richer tool result views |
| Diff review | Files, search, unified diffs, stage, and unstage are available | Add native hunk accept/reject and checkpoint-aware review |
| Context accounting | `/compact` uses the native command path | Show token usage, context limits, compaction state, and supported settings |
| MCP and tool configuration | Existing Zed MCP servers and tools execute in the native runtime | Add read-only status and safe per-thread configuration where Zed exposes it |
| Worktrees and collaboration | Child agents are visible and cancellable | Add worktree selection and supported native collaboration controls |

Remote shell access, blanket auto-approval, and direct model credentials are intentionally outside ZedLink's design. Sensitive actions must continue through Zed's native permission and Agent paths.


## Validation and limitations

Verified:

- desktop-created native Agent thread exposed with `/remote-control`,
- terminal and gateway prompts appearing in that same native conversation,
- physical iPhone Safari prompt round trip over trusted Tailscale HTTPS,
- persistent browser pairing across refreshes and normal Safari tabs,
- request replay and same-ID deduplication,
- native cancellation in an isolated real-Zed fixture,
- browser `/compact` through the native command path,
- automatically visible live reasoning and tool activity from a bounded recent native snapshot,
- source-compiled root ACP exposure plus authenticated browser coverage for agent identity, external configuration ownership, commands, streaming, send, cancel, and approvals,
- global Zed task discovery and Status execution in an already-open Zed window,
- authenticated Web Push registration, private-endpoint rejection, persisted VAPID identity, subscription removal on revocation, and service-worker notification/open-session handling in deterministic tests.

Still incomplete:

- stock Zed Gallery packaging, which is blocked by the missing native-thread extension API and the current prohibition on new slash-command and agent-server submissions,
- a real Codex or Claude Code prompt round trip through the newly built ACP exposure path (the browser fixture passes; a real external thread has not yet been exposed),
- supervised background startup and certificate renewal,
- physical Web Push delivery on an installed iPhone/Android web app and native APNs/FCM delivery,
- paged, structured transcript/tool output and native image output,
- Git commit, branch, checkout, reset, push, pull, and hunk-level actions,
- a simultaneous desktop-versus-remote approval race against live Zed (the paired two-device fixture and direct native approve/deny/stale tests pass),
- broader physical-device and VPN-provider coverage.
