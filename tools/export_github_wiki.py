#!/usr/bin/env python3
"""Export the tracked wiki sources into GitHub Wiki repository format."""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "wiki"
SCREENSHOTS = ROOT / "assets" / "screenshots"
REPOSITORY_BLOB = "https://github.com/tjnull/zedlink/blob/main"
IMAGE_SUFFIXES = {".gif", ".jpeg", ".jpg", ".png", ".webp"}


def rewrite(markdown: str) -> str:
    markdown = markdown.replace("(README.md", "(Home.md")
    markdown = markdown.replace(
        "../assets/screenshots/README.md",
        f"{REPOSITORY_BLOB}/assets/screenshots/README.md",
    )
    markdown = markdown.replace("../assets/screenshots/", "images/")

    def main_repository_link(match: re.Match[str]) -> str:
        suffix = match.group(1)
        return f"({REPOSITORY_BLOB}/{suffix})"

    return re.sub(
        r"\(\.\./(AGENTS\.md|CONTRIBUTING\.md|LICENSE|README\.md|SECURITY\.md)\)",
        main_repository_link,
        markdown,
    )


def export(destination: Path) -> None:
    if destination.exists() and any(destination.iterdir()):
        raise SystemExit(f"destination must be empty: {destination}")
    destination.mkdir(parents=True, exist_ok=True)

    for source in sorted(SOURCE.glob("*.md")):
        target_name = "Home.md" if source.name == "README.md" else source.name
        (destination / target_name).write_text(rewrite(source.read_text()))

    image_destination = destination / "images"
    image_destination.mkdir()
    for source in sorted(SCREENSHOTS.iterdir()):
        if source.is_file() and source.suffix.lower() in IMAGE_SUFFIXES:
            shutil.copy2(source, image_destination / source.name)

    (destination / "_Footer.md").write_text(
        "[Project source](https://github.com/tjnull/zedlink) · "
        "[Security policy](https://github.com/tjnull/zedlink/security/policy) · "
        "[Report an issue](https://github.com/tjnull/zedlink/issues)\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path, help="empty export directory")
    args = parser.parse_args()
    export(args.destination.resolve())
    print(f"Exported GitHub Wiki pages to {args.destination.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
