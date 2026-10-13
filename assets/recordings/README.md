# Product recording

The main README uses a GitHub-hosted attachment for inline playback. The [MP4](zedlink-in-action.mp4) in this directory is the reproducible source artifact.

https://github.com/user-attachments/assets/eb599434-e283-4828-a300-e5e77d1c93f4

## Sequence

1. Choose an exposed conversation.
2. Type a prompt and submit it through the browser.
3. Follow the native thread's streamed response.
4. Open Workspace, browse a folder, and read a source file.
5. Request tests, review the native approval, and allow the command.
6. Delegate a review to a native child agent and open its reader.
7. Revisit the completed child through Agent history.
8. Return to the main conversation.

The recording uses the production browser, HTTPS gateway and maintained native Zed bridge in a disposable **Orbit Notes** project and new profiles. The model is a scripted loopback demo provider: its wording and timing are controlled for the recording. The terminal command actually executes three Python unit tests in that disposable project. Child creation, streaming, approval and history use native Zed paths. This is not a recording of the owner's local GLM or a native iOS/Android app.

Only the isolated kiosk is captured. The owner's desktop, running Zed, urizen project, credentials and operating-system branding are excluded. Pairing is completed before recording so no pairing code appears. The footage is captured continuously at 60 fps, with pointer motion, click cues, readable pauses and chapter headings in a separate band above the application. No screenshot slideshow or playback speed-up is used.

## Design references

- [VHS](https://github.com/charmbracelet/vhs): scripted typing, deliberate pauses and reproducible recording sources.
- [Gum](https://github.com/charmbracelet/gum): visible user interaction and focused examples beside the relevant feature.
- [asciinema](https://github.com/asciinema/asciinema): readable playback, explicit recording steps and embedded presentation.

These informed the recording structure; no footage or graphics were copied.

## Regenerate locally

Requires the existing browser test dependencies, Xvfb, xdotool, Pillow and imageio-ffmpeg, plus rebuilt gateway and patched Zed binaries.

```sh
cargo build --manifest-path gateway/Cargo.toml --offline
RUSTUP_TOOLCHAIN=stable cargo build --manifest-path zed-source/Cargo.toml -p zed --offline
ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY=1 env -u WAYLAND_DISPLAY \
  xvfb-run -a -s '-screen 0 1280x800x24' \
  python3 tools/record_readme_demo.py
```

Outputs: `zedlink-in-action.mp4`, `walkthrough-poster.png`, `chapters.json` and `native-demo-evidence.json`. Temporary project files, TLS certificates, model service, gateway state and native/browser profiles are cleaned up. No hosted CI is required. The provenance file contains assertions about this disposable run; it does not stand in for release/device validation.
