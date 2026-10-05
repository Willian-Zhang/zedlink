#!/usr/bin/env python3
"""Drive paired Firefox Stop through HTTPS into one disposable native Zed Agent turn."""

import argparse
import json
import subprocess
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options as FirefoxOptions
from selenium.webdriver.firefox.service import Service as FirefoxService
from selenium.webdriver.support.ui import WebDriverWait

from test_native_fixture import counters, rpc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--gateway-id", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--fixture-url", default="http://127.0.0.1:54259")
    parser.add_argument("--allow-shared-gateway", action="store_true",
                        help="Explicitly permit testing a non-loopback gateway with existing pairings")
    args = parser.parse_args()
    if not args.base_url.startswith("https://") or not args.fixture_url.startswith("http://127.0.0.1:"):
        parser.error("verified HTTPS gateway and loopback model fixture are required")
    if urlparse(args.base_url).hostname not in ("localhost", "127.0.0.1") and not args.allow_shared_gateway:
        parser.error("use an isolated localhost gateway for fixture tests; --allow-shared-gateway overrides this guard")
    binary = Path(__file__).resolve().parents[1] / "gateway/target/debug/zedlink-gateway"

    def admin(*command):
        completed = subprocess.run([str(binary), "admin", str(args.state_dir), *command],
                                   capture_output=True, text=True, check=True, timeout=8)
        return json.loads(completed.stdout)

    info = rpc(args.socket, "instance.info", {})
    if "thread.cancel" not in info.get("capabilities", []):
        raise RuntimeError("native instance does not advertise Stop")
    listing = rpc(args.socket, "thread.list", {})
    if len(listing["threads"]) != 1 or listing["epoch"] != info["epoch"]:
        raise RuntimeError("expected one exposed disposable native thread")
    thread_id = listing["threads"][0]["thread_id"]
    baseline = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
    if baseline["status"] != "Idle" or baseline["truncated"]:
        raise RuntimeError("native thread is not idle or snapshot is truncated")
    initial_entries = len(baseline["entries_markdown"])
    fixture_before = counters(args.fixture_url + "/fixture/counters")["browser_stop"]
    devices_before = {device["id"] for device in admin("devices")["devices"]}
    code = admin("pair-short-code")["code"]
    options = FirefoxOptions()
    options.add_argument("-headless")
    options.set_preference("network.proxy.type", 0)
    browser = webdriver.Firefox(service=FirefoxService("/usr/bin/geckodriver"), options=options)
    try:
        wait = WebDriverWait(browser, 15)
        browser.get(args.base_url.rstrip("/") + "/#gateway=" + args.gateway_id)
        wait.until(lambda driver: driver.find_element(By.ID, "gateway-id").text == args.gateway_id)
        browser.find_element(By.ID, "pair-code").send_keys(code)
        browser.find_element(By.ID, "pair-button").click()
        wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item"))
        browser.find_element(By.CSS_SELECTOR, ".thread-item").click()
        wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text)
        marker = "ZEDLINK_FIXTURE_BROWSER_STOP " + uuid.uuid4().hex
        browser.find_element(By.ID, "prompt").send_keys(marker)
        browser.find_element(By.ID, "send").click()
        wait.until(lambda driver: "Browser stop fixture" in driver.find_element(By.ID, "messages").text)
        wait.until(lambda driver: driver.find_element(By.ID, "stop-turn").is_displayed())
        active = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
        turn_id = active["current_turn_id"]
        if turn_id is None:
            raise RuntimeError("native turn finished before browser Stop")
        browser.find_element(By.ID, "stop-turn").click()
        wait.until(lambda driver: "Stop requested" in driver.find_element(By.ID, "notice").text)
        time.sleep(0.4)
        settled = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
        time.sleep(1.5)
        later = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
        if settled["entries_markdown"][initial_entries:] != later["entries_markdown"][initial_entries:]:
            raise RuntimeError("native transcript changed after browser Stop")
        if later["current_turn_id"] is not None:
            raise RuntimeError("native turn remained active after browser Stop")
        if any("response complete." in entry for entry in later["entries_markdown"][initial_entries:]):
            raise RuntimeError("cancelled fixture reply completed visibly")
        if counters(args.fixture_url + "/fixture/counters")["browser_stop"] != fixture_before + 1:
            raise RuntimeError("browser prompt did not reach fixture model exactly once")
        print(json.dumps({"result": "PASS", "instance_id": info["instance_id"],
                          "thread_id": thread_id, "turn_id": turn_id,
                          "browser_stop_visible": True, "native_state_stable": True,
                          "fixture_calls": 1}))
    finally:
        browser.quit()
        new_devices = [device for device in admin("devices")["devices"]
                       if device["id"] not in devices_before]
        for device in new_devices:
            admin("revoke", device["id"])


if __name__ == "__main__":
    main()
