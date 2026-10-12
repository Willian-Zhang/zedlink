#!/usr/bin/env python3
"""Verify control keys against a terminal in a disposable patched Zed workspace."""

import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import uuid

from test_native_fixture import rpc


def main():
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("NOT RUN: a graphical session is required.")
    root = Path(__file__).resolve().parents[1]
    fixture = Path(tempfile.mkdtemp(prefix="zedlink-native-terminal-"))
    project, profile, probe = (fixture / name for name in ("project", "profile", "probe"))
    (project / ".zed").mkdir(parents=True)
    (profile / "config").mkdir(parents=True)
    probe.mkdir(mode=0o700)
    (project / "fixture.txt").write_text("Terminal completion fixture\n")
    (project / ".zed/tasks.json").write_text(json.dumps([{
        "label": "Terminal keyboard fixture", "command": "bash --noprofile --norc -i",
        "use_new_terminal": True, "env": {"PS1": "FIXTURE> "},
    }]))
    (profile / "config/settings.json").write_text(json.dumps({
        "zedlink": {"allow_terminal_read": True, "allow_terminal_input": True, "allow_task_start": True},
        "session": {"trust_all_worktrees": True},
    }))
    env = {**os.environ, "ZED_RELEASE_CHANNEL": "dev", "ZEDLINK_PROBE_DIR": str(probe),
           "ZEDLINK_PROBE_PROJECT_ROOT": str(project)}
    with (fixture / "zed.log").open("w") as log:
        process = subprocess.Popen([str(root / "zed-source/target/debug/zed"), "--user-data-dir", str(profile), str(project)],
                                   env=env, stdout=log, stderr=log)
        try:
            socket_path = str(probe / "zedlink.sock")
            for _ in range(150):
                try:
                    info = rpc(socket_path, "instance.info", {})
                    break
                except (FileNotFoundError, ConnectionRefusedError):
                    time.sleep(0.1)
            else:
                raise AssertionError("Isolated Zed bridge did not start")
            base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
            for _ in range(100):
                try:
                    tasks = rpc(socket_path, "task.catalog", base)["tasks"]
                except RuntimeError as error:
                    if "INSTANCE_UNAVAILABLE" not in str(error):
                        raise
                    info = rpc(socket_path, "instance.info", {})
                    base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
                    time.sleep(0.1)
                    continue
                if tasks:
                    break
                time.sleep(0.1)
            task = next(task for task in tasks if task["label"] == "Terminal keyboard fixture")
            rpc(socket_path, "task.run", {**base, "task_id": task["task_id"]})
            for _ in range(100):
                terminals = rpc(socket_path, "terminal.list", base)["terminals"]
                if terminals:
                    break
                time.sleep(0.1)
            terminal = terminals[0]["terminal_id"]
            params = {**base, "terminal_id": terminal}

            def wait_output(marker):
                for _ in range(100):
                    content = rpc(socket_path, "terminal.snapshot", params)["content"]
                    if marker in content:
                        return content
                    time.sleep(0.1)
                raise AssertionError(f"Terminal output did not contain fixture marker: {marker}; isolated output: {content!r}")

            def send(text, request_id=None):
                return rpc(socket_path, "terminal.input", {**params, "input": text}, request_id)

            time.sleep(0.5)
            send("printf 'CONTROL_%s\\n' OK\r")
            wait_output("CONTROL_OK")
            send("cat fi")
            send("\t")
            send("\r")
            wait_output("Terminal completion fixture")
            send("\x1b[A")
            send("\r")
            for _ in range(100):
                if rpc(socket_path, "terminal.snapshot", params)["content"].count("Terminal completion fixture") >= 2:
                    break
                time.sleep(0.1)
            else:
                raise AssertionError("Up arrow did not recall command history")
            send("sleep 30\r")
            time.sleep(0.3)
            send("\x03")
            send("printf 'INTERRUPT_%s\\n' OK\r")
            wait_output("INTERRUPT_OK")
            request_id = str(uuid.uuid4())
            first = send("printf 'ONCE_%s\\n' OK\r", request_id)
            replay = send("printf 'ONCE_%s\\n' OK\r", request_id)
            assert not first["duplicate"] and replay["duplicate"]
            assert wait_output("ONCE_OK").count("ONCE_OK") == 1
            send("printf '\\033[1;31mCOLOR_%s\\033[0m 📁 \uf07b e\u0301 界\\n' OK\r")
            wait_output("COLOR_OK")
            styled = rpc(socket_path, "terminal.snapshot", params)
            color_runs = [run for run in styled["styled_runs"] if "COLOR_OK" in run["text"]]
            assert color_runs and color_runs[0]["bold"] and color_runs[0]["foreground"].startswith("#"), color_runs
            styled_text = "".join(run["text"] for run in styled["styled_runs"])
            assert "📁" in styled_text and "\uf07b" in styled_text and "e\u0301" in styled_text and "界" in styled_text
            assert not styled["styles_truncated"]
            send("exit\r")
            print("PASS: real isolated Zed terminal Enter, Tab completion, history, Ctrl C, input replay, colors, wide Unicode and shell icons")
        finally:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
            shutil.rmtree(fixture)


if __name__ == "__main__":
    main()
