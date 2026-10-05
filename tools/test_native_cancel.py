#!/usr/bin/env python3
"""Exercise a guarded cancel in one explicitly exposed disposable native Zed thread."""

import argparse
import time
import uuid

from test_native_fixture import counters, rpc


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True)
    parser.add_argument("--fixture-url", default="http://127.0.0.1:54259")
    args = parser.parse_args()
    if not args.fixture_url.startswith("http://127.0.0.1:"):
        parser.error("fixture must use loopback HTTP")

    info = rpc(args.socket, "instance.info", {})
    threads = rpc(args.socket, "thread.list", {})["threads"]
    if len(threads) != 1:
        parser.exit(3, f"NOT RUN: expected one exposed disposable thread, found {len(threads)}\n")
    thread_id = threads[0]["thread_id"]
    before = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
    if before["status"] != "Idle" or before["truncated"]:
        parser.exit(3, "NOT RUN: thread is not idle or snapshot is truncated\n")

    baseline = len(before["entries_markdown"])
    delay_before = counters(args.fixture_url + "/fixture/counters")["delay"]
    marker = "ZEDLINK_FIXTURE_DELAY " + uuid.uuid4().hex
    rpc(args.socket, "thread.send", {"instance_id": info["instance_id"],
        "epoch": info["epoch"], "thread_id": thread_id, "text": marker})

    turn_id = None
    first_chunk = False
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        snap = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
        turn_id = snap.get("current_turn_id")
        added = snap["entries_markdown"][baseline:]
        first_chunk = any("Delayed fixture" in entry for entry in added)
        if turn_id is not None and first_chunk:
            break
        time.sleep(0.08)
    if turn_id is None or not first_chunk:
        raise RuntimeError("native turn or first fixture chunk did not appear before cancel")
    if counters(args.fixture_url + "/fixture/counters")["delay"] != delay_before + 1:
        raise RuntimeError("delayed response did not originate in fixture")

    params = {"instance_id": info["instance_id"], "epoch": info["epoch"],
              "thread_id": thread_id, "turn_id": turn_id}
    outcome = rpc(args.socket, "thread.cancel", params)
    if outcome.get("outcome") != "requested":
        raise RuntimeError("native cancel did not accept exact active turn")
    time.sleep(0.4)
    settled = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
    settled_entries = settled["entries_markdown"][baseline:]
    time.sleep(3.5)
    later = rpc(args.socket, "thread.snapshot", {"thread_id": thread_id})
    if later["entries_markdown"][baseline:] != settled_entries:
        raise RuntimeError("visible native entries changed after cancel settled")
    if any("response complete." in entry for entry in later["entries_markdown"][baseline:]):
        raise RuntimeError("cancelled response completed visibly")
    if later["current_turn_id"] is not None:
        raise RuntimeError("native turn still active after cancel")
    try:
        rpc(args.socket, "thread.cancel", params)
    except RuntimeError as exc:
        if "STALE_TURN" not in str(exc):
            raise
    else:
        raise RuntimeError("replayed cancel did not reject a stale turn")
    print({"result": "PASS", "thread_id": thread_id, "turn_id": turn_id,
           "fixture_calls": 1, "visible_state_stable": True, "stale_replay_rejected": True})


if __name__ == "__main__":
    main()
