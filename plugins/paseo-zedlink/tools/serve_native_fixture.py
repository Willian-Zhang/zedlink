#!/usr/bin/env python3
"""Serve a disposable real Zed thread through Paseo for an iPhone Tailscale test.

Uses a deterministic loopback model, isolated Zed profile/project, isolated TLS
gateway and a preconfigured password-protected Paseo home. Never changes the
normal ZedLink gateway or a real project. Ctrl-C stops all fixture services.
"""

import argparse
import json
import os
import socket
import ssl
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import uuid
from http.server import ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "tools"))
import deterministic_model_fixture as model  # noqa: E402
from test_native_fixture import rpc  # noqa: E402
from test_native_agent_smoke import until  # noqa: E402


def cli(binary, home, env, *args):
    result = subprocess.run([str(binary), *args, "--home", str(home), "--json"],
                            env=env, capture_output=True, text=True, timeout=45)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Paseo {args[0]} returned invalid JSON (exit {result.returncode})") from error
    if result.returncode:
        raise RuntimeError(f"Paseo {args[0]} failed: {value.get('error', {}).get('message', 'unknown error')}")
    return value


def free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def stop(process):
    if process is None or process.poll() is not None:
        return
    process.terminate()
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True)
    parser.add_argument("--home", type=Path, required=True,
                        help="preconfigured disposable Paseo home; the daemon must be stopped")
    parser.add_argument("--password-file", type=Path, required=True)
    args = parser.parse_args()
    binary = args.cli.resolve(strict=True)
    home = args.home.resolve(strict=True)
    password_file = args.password_file.resolve(strict=True)
    if password_file.stat().st_mode & 0o077:
        raise RuntimeError("Paseo password file must be private")
    env = os.environ.copy()
    env["PASEO_PASSWORD"] = password_file.read_text().strip()
    if not env["PASEO_PASSWORD"]:
        raise RuntimeError("Paseo password file is empty")
    config = cli(binary, home, env, "daemon", "config", "get", "pluginsEnabled")
    status = cli(binary, home, env, "daemon", "status")
    listen = status.get("configuredListen", "")
    if config.get("value") is not True or status.get("localDaemon") != "stopped":
        raise RuntimeError("Require a stopped disposable Paseo daemon with plugins enabled")
    if not listen.startswith("100.") or listen.startswith("100.0.0.0:"):
        raise RuntimeError("This fixture requires Paseo bound to a specific Tailscale IPv4 address")
    if not (ROOT / "zed-source/target/debug/zed").is_file() or not (ROOT / "gateway/target/debug/zedlink-gateway").is_file():
        raise RuntimeError("Existing patched Zed and gateway binaries are required")

    zed = gateway = display = None
    daemon_started = False
    agent_id = None
    server = None
    log = gateway_log = None
    with tempfile.TemporaryDirectory(prefix="native-phone-", dir=home) as temporary:
        work = Path(temporary)
        project, profile, probe, state = (work / name for name in ("project", "profile", "probe", "gateway-state"))
        project.mkdir()
        (project / "README.md").write_text("# Disposable Paseo native thread fixture\n")
        (profile / "config").mkdir(parents=True)
        probe.mkdir(mode=0o700)
        state.mkdir(mode=0o700)
        model.FIXTURE_ROOT = project
        server = ThreadingHTTPServer(("127.0.0.1", 0), model.Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        settings = {
            "zedlink": {"allow_session_creation": True, "allow_approval_decisions": True,
                        "start_gateway_on_launch": False},
            "telemetry": {"metrics": False, "diagnostics": False},
            "session": {"trust_all_worktrees": True},
            "agent": {"enable_feedback": False,
                      "default_model": {"provider": "openai", "model": "zedlink-fixture"},
                      "default_profile": "write",
                      "tool_permissions": {"tools": {"terminal": {"default": "confirm"}}}},
            "language_models": {"openai": {"api_url": f"http://127.0.0.1:{server.server_port}/v1",
                "available_models": [{"name": "zedlink-fixture", "max_tokens": 131072,
                                      "max_output_tokens": 2048,
                                      "capabilities": {"chat_completions": True, "images": False}}]}},
        }
        (profile / "config/settings.json").write_text(json.dumps(settings))
        try:
            display = subprocess.Popen(["Xvfb", "-displayfd", "1", "-screen", "0", "1280x800x24", "-nolisten", "tcp"],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
            display_number = display.stdout.readline().strip()
            if not display_number.isdigit():
                raise RuntimeError("Xvfb did not start")
            zed_env = {key: value for key, value in env.items()
                       if not key.startswith("ZEDLINK_") and key not in ("WAYLAND_DISPLAY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "PASEO_PASSWORD")}
            zed_env.update(DISPLAY=f":{display_number}", ZED_RELEASE_CHANNEL="dev", ZED_ALLOW_EMULATED_GPU="1",
                           OPENAI_API_KEY="disposable-fixture", ZEDLINK_PROBE_DIR=str(probe),
                           ZEDLINK_PROBE_PROJECT_ROOT=str(project))
            log = (work / "zed.log").open("w")
            zed = subprocess.Popen([str(ROOT / "zed-source/target/debug/zed"), "--user-data-dir", str(profile), str(project)],
                                   cwd=ROOT / "zed-source", env=zed_env, stdout=log, stderr=log)
            socket_path = str(probe / "zedlink.sock")
            until(lambda: Path(socket_path).exists(), timeout=45)
            info = rpc(socket_path, "instance.info", {})
            base = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
            create_id = str(uuid.uuid4())

            def create():
                nonlocal base
                try:
                    result = rpc(socket_path, "thread.create", {**base, "title": "Disposable Paseo iPhone check"}, create_id)
                except RuntimeError as error:
                    if "INSTANCE_UNAVAILABLE" not in str(error):
                        raise
                    current = rpc(socket_path, "instance.info", {})
                    base = {"instance_id": current["instance_id"], "epoch": current["epoch"]}
                    return None
                return result.get("thread_id")

            thread_id = until(create, timeout=45)
            listing = rpc(socket_path, "thread.list", {})
            if len(listing["threads"]) != 1 or listing["threads"][0]["thread_id"] != thread_id:
                raise RuntimeError("Native fixture did not expose exactly one created thread")

            cert, key = work / "cert.pem", work / "key.pem"
            subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                            "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
                            "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            key.chmod(0o600)
            gateway_port = free_port()
            gateway_log = (work / "gateway.log").open("w")
            gateway_binary = ROOT / "gateway/target/debug/zedlink-gateway"
            gateway = subprocess.Popen([str(gateway_binary), "serve", f"127.0.0.1:{gateway_port}",
                                        str(cert), str(key), socket_path, str(state)],
                                       stdout=gateway_log, stderr=gateway_log)
            until(lambda: (state / "admin.sock").exists(), timeout=15)
            base_url = f"https://localhost:{gateway_port}"
            opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                urllib.request.HTTPSHandler(context=ssl.create_default_context(cafile=str(cert))))

            def http(path, payload=None):
                request = urllib.request.Request(base_url + path,
                    data=json.dumps(payload).encode() if payload is not None else None,
                    headers={"Content-Type": "application/json"}, method="POST" if payload is not None else "GET")
                with opener.open(request, timeout=8) as response:
                    return json.load(response)

            identity = http("/v1/gateway")["gateway_id"]
            code_result = subprocess.run([str(gateway_binary), "admin", str(state), "pair-code"],
                                         check=True, capture_output=True, text=True, timeout=8)
            code = json.loads(code_result.stdout)["code"]
            paired = http("/v1/pair", {"code": code, "device_name": "Paseo isolated native fixture"})
            if paired.get("gateway_id") != identity:
                raise RuntimeError("Gateway pairing identity mismatch")
            credential = work / "device.json"
            with os.fdopen(os.open(credential, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as output:
                json.dump(paired, output)
            env.update(ZEDLINK_PASEO_URL=base_url, ZEDLINK_PASEO_TARGET_ID="default",
                       ZEDLINK_PASEO_CREDENTIAL_FILE=str(credential), ZEDLINK_PASEO_CA_FILE=str(cert))
            cli(binary, home, env, "daemon", "start")
            daemon_started = True
            # A killed earlier fixture may leave a named workspace whose
            # temporary project is already gone. Remove only those stale
            # workspaces from this disposable Paseo home.
            for row in cli(binary, home, env, "workspace", "ls"):
                cwd = Path(row.get("cwd", ""))
                if (row.get("name") == "ZedLink phone fixture" and
                    cwd.parent.parent == home and cwd.parent.name.startswith("native-phone-") and
                    not cwd.exists()):
                    cli(binary, home, env, "workspace", "archive", row["workspaceId"])
            plugins = cli(binary, home, env, "plugin", "ls")
            if not any(row.get("id") == "zedlink" and row.get("status") == "running" for row in plugins):
                raise RuntimeError("ZedLink plugin did not start")
            models = cli(binary, home, env, "provider", "models", "zedlink")
            if len(models) != 1 or not models[0]["model"].startswith("Disposable Paseo iPhone check"):
                raise RuntimeError("Paseo did not list exactly the isolated native thread")
            prompt = "ZEDLINK_FIXTURE_STREAM " + uuid.uuid4().hex
            result = cli(binary, home, env, "run", "--background", "--title", "Disposable ZedLink native thread",
                         "--provider", "zedlink", "--model", models[0]["id"], "--cwd", str(project), prompt)
            agent_id = result.get("agentId")
            if not agent_id:
                raise RuntimeError("Paseo did not create a fixture agent")
            workspaces = cli(binary, home, env, "workspace", "ls")
            current_workspace = next((row for row in workspaces if row.get("cwd") == str(project)), None)
            if not current_workspace:
                raise RuntimeError("Paseo did not create the disposable workspace")
            cli(binary, home, env, "workspace", "rename", current_workspace["workspaceId"],
                "ZedLink phone fixture")

            def complete():
                snapshot = rpc(socket_path, "thread.snapshot", {"thread_id": thread_id})
                entries = snapshot["entries_markdown"]
                return (snapshot if snapshot["status"] == "Idle" and
                        sum(prompt in entry for entry in entries) == 1 and
                        any("Fixture stream response complete." in entry for entry in entries) else None)

            until(complete, timeout=45)
            # Exercise Paseo's queued Stop against a real native Zed turn. The
            # desktop-owned delayed request must keep running while the phone
            # provider removes only its own queued entry.
            desktop_marker = "ZEDLINK_FIXTURE_BROWSER_STOP " + uuid.uuid4().hex
            queued_marker = "ZEDLINK_QUEUED_PASEO_" + uuid.uuid4().hex
            rpc(socket_path, "thread.send", {**base, "thread_id": thread_id, "text": desktop_marker})
            until(lambda: (snapshot if snapshot["status"] == "Generating" else None)
                  if (snapshot := rpc(socket_path, "thread.snapshot", {"thread_id": thread_id})) else None)
            cli(binary, home, env, "send", agent_id, queued_marker, "--no-wait")
            until(lambda: (queue if any(queued_marker in row["preview"] for row in queue["entries"]) else None)
                  if (queue := rpc(socket_path, "thread.queue", {"thread_id": thread_id})) else None)
            cli(binary, home, env, "stop", agent_id)
            until(lambda: not any(queued_marker in row["preview"] for row in
                      rpc(socket_path, "thread.queue", {"thread_id": thread_id})["entries"]))
            snapshot = rpc(socket_path, "thread.snapshot", {"thread_id": thread_id})
            if snapshot["status"] != "Generating" or not any(desktop_marker in entry for entry in snapshot["entries_markdown"]):
                raise RuntimeError("Queued Paseo Stop interrupted the desktop-owned native turn")
            if any(queued_marker in entry for entry in snapshot["entries_markdown"]):
                raise RuntimeError("Queued Paseo prompt was dispatched after Stop")
            rpc(socket_path, "thread.cancel", {**base, "thread_id": thread_id,
                "turn_id": snapshot["current_turn_id"]})
            until(lambda: rpc(socket_path, "thread.snapshot", {"thread_id": thread_id})["status"] == "Idle")
            print("PASS: Paseo queued Stop removed its own native entry while the desktop turn continued", flush=True)
            print(f"READY: real native fixture thread reached through Paseo; daemon {listen}; agent {agent_id}", flush=True)
            print(f"Phone: connect Tailscale, then Paseo Settings > Add host > Direct connection; Host {listen.rsplit(':', 1)[0]}, Port 6767, Use SSL off.", flush=True)
            print(f"Read the private daemon password locally from {password_file}; send only harmless fixture prompts.", flush=True)
            print("Press Ctrl-C to stop this disposable fixture.", flush=True)
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("Stopping disposable Paseo fixture.", flush=True)
        finally:
            if agent_id and daemon_started:
                try:
                    cli(binary, home, env, "delete", agent_id)
                except Exception:
                    pass
            if daemon_started:
                try:
                    for row in cli(binary, home, env, "workspace", "ls"):
                        if row.get("cwd") == str(project):
                            cli(binary, home, env, "workspace", "archive", row["workspaceId"])
                except Exception:
                    pass
            if daemon_started:
                try:
                    cli(binary, home, env, "daemon", "stop")
                except Exception:
                    pass
            stop(gateway)
            stop(zed)
            stop(display)
            if log is not None:
                log.close()
            if gateway_log is not None:
                gateway_log.close()
            if server is not None:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
