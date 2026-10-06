#!/usr/bin/env python3
"""Reject common private-machine artifacts before publishing ZedLink.

This scans the working tree, not Git history. It intentionally does not inspect
ignored local Zed source, build outputs, or internal validation documents.
"""

from __future__ import annotations

import re
import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKIP_PARTS = {".git", ".agents", ".aws", ".codex", "docs", "target", "zed-source", "__pycache__"}
SKIP_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".pyc", ".lock"}
PATTERNS = {
    "private key": re.compile(r"BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY"),
    "local user path": re.compile(r"/home/(?!you(?:/|\b))[A-Za-z0-9._-]+(?:/|\b)"),
    "private tailnet hostname": re.compile(
        r"\b(?!computer\.example-tailnet\.ts\.net\b)[a-z0-9-]+\.tail[0-9a-z.-]*\.ts\.net\b",
        re.I,
    ),
    "private Tailscale address": re.compile(
        r"\b100\.(?!64\.(?:10\.20|0\.0)\b)(?:6[4-9]|[789][0-9]|1[01][0-9]|12[0-7])\.\d{1,3}\.\d{1,3}\b"
    ),
    "persisted gateway identity": re.compile(
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}\b",
        re.I,
    ),
}


def files():
    for directory, names, filenames in os.walk(ROOT):
        names[:] = [name for name in names if name not in SKIP_PARTS]
        for filename in filenames:
            path = Path(directory, filename)
            relative = path.relative_to(ROOT)
            if path == Path(__file__).resolve() or path.suffix.lower() in SKIP_SUFFIXES:
                continue
            yield path, relative


def main() -> int:
    failures: list[str] = []
    for path, relative in files():
        try:
            content = path.read_text(errors="strict")
        except (UnicodeDecodeError, OSError):
            continue
        for label, pattern in PATTERNS.items():
            for match in pattern.finditer(content):
                line = content.count("\n", 0, match.start()) + 1
                failures.append(f"{relative}:{line}: {label}")

    for required in ("README.md", "AGENTS.md", "wiki/Publishing-and-Upstream.md"):
        if not (ROOT / required).is_file():
            failures.append(f"{required}: required public documentation is missing")

    license_present = any((ROOT / name).is_file() for name in ("LICENSE", "LICENSE.md", "LICENSE.txt"))
    if not license_present:
        failures.append("LICENSE: choose and commit an open-source license before making the repository public")

    if failures:
        print("Public release check failed:")
        for failure in failures:
            print(f"  - {failure}")
        print("This check covers the working tree only; review Git history separately.")
        return 1

    print("PASS: public working-tree checks. Review Git history and release evidence separately.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
