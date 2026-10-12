# ZedLink interface walkthrough

[View or download the recording](zedlink-walkthrough.mp4).

A silent 32-second, captioned H.264 MP4 (1440 × 1000, 4 frames/second), captured from the production browser UI in a fresh Firefox profile with a disposable zedlink-demo project and loopback TLS gateway. Conversation and terminal output are synthetic demonstration data. The final Settings segment uses the actual patched-Zed Settings screenshot taken in a separate user-data profile and virtual display. It is a UI tour, not evidence of a live model or native mobile app round trip.

No footage is taken from the user's running Zed, urizen project, or physical desktop. The recording contains no OS branding, pairing codes, model credentials, or private routes.

## Regenerate locally

Follow the [screenshot capture instructions](../screenshots/README.md) to update the isolated native Settings image first. Then use Python with Pillow and imageio-ffmpeg installed:

```sh
cargo build --manifest-path gateway/Cargo.toml --offline
python3 tools/capture_readme_screenshots.py --record
```

The script records UI states while exercising local browser controls, adds captions and the demo-data notice, and writes the MP4 plus a poster. The native Settings segment is a held image. Temporary gateway state, certificates, project files, and browser profiles are removed after capture. No desktop screen-recording API is used.
