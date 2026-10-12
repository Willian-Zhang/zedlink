# Development and Testing

[← Wiki home](README.md)

## Build and test from a terminal

After building patched Zed, run `python3 tools/test_native_debugger.py` from a graphical Linux session to create an isolated project/profile and exercise saved debugger launch, DAP state, replay, pause, continue, stepping, restart, and stop. The script uses a deterministic local DAP fixture, removes its temporary files after success, and does not open or modify your normal Zed profile.

The IDE tasks call these same scripts:

```sh
# Build or update the pinned patched Zed and gateway
bash tools/install_linux.sh

# Install, configure, and add global IDE tasks
bash tools/setup_zed_ide.sh

# Run static checks and protocol tests
bash tools/check_linux.sh

# Run the synthetic HTTPS/WebSocket browser transport test
python3 tools/test_gateway_transport.py
```

The browser transport fixture does not prove native Zed integration. Native tests must use a disposable project, a real patched Zed process, and an explicitly exposed native Agent thread.

The patch is pinned to Zed revision:

```text
76659a55a8c10ed355a070f8764a0b1733e3c115
```

The stock extension API at that revision cannot enumerate or control an existing native Agent thread, which is why ZedLink requires the narrow, reviewable source patch under `patches/`.

### Zed upstream fork and contribution path

The nested checkout follows [`tjnull/zed:zedlink/native-agent-remote-control`](https://github.com/tjnull/zed/tree/zedlink/native-agent-remote-control), based on the exact pinned revision above. Its commits separate cancellation correctness, the opt-in local Agent bridge, native failure reporting, project and Git context, search, and native ZedLink settings. The fork is the checkout's `origin`; the official [`zed-industries/zed`](https://github.com/zed-industries/zed) repository is retained as `upstream` for revision comparison and future rebases.

Zed's contribution policy requires feature work of this size to start as a GitHub Discussion unless a staff-confirmed issue already exists. It also requires the human author to understand and review all AI-assisted code, manually test Zed, retain tests and evidence, sign the CLA, and write the maintainer communication. The checkout deliberately retains Zed's README review marker until that human review is complete. Do not remove it automatically.


## GitHub Actions budget

Android and macOS workflows run **only on manual dispatch**. Pushes do not launch hosted builds. Do not dispatch either workflow without the repository owner's approval while the Actions allowance is nearly exhausted. Use local Linux static checks, browser fixtures, and isolated native terminal checks by default. SwiftUI and Compose source changes that cannot be built locally must be labeled uncompiled, rather than silently running a cloud build.

Terminal icon fonts are bundled and self-hosted. Source, subset ranges, and upstream notices live in `gateway/web/fonts/`; copies of the notices accompany the native app resources.
