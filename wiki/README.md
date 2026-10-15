# ZedLink Wiki

ZedLink is a self-hosted companion for Zed that lets you securely continue an explicitly exposed Zed Agent or ACP conversation from a browser, iPhone, or Android device. The model, project, tools, permissions, and execution stay in desktop Zed.

> [!IMPORTANT]
> ZedLink currently requires the maintained patched Zed build. It is not a Marketplace extension for stock Zed. The browser or installed web app is the most complete client; the native apps are development builds.

## Start here

| Step | Guide | Outcome |
| --- | --- | --- |
| 1 | [Install ZedLink](Installation.md) | Build the pinned Zed integration and gateway on Linux |
| 2 | [Configure a connection](Configuration.md) | Create a trusted private HTTPS route and choose remote permissions |
| 3 | [Pair your device](Pairing-and-First-Run.md) | Expose one thread, pair, and complete a same-thread test |
| 4 | [Use ZedLink](User-Guide.md) | Work with sessions, files, terminals, agents, approvals, and commands |

Use [Troubleshooting](Troubleshooting.md) when a check fails. Read [Security](Security.md) before exposing a work project or pairing another device.

## What stays where

```text
Browser, iPhone, or Android
          │  authenticated HTTPS / WebSocket
          ▼
    ZedLink gateway
          │  private local Unix socket
          ▼
    Patched desktop Zed
          └─ exposed thread · configured model · tools · project
```

- Zed remains authoritative for the conversation, model, tools, approvals, and cancellation.
- The gateway stores paired-device authorization and forwards narrow protocol requests.
- A phone disconnect does not stop the Agent. Closing Zed makes that instance unavailable.
- Only projects and conversations explicitly enabled for ZedLink can be reached.

## Interface tour

<table>
  <tr>
    <td width="50%" align="center"><img src="../assets/screenshots/mobile-conversation.png" width="300" alt="ZedLink mobile conversation view"><br><strong>Continue the same conversation</strong></td>
    <td width="50%" align="center"><img src="../assets/screenshots/mobile-terminal.png" width="300" alt="ZedLink mobile terminal view"><br><strong>Use an enabled project terminal</strong></td>
  </tr>
</table>

![ZedLink project file browser](../assets/screenshots/file-browser.png)

The browser images use synthetic content from an isolated documentation fixture. They contain no real project transcript or credentials. See the [screenshot provenance](../assets/screenshots/README.md).

## Reference

- [Mobile apps](Mobile-Apps.md)
- [Security](Security.md)
- [Troubleshooting](Troubleshooting.md)
- [Development and testing](Development.md)
- [Project status and validation](Project-Status.md)
- [Credits](Credits.md)
- [Draft Zed upstream proposal](Zed-Upstream-Proposal.md)

[← Project README](../README.md)
