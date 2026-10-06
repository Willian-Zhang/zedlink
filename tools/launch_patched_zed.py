#!/usr/bin/env python3
"""Detach patched Zed from a Linux desktop launcher and preserve startup errors."""

import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import zedlink_manager as manager


def main() -> None:
    data = manager.validate(manager.read_config())
    state = Path(data["state_dir"])
    manager.private_directory(state)
    log_path = state / "patched-zed-launcher.log"
    descriptor = os.open(log_path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    with os.fdopen(descriptor, "a", encoding="utf-8") as log:
        log.write(f"\nStarting ZedLink patched Zed at {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
        log.flush()
        process = subprocess.Popen(
            [sys.executable, str(manager.ROOT / "tools/zedlink_manager.py"), "start-zed"],
            cwd=manager.ROOT,
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            start_new_session=True,
            close_fds=True,
        )
        time.sleep(1)
        result = process.poll()
    if result not in (None, 0):
        notifier = shutil.which("notify-send")
        if notifier:
            subprocess.run(
                [notifier, "ZedLink could not start patched Zed", f"See {log_path}"],
                check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        raise RuntimeError(f"patched Zed exited during startup; see {log_path}")


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError) as error:
        raise SystemExit(f"ZedLink launcher: {error}") from error
