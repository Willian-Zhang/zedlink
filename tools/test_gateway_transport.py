#!/usr/bin/env python3
"""Local gateway transport fixture; this does not test native Zed behavior."""
import json
import os
import socket
import ssl
import subprocess
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

from websockets.sync.client import connect
from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "gateway/target/debug/zedlink-gateway"


class ProbeFixture:
    def __init__(self, path):
        self.path = path
        self.seen_sends = {}
        self.accepted = 0
        self.entries = ['<img src=x onerror="window.syntheticXss=1">']
        self.sequence = 0
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
                result = {}
                error = None
                if method == "thread.list":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "threads": [{"thread_id": "fixture-thread", "title": "Synthetic test thread", "status": "Idle"}]}
                elif method == "thread.snapshot":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": "fixture-thread", "title": "Synthetic test thread",
                              "status": "Idle", "truncated": False,
                              "entries_markdown": list(self.entries), "pending_approvals": [],
                              "last_sequence": self.sequence}
                elif method == "thread.events":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": params["thread_id"],
                              "events": [{"sequence": self.sequence, "kind": "entry.added"}]
                              if params["after_sequence"] < self.sequence else [],
                              "last_sequence": self.sequence}
                elif method == "thread.send":
                    key = request["request_id"]
                    text = params["text"]
                    if key in self.seen_sends and self.seen_sends[key] != text:
                        error = {"code": "REQUEST_ID_CONFLICT"}
                    else:
                        if key not in self.seen_sends:
                            self.seen_sends[key] = text
                            self.accepted += 1
                            self.entries.extend([text, "Synthetic fixture reply."])
                            self.sequence += 1
                        result = {"outcome": "unknown"}
                elif method == "request.status":
                    key = params["original_request_id"]
                    result = {"known": key in self.seen_sends, "outcome": "unknown"}
                elif method == "instance.info":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch"}
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
            denied = dict(request, method="approval.respond")
            status, _ = http(base, context, "/v1/rpc", "POST", denied, token1)
            assert status == 403
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
                browser.find_element(By.ID, "expected-id").clear()
                browser.find_element(By.ID, "expected-id").send_keys("wrong-gateway")
                browser.find_element(By.ID, "pair-code").send_keys(browser_code)
                browser.find_element(By.ID, "pair-button").click()
                wait.until(lambda driver: "Pairing code was not sent" in driver.find_element(By.ID, "notice").text)
                assert not admin(state, "devices")["devices"]
                browser.find_element(By.ID, "expected-id").clear()
                browser.find_element(By.ID, "expected-id").send_keys(info["gateway_id"])
                browser.find_element(By.ID, "pair-button").click()
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item"))
                browser.find_element(By.CSS_SELECTOR, ".thread-item").click()
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Synthetic test thread")
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
                browser.find_element(By.ID, "retry").click()
                time.sleep(0.3)
                assert probe.accepted == accepted_before_browser + 1
                browser.save_screenshot("/tmp/zedlink-browser-fixture.png")
                browser.set_window_size(390, 844)
                layout = browser.execute_script("return {width:innerWidth, pageWidth:document.documentElement.scrollWidth, composerBottom:document.getElementById('composer-form').getBoundingClientRect().bottom, height:innerHeight, messagesHeight:document.getElementById('messages').getBoundingClientRect().height, sidebarHidden:getComputedStyle(document.querySelector('.sidebar')).display==='none'}")
                assert layout["pageWidth"] <= layout["width"] + 1
                assert layout["composerBottom"] <= layout["height"]
                browser.save_screenshot("/tmp/zedlink-browser-fixture-mobile.png")
                assert layout["messagesHeight"] >= 250 and layout["sidebarHidden"], layout
                browser.find_element(By.ID, "show-sessions").click()
                assert browser.find_element(By.ID, "sessions-panel").is_displayed()
                browser.find_element(By.CSS_SELECTOR, ".thread-item").click()
                wait.until(lambda driver: driver.find_element(By.ID, "messages").is_displayed())
                browser.refresh()
                wait.until(lambda driver: "A previous send has uncertain delivery" in
                           driver.execute_script("return document.getElementById('delivery').textContent"))
                assert probe.accepted == accepted_before_browser + 1
                browser_device = next(device for device in admin(state, "devices")["devices"]
                                      if device["name"] == "Browser")
                assert admin(state, "revoke", browser_device["id"])["revoked"]
                wait.until(lambda driver: driver.find_element(By.ID, "pair-panel").is_displayed())
            finally:
                browser.quit()
            print("PASS: private bind/state, TLS identity, paired browser UI, retry/reload without duplicate send, pairing lockout/one-use, device-scoped send/status, gateway restart, method allowlist, WSS and credential revocation")
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
