#!/usr/bin/env python3
"""Exercise configured debugger launch and controls through a real patched Zed."""

import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import uuid


def read_dap_message():
    headers = {}
    while True:
        line = sys.stdin.buffer.readline()
        if not line:
            return None
        if line in (b"\r\n", b"\n"):
            break
        key, value = line.decode("ascii").split(":", 1)
        headers[key.lower()] = value.strip()
    return json.loads(sys.stdin.buffer.read(int(headers["content-length"])))


def run_adapter():
    fixture = Path(os.environ["ZEDLINK_DAP_FIXTURE_DIR"])
    log_path = fixture / "dap-commands.log"
    sequence = 1

    def send(message):
        nonlocal sequence
        message["seq"] = sequence
        sequence += 1
        body = json.dumps(message, separators=(",", ":")).encode()
        sys.stdout.buffer.write(f"Content-Length: {len(body)}\r\n\r\n".encode() + body)
        sys.stdout.buffer.flush()

    def response(request, body=None):
        send({"type": "response", "request_seq": request["seq"], "success": True,
              "command": request["command"], "body": body or {}})

    def event(name, body=None):
        send({"type": "event", "event": name, "body": body or {}})

    with log_path.open("a", encoding="utf-8") as log:
        while request := read_dap_message():
            command = request.get("command", "")
            log.write(command + "\n")
            log.flush()
            if command == "initialize":
                response(request, {"supportsConfigurationDoneRequest": True,
                                   "supportsRestartRequest": True,
                                   "supportsStepBack": True,
                                   "supportsTerminateRequest": True,
                                   "supportsSingleThreadExecutionRequests": True})
                event("initialized")
            elif command in ("launch", "setBreakpoints", "setFunctionBreakpoints",
                             "setExceptionBreakpoints", "configurationDone"):
                response(request)
                if command == "configurationDone":
                    event("process", {"name": "ZedLink DAP fixture", "systemProcessId": 4242,
                                      "isLocalProcess": True, "startMethod": "launch"})
                    event("thread", {"reason": "started", "threadId": 1})
                    event("stopped", {"reason": "entry", "threadId": 1, "allThreadsStopped": True})
            elif command == "threads":
                response(request, {"threads": [{"id": 1, "name": "fixture-main"}]})
            elif command == "stackTrace":
                response(request, {"stackFrames": [{"id": 10, "name": "fixture_main", "line": 1,
                          "column": 1, "source": {"name": "fixture.c",
                          "path": str(fixture / "project" / "fixture.c")}}], "totalFrames": 1})
            elif command == "scopes":
                response(request, {"scopes": []})
            elif command == "continue":
                response(request, {"allThreadsContinued": True})
                event("continued", {"threadId": 1, "allThreadsContinued": True})
            elif command == "pause":
                response(request)
                event("stopped", {"reason": "pause", "threadId": 1, "allThreadsStopped": True})
            elif command in ("next", "stepIn", "stepOut", "stepBack"):
                response(request)
                event("continued", {"threadId": 1, "allThreadsContinued": True})
                event("stopped", {"reason": "step", "threadId": 1, "allThreadsStopped": True})
            elif command == "restart":
                response(request)
                event("stopped", {"reason": "restart", "threadId": 1, "allThreadsStopped": True})
            elif command in ("disconnect", "terminate"):
                response(request)
                event("terminated")
                return
            else:
                response(request)


def rpc(socket_path, method, params, request_id=None):
    request_id = request_id or str(uuid.uuid4())
    request = {"version": 1, "request_id": request_id, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as stream:
        stream.settimeout(8)
        stream.connect(socket_path)
        stream.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        response = json.loads(stream.makefile("rb").readline())
    assert response["request_id"] == request_id, response
    return response


def run_test(binary, keep):
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("A graphical session is required to launch patched Zed.")
    fixture = Path(tempfile.mkdtemp(prefix="zedlink-native-debugger-"))
    project = fixture / "project"
    profile = fixture / "profile"
    probe = fixture / "probe"
    (project / ".zed").mkdir(parents=True)
    (profile / "config").mkdir(parents=True)
    probe.mkdir(mode=0o700)
    script = Path(__file__).resolve()
    (project / "fixture.c").write_text("int main(void) { return 0; }\n", encoding="utf-8")
    program = project / "fixture-program"
    program.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    program.chmod(0o700)
    (project / ".zed" / "debug.json").write_text(json.dumps([{
        "adapter": "GDB", "label": "ZedLink DAP fixture", "request": "launch",
        "program": str(program), "gdb_path": str(script), "stopOnEntry": True,
    }], indent=2) + "\n", encoding="utf-8")
    (profile / "config" / "settings.json").write_text(json.dumps({
        "zedlink": {"allow_debugger_read": True, "allow_debugger_start": True,
                    "allow_debugger_control": True},
        "session": {"trust_all_worktrees": True},
    }, indent=2) + "\n", encoding="utf-8")
    environment = os.environ.copy()
    environment.update({"ZED_RELEASE_CHANNEL": "dev", "ZEDLINK_PROBE_DIR": str(probe),
                        "ZEDLINK_PROBE_PROJECT_ROOT": str(project),
                        "ZEDLINK_DAP_FIXTURE_DIR": str(fixture)})
    process = subprocess.Popen([str(binary), "--user-data-dir", str(profile), str(project)], env=environment)
    socket_path = str(probe / "zedlink.sock")
    try:
        for _ in range(120):
            try:
                info = rpc(socket_path, "instance.info", {})["result"]
                break
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.1)
        else:
            raise AssertionError("native probe socket unavailable")
        base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
        assert {"debugger.catalog", "debugger.launch", "debugger.snapshot", "debugger.control"} <= set(info["capabilities"])
        for _ in range(100):
            response = rpc(socket_path, "debugger.catalog", base)
            if response.get("error", {}).get("code") == "INSTANCE_UNAVAILABLE":
                # Startup may replace the provisional identity before the workspace opens.
                # Refresh only here, before any debugger mutation has been submitted.
                info = rpc(socket_path, "instance.info", {})["result"]
                base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
                time.sleep(0.1)
                continue
            assert "result" in response, response
            catalog = response["result"]["scenarios"]
            if len(catalog) == 1:
                break
            time.sleep(0.1)
        assert catalog[0]["label"] == "ZedLink DAP fixture", catalog
        launch = {**base, "scenario_id": catalog[0]["scenario_id"]}
        first = rpc(socket_path, "debugger.launch", launch, "debug-launch")
        replay = rpc(socket_path, "debugger.launch", launch, "debug-launch")
        assert not first["result"]["duplicate"] and replay["result"]["duplicate"]
        injected = rpc(socket_path, "debugger.launch", {**launch, "program": "/tmp/never"}, "debug-injected")
        assert injected["error"]["code"] == "INVALID_REQUEST", injected

        def session_in(state):
            latest = None
            for _ in range(100):
                latest = rpc(socket_path, "debugger.snapshot", base)["result"]
                if latest["sessions"] and any(t["status"] == state for t in latest["sessions"][0]["threads"]):
                    return latest["sessions"][0]
                time.sleep(0.1)
            raise AssertionError(f"debugger never reached {state}: {latest}")

        session = session_in("stopped")
        session_id = session["session_id"]
        thread_id = session["threads"][0]["thread_id"]
        control = {**base, "session_id": session_id, "thread_id": thread_id}
        invalid = rpc(socket_path, "debugger.control", {**control, "action": "pause"})
        assert invalid["error"]["code"] == "DEBUGGER_STATE_CONFLICT", invalid
        continued = rpc(socket_path, "debugger.control", {**control, "action": "continue"}, "debug-continue")
        continued_replay = rpc(socket_path, "debugger.control", {**control, "action": "continue"}, "debug-continue")
        assert not continued["result"]["duplicate"] and continued_replay["result"]["duplicate"]
        session_in("running")
        rpc(socket_path, "debugger.control", {**control, "action": "pause"})
        session_in("stopped")
        for action in ("step_over", "step_in", "step_out", "step_back"):
            rpc(socket_path, "debugger.control", {**control, "action": action})
            session_in("stopped")
        rpc(socket_path, "debugger.control", {**base, "session_id": session_id, "action": "restart"})
        session_in("stopped")
        rpc(socket_path, "debugger.control", {**base, "session_id": session_id, "action": "stop"})
        commands = (fixture / "dap-commands.log").read_text(encoding="utf-8").splitlines()
        expected = {"initialize", "launch", "configurationDone", "continue", "pause", "next",
                    "stepIn", "stepOut", "stepBack", "restart", "terminate"}
        assert expected <= set(commands), commands
        print(json.dumps({"result": "PASS", "scenario": catalog[0]["label"],
                          "session_id": session_id, "thread_id": thread_id,
                          "commands": commands, "fixture": str(fixture) if keep else "removed"}))
    finally:
        process.terminate()
        try:
            process.wait(timeout=8)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=3)
        if not keep:
            shutil.rmtree(fixture, ignore_errors=True)


def main():
    if "-i=dap" in sys.argv:
        run_adapter()
        return
    parser = argparse.ArgumentParser()
    default_binary = Path(__file__).resolve().parents[1] / "zed-source" / "target" / "debug" / "zed"
    parser.add_argument("--zed", type=Path, default=default_binary)
    parser.add_argument("--keep", action="store_true")
    args = parser.parse_args()
    if not args.zed.is_file():
        raise SystemExit(f"Patched Zed binary not found: {args.zed}")
    run_test(args.zed.resolve(), args.keep)


if __name__ == "__main__":
    main()
