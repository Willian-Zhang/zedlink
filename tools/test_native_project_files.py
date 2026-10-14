#!/usr/bin/env python3
"""Real project listing/preview checks in an isolated patched Zed profile."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time
import uuid

from test_native_fixture import rpc


def main():
    root = Path(__file__).resolve().parents[1]
    binary = root / "zed-source/target/debug/zed"
    if not binary.is_file() or not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        raise SystemExit("NOT RUN: existing patched Zed and graphical session required")
    with tempfile.TemporaryDirectory(prefix="zedlink-project-files-") as directory:
        fixture = Path(directory)
        project, profile, probe = [fixture / name for name in ("project", "profile", "probe")]
        (project / "src").mkdir(parents=True)
        (profile / "config").mkdir(parents=True)
        probe.mkdir(mode=0o700)
        text = "# Disposable file\nUnicode: café ✓\n"
        (project / "src/readme.md").write_text(text)
        (project / "empty.txt").write_text("")
        (project / "data.bin").write_bytes(b"binary\0fixture")
        (project / "large.txt").write_text("x\n" * 140000)
        (project / ".private").write_text("fixture-only excluded")
        (fixture / "outside.txt").write_text("fixture-only outside root")
        (project / "escape.txt").symlink_to(fixture / "outside.txt")
        (profile / "config/settings.json").write_text(json.dumps({
            "zedlink": {"allow_project_context": True, "allow_session_creation": True}, "session": {"trust_all_worktrees": True},
        }))
        environment = {**os.environ, "ZED_RELEASE_CHANNEL": "dev", "ZEDLINK_PROBE_DIR": str(probe),
                       "ZEDLINK_PROBE_PROJECT_ROOT": str(project)}
        with (fixture / "zed.log").open("w") as log:
            process = subprocess.Popen([str(binary), "--user-data-dir", str(profile), str(project)],
                                       env=environment, stdout=log, stderr=log)
            try:
                socket = str(probe / "zedlink.sock")
                request_id = str(uuid.uuid4())
                for _ in range(150):
                    try:
                        info = rpc(socket, "instance.info", {})
                        base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
                        created = rpc(socket, "thread.create", {**base, "title": "Disposable files check"}, request_id)
                        if not created.get("thread_id"):
                            time.sleep(0.1)
                            continue
                        params = {**base, "thread_id": created["thread_id"]}
                        listing = rpc(socket, "project.directory", {**params, "path": "src"})
                        if any(entry["path"] == "src/readme.md" for entry in listing["entries"]):
                            break
                    except (FileNotFoundError, ConnectionRefusedError, RuntimeError):
                        pass
                    time.sleep(0.1)
                else:
                    raise AssertionError("Isolated Zed project did not become readable")
                assert listing["directory"] == "src"
                assert rpc(socket, "project.file", {**params, "path": "src/readme.md"})["content"] == text
                assert rpc(socket, "project.file", {**params, "path": "empty.txt"})["content"] == ""
                assert rpc(socket, "project.file", {**params, "path": "large.txt"})["truncated"]
                for path, code in [("data.bin", "UNSUPPORTED_FILE"), (".private", "INVALID_REQUEST"),
                                   ("escape.txt", "FILE_UNAVAILABLE"), ("../outside.txt", "INVALID_REQUEST")]:
                    try:
                        rpc(socket, "project.file", {**params, "path": path})
                    except RuntimeError as error:
                        assert code in str(error), (path, str(error))
                    else:
                        raise AssertionError("Unsafe/unsupported preview was accepted")
                try:
                    rpc(socket, "project.file", {**params, "thread_id": str(uuid.uuid4()), "path": "empty.txt"})
                except RuntimeError as error:
                    assert "THREAD_NOT_EXPOSED" in str(error), str(error)
                else:
                    raise AssertionError("Unexposed thread could read project files")
                settings = {"zedlink": {"allow_project_context": False, "allow_session_creation": True}, "session": {"trust_all_worktrees": True}}
                (profile / "config/settings.json").write_text(json.dumps(settings))
                for _ in range(100):
                    if "project.file" not in rpc(socket, "instance.info", {})["capabilities"]:
                        break
                    time.sleep(0.1)
                else:
                    raise AssertionError("File permission revocation did not become authoritative")
                try:
                    rpc(socket, "project.file", {**params, "path": "empty.txt"})
                except RuntimeError as error:
                    assert "UNSUPPORTED_CAPABILITY" in str(error), str(error)
                else:
                    raise AssertionError("Revoked file access still accepted")
                print("PASS: real isolated Zed folder/text previews, unsafe/binary rejection, unexposed thread and live permission revocation")
            finally:
                process.terminate()
                try:
                    process.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    process.kill(); process.wait(timeout=3)


if __name__ == "__main__":
    main()
