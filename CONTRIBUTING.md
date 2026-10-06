# Contributing to ZedLink

Thank you for helping improve ZedLink. The project is currently development software tied to a pinned Zed source revision.

## Before opening a change

1. Read [AGENTS.md](AGENTS.md), the [architecture and development guide](wiki/Development-and-Testing.md), and the [publishing status](wiki/Publishing-and-Upstream.md).
2. Open an issue for protocol changes, new remote powers, or changes to the trust boundary before implementation.
3. Keep model credentials and Agent execution inside Zed.
4. Use disposable projects and isolated Zed profiles for native integration tests.

## Build and test

```sh
bash tools/install_linux.sh
bash tools/check_linux.sh
python3 tools/test_gateway_transport.py
python3 tools/check_public_release.py
```

The browser fixture proves gateway behavior only. Changes to the native bridge also require a real patched Zed test with an explicitly exposed disposable Agent thread. Record commands and actual results without including transcripts, credentials, or private network details.

## Extension and Zed core changes

Do not add an `extension.toml` that claims to provide native-thread remote control. Stock Zed does not currently expose the required extension API, and Zed no longer accepts new slash-command or agent-server extension submissions.

Changes to `zed-source` belong on the maintained Zed fork branch and must follow Zed's contribution rules. Feature work of this size requires maintainer alignment, human review of AI-assisted code, focused tests, and the Zed CLA before an upstream pull request.

## Pull requests

- Keep changes focused and preserve unrelated user work.
- Explain the user-visible behavior, trust-boundary impact, tests run, and remaining limitations.
- Never commit certificates, keys, pairing material, device tokens, local state, personal paths, or private deployment addresses.
- Update the compatibility and validation documentation when native behavior changes.
