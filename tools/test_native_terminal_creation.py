#!/usr/bin/env python3
"""Exercise terminal creation through real Zed in a disposable project/profile."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from test_native_fixture import rpc


def rejects(socket, params, code, request_id=None):
    try:
        rpc(socket, "terminal.create", params, request_id)
    except RuntimeError as error:
        assert code in str(error), str(error)
    else:
        raise AssertionError(f"Expected {code}")


def main():
    root = Path(__file__).resolve().parents[1]
    binary = root / "zed-source/target/debug/zed"
    if not binary.is_file() or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise SystemExit("NOT RUN: patched Zed and graphical session required")
    with tempfile.TemporaryDirectory(prefix="zedlink-terminal-create-") as directory:
        fixture = Path(directory)
        project, profile, probe = [fixture / name for name in ("project", "profile", "probe")]
        project.mkdir(); (profile / "config").mkdir(parents=True); probe.mkdir(mode=0o700)
        settings = {"zedlink": {"allow_terminal_read": True, "allow_terminal_input": True, "allow_session_creation": True},
                    "terminal": {"shell": {"program": "/bin/bash", "args": ["--noprofile", "--norc"]}},
                    "session": {"trust_all_worktrees": True}}
        settings_path = profile / "config/settings.json"
        settings_path.write_text(json.dumps(settings))
        environment = {**os.environ, "ZED_RELEASE_CHANNEL": "dev", "ZEDLINK_PROBE_DIR": str(probe),
                       "ZEDLINK_PROBE_PROJECT_ROOT": str(project)}
        with (fixture / "zed.log").open("w") as log:
            process = subprocess.Popen([str(binary), "--user-data-dir", str(profile), str(project)],
                                       env=environment, stdout=log, stderr=log)
            try:
                socket = str(probe / "zedlink.sock")
                thread_request = str(uuid.uuid4())
                for _ in range(150):
                    try:
                        info = rpc(socket, "instance.info", {})
                        assert "terminal.create" in info["capabilities"], "Rebuild Zed with terminal.create first"
                        base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
                        thread = rpc(socket, "thread.create", {**base, "title": "Disposable terminal creation"}, thread_request)
                        if thread.get("thread_id"):
                            break
                    except (FileNotFoundError, ConnectionRefusedError, RuntimeError):
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("Disposable native thread did not become ready")
                params = {**base, "thread_id": thread["thread_id"]}
                assert rpc(socket, "terminal.list", base)["terminals"] == []
                rejects(socket, {**params, "thread_id": "not-exposed"}, "THREAD_NOT_EXPOSED")
                rejects(socket, {**params, "command": "not accepted"}, "INVALID_REQUEST")
                rejects(socket, {**params, "epoch": "stale"}, "INSTANCE_UNAVAILABLE")
                ids = []
                for _ in range(2):
                    request_id = str(uuid.uuid4())
                    for _ in range(100):
                        result = rpc(socket, "terminal.create", params, request_id)
                        if result["outcome"] == "ready":
                            break
                        assert result["outcome"] == "pending"
                        time.sleep(0.1)
                    else:
                        raise AssertionError("Terminal creation never completed")
                    terminal_id = result["terminal"]["terminal_id"]
                    ids.append(terminal_id)
                    assert rpc(socket, "terminal.create", params, request_id) == result
                    rejects(socket, {**params, "thread_id": "not-exposed"}, "THREAD_NOT_EXPOSED", request_id)
                    assert rpc(socket, "terminal.snapshot", {**base, "terminal_id": terminal_id})["terminal"]["terminal_id"] == terminal_id
                assert len(set(ids)) == 2
                assert {row["terminal_id"] for row in rpc(socket, "terminal.list", base)["terminals"]} == set(ids)
                second_id = str(uuid.uuid4())
                for _ in range(100):
                    other = rpc(socket, "thread.create", {**base, "title": "Second disposable session"}, second_id)
                    if other.get("thread_id"):
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("Second native thread did not become ready")
                rejects(socket, {**params, "thread_id": other["thread_id"]}, "REQUEST_ID_CONFLICT", request_id)
                settings["zedlink"]["allow_terminal_input"] = False
                settings_path.write_text(json.dumps(settings))
                for _ in range(100):
                    if "terminal.create" not in rpc(socket, "instance.info", {})["capabilities"]:
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("Creation permission revocation was not applied")
                rejects(socket, params, "UNSUPPORTED_CAPABILITY")
                print("PASS: empty workspace creation, two terminal identities/snapshots, replay, scope/parameter checks and permission revocation")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)


if __name__ == "__main__":
    main()
