#!/usr/bin/env python3
"""Wrap the optimized patched Zed in ~/Applications/ZedLink.app (macOS only).

Rerun after every rebuild: the app holds a copy of the binary. The bundle uses
its own identifier and registers no URL schemes or document types, so it never
takes zed:// links or file associations from the official Zed.
"""

import os
from pathlib import Path
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "zed-source"
BINARY = SOURCE / "target/release/zed"
APP = Path.home() / "Applications/ZedLink.app"
MARKER = "zedlink-managed"
IDENTIFIER = "dev.zedlink.Zed"
# Apps opened from Finder or the Dock get launchd's minimal PATH; the ZedLink
# manager needs Homebrew's python3 (the system 3.9 can't run it).
PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def version() -> str:
    text = (SOURCE / "crates/zed/Cargo.toml").read_text(encoding="utf-8")
    return re.search(r'^version = "([^"]+)"', text, re.M).group(1)


def usage_descriptions() -> dict:
    # Zed's bundle declares these so programs run inside its terminal can ask for
    # camera, microphone, etc. instead of being silently denied.
    raw = (SOURCE / "crates/zed/resources/info/Permissions.plist").read_text(encoding="utf-8")
    return plistlib.loads(f'<plist version="1.0"><dict>{raw}</dict></plist>'.encode())


def make_icon(resources: Path) -> None:
    icons = SOURCE / "crates/zed/resources"
    with tempfile.TemporaryDirectory() as temporary:
        iconset = Path(temporary) / "ZedLink.iconset"
        iconset.mkdir()
        for size in (16, 32, 128, 256, 512):
            for scale in (1, 2):
                pixels = size * scale
                name = f"icon_{size}x{size}{'@2x' if scale == 2 else ''}.png"
                subprocess.run(["sips", "-z", str(pixels), str(pixels),
                                str(icons / "app-icon-nightly@2x.png"), "--out", str(iconset / name)],
                               check=True, capture_output=True)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(resources / "ZedLink.icns")],
                       check=True)


def build(bundle: Path) -> None:
    contents = bundle / "Contents"
    (contents / "MacOS").mkdir(parents=True)
    (contents / "Resources").mkdir()
    shutil.copy2(BINARY, contents / "MacOS/zed")
    make_icon(contents / "Resources")
    (contents / "Resources" / MARKER).write_text("Managed by tools/install_macos_app.py\n")
    info = {
        "CFBundleName": "ZedLink",
        "CFBundleDisplayName": "ZedLink",
        "CFBundleExecutable": "zed",
        "CFBundleIdentifier": IDENTIFIER,
        "CFBundleIconFile": "ZedLink",
        "CFBundlePackageType": "APPL",
        "CFBundleShortVersionString": version(),
        "CFBundleVersion": version(),
        "CFBundleInfoDictionaryVersion": "6.0",
        "LSMinimumSystemVersion": "10.15.7",
        "LSApplicationCategoryType": "public.app-category.developer-tools",
        "NSHighResolutionCapable": True,
        "LSEnvironment": {
            "PATH": PATH,
            # Disables Zed's updater entirely, in addition to auto_update=false in the
            # "nightly" settings block, so this build is never replaced by official Nightly.
            "ZED_UPDATE_EXPLANATION": "This is the patched ZedLink build. Rebuild it from ~/Github/run/zed to update.",
        },
        **usage_descriptions(),
    }
    (contents / "Info.plist").write_bytes(plistlib.dumps(info))
    subprocess.run(["codesign", "--force", "--sign", "-", str(bundle)], check=True,
                   capture_output=True)


def main() -> None:
    if sys.platform != "darwin":
        raise SystemExit("install_macos_app.py only runs on macOS")
    if not BINARY.is_file():
        raise SystemExit(f"build the optimized patched Zed first: {BINARY}")
    if APP.exists() and not (APP / "Contents/Resources" / MARKER).is_file():
        raise SystemExit(f"refusing to replace an app not managed by ZedLink: {APP}")
    running = subprocess.run(["pgrep", "-f", str(APP / "Contents/MacOS/zed")],
                             capture_output=True).returncode == 0
    if running:
        raise SystemExit("quit ZedLink before reinstalling it")
    APP.parent.mkdir(exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=".ZedLink-", dir=APP.parent)) / "ZedLink.app"
    try:
        build(staging)
        if APP.exists():
            shutil.rmtree(APP)
        staging.rename(APP)
    finally:
        shutil.rmtree(staging.parent, ignore_errors=True)
    lsregister = ("/System/Library/Frameworks/CoreServices.framework/Frameworks/"
                  "LaunchServices.framework/Support/lsregister")
    subprocess.run([lsregister, "-f", str(APP)], check=False)
    print(f"Installed {APP} ({version()})")


if __name__ == "__main__":
    main()
