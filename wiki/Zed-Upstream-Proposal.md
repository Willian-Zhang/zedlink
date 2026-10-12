# Draft Zed Upstream Proposal

[← Publishing and upstream readiness](Publishing-and-Upstream.md)

Use this as a starting point for a Zed GitHub Discussion. Review every statement and replace the maintainer notes before posting. The implementation was developed with AI assistance and must be disclosed and understood by the human contributor under Zed's contribution policy.

## Proposed title

Opt-in local control interface for existing Zed-hosted Agent threads

## Problem

Zed owns valuable Agent state that currently exists only inside the desktop application: the selected provider and model, conversation context, tools, MCP servers, permission state, approvals, streamed output, and project entities. Users who step away from the workstation cannot safely continue that same conversation from another private device.

External ACP clients and direct model APIs do not solve this problem. They create or control a different agent runtime and cannot preserve the authoritative native Zed thread.

## User experience

1. The user explicitly enables a local bridge in Zed settings.
2. The user opts a single root Agent or ACP conversation into remote access.
3. A separate authenticated gateway connects to a local-only Zed socket.
4. A paired client lists only opted-in threads and submits through each thread's normal native path.
5. Zed remains authoritative for execution, cancellation, tools, approvals, project state, and persistence.
6. Closing Zed makes the instance unavailable; it does not transfer the runtime or credentials elsewhere.

The prototype uses `/remote-control` as the per-thread toggle. That command and the transport shape are open design questions rather than requirements for upstream Zed.

## Proposed integration boundary

The prototype adds a narrow, versioned local interface around existing `agent`, `acp_thread`, and `agent_ui` paths. It does not add a model provider, remote shell, public listener, or mobile network stack to Zed.

The current capability set includes:

- explicitly expose or hide a root native/ACP thread;
- list exposed threads and authoritative status;
- obtain bounded snapshots and ordered events;
- submit a prompt with a stable client request ID;
- cancel the active turn;
- resolve an identified pending approval with stale-decision protection;
- create a native thread in the configured project;
- read bounded project/Git context used by the browser review surface.

All application entity access is scheduled on Zed's application thread. The socket is local and private; external TLS, routing, device pairing, and credential storage remain outside the Zed process.

## Security properties

- Disabled by default.
- No thread is visible until explicitly exposed.
- Exposure applies to the selected root thread and its referenced child agents.
- The local socket is created in a private state directory.
- Requests are method allowlisted, bounded, and versioned.
- Stable request IDs prevent duplicate turns after uncertain delivery.
- Approval decisions identify the exact pending request and fail when stale.
- Model credentials never cross the interface.
- No generic command execution, terminal input, or arbitrary filesystem endpoint is exposed.

The external gateway separately requires trusted HTTPS and revocable device pairing. Private-network reachability alone does not authorize a client.

## Why the existing extension API is insufficient

The supported extension API does not provide an entity for an open native Agent thread or methods to enumerate, submit, stream, cancel, or resolve its approvals. Legacy extension slash commands return command output and cannot preserve the selected thread's native execution state. A separate ACP agent would change the runtime and fail the same-thread requirement.

## Prototype and evidence

- Base Zed revision: `c66312b200d113694fca08c1d468669028a09a0e`
- Prototype branch: `tjnull/zed:zedlink/native-agent-remote-control`
- ZedLink repository: `tjnull/zedlink`
- Reviewable patch: `patches/zed-native-agent-remote-control.patch`

Validated in the prototype:

- a desktop-created native thread exposed explicitly;
- terminal, browser, and physical iPhone prompts appearing in that same desktop conversation;
- streamed responses, reasoning, tools, failures, approvals, and cancellation;
- replay and request-ID deduplication;
- browser `/compact` through the native command path;
- authenticated private HTTPS over Tailscale.

The browser transport fixture is kept separate from real native Zed evidence. Broader platform, network-provider, and physical notification coverage remains incomplete.

## Questions for Zed maintainers

1. Is remote control of an existing Zed-hosted Agent thread a capability Zed would consider supporting?
2. Should the integration be a built-in feature, an authenticated local service owned by Zed, or a new constrained extension API?
3. Which thread and event abstractions would Zed want to stabilize across native and ACP agents?
4. Should per-thread exposure be represented as a command, a conversation action, a setting, or another permission surface?
5. Which operations should remain desktop-only even after explicit exposure?
6. What smaller first pull request would be most useful for evaluating the architecture?

## Maintainer review requested

The initial request is for architectural direction before rebasing and reducing the prototype into upstream pull requests. No extension registry submission is proposed while the required capability is absent and new slash-command/agent-server submissions are disallowed.
