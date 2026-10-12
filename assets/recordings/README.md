# ZedLink walkthrough recording

The main README uses a GitHub-hosted attachment for inline playback. The [repository MP4](zedlink-walkthrough.mp4) remains the reproducible source artifact.

https://github.com/user-attachments/assets/b188b55f-f55f-4d20-813a-5b956c1d6eff

Continuous, silent H.264 footage at 1440 × 900 and 30 frames/second shows browser controls being clicked, prompts being typed, thinking and response updates, directory navigation, syntax-highlighted file contents, changes, and terminal input/output. Pointer movement and click rings make the interactions visible. There are no caption overlays or held screenshots.

The production browser UI runs in a fresh Firefox profile against a disposable zedlink-demo project and loopback TLS gateway. Conversation streaming and terminal results are synthetic fixture data, including the displayed test results. This recording demonstrates presentation and controls; it is not evidence of a live model, real command execution, or a native mobile round trip.

No footage is taken from the user's running Zed, urizen project, or physical desktop. The recording contains no OS branding, pairing codes, model credentials, or private routes.

## Regenerate locally

Use the dependencies listed in the [screenshot capture instructions](../screenshots/README.md), plus imageio-ffmpeg and Xvfb. Build the gateway locally, then record only a separate virtual display:

```sh
cargo build --manifest-path gateway/Cargo.toml --offline
ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY=1 env -u WAYLAND_DISPLAY \
  xvfb-run -a -s '-screen 0 1440x900x24' \
  python3 tools/capture_readme_screenshots.py --record
```

The script records the isolated browser continuously and writes the MP4 plus a poster. Temporary gateway state, certificates, project files, and browser profiles are removed after capture. It does not capture the active desktop or start the user's Zed. No hosted CI is required.
