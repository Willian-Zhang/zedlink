#!/usr/bin/env python3
"""Install or remove ZedLink entries in Zed's global tasks.json."""

import argparse
from datetime import datetime
import json
import os
from pathlib import Path
import tempfile


ROOT = Path(__file__).resolve().parent.parent
PREFIX = "ZedLink:"


def strip_jsonc(source: str) -> str:
    result = []
    index = 0
    in_string = False
    escaped = False
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
            result.append(char)
            index += 1
        elif char == "/" and following == "/":
            index += 2
            while index < len(source) and source[index] not in "\r\n":
                index += 1
        elif char == "/" and following == "*":
            end = source.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment in tasks file")
            index = end + 2
        else:
            result.append(char)
            index += 1
    cleaned = "".join(result)
    result = []
    index = 0
    in_string = False
    escaped = False
    while index < len(cleaned):
        char = cleaned[index]
        if in_string:
            result.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            index += 1
            continue
        if char == '"':
            in_string = True
        if char == ",":
            following = index + 1
            while following < len(cleaned) and cleaned[following].isspace():
                following += 1
            if following < len(cleaned) and cleaned[following] in "}]":
                index += 1
                continue
        result.append(char)
        index += 1
    return "".join(result)


def read_tasks(path: Path) -> list:
    if not path.exists():
        return []
    value = json.loads(strip_jsonc(path.read_text(encoding="utf-8")))
    if not isinstance(value, list) or not all(isinstance(item, dict) for item in value):
        raise ValueError("Zed tasks file must contain an array of task objects")
    return value


def zedlink_tasks() -> list:
    manager = str(ROOT / "tools/zedlink_manager.py")
    installer = str(ROOT / "tools/install_linux.sh")
    setup = str(ROOT / "tools/setup_zed_ide.sh")
    common = {
        "cwd": str(ROOT),
        "shell": {"program": "/bin/sh"},
        "use_new_terminal": True,
    }
    tasks = [
        {"label": "ZedLink: Set up this project", "command": "python3",
         "args": [manager, "quick-setup", "$ZED_WORKTREE_ROOT"], **common},
        {"label": "ZedLink: Guided setup / update", "command": "bash", "args": [setup], **common},
        {"label": "ZedLink: Rebuild patched Zed", "command": "bash", "args": [installer], **common},
    ]
    for label, action in (
        ("Configure", "configure"),
        ("Diagnose setup", "diagnose"),
        ("Repair setup", "repair"),
        ("Install patched Zed launcher", "install-launcher"),
        ("Start patched Zed", "start-zed"),
        ("Start gateway", "start-gateway"),
        ("Restart gateway", "restart-gateway"),
        ("Stop gateway", "stop-gateway"),
        ("Manage connections", "manage-routes"),
        ("Manage Zed targets", "manage-targets"),
        ("Check connections", "check-routes"),
        ("Pair a device", "pair"),
        ("Status", "status"),
        ("Paired devices", "devices"),
        ("Revoke device", "revoke"),
    ):
        task = {"label": f"ZedLink: {label}", "command": "python3",
                "args": [manager, action], **common}
        if action == "pair":
            task.update({
                "reveal": "never",
                "hide": "on_success",
                "show_summary": False,
                "show_command": False,
            })
        tasks.append(task)
    return tasks


def write_tasks(path: Path, tasks: list) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.exists():
        backup = path.with_name(path.name + ".zedlink-backup-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
        backup.write_bytes(path.read_bytes())
        os.chmod(backup, path.stat().st_mode & 0o777)
        print(f"Backup: {backup}")
    descriptor, temporary_name = tempfile.mkstemp(prefix="tasks-", suffix=".json", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(tasks, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def main() -> None:
    default = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config")) / "zed/tasks.json"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("install", "remove"))
    parser.add_argument("--tasks-file", type=Path, default=default)
    args = parser.parse_args()
    path = args.tasks_file.expanduser().resolve()
    tasks = read_tasks(path)
    retained = [task for task in tasks if not str(task.get("label", "")).startswith(PREFIX)]
    updated = retained + (zedlink_tasks() if args.operation == "install" else [])
    if updated == tasks:
        print(f"No changes needed: {path}")
        return
    write_tasks(path, updated)
    if args.operation == "install":
        print(f"Installed {len(updated) - len(retained)} ZedLink tasks in {path}")
    else:
        print(f"Removed {len(tasks) - len(retained)} ZedLink tasks from {path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, json.JSONDecodeError) as error:
        raise SystemExit(f"ZedLink task installer: {error}") from error
