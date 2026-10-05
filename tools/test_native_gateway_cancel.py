#!/usr/bin/env python3
"""Cancel one delayed turn in an exposed disposable native Zed thread through paired HTTPS."""

import argparse
import json
import ssl
import subprocess
import time
import urllib.request
import uuid
from pathlib import Path

from test_native_fixture import counters


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--gateway-id", required=True)
    parser.add_argument("--state-dir", type=Path, required=True)
    parser.add_argument("--fixture-url", default="http://127.0.0.1:54259")
    args = parser.parse_args()
    if not args.base_url.startswith("https://") or not args.fixture_url.startswith("http://127.0.0.1:"):
        parser.error("verified HTTPS gateway and loopback model fixture are required")
    binary = Path(__file__).resolve().parents[1] / "gateway/target/debug/zedlink-gateway"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}),
                                         urllib.request.HTTPSHandler(context=ssl.create_default_context()))

    def http(path, payload=None, token=None):
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(args.base_url.rstrip("/") + path,
            data=json.dumps(payload).encode() if payload is not None else None,
            headers=headers, method="POST" if payload is not None else "GET")
        with opener.open(request, timeout=8) as response:
            return json.load(response)

    def admin(*command):
        completed = subprocess.run([str(binary), "admin", str(args.state_dir), *command],
                                   capture_output=True, text=True, check=True, timeout=8)
        return json.loads(completed.stdout)

    def rpc(method, params=None):
        request_id = str(uuid.uuid4())
        response = http("/v1/rpc", {"version": 1, "request_id": request_id,
                                    "method": method, "params": params or {}}, token)
        if response.get("version") != 1 or response.get("request_id") != request_id:
            raise RuntimeError("gateway RPC envelope mismatch")
        if "error" in response:
            raise RuntimeError(f"{method}: {response['error'].get('code')}")
        return response["result"]

    gateway = http("/v1/gateway")
    if gateway.get("gateway_id") != args.gateway_id:
        raise RuntimeError("trusted gateway identity mismatch; no pairing attempted")
    code = admin("pair-short-code")["code"]
    pairing = http("/v1/pair", {"code": code, "device_name": "Native cancel validation"})
    token = pairing["token"]
    device_id = pairing["device_id"]
    try:
        info = rpc("instance.info")
        listing = rpc("thread.list")
        if (listing["instance_id"], listing["epoch"]) != (info["instance_id"], info["epoch"]):
            raise RuntimeError("native identity changed")
        if len(listing["threads"]) != 1:
            raise RuntimeError("expected exactly one exposed disposable thread; no prompt sent")
        thread_id = listing["threads"][0]["thread_id"]
        before = rpc("thread.snapshot", {"thread_id": thread_id})
        if before["status"] != "Idle" or before["truncated"]:
            raise RuntimeError("native thread not ready for guarded cancellation")
        baseline = len(before["entries_markdown"])
        delay_before = counters(args.fixture_url + "/fixture/counters")["delay"]
        marker = "ZEDLINK_FIXTURE_DELAY " + uuid.uuid4().hex
        rpc("thread.send", {"instance_id": info["instance_id"], "epoch": info["epoch"],
                            "thread_id": thread_id, "text": marker})
        deadline = time.monotonic() + 15
        turn_id = None
        while time.monotonic() < deadline:
            snap = rpc("thread.snapshot", {"thread_id": thread_id})
            turn_id = snap.get("current_turn_id")
            if turn_id is not None and any("Delayed fixture" in entry
                                           for entry in snap["entries_markdown"][baseline:]):
                break
            time.sleep(0.08)
        else:
            raise RuntimeError("first native fixture chunk/turn not observed")
        if counters(args.fixture_url + "/fixture/counters")["delay"] != delay_before + 1:
            raise RuntimeError("fixture did not receive exactly one delayed call")
        params = {"instance_id": info["instance_id"], "epoch": info["epoch"],
                  "thread_id": thread_id, "turn_id": turn_id}
        outcome = rpc("thread.cancel", params)
        if outcome.get("outcome") != "requested" or outcome.get("turn_id") != turn_id:
            raise RuntimeError("exact native turn cancellation not acknowledged")
        time.sleep(0.4)
        settled = rpc("thread.snapshot", {"thread_id": thread_id})
        time.sleep(3.5)
        later = rpc("thread.snapshot", {"thread_id": thread_id})
        if settled["entries_markdown"][baseline:] != later["entries_markdown"][baseline:]:
            raise RuntimeError("native transcript changed after cancellation")
        if later["current_turn_id"] is not None:
            raise RuntimeError("cancelled native turn remains active")
        try:
            rpc("thread.cancel", params)
        except RuntimeError as exc:
            if "STALE_TURN" not in str(exc):
                raise
        else:
            raise RuntimeError("stale cancellation replay was not rejected")
        print(json.dumps({"result": "PASS", "instance_id": info["instance_id"],
                          "epoch": info["epoch"], "thread_id": thread_id,
                          "turn_id": turn_id, "fixture_calls": 1,
                          "visible_state_stable": True, "stale_replay_rejected": True}))
    finally:
        revoked = admin("revoke", device_id)
        if not revoked.get("revoked"):
            raise RuntimeError("temporary validation device was not revoked")


if __name__ == "__main__":
    main()
