#!/usr/bin/env python3
"""One real native-thread streaming check against an explicitly exposed disposable Zed thread."""

import argparse
import json
import socket
import time
import urllib.request
import uuid


def rpc(socket_path, method, params, request_id=None):
    request_id = request_id or str(uuid.uuid4())
    request = {"version": 1, "request_id": request_id, "method": method, "params": params}
    with socket.socket(socket.AF_UNIX) as stream:
        stream.settimeout(8)
        stream.connect(socket_path)
        stream.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
        with stream.makefile("rb") as reader:
            raw = reader.readline(1024 * 1024 + 1)
    if not raw or len(raw) > 1024 * 1024:
        raise RuntimeError("missing or oversized native response")
    response = json.loads(raw)
    if response.get("version") != 1 or response.get("request_id") != request_id:
        raise RuntimeError("native response envelope mismatch")
    if "error" in response:
        raise RuntimeError(f"native {method}: {response['error'].get('code')}")
    return response["result"]


def counters(url):
    with urllib.request.urlopen(url, timeout=5) as response:
        return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--fixture-url", default="http://127.0.0.1:54259")
    parser.add_argument("--timeout", type=float, default=45)
    args = parser.parse_args()
    if args.timeout <= 0 or not args.fixture_url.startswith("http://127.0.0.1:"):
        parser.error("fixture must use loopback HTTP and timeout must be positive")

    info = rpc(args.socket, "instance.info", {})
    listing = rpc(args.socket, "thread.list", {})
    threads = listing["threads"]
    if len(threads) != 1:
        parser.exit(3, f"NOT RUN: expected exactly one explicitly exposed native thread, found {len(threads)}; no prompt sent\n")
    if (listing["instance_id"], listing["epoch"]) != (info["instance_id"], info["epoch"]):
        raise RuntimeError("native instance changed before sending")
    thread_id = threads[0]["thread_id"]
    before = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
    if before["truncated"]:
        raise RuntimeError("baseline snapshot truncated")
    if before["status"] != "Idle":
        raise RuntimeError("exposed native thread must be idle for this fixture check")
    initial_entries = len(before["entries_markdown"])
    initial_sequence = before["last_sequence"]
    initial_calls = counters(args.fixture_url + "/fixture/counters")["stream"]
    marker = "ZEDLINK_FIXTURE_STREAM " + uuid.uuid4().hex
    send_id = "native-fixture-" + uuid.uuid4().hex
    params = {"instance_id": info["instance_id"], "epoch": info["epoch"],
              "thread_id": thread_id, "text": marker}
    first = rpc(args.socket, "thread.send", params, send_id)
    retry = rpc(args.socket, "thread.send", params, send_id)
    if first != retry or first["outcome"] not in ("unknown", "queued"):
        raise RuntimeError("native retry changed its provisional submission result")
    status = rpc(args.socket, "request.status", {"instance_id": info["instance_id"],
                 "epoch": info["epoch"], "original_request_id": send_id})
    if not status["known"]:
        raise RuntimeError("native request ledger lost the submitted ID")

    deadline = time.monotonic() + args.timeout
    saw_event = False
    while time.monotonic() < deadline:
        events = rpc(args.socket, "thread.events", {"thread_id": thread_id,
                     "after_sequence": initial_sequence})
        saw_event = saw_event or bool(events["events"])
        snapshot = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
        if snapshot["truncated"]:
            raise RuntimeError("result snapshot truncated")
        added = snapshot["entries_markdown"][initial_entries:]
        user_matches = sum(marker in entry for entry in added)
        assistant_matches = sum("Fixture stream response complete." in entry for entry in added)
        model_calls = counters(args.fixture_url + "/fixture/counters")["stream"] - initial_calls
        if user_matches == 1 and assistant_matches == 1 and model_calls >= 1 and saw_event:
            print(json.dumps({"result": "PASS", "instance_id": info["instance_id"],
                              "epoch": info["epoch"], "thread_id": thread_id,
                              "request_id": send_id, "user_entries": user_matches,
                              "assistant_entries": assistant_matches,
                              "fixture_calls": model_calls, "native_events_observed": saw_event,
                              "submission_outcome": first["outcome"]}, indent=2))
            return
        if user_matches > 1 or assistant_matches > 1:
            raise RuntimeError("duplicate native entry detected")
        time.sleep(0.25)
    raise RuntimeError("timed out before a single matching native turn and fixture call were observed")


if __name__ == "__main__":
    main()
