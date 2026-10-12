# Screenshot provenance

These images document the interface, not release certification. No screenshots use the owner's running Zed instance, urizen project, model credentials, or conversations.

## Browser captures

`desktop-conversation.png`, `mobile-conversation.png`, `mobile-terminal.png`, `file-browser.png`, and `no-sessions.png` were captured from browser build **2026.10.12.13** on October 12, 2026.

The capture script creates a disposable `zedlink-demo` project, temporary gateway state, a loopback TLS certificate, and a new Selenium Firefox profile. It renders the production HTML/CSS/JavaScript against synthetic protocol responses. Conversation text and terminal output are demo data, not results from an actual model or shell execution. Mobile images use a narrow desktop Firefox viewport; they are not physical iPhone captures or native SwiftUI/Compose screenshots.

Regenerate locally after building the gateway:

```sh
cargo build --manifest-path gateway/Cargo.toml --offline
python3 tools/capture_readme_screenshots.py
```

Dependencies match the [browser test setup](../../wiki/Development-and-Testing.md): Firefox, geckodriver, Selenium, Python websockets, and OpenSSL.

## Native Settings capture

`zed-settings.png` shows the actual Settings UI of the patched Zed build in a **new user-data profile** with a disposable `zedlink-demo` project. A separate Xvfb display prevents capturing the user's current desktop. Bridge startup and gateway auto-start are disabled; no existing devices or connections are loaded.

```sh
env -u WAYLAND_DISPLAY ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY=1 \
  xvfb-run -a -s '-screen 0 1280x960x24' \
  python3 tools/capture_readme_screenshots.py --native-settings
```

Requires the locally built patched Zed binary, Xvfb, xdotool, and ImageMagick `import`. All temporary profiles and projects are removed when capture completes. Screenshots are inspected before use.

`code-review.png` is an older synthetic UI capture retained for documentation compatibility; the current README uses `file-browser.png` instead.
