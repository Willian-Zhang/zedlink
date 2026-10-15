#!/usr/bin/env python3
"""Exercise the installed Paseo provider against a disposable HTTPS gateway.

The supplied Paseo home must already be an isolated profile with plugins enabled
and this directory plugin installed. No real Zed probe or project is used.
"""

import argparse
import json
import os
import ssl
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import ProxyHandler, build_opener


class Fixture:
    def __init__(self):
        self.entries = ["## User\n\nDesktop fixture\n\n", "## Assistant\n\nReady\n\n"]
        self.sends = []
        self.request_ids = set()
        self.lock = threading.Lock()

    def handler(self):
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *_args):
                pass

            def reply(self, value, status=200):
                data = json.dumps(value).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self):
                if self.path != "/v1/gateway":
                    return self.reply({"error": "not-found"}, 404)
                self.reply({"version": 1, "gateway_id": "fixture-gateway"})

            def do_POST(self):
                try:
                    request = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
                except (ValueError, TypeError):
                    return self.reply({"error": "invalid-request"}, 400)
                if (self.path != "/v1/rpc" or self.headers.get("Authorization") != "Bearer fixture-token"
                        or request.get("target_id") != "fixture"):
                    return self.reply({"error": "forbidden"}, 403)
                method, params = request.get("method"), request.get("params", {})
                if method == "thread.list":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch", "threads": [
                        {"thread_id": "native-fixture", "title": "Synthetic Paseo thread",
                         "agent": {"kind": "zed", "name": "Zed Agent"}},
                        {"thread_id": "external-fixture", "title": "External fixture",
                         "agent": {"kind": "external_acp", "name": "ACP"}},
                    ]}
                elif method == "thread.snapshot":
                    with fixture.lock:
                        entries = list(fixture.entries)
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": "native-fixture", "entry_start_index": 0,
                              "entry_end_index": len(entries), "entries_markdown": entries,
                              "status": "Idle", "current_turn_id": None,
                              "had_error": False, "pending_approvals": []}
                elif method == "thread.send":
                    if (params.get("instance_id"), params.get("epoch"), params.get("thread_id")) != (
                            "fixture-instance", "fixture-epoch", "native-fixture"):
                        return self.reply({"version": 1, "request_id": request["request_id"],
                                           "error": {"code": "INSTANCE_UNAVAILABLE"}})
                    with fixture.lock:
                        if request["request_id"] not in fixture.request_ids:
                            fixture.request_ids.add(request["request_id"])
                            fixture.sends.append(params["text"])
                            fixture.entries.extend([f"## User\n\n{params['text']}\n\n",
                                                    "## Assistant\n\nFixture Paseo reply\n\n"])
                    result = {"outcome": "unknown"}
                elif method == "request.status":
                    with fixture.lock:
                        known = params.get("original_request_id") in fixture.request_ids
                    result = {"known": params.get("instance_id") == "fixture-instance"
                              and params.get("epoch") == "fixture-epoch" and known,
                              "outcome": "unknown"}
                else:
                    return self.reply({"version": 1, "request_id": request["request_id"],
                                       "error": {"code": "UNSUPPORTED_CAPABILITY"}})
                self.reply({"version": 1, "request_id": request["request_id"], "result": result})

        return Handler


def command(cli, home, env, *args):
    result = subprocess.run([str(cli), *args, "--home", str(home), "--json"], env=env,
                            text=True, capture_output=True, timeout=45)
    try:
        value = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise RuntimeError(f"Paseo {args[0]} returned invalid JSON (exit {result.returncode})") from error
    if result.returncode:
        raise RuntimeError(f"Paseo {args[0]} failed: {value.get('error', {}).get('message', 'unknown error')}")
    return value


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--cli", type=Path, required=True, help="absolute path to pinned Paseo CLI")
    parser.add_argument("--home", type=Path, required=True, help="preconfigured disposable Paseo home")
    parser.add_argument("--password-file", type=Path, help="private daemon password file, when configured")
    args = parser.parse_args()
    cli, home = args.cli.resolve(strict=True), args.home.resolve(strict=True)
    env = os.environ.copy()
    if args.password_file:
        password_file = args.password_file.resolve(strict=True)
        if password_file.stat().st_mode & 0o077:
            raise RuntimeError("Paseo password file must be private")
        env["PASEO_PASSWORD"] = password_file.read_text().strip()
        if not env["PASEO_PASSWORD"]:
            raise RuntimeError("Paseo password file is empty")
    config = command(cli, home, env, "daemon", "config", "get", "pluginsEnabled")
    if config.get("value") is not True:
        raise RuntimeError("Disposable Paseo profile must have pluginsEnabled=true before this test")
    status = command(cli, home, env, "daemon", "status")
    if status.get("localDaemon") != "stopped":
        raise RuntimeError("Stop the disposable Paseo daemon before this test so it receives fixture settings")

    fixture = Fixture()
    with tempfile.TemporaryDirectory(prefix="zedlink-paseo-host-") as temporary:
        directory = Path(temporary)
        cert, key, credential, project = (directory / name for name in
                                           ("cert.pem", "key.pem", "device.json", "project"))
        project.mkdir()
        (project / "README.txt").write_text("Disposable Paseo host fixture.\n")
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1", "-subj", "/CN=localhost",
                        "-addext", "subjectAltName=DNS:localhost,IP:127.0.0.1"], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        credential.write_text(json.dumps({"gateway_id": "fixture-gateway", "device_id": "fixture-device",
                                          "token": "fixture-token"}))
        credential.chmod(0o600)
        server = ThreadingHTTPServer(("127.0.0.1", 0), fixture.handler())
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(cert), str(key))
        server.socket = context.wrap_socket(server.socket, server_side=True)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        env.update({"ZEDLINK_PASEO_URL": f"https://127.0.0.1:{server.server_port}",
                    "ZEDLINK_PASEO_TARGET_ID": "fixture", "ZEDLINK_PASEO_CREDENTIAL_FILE": str(credential),
                    "ZEDLINK_PASEO_CA_FILE": str(cert)})
        agent_id = None
        try:
            preflight = subprocess.run(["node", str(Path(__file__).parent / "preflight.mjs")],
                                      env=env, capture_output=True, text=True, timeout=15, check=True)
            assert "Exposed native Zed threads: 1" in preflight.stdout
            command(cli, home, env, "daemon", "start")
            if args.password_file:
                listen = command(cli, home, env, "daemon", "status")["configuredListen"]
                try:
                    build_opener(ProxyHandler({})).open(f"http://{listen}/api/providers", timeout=5)
                except HTTPError as error:
                    assert error.code == 401, f"Expected unauthenticated 401, got {error.code}"
                else:
                    raise AssertionError("Paseo daemon exposed unauthenticated API access")
            plugins = command(cli, home, env, "plugin", "ls")
            assert any(row.get("id") == "zedlink" and row.get("status") == "running" for row in plugins), plugins
            models = command(cli, home, env, "provider", "models", "zedlink")
            assert len(models) == 1 and models[0]["model"].startswith("Synthetic Paseo thread"), models
            result = command(cli, home, env, "run", "--background", "--provider", "zedlink",
                             "--model", models[0]["id"], "--cwd", str(project), "Harmless host fixture prompt")
            agent_id = result.get("agentId")
            assert isinstance(agent_id, str) and agent_id, result
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline:
                with fixture.lock:
                    sends = list(fixture.sends)
                if sends:
                    break
                time.sleep(0.1)
            assert sends == ["Harmless host fixture prompt"], sends
            print("PASS: Paseo loaded ZedLink, listed only the native fixture thread, and sent one prompt")
        finally:
            if agent_id:
                try:
                    command(cli, home, env, "delete", agent_id)
                except (RuntimeError, subprocess.TimeoutExpired):
                    pass
            try:
                for row in command(cli, home, env, "workspace", "ls"):
                    if row.get("cwd") == str(project):
                        command(cli, home, env, "workspace", "archive", row["workspaceId"])
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
            try:
                command(cli, home, env, "daemon", "stop")
            finally:
                server.shutdown()
                server.server_close()


if __name__ == "__main__":
    main()
