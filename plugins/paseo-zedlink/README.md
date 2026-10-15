# ZedLink provider for Paseo

This is an experimental **server-side Paseo provider plugin**. It attaches to one explicitly exposed, loaded thread in the existing ZedLink gateway. Zed continues to own the agent, model, tools, queue, and approval policy. Paseo does not launch a second agent or receive a model key.

The directory includes the compiled `server/connection.mjs`, so installing it does not require an npm install or a TypeScript build. `server/connection.ts` and `server/gateway.ts` are its reviewed source. To rebuild after an edit, use a locally available Rolldown 1.0.0-rc.13 with `npm run build`; do not install build dependencies into this repository or `/tmp` on the ZedLink workstation.

## Current scope

- Lists explicitly exposed native Zed Agent threads in Paseo's provider model selector. The selector label is the native thread title and Agent name; its internal value is the thread ID, **not a model choice**. The actual model remains configured in Zed.
- Attaches to the selected native thread, replays bounded native history, checks the native event cursor before refreshing snapshots, and submits text through ZedLink `thread.send`. A candidate native echo is held until it can be linked to the Paseo prompt, so the normal phone timeline shows one user bubble.
- Checks the expected gateway identity over verified HTTPS before each authenticated RPC. The device credential stays on the Paseo daemon host in a private file; it is not sent to the phone or placed in plugin settings.
- Uses a stable request ID for each submission, queries `request.status` after an ambiguous response, and never automatically resends uncertain work. Accepted in-flight and uncertain receipts survive a Paseo session reload with their original Zed instance and epoch. Closing/reloading the Paseo session detaches the view and does not stop Zed.
- Maps Paseo Stop to the exact native request: `thread.queue.remove` removes only its own queued entry; once running, `thread.cancel` requires a fresh snapshot identifying the same native request and turn. Stop completion requires native acknowledgment. Older Zed builds without exact request identity can still show/send text, but the plugin refuses Stop rather than guessing from prompt text.
- Projects native thought segments, tool status, model/profile ownership, and context usage into Paseo when the patched Zed source supplies them. Model and profile remain controlled by Zed; the displayed model selector identifies a thread.
- Presents complete native permission-grant requests in Paseo with the exact **Allow once** and **Deny once** choices. Each choice is rechecked against `thread.approvals` before the native `approval.respond` call. No approval is decided automatically.

Approvals with missing details, action choices, persistent grants, and pattern-scoped choices stay in Zed or ZedLink. Images, attachments, commands, edits/rewinds, and exact tool cards are also deferred. If Stop appears before the plugin has identified the native turn, it refuses the request instead of canceling another turn. A failed or ambiguous approval response is reported as an error and is never retried automatically. The Paseo provider contract was checked against its tagged 0.10.3 source. An isolated iPhone prompt, one-time Allow and Deny, native tool display, and active-turn Stop after reopening passed on the disposable real native Zed fixture. Queued Stop passed through Paseo CLI while a desktop-owned native turn continued. The authoritative Zed thread settled Idle with only a partial delayed reply after iPhone Stop. The fixture uses a deterministic local model stub; the owner's configured local LLM remains untested through Paseo.

## Prerequisites

1. Run the patched Zed build and ZedLink gateway using the normal [gateway setup](../../docs/GATEWAY.md). In Zed, expose the intended existing Agent thread with `/remote-control`.
2. Run a Paseo daemon on a machine that can reach the gateway's trusted HTTPS address. The simplest topology is the same workstation. The iOS Paseo app connects to that daemon; it does not connect to the ZedLink gateway directly. See [Paseo getting started](https://paseo.sh/docs) and [connectivity](https://paseo.sh/docs/connectivity).
3. Pair a **separate ZedLink device identity for Paseo** using the existing gateway terminal client, then keep its JSON credential file readable only by the daemon account (mode `0600`). See [gateway pairing](../../docs/GATEWAY.md). Revoke this device from ZedLink if the Paseo installation is removed or compromised.

Set these variables in the **Paseo daemon's** environment before it loads the plugin:

| Variable | Meaning |
| --- | --- |
| `ZEDLINK_PASEO_URL` | Trusted `https://` origin of the ZedLink gateway; an explicit path prefix is allowed |
| `ZEDLINK_PASEO_TARGET_ID` | One configured gateway target ID, such as `primary`; no automatic target switching |
| `ZEDLINK_PASEO_CREDENTIAL_FILE` | Absolute path to the private paired-device JSON file containing `gateway_id`, `device_id`, and `token` |
| `ZEDLINK_PASEO_CA_FILE` | Optional PEM trust file for a private CA; omit for system-trusted certificates |
| `ZEDLINK_PASEO_TRACE_STOP` | Optional diagnostic value `1`: log only `stop.received` and `stop.native_requested` at the plugin boundary, without IDs, prompts, or arguments |

No token, pairing code, or model credential belongs in these environment values. Keep the token file outside the repository and out of logs. The plugin refuses gateway redirects and a changed gateway ID before transmitting the bearer token.

Once Paseo is running and its **Enable plugins** setting has been reviewed and enabled by the owner, install this directory on the daemon host:

```sh
paseo plugin install /absolute/path/to/zedlink/plugins/paseo-zedlink
paseo plugin ls
```

Before opening a Paseo session, run the read-only connection check from this plugin directory with the same daemon environment:

```sh
npm run preflight
```

It verifies HTTPS trust, gateway identity, the private paired-device file, the configured target, and the count of exposed native Zed threads. It prints no credential, prompt, thread title, or tool argument. A zero count means the intended thread still needs `/remote-control` in Zed.

Paseo's plugin setting is global and plugins are trusted code with daemon-account access; this repo does not enable that switch automatically. In Paseo, add/select the ZedLink provider, choose the exposed thread in the provider's model selector, then open it with no initial prompt. Do not select a different workspace expecting Zed to switch projects: the selected native thread retains its existing project. An empty selector means no thread is currently exposed or the configured target is unavailable.

For a direct Tailscale phone test, bind the **disposable** Paseo profile's `daemon.listen` to the workstation's specific Tailscale IP and set a daemon password before starting it. Keep Paseo relay disabled. Connect Tailscale on the phone, then choose Paseo Settings → Add host → Direct connection, enter that IP and port `6767`, leave **Use SSL** off as [Paseo's Tailscale instructions](https://paseo.sh/docs/connectivity) specify, and enter the daemon password. Tailscale encrypts this client-to-daemon hop; the daemon password supplies application authorization. The plugin's separate hop to ZedLink still uses verified HTTPS and a paired ZedLink device credential. Open the attached session, send a harmless text prompt, and verify exactly one matching user entry and reply in ZedLink's authoritative native snapshot.

## Local verification

```sh
cd plugins/paseo-zedlink
npm test
```

The tests use a disposable mocked thread and a local HTTPS server. They exercise replay, same-thread scope, one send, unknown-delivery behavior, queued and running Stop, reconnect recovery without resend, structured native state, exact one-time approvals, TLS identity before authentication, redirect refusal, and private credential permissions. They do **not** prove iOS rendering or real native Zed behavior; see [validation report](../../docs/VALIDATION_REPORT.md) for the separate host, native fixture, and iPhone results.

With a Paseo CLI installed and this plugin already installed in an **isolated** Paseo home whose `pluginsEnabled` value you explicitly chose, run the daemon-to-plugin fixture:

```sh
python3 plugins/paseo-zedlink/tools/test_host.py --cli /absolute/path/to/paseo --home /absolute/path/to/disposable-paseo-home --password-file /absolute/path/to/private-daemon-password
```

The password-file flag is optional when the disposable profile has no password. The script refuses a running daemon, starts the isolated one with a temporary HTTPS gateway and fake device credential, checks unauthenticated API rejection when a password is supplied, lists the native fixture thread, sends one harmless prompt through Paseo, then deletes its agent, archives its temporary workspace, and stops the daemon. It does not touch a real Zed project or validate the iOS app.

For a disposable **real native Zed** fixture with a deterministic loopback model, an isolated Zed profile/project, a separate HTTPS gateway and pairing state, and a preconfigured password-protected Paseo daemon bound to a specific Tailscale IP, run:

```sh
python3 -u plugins/paseo-zedlink/tools/serve_native_fixture.py --cli /absolute/path/to/paseo --home /absolute/path/to/disposable-paseo-home --password-file /absolute/path/to/private-daemon-password
```

It creates one exposed native thread, verifies one Paseo CLI prompt and native assistant reply, then stays up for the phone test. Ctrl-C tears down the fixture services, archives its temporary Paseo workspace, and deletes the temporary project. This proves the integration path through the real native thread, but its model is a stub and does not verify the user's configured local LLM. Physical iPhone checks are recorded separately in the validation report.
