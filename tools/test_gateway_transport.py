#!/usr/bin/env python3
"""Local gateway transport fixture; this does not test native Zed behavior."""
import json
import html
import os
import re
import shutil
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
from pathlib import Path

from websockets.sync.client import connect
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import Select
from selenium.webdriver.support.ui import WebDriverWait
from pair_phone import qr_svg

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "gateway/target/debug/zedlink-gateway"


class ProbeFixture:
    def __init__(self, path):
        self.path = path
        self.seen_sends = {}
        self.created_requests = {}
        self.accepted = 0
        self.entries = ['<img src=x onerror="window.syntheticXss=1">']
        self.sequence = 0
        self.extra_thread = False
        self.created_thread = False
        self.truncated = False
        self.activity_truncated = False
        self.active_turn_id = None
        self.agent_error = None
        self.retry_status = None
        self.cancelled = 0
        self.profile_id = "write"
        self.thinking_enabled = True
        self.settings_updates = 0
        self.approvals = []
        self.approval_decisions = 0
        self.change_operations = {}
        self.drop_send_before_accept_once = False
        self.stopped = False
        self.listener = socket.socket(socket.AF_UNIX)
        self.listener.bind(str(path))
        os.chmod(path, 0o600)
        self.listener.listen(5)
        self.listener.settimeout(0.2)
        self.worker = threading.Thread(target=self.run, daemon=True)
        self.worker.start()

    def run(self):
        while not self.stopped:
            try:
                connection, _ = self.listener.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with connection:
                request = json.loads(connection.makefile("rb").readline())
                method = request["method"]
                params = request["params"]
                if method == "thread.send" and self.drop_send_before_accept_once:
                    self.drop_send_before_accept_once = False
                    continue
                result = {}
                error = None
                if method == "thread.list":
                    threads = [{"thread_id": "fixture-thread", "title": "Synthetic test thread",
                                "status": "Generating" if self.active_turn_id is not None else "Idle",
                                "current_turn_id": self.active_turn_id,
                                "had_error": self.agent_error is not None,
                                "agent_error": self.agent_error,
                                "retry_status": self.retry_status}]
                    if self.extra_thread:
                        threads.append({"thread_id": "fixture-second", "title": "Second synthetic thread", "status": "Idle"})
                    if self.created_thread:
                        threads.append({"thread_id": "fixture-created", "title": "Created from browser", "status": "Idle"})
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "threads": threads}
                elif method == "thread.create":
                    key = request["request_id"]
                    title = params.get("title")
                    if key in self.created_requests and self.created_requests[key] != title:
                        error = {"code": "REQUEST_CONFLICT"}
                    else:
                        self.created_requests[key] = title
                        self.created_thread = True
                        result = {"outcome": "ready", "thread_id": "fixture-created"}
                elif method == "thread.snapshot":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": params["thread_id"],
                              "title": ("Second synthetic thread" if params["thread_id"] == "fixture-second"
                                        else "Created from browser" if params["thread_id"] == "fixture-created"
                                        else "Synthetic test thread"),
                              "status": "Generating" if self.active_turn_id is not None else "Idle",
                              "current_turn_id": self.active_turn_id, "truncated": self.truncated,
                              "had_error": self.agent_error is not None,
                              "agent_error": self.agent_error, "retry_status": self.retry_status,
                              "entries_markdown": list(self.entries),
                              "activity_entries_markdown": list(self.entries[-8:]),
                              "activity_truncated": self.activity_truncated, "pending_approvals": list(self.approvals),
                              "last_sequence": self.sequence}
                elif method == "thread.events":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": params["thread_id"],
                              "events": [{"sequence": self.sequence, "kind": "entry.added"}]
                              if params["after_sequence"] < self.sequence else [],
                              "last_sequence": self.sequence}
                elif method == "thread.commands":
                    result = {"thread_id": params["thread_id"], "commands": [
                        {"name": "compact", "description": "Compact context", "category": "native", "requires_argument": False},
                        {"name": "help", "description": "Show agent help", "category": "agent", "requires_argument": False},
                    ]}
                elif method in ("thread.settings", "thread.settings.update"):
                    if method == "thread.settings.update":
                        if "profile_id" in params:
                            self.profile_id = params["profile_id"]
                        if "thinking_enabled" in params:
                            self.thinking_enabled = params["thinking_enabled"]
                        self.settings_updates += 1
                    result = {
                        "thread_id": params["thread_id"],
                        "status": "Generating" if self.active_turn_id is not None else "Idle",
                        "model": {"id": "glm-local", "name": "Local GLM fixture", "provider_id": "openai-compatible"},
                        "profile_id": self.profile_id,
                        "profiles": [{"id": "write", "name": "Write"}, {"id": "ask", "name": "Ask"}],
                        "thinking_enabled": self.thinking_enabled,
                        "thinking_supported": True,
                        "thinking_can_disable": True,
                    }
                elif method == "project.files":
                    result = {"entries": [
                        {"path": "src", "kind": "directory", "size": 0},
                        {"path": "src/main.rs", "kind": "file", "size": 31},
                        {"path": "README.md", "kind": "file", "size": 18},
                    ], "truncated": False}
                elif method == "project.file":
                    files = {"src/main.rs": "fn main() { println!(\"ready\"); }\n",
                             "README.md": "# Fixture project\n"}
                    if params.get("path") not in files:
                        error = {"code": "FILE_UNAVAILABLE"}
                    else:
                        result = {"path": params["path"], "content": files[params["path"]], "truncated": False}
                elif method == "changes.snapshot":
                    result = {"repository": {"branch": "main", "head": "fixture-head",
                                               "revision": "fixture-head:4"},
                              "entries": [{"path": "src/main.rs", "status": "modified",
                                           "staging": "unstaged", "added": 2, "deleted": 1}]}
                elif method == "changes.diff":
                    if params.get("revision") != "fixture-head:4":
                        error = {"code": "STALE_REVISION"}
                    else:
                        result = {"outcome": "ready", "revision": "fixture-head:4",
                                  "diff": "diff --git a/src/main.rs b/src/main.rs\n+println!(\"ready\");\n",
                                  "truncated": False}
                elif method in ("changes.stage", "changes.unstage"):
                    key = request["request_id"]
                    payload = json.dumps(params, sort_keys=True)
                    if key in self.change_operations and self.change_operations[key] != payload:
                        error = {"code": "REQUEST_CONFLICT"}
                    else:
                        self.change_operations[key] = payload
                        result = {"outcome": "succeeded", "provisional": False}
                elif method == "approval.respond":
                    matching = [item for item in self.approvals
                                if item["approval_id"] == params.get("approval_id")
                                and item["turn_id"] == params.get("turn_id")]
                    if not matching:
                        error = {"code": "APPROVAL_EXPIRED"}
                    else:
                        self.approvals = []
                        self.approval_decisions += 1
                        result = {"outcome": "resolved"}
                elif method == "thread.send":
                    key = request["request_id"]
                    text = params["text"]
                    payload = json.dumps(params, sort_keys=True)
                    if key in self.seen_sends and self.seen_sends[key] != payload:
                        error = {"code": "REQUEST_ID_CONFLICT"}
                    else:
                        if key not in self.seen_sends:
                            self.seen_sends[key] = payload
                            self.accepted += 1
                            self.entries.extend([
                                f"## User\n\n{text}\n\n",
                                "## Assistant\n\n**Synthetic fixture reply.**\n\n- One\n- Two\n\n| Step | State |\n| --- | --- |\n| Build | Ready |\n\n```text\nok\n```\n\n",
                            ])
                            self.sequence += 1
                        result = {"outcome": "unknown"}
                elif method == "request.status":
                    key = params["original_request_id"]
                    result = {"known": key in self.seen_sends, "outcome": "unknown"}
                elif method == "thread.cancel":
                    if (params.get("instance_id"), params.get("epoch")) != ("fixture-instance", "fixture-epoch"):
                        error = {"code": "INSTANCE_UNAVAILABLE"}
                    elif params.get("thread_id") not in ("fixture-thread", "fixture-second", "fixture-created"):
                        error = {"code": "THREAD_NOT_EXPOSED"}
                    elif params.get("turn_id") != self.active_turn_id:
                        error = {"code": "STALE_TURN"}
                    else:
                        self.active_turn_id = None
                        self.cancelled += 1
                        self.sequence += 1
                        result = {"outcome": "requested", "turn_id": params["turn_id"]}
                elif method == "instance.info":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "capabilities": ["thread.list", "thread.create", "thread.snapshot", "thread.events",
                                               "thread.commands", "thread.settings", "thread.settings.update",
                                               "thread.send", "thread.attachments", "thread.cancel",
                                               "thread.approvals", "approval.respond", "project.files",
                                               "project.file", "changes.snapshot", "changes.diff",
                                               "changes.stage", "changes.unstage", "request.status"]}
                else:
                    error = {"code": "UNSUPPORTED_CAPABILITY"}
                response = {"version": 1, "request_id": request["request_id"]}
                response["error" if error else "result"] = error or result
                connection.sendall(json.dumps(response).encode() + b"\n")

    def close(self):
        self.stopped = True
        self.listener.close()
        self.worker.join(timeout=1)


def http(base, context, path, method="GET", data=None, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = "Bearer " + token
    request = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None,
                                     headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, context=context, timeout=5) as response:
            return response.status, json.load(response)
    except urllib.error.HTTPError as error:
        return error.code, json.load(error)


def admin(directory, *args):
    result = subprocess.run([str(BINARY), "admin", str(directory), *args],
                            capture_output=True, text=True, check=True, timeout=5)
    return json.loads(result.stdout)


def main():
    with tempfile.TemporaryDirectory(prefix="zedlink-gateway-fixture.") as temporary:
        root = Path(temporary)
        state = root / "state"
        probe_dir = root / "probe"
        probe_dir.mkdir(mode=0o700)
        probe = ProbeFixture(probe_dir / "zedlink.sock")
        cert = root / "cert.pem"
        key = root / "key.pem"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        for unsafe_address in (f"0.0.0.0:{port}", f"8.8.8.8:{port}"):
            unsafe_bind = subprocess.run([str(BINARY), "serve", unsafe_address, str(cert), str(key),
                                          str(probe.path), str(state)],
                                         capture_output=True, text=True, timeout=5)
            assert unsafe_bind.returncode != 0 and "loopback or private address" in unsafe_bind.stderr
        os.chmod(key, 0o644)
        unsafe_key = subprocess.run([str(BINARY), "serve", f"127.0.0.1:{port}", str(cert), str(key),
                                     str(probe.path), str(state)],
                                    capture_output=True, text=True, timeout=5)
        assert unsafe_key.returncode != 0 and "TLS private key" in unsafe_key.stderr
        os.chmod(key, 0o600)
        server = subprocess.Popen([str(BINARY), "serve", f"127.0.0.1:{port}", str(cert), str(key),
                                   str(probe.path), str(state)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if (state / "admin.sock").exists():
                    break
                if server.poll() is not None:
                    raise AssertionError("gateway exited during startup")
                time.sleep(0.05)
            else:
                raise AssertionError("admin socket missing")
            assert state.stat().st_mode & 0o077 == 0
            assert (state / "state.json").stat().st_mode & 0o077 == 0
            assert (state / "admin.sock").stat().st_mode & 0o077 == 0
            context = ssl.create_default_context(cafile=str(cert))
            base = f"https://localhost:{port}"
            status, info = http(base, context, "/v1/gateway")
            assert status == 200 and info["gateway_id"]
            with urllib.request.urlopen(base + "/", context=context, timeout=5) as page_response:
                page_html = page_response.read().decode()
                assert "ZedLink" in page_html and "pair-form" in page_html
                assert "default-src 'none'" in page_response.headers["Content-Security-Policy"]
                assert page_response.headers["Cache-Control"] == "no-store"
                assert page_response.headers["X-Content-Type-Options"] == "nosniff"
            with urllib.request.urlopen(base + "/app.js", context=context, timeout=5) as script_response:
                assert "thread.send" in script_response.read().decode()
                assert script_response.headers["Content-Type"].startswith("text/javascript")
            with urllib.request.urlopen(base + "/manifest.webmanifest", context=context, timeout=5) as manifest_response:
                manifest = json.load(manifest_response)
                assert manifest["display"] == "standalone" and manifest["theme_color"] == "#000000"
                assert manifest_response.headers["Content-Type"].startswith("application/manifest+json")
            with urllib.request.urlopen(base + "/service-worker.js", context=context, timeout=5) as worker_response:
                worker = worker_response.read().decode()
                assert 'url.pathname.startsWith("/v1/")' in worker and "SHELL_CACHE" in worker
                assert 'addEventListener("push"' in worker and 'addEventListener("notificationclick"' in worker
            with urllib.request.urlopen(base + "/icons/icon-192.png", context=context, timeout=5) as icon_response:
                assert icon_response.headers["Content-Type"] == "image/png"
                assert icon_response.read(8) == b"\x89PNG\r\n\x1a\n"
            try:
                http(f"https://127.0.0.1:{port}", context, "/v1/gateway")
            except urllib.error.URLError as error:
                assert isinstance(error.reason, ssl.SSLCertVerificationError)
            else:
                raise AssertionError("wrong TLS hostname accepted")
            request = {"version": 1, "request_id": "same-id", "method": "thread.list", "params": {}}
            status, _ = http(base, context, "/v1/rpc", "POST", request)
            assert status == 401
            blocked_code = admin(state, "pair-code")["code"]
            for _ in range(5):
                status, _ = http(base, context, "/v1/pair", "POST",
                                 {"code": "0" * 64, "device_name": "bad attempt"})
                assert status == 403
            status, _ = http(base, context, "/v1/pair", "POST",
                             {"code": blocked_code, "device_name": "too late"})
            assert status == 403
            code1 = admin(state, "pair-code")["code"]
            status, device1 = http(base, context, "/v1/pair", "POST",
                                   {"code": code1, "device_name": "fixture one"})
            assert status == 200 and device1["gateway_id"] == info["gateway_id"]
            status, _ = http(base, context, "/v1/pair", "POST",
                             {"code": code1, "device_name": "reused"})
            assert status == 403
            token1 = device1["token"]
            status, notification_config = http(base, context, "/v1/notifications/config", token=token1)
            assert status == 200 and notification_config["supported"]
            assert not notification_config["enabled"] and notification_config["application_server_key"]
            status, notification_status = http(
                base, context, "/v1/notifications/status", "POST",
                {"endpoint": "https://fcm.googleapis.com/device"}, token1,
            )
            assert status == 200 and not notification_status["enabled"]
            status, invalid_subscription = http(
                base, context, "/v1/notifications/subscribe", "POST",
                {"endpoint": "https://127.0.0.1/private", "keys": {"p256dh": "AA", "auth": "AA"}}, token1,
            )
            assert status == 400 and invalid_subscription["error"] == "INVALID_SUBSCRIPTION"
            token_file = root / "device-one.json"
            token_file.write_text(json.dumps(device1))
            os.chmod(token_file, 0o600)
            terminal = subprocess.run([
                "python3", str(ROOT / "tools/zedlink_gateway_client.py"),
                "--base-url", base, "--ca-file", str(cert), "--token-file", str(token_file),
                "rpc", "thread.list", "{}",
            ], capture_output=True, text=True, check=True, timeout=5)
            assert json.loads(terminal.stdout)["result"]["threads"][0]["thread_id"] == "fixture-thread"
            mismatch = subprocess.run([
                "python3", str(ROOT / "tools/zedlink_gateway_client.py"),
                "--base-url", base, "--ca-file", str(cert), "--token-file", str(token_file),
                "--expected-gateway-id", "wrong-gateway", "rpc", "thread.list", "{}",
            ], capture_output=True, text=True, timeout=5)
            assert mismatch.returncode == 2 and "Gateway identity changed" in mismatch.stderr
            status, listing = http(base, context, "/v1/rpc", "POST", request, token1)
            assert status == 200 and listing["result"]["threads"][0]["thread_id"] == "fixture-thread"
            denied = dict(request, method="arbitrary.shell")
            status, _ = http(base, context, "/v1/rpc", "POST", denied, token1)
            assert status == 403
            cancellation = {"version": 1, "request_id": "cancel-one", "method": "thread.cancel",
                            "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                       "thread_id": "fixture-thread", "turn_id": 9}}
            status, _ = http(base, context, "/v1/rpc", "POST", cancellation)
            assert status == 401
            status, stale = http(base, context, "/v1/rpc", "POST", cancellation, token1)
            assert status == 200 and stale["error"]["code"] == "STALE_TURN"
            sent = {"version": 1, "request_id": "stable-send", "method": "thread.send",
                    "params": {"thread_id": "fixture-thread", "text": "harmless fixture"}}
            for _ in range(2):
                status, response = http(base, context, "/v1/rpc", "POST", sent, token1)
                assert status == 200 and response["request_id"] == "stable-send"
            assert probe.accepted == 1
            lookup = {"version": 1, "request_id": "lookup", "method": "request.status",
                      "params": {"original_request_id": "stable-send"}}
            status, response = http(base, context, "/v1/rpc", "POST", lookup, token1)
            assert status == 200 and response["result"]["known"]
            code2 = admin(state, "pair-code")["code"]
            status, device2 = http(base, context, "/v1/pair", "POST",
                                   {"code": code2, "device_name": "fixture two"})
            assert status == 200
            token2 = device2["token"]
            status, response = http(base, context, "/v1/rpc", "POST", lookup, token2)
            assert status == 200 and not response["result"]["known"]
            status, _ = http(base, context, "/v1/rpc", "POST", sent, token2)
            assert status == 200 and probe.accepted == 2
            status, response = http(base, context, "/v1/rpc", "POST", lookup, token2)
            assert status == 200 and response["result"]["known"]
            probe.approvals = [{"approval_id": "race-approval", "turn_id": 11,
                                "tool_name": "terminal", "display": "Race fixture",
                                "raw_input": {"command": "printf race"},
                                "details_truncated": False, "can_approve_once": True,
                                "can_deny_once": True}]
            approval = {"version": 1, "request_id": "approval-race",
                        "method": "approval.respond",
                        "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                   "thread_id": "fixture-thread", "turn_id": 11,
                                   "approval_id": "race-approval", "decision": "deny_once"}}
            status, response = http(base, context, "/v1/rpc", "POST", approval, token1)
            assert status == 200 and response["result"]["outcome"] == "resolved"
            status, response = http(base, context, "/v1/rpc", "POST", approval, token2)
            assert status == 200 and response["error"]["code"] == "APPROVAL_EXPIRED"
            probe.approval_decisions = 0
            server.terminate()
            server.communicate(timeout=3)
            server = subprocess.Popen([str(BINARY), "serve", f"127.0.0.1:{port}", str(cert), str(key),
                                       str(probe.path), str(state)],
                                      stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
            for _ in range(100):
                try:
                    status, restarted = http(base, context, "/v1/gateway")
                    if status == 200:
                        break
                except urllib.error.URLError:
                    time.sleep(0.05)
            else:
                raise AssertionError("gateway did not restart")
            assert restarted["gateway_id"] == info["gateway_id"]
            status, response = http(base, context, "/v1/rpc", "POST", sent, token2)
            assert status == 200 and response["request_id"] == "stable-send" and probe.accepted == 2
            websocket_url = f"wss://localhost:{port}/v1/events?thread_id=fixture-thread"
            with connect(websocket_url, ssl=context,
                         additional_headers={"Authorization": "Bearer " + token2},
                         open_timeout=5, close_timeout=2) as websocket:
                event = json.loads(websocket.recv(timeout=5))
                assert event["result"]["thread_id"] == "fixture-thread"
                assert admin(state, "revoke", device2["device_id"])["revoked"]
                try:
                    websocket.recv(timeout=3)
                except Exception:
                    pass
                else:
                    raise AssertionError("revoked WebSocket remained open")
            status, _ = http(base, context, "/v1/rpc", "POST", request, token2)
            assert status == 401
            assert admin(state, "revoke", device1["device_id"])["revoked"]
            status, _ = http(base, context, "/v1/rpc", "POST", request, token1)
            assert status == 401
            assert not admin(state, "devices")["devices"]
            browser_code = admin(state, "pair-short-code")["code"]
            assert len(browser_code) == 10 and browser_code.isascii() and browser_code.isdecimal()
            accepted_before_browser = probe.accepted
            browser_options = FirefoxOptions()
            browser_options.add_argument("-headless")
            browser_options.accept_insecure_certs = True  # Disposable localhost fixture certificate only.
            browser_options.set_preference("network.proxy.type", 0)
            browser = webdriver.Firefox(service=FirefoxService("/usr/bin/geckodriver"),
                                        options=browser_options)
            try:
                wait = WebDriverWait(browser, 8)
                browser.get(base + "/#gateway=" + info["gateway_id"])
                wait.until(lambda driver: driver.find_element(By.ID, "gateway-id").text == info["gateway_id"])
                assert browser.find_element(By.ID, "expected-id").get_attribute("value") == info["gateway_id"]
                browser.execute_script("document.getElementById('expected-id').value='wrong-gateway'")
                browser.find_element(By.ID, "pair-code").send_keys(browser_code)
                browser.find_element(By.ID, "pair-button").click()
                wait.until(lambda driver: "Pairing code was not sent" in driver.find_element(By.ID, "pair-notice").text)
                assert not admin(state, "devices")["devices"]
                browser.execute_script("document.getElementById('expected-id').value=arguments[0]", info["gateway_id"])
                browser.find_element(By.ID, "pair-button").click()
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item"))
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Synthetic test thread")
                assert "Choose a session" not in browser.page_source
                assert browser.find_element(By.ID, "thread-count").text == "1"
                assert browser.find_element(By.ID, "ui-build").get_attribute("textContent") == "2026.10.05.15"
                assert browser.find_element(By.ID, "notification-state")
                assert browser.find_element(By.ID, "enable-notifications")
                wait.until(lambda driver: "checking" not in driver.find_element(By.ID, "notification-state").text.casefold())
                assert "checking" not in browser.find_element(By.ID, "header-notifications").text.casefold()
                assert browser.execute_script(
                    "return document.getElementById('show-sessions').closest('.topbar') !== null"
                )
                assert not browser.find_elements(By.CSS_SELECTOR, ".workspace #show-sessions")
                assert len(browser.find_elements(By.ID, "sign-out")) == 1
                assert not browser.find_elements(By.ID, "forget")
                assert not browser.find_elements(By.ID, "mobile-forget")
                assert browser.find_element(By.ID, "device-name").get_attribute("value") == "Firefox on Linux"
                assert browser.execute_script(
                    "return browserDeviceName(arguments[0])",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0",
                ) == "Firefox on Windows"
                assert browser.execute_script(
                    "return browserDeviceName(arguments[0])",
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/150.0.0.0 Safari/537.36 Edg/150.0.0.0",
                ) == "Edge on Windows"
                browser.find_element(By.ID, "new-session").click()
                browser.find_element(By.ID, "new-session-title").send_keys("Created from browser")
                browser.find_element(By.ID, "create-session").click()
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Created from browser")
                assert browser.find_element(By.ID, "thread-count").text == "2"
                assert len(probe.created_requests) == 1
                search = browser.find_element(By.ID, "session-search")
                search.send_keys("no such session")
                assert not browser.find_elements(By.CSS_SELECTOR, ".thread-item")
                assert "No sessions match" in browser.find_element(By.ID, "thread-list").text
                search.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item"))
                assert browser.find_element(By.CSS_SELECTOR, ".thread-badge").text == "ZED AGENT"
                browser.find_element(By.CSS_SELECTOR, ".thread-item").click()
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Synthetic test thread")
                wait.until(lambda driver: "Zed connected · live updates" in driver.find_element(By.ID, "connection").get_attribute("textContent"))
                browser.find_element(By.ID, "open-settings").click()
                wait.until(lambda driver: "Local GLM fixture" in driver.find_element(By.ID, "zed-model").get_attribute("value"))
                assert "Local GLM fixture" in browser.find_element(By.ID, "header-model").text
                assert Select(browser.find_element(By.ID, "zed-profile")).first_selected_option.get_attribute("value") == "write"
                Select(browser.find_element(By.ID, "zed-profile")).select_by_value("ask")
                browser.find_element(By.ID, "zed-thinking").click()
                browser.find_element(By.ID, "save-zed-settings").click()
                wait.until(lambda driver: probe.settings_updates == 1)
                assert probe.profile_id == "ask" and probe.thinking_enabled is False
                assert "updated" in browser.find_element(By.ID, "notice").text
                browser.save_screenshot("/tmp/zedlink-browser-settings.png")
                browser.find_element(By.ID, "settings-back").click()
                assert browser.find_element(By.ID, "sessions-panel").is_displayed()
                browser.find_element(By.ID, "show-context").click()
                wait.until(lambda driver: driver.find_element(By.ID, "context-panel").is_displayed())
                wait.until(lambda driver: "src/main.rs" in driver.find_element(By.ID, "file-list").text)
                file_rows = browser.find_elements(By.CSS_SELECTOR, "#file-list .context-row:not(.directory)")
                next(row for row in file_rows if "src/main.rs" in row.text).click()
                wait.until(lambda driver: "println" in driver.find_element(By.ID, "file-preview-content").text)
                browser.find_element(By.ID, "attach-preview").click()
                assert "src/main.rs" in browser.find_element(By.ID, "attachment-strip").text
                browser.find_element(By.ID, "show-context").click()
                browser.find_element(By.ID, "context-changes-tab").click()
                wait.until(lambda driver: "main · 1 changed file" in driver.find_element(By.ID, "changes-summary").text)
                assert "MODIFIED" in browser.find_element(By.ID, "changes-list").text
                browser.find_element(By.ID, "load-diff").click()
                wait.until(lambda driver: "diff --git" in driver.find_element(By.ID, "git-diff").text)
                browser.find_element(By.CSS_SELECTOR, "#changes-list .change-action").click()
                wait.until(lambda driver: len(probe.change_operations) == 1)
                browser.find_element(By.ID, "close-context").click()
                upload = root / "browser-note.txt"
                upload.write_text("browser upload fixture\n")
                browser.find_element(By.ID, "upload-file").send_keys(str(upload))
                wait.until(lambda driver: "browser-note.txt" in driver.find_element(By.ID, "attachment-strip").text)
                assert not browser.find_elements(By.CSS_SELECTOR, "#messages img")
                assert browser.execute_script("return window.syntheticXss || 0") == 0
                browser.find_element(By.ID, "prompt").send_keys("Browser fixture prompt")
                browser.find_element(By.ID, "send").click()
                try:
                    wait.until(lambda driver: "Browser fixture prompt" in driver.find_element(By.ID, "messages").text)
                except TimeoutException:
                    print("browser fixture state:", {name: browser.find_element(By.ID, name).text
                          for name in ("connection", "notice", "delivery", "thread-title")},
                          "accepted:", probe.accepted)
                    raise
                assert probe.accepted == accepted_before_browser + 1
                sent_payload = json.loads(list(probe.seen_sends.values())[-1])
                assert sent_payload["context_paths"] == ["src/main.rs"]
                assert sent_payload["uploads"][0]["name"] == "browser-note.txt"
                assert browser.find_elements(By.CSS_SELECTOR, ".message.user .message-label")[-1].get_attribute("textContent") == "You"
                assert browser.find_elements(By.CSS_SELECTOR, ".message.assistant .message-label")[-1].get_attribute("textContent") == "Zed Agent"
                assert browser.find_elements(By.CSS_SELECTOR, ".message.assistant strong")
                assert browser.find_elements(By.CSS_SELECTOR, ".message.assistant pre code")
                assert browser.find_element(By.CSS_SELECTOR, ".message.assistant table").text == "Step State\nBuild Ready"
                assert browser.find_element(By.CSS_SELECTOR, ".message.assistant .code-block-head").text.startswith("TEXT")
                assert not browser.find_element(By.ID, "delivery-details").is_displayed()
                assert browser.find_element(By.ID, "send").is_enabled()
                probe.active_turn_id = 8
                probe.entries[-1] = "## Assistant\n\n<thinking>\nChecking the fixture stream\n</thinking>\n\n**Synthetic fixture reply.**\n\n"
                probe.sequence += 1
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item.running .thread-progress"))
                assert "Working" in browser.find_element(By.CSS_SELECTOR, ".thread-status.busy").text
                browser.save_screenshot("/tmp/zedlink-browser-active-session.png")
                wait.until(lambda driver: "Checking the fixture stream" in driver.find_element(By.ID, "activity-content").text)
                assert browser.find_element(By.ID, "activity").is_displayed()
                assert browser.execute_script("return document.getElementById('messages').contains(document.getElementById('activity'))")
                assert browser.find_element(By.ID, "activity-toggle").get_attribute("aria-expanded") == "true"
                assert "THINKING" in browser.find_element(By.ID, "activity-content").text
                assert browser.find_element(By.CSS_SELECTOR, ".message.assistant details.thinking-block").get_attribute("open") == "true"
                probe.activity_truncated = True
                probe.sequence += 1
                wait.until(lambda driver: "Earlier activity is omitted" in driver.find_element(By.ID, "activity-content").text)
                probe.activity_truncated = False
                probe.sequence += 1
                probe.entries.append("**Tool Call: Run safe fixture command**\nStatus: InProgress\n\nTerminal:\n```\nline one\nline two\n```\n\nDiff: fixture.txt\n```\nnew file content\n```\n")
                probe.sequence += 1
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".message.tool .tool-title"))
                assert "Run safe fixture command" in browser.find_element(By.CSS_SELECTOR, ".message.tool .tool-title").text
                assert "InProgress" in browser.find_element(By.CSS_SELECTOR, ".message.tool .tool-state").text
                tool_details = browser.find_element(By.CSS_SELECTOR, ".message.tool .tool-details")
                assert tool_details.get_attribute("open") == "true"
                assert "Hide live tool output" in tool_details.find_element(By.TAG_NAME, "summary").text
                outputs = browser.find_elements(By.CSS_SELECTOR, ".message.tool .tool-output")
                assert len(outputs) == 2
                assert "line two" in outputs[0].text
                assert "File content · fixture.txt" in outputs[1].text
                browser.execute_script("arguments[0].scrollIntoView({block:'center'})", browser.find_element(By.CSS_SELECTOR, ".message.tool"))
                browser.save_screenshot("/tmp/zedlink-browser-tool-fixture.png")
                probe.entries[-1] = probe.entries[-1].replace("Status: InProgress", "Status: Completed").replace("line two", "line two\nline three")
                wait.until(lambda driver: "line three" in driver.execute_script(
                    "return document.querySelector('#activity .tool-output')?.textContent || ''"
                ))
                assert browser.find_element(By.CSS_SELECTOR, ".message.tool .tool-details").get_attribute("open") is None
                assert "line three" in browser.find_element(By.CSS_SELECTOR, "#activity .tool-output").text
                probe.truncated = True
                probe.sequence += 1
                wait.until(lambda driver: "Older conversation omitted here" in driver.find_element(By.ID, "thread-meta").text)
                assert not browser.find_elements(By.ID, "snapshot-warning")
                probe.truncated = False
                probe.sequence += 1
                wait.until(lambda driver: "Thread fixture-thre" in driver.find_element(By.ID, "thread-meta").text)
                probe.approvals = [{"approval_id": "fixture-approval", "turn_id": 8,
                                    "tool_name": "terminal", "display": "Run fixture command",
                                    "raw_input": {"command": "printf fixture"},
                                    "details_truncated": False, "can_approve_once": True,
                                    "can_deny_once": True}]
                probe.sequence += 1
                wait.until(lambda driver: driver.find_element(By.ID, "approvals").is_displayed())
                assert "printf fixture" in browser.find_element(By.ID, "approvals").text
                browser.find_element(By.CSS_SELECTOR, "#approvals .primary").click()
                wait.until(lambda driver: probe.approval_decisions == 1)
                wait.until(lambda driver: not driver.find_element(By.ID, "approvals").is_displayed())
                probe.active_turn_id = None
                probe.sequence += 1
                wait.until(lambda driver: not driver.find_elements(By.CSS_SELECTOR, ".thread-item.running"))
                wait.until(lambda driver: driver.find_element(By.ID, "activity-toggle").get_attribute("aria-expanded") == "false")
                probe.agent_error = {"kind": "stream_error", "title": "Model connection interrupted",
                                     "message": "The local model endpoint refused the connection.", "retrying": True}
                assert browser.execute_async_script(
                    "const done=arguments[0]; loadThreads().then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: driver.find_element(By.ID, "agent-health").is_displayed())
                assert "local model endpoint" in browser.find_element(By.ID, "agent-health-message").text
                assert browser.find_element(By.ID, "thread-state").text == "REQUEST FAILED"
                assert "request failed" in browser.find_element(By.ID, "header-model").text.casefold()
                assert "error" in browser.find_element(By.ID, "header-model").get_attribute("class")
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item.error"))
                probe.retry_status = {"last_error": "Local model connection refused", "attempt": 2,
                                      "max_attempts": 5, "next_attempt_in_ms": 3000}
                probe.active_turn_id = 10
                assert browser.execute_async_script(
                    "const done=arguments[0]; loadThreads().then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: "ATTEMPT 2 OF 5" in driver.find_element(By.ID, "agent-health-recovery").text)
                assert browser.find_element(By.ID, "thread-state").text == "RETRYING"
                assert "retrying" in browser.find_element(By.ID, "header-model").text.casefold()
                assert "warning" in browser.find_element(By.ID, "header-model").get_attribute("class")
                probe.agent_error = None
                probe.retry_status = None
                probe.active_turn_id = None
                assert browser.execute_async_script(
                    "const done=arguments[0]; loadThreads().then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: not driver.find_element(By.ID, "agent-health").is_displayed())
                assert "request failed" not in browser.find_element(By.ID, "header-model").text.casefold()
                browser.find_element(By.ID, "show-actions").click()
                browser.find_element(By.ID, "action-commands").click()
                wait.until(lambda driver: driver.find_element(By.ID, "command-menu").is_displayed())
                assert "/compact" in browser.find_element(By.ID, "command-menu").text
                browser.find_element(By.ID, "prompt").send_keys("unknown")
                assert not browser.find_elements(By.CSS_SELECTOR, ".command-option")
                browser.find_element(By.ID, "prompt").send_keys(Keys.ESCAPE)
                browser.find_element(By.ID, "prompt").clear()
                probe.drop_send_before_accept_once = True
                browser.find_element(By.ID, "prompt").send_keys("Connection loss fixture prompt")
                browser.find_element(By.ID, "send").click()
                wait.until(lambda driver: driver.find_element(By.ID, "delivery-details").is_displayed())
                accepted_after_drop = probe.accepted
                browser.find_element(By.ID, "delivery-details").find_element(By.TAG_NAME, "summary").click()
                browser.find_element(By.ID, "retry").click()
                wait.until(lambda driver: not driver.find_element(By.ID, "delivery-details").is_displayed())
                assert probe.accepted == accepted_after_drop + 1
                probe.active_turn_id = 9
                probe.sequence += 1
                wait.until(lambda driver: driver.find_element(By.ID, "send").get_attribute("data-mode") == "stop")
                assert browser.find_element(By.ID, "send").get_attribute("aria-label") == "Stop current Zed Agent turn"
                browser.save_screenshot("/tmp/zedlink-browser-fixture-stop.png")
                browser.find_element(By.ID, "send").click()
                wait.until(lambda driver: probe.cancelled == 1)
                wait.until(lambda driver: driver.find_element(By.ID, "send").get_attribute("data-mode") == "send")
                assert browser.find_element(By.ID, "send").get_attribute("aria-label") == "Send message"
                browser.save_screenshot("/tmp/zedlink-browser-fixture.png")
                browser.set_window_size(1920, 1080)
                wide = browser.execute_script("return {width:innerWidth, layoutWidth:document.querySelector('.layout').getBoundingClientRect().width, sidebarWidth:document.querySelector('.sidebar').getBoundingClientRect().width, workspaceWidth:document.querySelector('.workspace').getBoundingClientRect().width}")
                assert wide["layoutWidth"] >= wide["width"] - 2 and wide["sidebarWidth"] >= 340, wide
                browser.find_element(By.ID, "show-sessions").click()
                collapsed = browser.execute_script("return {sidebarHidden:getComputedStyle(document.querySelector('.sidebar')).visibility==='hidden', workspaceWidth:document.querySelector('.workspace').getBoundingClientRect().width, width:innerWidth}")
                assert collapsed["sidebarHidden"] and collapsed["workspaceWidth"] >= collapsed["width"] - 20, collapsed
                assert browser.find_element(By.ID, "show-sessions").get_attribute("aria-label") == "Show sessions"
                browser.save_screenshot("/tmp/zedlink-browser-fixture-wide-collapsed.png")
                browser.find_element(By.ID, "show-sessions").click()
                assert browser.find_element(By.ID, "show-sessions").get_attribute("aria-label") == "Hide sessions"
                browser.save_screenshot("/tmp/zedlink-browser-fixture-wide.png")
                browser.set_window_size(390, 844)
                layout = browser.execute_script("return {width:innerWidth, pageWidth:document.documentElement.scrollWidth, composerBottom:document.getElementById('composer-form').getBoundingClientRect().bottom, height:innerHeight, messagesHeight:document.getElementById('messages').getBoundingClientRect().height, sidebarHidden:getComputedStyle(document.querySelector('.sidebar')).display==='none'}")
                assert layout["pageWidth"] <= layout["width"] + 1
                assert layout["composerBottom"] <= layout["height"]
                assert not browser.find_element(By.ID, "tab-sessions").is_displayed()
                assert browser.find_element(By.CSS_SELECTOR, ".topbar").is_displayed()
                browser.save_screenshot("/tmp/zedlink-browser-fixture-mobile.png")
                assert layout["messagesHeight"] >= 390 and layout["sidebarHidden"], layout
                assert browser.find_element(By.ID, "prompt").is_displayed()
                assert browser.find_element(By.ID, "send").is_displayed()
                assert not browser.find_elements(By.ID, "toggle-compose")
                assert browser.find_element(By.ID, "send").get_attribute("aria-label") == "Send message"
                browser.find_element(By.ID, "show-sessions").click()
                assert browser.find_element(By.ID, "sessions-panel").is_displayed()
                assert browser.find_element(By.ID, "tab-sessions").is_displayed()
                browser.find_element(By.CSS_SELECTOR, ".thread-item").click()
                wait.until(lambda driver: driver.find_element(By.CSS_SELECTOR, ".workspace").is_displayed())
                assert browser.find_element(By.ID, "activity-toggle").get_attribute("aria-expanded") == "false"
                assert not browser.find_element(By.ID, "activity-content").is_displayed()
                browser.find_element(By.ID, "show-sessions").click()
                browser.find_element(By.ID, "tab-connections").click()
                assert browser.find_element(By.ID, "connection-panel").is_displayed()
                assert browser.find_element(By.ID, "device-network-state").text.casefold() == "online"
                assert browser.find_element(By.ID, "gateway-connection-state").text.casefold() == "reachable"
                assert browser.find_element(By.ID, "zed-connection-state").text.casefold() == "connected"
                assert browser.find_element(By.ID, "stream-connection-state").text.casefold() in ("live", "connecting…", "polling")
                browser.find_element(By.ID, "tab-settings").click()
                assert browser.find_element(By.ID, "settings-panel").is_displayed()
                browser.find_element(By.ID, "tab-sessions").click()
                assert browser.find_element(By.ID, "sessions-panel").is_displayed()
                probe.extra_thread = True
                browser.find_element(By.ID, "refresh").click()
                wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, ".thread-item")) == 3)
                browser.find_elements(By.CSS_SELECTOR, ".thread-item")[1].click()
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Second synthetic thread")
                assert browser.find_element(By.ID, "messages").is_displayed()
                assert browser.find_element(By.ID, "send").is_enabled()
                assert probe.accepted == accepted_before_browser + 2
                browser.refresh()
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").get_attribute("textContent") == "Second synthetic thread")
                assert browser.find_element(By.ID, "messages").is_displayed()
                assert not browser.find_element(By.ID, "delivery-details").is_displayed()
                assert probe.accepted == accepted_before_browser + 2
                original_tab = browser.current_window_handle
                second_tab_url = base + "/#gateway=" + info["gateway_id"]
                browser.execute_script("window.open('about:blank', '_blank')")
                browser.switch_to.window(next(handle for handle in browser.window_handles if handle != original_tab))
                browser.get(second_tab_url)
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").get_attribute("textContent") == "Second synthetic thread")
                assert browser.find_element(By.ID, "messages").is_displayed()
                wait.until(lambda driver: not driver.find_element(By.ID, "pair-panel").is_displayed())
                assert probe.accepted == accepted_before_browser + 2
                browser.close()
                browser.switch_to.window(original_tab)
                probe.close()
                wait.until(lambda driver: "Zed unavailable" in driver.find_element(By.ID, "connection").get_attribute("textContent"))
                assert browser.find_element(By.ID, "zed-connection-state").get_attribute("textContent") == "Unavailable"
                os.unlink(probe.path)
                probe = ProbeFixture(probe_dir / "zedlink.sock")
                probe.extra_thread = True
                wait.until(lambda driver: "online" in driver.find_element(By.ID, "connection").get_attribute("class")
                           and "Zed" in driver.find_element(By.ID, "connection").get_attribute("textContent"))
                assert browser.find_element(By.ID, "zed-connection-state").get_attribute("textContent") == "Connected"
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").get_attribute("textContent") == "Second synthetic thread")
                assert browser.find_element(By.ID, "messages").is_displayed()
                browser_device = next(device for device in admin(state, "devices")["devices"]
                                      if device["name"] == "Firefox on Linux")
                assert admin(state, "revoke", browser_device["id"])["revoked"]
                try:
                    WebDriverWait(browser, 15).until(
                        lambda driver: driver.find_element(By.ID, "pair-panel").is_displayed()
                    )
                except TimeoutException:
                    print("revocation browser state:", browser.execute_script(
                        "return {pair:!document.getElementById('pair-panel').classList.contains('hidden'),"
                        "pairDisplay:getComputedStyle(document.getElementById('pair-panel')).display,"
                        "body:document.body.className, live:document.body.dataset.liveTransport,"
                        "connection:document.getElementById('connection').textContent}"
                    ))
                    raise
                assert browser.find_element(By.ID, "expected-id").get_attribute("value") == info["gateway_id"]
                assert browser.find_element(By.ID, "pair-origin").get_attribute("textContent") == base
                assert browser.find_element(By.ID, "manual-confirm").is_displayed()
                assert not browser.find_element(By.ID, "verify-gateway").is_selected()
                manual_layout = browser.execute_script(
                    "return {top:document.getElementById('pair-code').getBoundingClientRect().top,"
                    "bottom:document.getElementById('pair-code').getBoundingClientRect().bottom,height:innerHeight}"
                )
                assert 0 <= manual_layout["top"] and manual_layout["bottom"] <= manual_layout["height"], manual_layout
                browser.save_screenshot("/tmp/zedlink-browser-manual-pairing-mobile.png")
                manual_code = admin(state, "pair-short-code")["code"]
                browser.find_element(By.ID, "pair-code").send_keys(manual_code)
                assert not browser.find_element(By.ID, "pair-button").is_enabled()
                browser.find_element(By.ID, "verify-gateway").click()
                assert browser.find_element(By.ID, "pair-button").is_enabled()
                browser.find_element(By.ID, "pair-button").click()
                wait.until(lambda driver: not driver.find_element(By.ID, "pair-panel").is_displayed())
                assert (browser.find_element(By.ID, "sessions-panel").is_displayed()
                        or browser.find_element(By.CSS_SELECTOR, ".workspace").is_displayed())
                manual_device = next(device for device in admin(state, "devices")["devices"]
                                     if device["name"] == "Firefox on Linux")
                assert admin(state, "revoke", manual_device["id"])["revoked"]
                WebDriverWait(browser, 15).until(
                    lambda driver: driver.find_element(By.ID, "pair-panel").is_displayed()
                )
                helper = subprocess.run(["python3", str(ROOT / "tools/pair_phone.py"), base, str(state), "--no-open"],
                                        capture_output=True, text=True, check=True, timeout=5)
                pairing_page = Path(helper.stdout.splitlines()[0].split(": ", 1)[1])
                assert pairing_page.stat().st_mode & 0o077 == 0
                pairing_html = pairing_page.read_text()
                match = re.search(r'<div class="code">(\d{5}) (\d{5})</div>', pairing_html)
                assert match is not None
                quick_code = "".join(match.groups())
                expected_link = base + "/#" + urllib.parse.urlencode(
                    {"v": "1", "gateway": info["gateway_id"], "pair": quick_code})
                assert qr_svg(expected_link) in pairing_html
                assert '<title>Pair a ZedLink device</title>' in pairing_html
                assert "Already using the iPhone home-screen app?" in pairing_html
                assert f"Gateway ID <code>{info['gateway_id']}</code>" in pairing_html
                assert f'href="{html.escape(expected_link, quote=True)}"' in pairing_html
                browser.get(base + "/?pair-test=wrong#v=1&gateway=wrong-gateway&pair=" + quick_code)
                wait.until(lambda driver: "gateway identity differs" in
                           driver.find_element(By.ID, "pair-notice").get_attribute("textContent").lower())
                assert not admin(state, "devices")["devices"]
                assert "pair=" not in browser.current_url
                browser.get(base + "/?pair-test=correct#v=1&gateway=" + info["gateway_id"] + "&pair=" + quick_code)
                wait.until(lambda driver: not driver.find_element(By.ID, "pair-panel").is_displayed())
                assert (browser.find_element(By.ID, "sessions-panel").is_displayed()
                        or browser.find_element(By.CSS_SELECTOR, ".workspace").is_displayed())
                assert "pair=" not in browser.current_url
                quick_device = next(device for device in admin(state, "devices")["devices"]
                                    if device["name"] == "Firefox on Linux")
                browser.refresh()
                wait.until(lambda driver: not driver.find_element(By.ID, "pair-panel").is_displayed())
                assert (browser.find_element(By.ID, "sessions-panel").is_displayed()
                        or browser.find_element(By.CSS_SELECTOR, ".workspace").is_displayed())
                assert admin(state, "revoke", quick_device["id"])["revoked"]
            finally:
                browser.quit()
            chromium = shutil.which("chromium") or shutil.which("google-chrome")
            if not chromium:
                print("SKIP: Chromium browser check (Chromium is unavailable)")
            else:
                chromium_code = admin(state, "pair-short-code")["code"]
                chromium_link = base + "/#" + urllib.parse.urlencode(
                    {"v": "1", "gateway": info["gateway_id"], "pair": chromium_code})
                chromium_profile = root / "chromium-profile"
                chromium_command = [chromium, "--headless", "--no-sandbox",
                                    "--ignore-certificate-errors", "--disable-gpu",
                                    f"--user-data-dir={chromium_profile}",
                                    "--virtual-time-budget=6000", "--dump-dom"]
                first_page = subprocess.run(chromium_command + [chromium_link], check=True,
                                            capture_output=True, text=True, timeout=20).stdout
                assert re.search(r'<section class="panel hidden" id="pair-panel">', first_page)
                assert re.search(r'<section class="panel" id="sessions-panel">', first_page)
                chromium_device = next(device for device in admin(state, "devices")["devices"]
                                       if device["name"] == "Chrome on Linux")
                second_page = subprocess.run(chromium_command + [base + "/"], check=True,
                                             capture_output=True, text=True, timeout=20).stdout
                assert re.search(r'<section class="panel" id="sessions-panel">', second_page)
                assert admin(state, "revoke", chromium_device["id"])["revoked"]
            print("PASS: private bind/state, TLS identity, installable PWA shell/mobile navigation, authenticated Web Push configuration, paired browser UI, exact-turn cancellation, retry/reload without duplicate send, pairing lockout/one-use, device-scoped send/status, gateway restart, method allowlist, WSS and credential revocation")
        finally:
            server.terminate()
            try:
                server.communicate(timeout=3)
            except subprocess.TimeoutExpired:
                server.kill()
                server.communicate()
            probe.close()


if __name__ == "__main__":
    main()
