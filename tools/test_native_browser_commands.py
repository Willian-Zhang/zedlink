#!/usr/bin/env python3
"""Opt-in browser /compact check against one exposed disposable native Zed thread."""
import argparse
import json
import os
import socket
import ssl
import subprocess
import tempfile
import time
import urllib.request
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait

ROOT = Path(__file__).resolve().parents[1]
BINARY = ROOT / "gateway/target/debug/zedlink-gateway"


def probe(socket_path, method, params):
    request = {"version": 1, "request_id": "browser-command-check-" + str(time.time_ns()),
               "method": method, "params": params}
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
        connection.settimeout(8)
        connection.connect(str(socket_path))
        connection.sendall(json.dumps(request).encode() + b"\n")
        with connection.makefile("rb") as response:
            data = json.loads(response.readline())
    if "error" in data:
        raise RuntimeError(f"native probe returned {data['error']['code']}")
    return data["result"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture-socket", required=True, type=Path)
    parser.add_argument("--expected-thread-id", required=True)
    args = parser.parse_args()
    if not str(args.fixture_socket).startswith("/tmp/"):
        parser.error("this test only accepts a disposable socket under /tmp")
    listing = probe(args.fixture_socket, "thread.list", {})
    threads = listing["threads"]
    selected = next((thread for thread in threads if thread["thread_id"] == args.expected_thread_id), None)
    if selected is None or selected["status"] != "Idle":
        parser.error("expected an idle, exposed disposable native thread with the requested ID")
    identity = {"instance_id": listing["instance_id"], "epoch": listing["epoch"],
                "thread_id": args.expected_thread_id}
    commands = probe(args.fixture_socket, "thread.commands", identity)["commands"]
    if not any(command["name"] == "compact" and command["category"] == "native" for command in commands):
        parser.error("the fixture native thread does not advertise /compact")
    initial = probe(args.fixture_socket, "thread.snapshot", {"thread_id": args.expected_thread_id})
    probe(args.fixture_socket, "thread.send", {**identity,
          "text": "Disposable browser command setup: reply with one short sentence."})
    for _ in range(100):
        prepared = probe(args.fixture_socket, "thread.snapshot", {"thread_id": args.expected_thread_id})
        if prepared["status"] == "Idle" and len(prepared["entries_markdown"]) >= len(initial["entries_markdown"]) + 2:
            break
        if prepared.get("pending_approvals"):
            raise AssertionError("fixture preparation unexpectedly requested an approval")
        time.sleep(0.2)
    else:
        raise AssertionError("fixture preparation did not finish a native Agent turn")
    before = probe(args.fixture_socket, "thread.snapshot", {"thread_id": args.expected_thread_id})
    before_count = sum("## Context Compaction" in entry for entry in before["entries_markdown"])
    with tempfile.TemporaryDirectory(prefix="zedlink-native-browser.") as temporary:
        root = Path(temporary)
        cert, key, state = root / "cert.pem", root / "key.pem", root / "state"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
        with socket.socket() as candidate:
            candidate.bind(("127.0.0.1", 0))
            port = candidate.getsockname()[1]
        server = subprocess.Popen([str(BINARY), "serve", f"127.0.0.1:{port}", str(cert),
                                   str(key), str(args.fixture_socket), str(state)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        try:
            for _ in range(100):
                if (state / "admin.sock").exists():
                    break
                if server.poll() is not None:
                    raise RuntimeError("gateway exited during startup")
                time.sleep(0.05)
            else:
                raise RuntimeError("gateway did not create its admin socket")
            code = json.loads(subprocess.check_output([str(BINARY), "admin", str(state), "pair-code"]))["code"]
            base = f"https://localhost:{port}"
            context = ssl.create_default_context(cafile=str(cert))
            def request(path, body=None):
                payload = json.dumps(body).encode() if body is not None else None
                headers = {"Content-Type": "application/json"} if payload else {}
                with urllib.request.urlopen(urllib.request.Request(base + path, payload, headers),
                                            context=context, timeout=5) as response:
                    return json.load(response)
            gateway_id = request("/v1/gateway")["gateway_id"]
            token = request("/v1/pair", {"code": code, "device_name": "native browser command test"})["token"]
            options = FirefoxOptions()
            options.add_argument("-headless")
            options.accept_insecure_certs = True
            options.set_preference("network.proxy.type", 0)
            browser = webdriver.Firefox(options=options, service=FirefoxService("/usr/bin/geckodriver"))
            try:
                browser.set_window_size(430, 844)
                browser.get(base + "/")
                browser.execute_script("localStorage.setItem(arguments[0], arguments[1])",
                                       f"zedlink.token.{gateway_id}", token)
                browser.refresh()
                wait = WebDriverWait(browser, 20)
                wait.until(lambda driver: driver.find_element(By.ID, "sessions-panel").is_displayed())
                cards = browser.find_elements(By.CSS_SELECTOR, ".thread-item")
                card = next((candidate for candidate in cards
                             if candidate.find_element(By.TAG_NAME, "strong").text == selected["title"]), None)
                if card is None:
                    raise AssertionError("selected native thread missing from paired browser")
                card.click()
                wait.until(lambda driver: driver.find_element(By.ID, "prompt").is_enabled())
                browser.find_element(By.ID, "show-commands").click()
                wait.until(lambda driver: "/compact" in driver.find_element(By.ID, "command-menu").text)
                browser.find_element(By.CSS_SELECTOR, ".command-option").click()
                assert browser.find_element(By.ID, "prompt").get_attribute("value") == "/compact"
                browser.find_element(By.ID, "send").click()
                for _ in range(100):
                    after = probe(args.fixture_socket, "thread.snapshot", {"thread_id": args.expected_thread_id})
                    count = sum("## Context Compaction" in entry for entry in after["entries_markdown"])
                    if count == before_count + 1 and after["status"] == "Idle":
                        break
                    time.sleep(0.2)
                else:
                    raise AssertionError("browser /compact did not complete in the native thread")
                assert not any(entry.startswith("## User\n\n/compact") for entry in after["entries_markdown"])
                try:
                    wait.until(lambda driver: "context summary" in driver.find_element(By.ID, "messages").text.lower())
                except TimeoutException:
                    print("browser state:", {name: browser.find_element(By.ID, name).text[:300]
                                             for name in ("connection", "notice", "delivery", "messages")})
                    raise
                print("PASS: paired browser command picker sent /compact through the same disposable native Zed thread")
            finally:
                browser.quit()
        finally:
            server.terminate()
            server.wait(timeout=5)


if __name__ == "__main__":
    main()
