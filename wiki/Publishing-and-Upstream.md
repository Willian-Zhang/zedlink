# Publishing and Upstream Readiness

[← Wiki home](README.md)

## Current conclusion

ZedLink is a Zed core integration plus a separate gateway and clients. It is not currently eligible for the Zed Extension Gallery.

This conclusion was rechecked against Zed's official extension documentation on October 6, 2026 and against the pinned Zed source at revision `76659a55a8c10ed355a070f8764a0b1733e3c115`.

## Why a normal extension is insufficient

The supported WebAssembly extension API can contribute languages, themes, debuggers, snippets, and MCP servers. Its legacy slash-command entry point returns generated command output; it does not receive an entity for the open native Agent thread and cannot:

- enumerate existing native or ACP conversations;
- submit into the selected thread's normal execution path;
- subscribe to its streamed transcript, reasoning, tools, or failures;
- cancel its active turn;
- resolve its native tool approvals;
- add ZedLink's native settings and connection controls.

The inspected extension traits are in:

- `zed-source/crates/extension_api/src/extension_api.rs`
- `zed-source/crates/extension/src/extension.rs`

The native entities and execution paths ZedLink must reuse are in `agent`, `acp_thread`, and `agent_ui`. The maintained fork adds a narrow opt-in bridge around those paths instead of running a second agent.

## Gallery policy audit

| Zed publishing requirement | ZedLink result |
| --- | --- |
| Git repository with `extension.toml` | Not applicable yet; adding a manifest would imply unsupported functionality |
| Supported extension category | Blocked; native-thread remote control is not a published extension capability |
| New slash-command or agent-server submission | Blocked; Zed documents both categories as deprecated and no longer accepted |
| Extension ID | `zedlink` would be rejected because Gallery IDs may not contain `zed`; a future package needs a compliant ID |
| Extension sandbox | Current bridge must access native Agent entities and a private local socket, which a stock extension cannot do |
| Manual test at submitted commit | Required after a supported package exists |
| Public repository and branch-reachable commit | Required before a Gallery pull request |
| Accepted license | Pass; the project uses Apache License 2.0 |
| One-extension Gallery pull request | Required only after the native capability is supported |

Creating a decorative or task-only extension would not make the product installable: `/remote-control`, existing-thread access, streaming, approvals, and cancellation would still be absent. Zed's publishing prerequisites also prohibit using the extension API to work around its limits.

## Correct upstream sequence

A copy-ready starting point is available in [Draft Zed upstream proposal](Zed-Upstream-Proposal.md). Review and edit it before posting; it deliberately asks for architectural direction rather than presenting the prototype as a finished upstream design.

1. Open a Zed GitHub Discussion or use a staff-confirmed issue for the proposed native capability.
2. Present the user model and security boundary: explicit per-thread exposure, local-only bridge, authenticated external gateway, and no model credentials outside Zed.
3. Reduce and rebase the fork into reviewable Zed core commits with focused tests.
4. Complete human review of all AI-assisted code, Zed's contribution requirements, and the CLA.
5. Submit the core pull request from `tjnull/zed:zedlink/native-agent-remote-control` when the discussion has maintainer support.
6. If Zed chooses a public extension API rather than a core feature, build the smallest compliant extension against that released API and test it in stock Zed.
7. Publish that extension through a one-extension pull request to `zed-industries/extensions` using an HTTPS public submodule and matching manifest/catalog versions.

The Zed fork currently contains seven separated commits after the pinned revision. They cover cancellation correctness, the local bridge, failure state, project and Git context, image capability errors, bounded search, and native settings.

## Public repository checklist

Before changing the ZedLink repository from private to public:

- [x] Select and commit an accepted open-source license: Apache License 2.0.
- [ ] Review the complete Git history for credentials, certificates, pairing links, device tokens, private hostnames, IP addresses, and personal paths.
- [ ] Run `python3 tools/check_public_release.py`.
- [ ] Run `bash tools/check_linux.sh` and the authenticated browser transport fixture.
- [ ] Confirm the pinned fork branch and patch contain the same native changes.
- [ ] Keep `zed-source/`, build outputs, certificates, local state, and internal validation documents ignored.
- [ ] Add a security reporting policy and maintainer contact before accepting outside users.
- [ ] Confirm screenshots contain no private projects, hostnames, addresses, prompts, or credentials.
- [ ] State clearly that the current installer builds a patched Zed and is not a Gallery install.
- [ ] Record which Linux distributions and browser/device routes were actually tested.

The release checker examines the current working tree. A separate history review is still required because deleting a secret from the latest commit does not remove it from earlier commits.

## Official references

- [Developing Extensions](https://zed.dev/docs/extensions/developing-extensions)
- [Installing Extensions](https://zed.dev/docs/extensions/installing-extensions)
- [Publishing Extensions](https://zed.dev/docs/extensions/publishing/overview)
- [Publishing Prerequisites](https://zed.dev/docs/extensions/publishing/prerequisites)
- [Publishing Guide](https://zed.dev/docs/extensions/publishing/publishing-guide)
