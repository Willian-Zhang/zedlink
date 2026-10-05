# iPhone client build

The native SwiftUI project specification is `ios/project.yml`. The verified hosted runner uses macOS 15, Xcode 16.4, and XcodeGen. The app targets iOS 17 or newer. The project deliberately has no model API or model credentials.

From the project root on a Mac with Xcode and XcodeGen:

```sh
cd ios
xcodegen generate
cd ..
xcodebuild -project ios/ZedLink.xcodeproj -scheme ZedLink \
  -configuration Debug -sdk iphonesimulator \
  -destination 'generic/platform=iOS Simulator' \
  -derivedDataPath /tmp/zedlink-derived CODE_SIGNING_ALLOWED=NO build
```

The same commands run in the manually triggered `.github/workflows/macos-smoke.yml` workflow in the private repository. It always checks the launch-screen declaration. Select the `simulator` input to boot an iPhone simulator, install and launch the app, run the first-use navigation XCTest, and save an empty-state screenshot artifact. The generated Xcode project is ignored; XcodeGen's checked-in specification is the source of truth. This build creates an unsigned simulator app. Installing on a physical iPhone requires the user's Apple signing identity, provisioning, and a separate real-device test; none is present in this repository or CI.

The current app saves Tailscale, WireGuard, other VPN, local, and custom HTTPS endpoint profiles. These categories describe routes supplied by existing OS VPN clients. System TLS validation and the expected gateway UUID are checked before pairing or authenticated RPC. The app accepts the 10-digit single-use code or the legacy 64-character code and stores the resulting device token in Keychain. On a supported iPhone, VisionKit can scan the workstation's QR to fill the HTTPS address and expected gateway UUID; the QR contains no pairing secret. A clipboard fallback is available when scanning is unavailable, including in the simulator. The app checks HTTPS and observed gateway identity before sending a code. The app lists exposed native threads, reads snapshots and polled events, and submits a stable-ID request. Unknown delivery stays unknown; a reconnect checks request status and never creates an automatic replacement send. The gateway currently refuses remote cancel and approval operations, so the app does not offer those controls yet. Native snapshots supply flat Markdown entries; the app recognizes the pinned Zed export's user/assistant prefixes for readable bubbles while keeping unknown entries neutral. Diff inspection is also unavailable. These are implementation limits, not completed product features. [Hosted run 37256229900](https://github.com/tjnull/zedlink/actions/runs/37256229900) built and launched the scanner/bubble edit on an iPhone simulator but its first-use UI test failed because a button below the form fold was not scrolled into view. The UI test has been updated; its rerun is pending. Physical scanner and native-app operation remain untested.

The private repository's `.git` history is currently managed from a reviewed publication copy because this workspace has an empty read-only `.git` mount. Clone `https://github.com/tjnull/zedlink` into a normal writable Git directory for ordinary branch and pull-request work.
