#!/usr/bin/env python3
"""Verify 64k native auto-compaction in an isolated Zed profile and loopback model."""

import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from test_native_fixture import rpc


ROOT = Path(__file__).resolve().parents[1]
MODELS = ("zedlink-main-64k", "zedlink-summary-wide", "zedlink-title")


def until(check, timeout=45):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError("Timed out waiting for native auto-compaction fixture")


class ModelFixture(BaseHTTPRequestHandler):
    requests = []
    request_tags = []
    lock = threading.Lock()

    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path != "/v1/models":
            self.send_error(404)
            return
        body = json.dumps({"object": "list", "data": [
            {"id": model, "object": "model", "owned_by": "fixture"} for model in MODELS
        ]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 0 < length <= 1024 * 1024:
            self.send_error(413)
            return
        request = json.loads(self.rfile.read(length))
        model = request.get("model")
        if model not in MODELS or request.get("stream") is not True:
            self.send_error(400)
            return
        messages_text = json.dumps(request.get("messages", []))
        tag = "second" if "Second fixture turn." in messages_text else (
            "first" if "First fixture turn." in messages_text else "other"
        )
        with self.lock:
            self.requests.append(model)
            self.request_tags.append(tag)
            main_count = self.requests.count(MODELS[0])
        usage = 49_152 if model == MODELS[0] and main_count == 1 else 100
        answer = "Condensed fixture context." if model == MODELS[1] else "Fixture ready."
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        for event in (
            {"choices": [{"index": 0, "delta": {"content": answer}, "finish_reason": None}], "usage": None},
            {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": None},
            {"choices": [], "usage": {"prompt_tokens": usage, "completion_tokens": 8,
                                       "total_tokens": usage + 8}},
        ):
            self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def main():
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        raise SystemExit("NOT RUN: a graphical session is required")
    with tempfile.TemporaryDirectory(prefix="zedlink-auto-compaction-") as directory:
        fixture = Path(directory)
        project, profile, probe = (fixture / name for name in ("project", "profile", "probe"))
        project.mkdir()
        (profile / "config").mkdir(parents=True)
        probe.mkdir(mode=0o700)
        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelFixture)
        server.daemon_threads = True
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        url = f"http://127.0.0.1:{server.server_port}/v1"
        models = [
            {"name": MODELS[0], "max_tokens": 65_536, "max_output_tokens": 2_048,
             "capabilities": {"chat_completions": True, "images": False}},
            {"name": MODELS[1], "max_tokens": 262_144, "max_output_tokens": 16_384,
             "capabilities": {"chat_completions": True, "images": False}},
            {"name": MODELS[2], "max_tokens": 65_536, "max_output_tokens": 2_048,
             "capabilities": {"chat_completions": True, "images": False}},
        ]
        settings = {
            "zedlink": {"allow_session_creation": True},
            "session": {"trust_all_worktrees": True},
            "agent": {
                "default_model": {"provider": "openai", "model": MODELS[0]},
                "compaction_model": {"provider": "openai", "model": MODELS[1]},
                "thread_summary_model": {"provider": "openai", "model": MODELS[2]},
                "default_profile": "write",
                "auto_compact": {"enabled": True, "threshold": 65_536},
            },
            "language_models": {"openai": {"api_url": url, "available_models": models}},
        }
        (profile / "config/settings.json").write_text(json.dumps(settings))
        environment = {**os.environ, "ZED_RELEASE_CHANNEL": "dev",
                       "OPENAI_API_KEY": "disposable-fixture",
                       "ZEDLINK_PROBE_DIR": str(probe),
                       "ZEDLINK_PROBE_PROJECT_ROOT": str(project)}
        process = None
        try:
            with (fixture / "zed.log").open("w") as log:
                process = subprocess.Popen(
                    [str(ROOT / "zed-source/target/debug/zed"), "--user-data-dir", str(profile), str(project)],
                    env=environment, stdout=log, stderr=log,
                )
                socket = str(probe / "zedlink.sock")
                def ready():
                    if process.poll() is not None or not Path(socket).exists():
                        return None
                    try:
                        return rpc(socket, "instance.info", {})
                    except (OSError, RuntimeError):
                        return None
                info = until(ready)
                identity = {"instance_id": info["instance_id"], "epoch": info["epoch"]}
                create_request_id = str(uuid.uuid4())
                def create():
                    try:
                        return rpc(socket, "thread.create", {
                            **identity, "title": "Disposable 64k compaction fixture",
                        }, create_request_id).get("thread_id")
                    except RuntimeError as error:
                        if "INSTANCE_UNAVAILABLE" in str(error):
                            current = rpc(socket, "instance.info", {})
                            identity.update(instance_id=current["instance_id"], epoch=current["epoch"])
                            return None
                        raise
                thread_id = until(create)
                identity["thread_id"] = thread_id

                rpc(socket, "thread.send", {**identity, "text": "First fixture turn."}, str(uuid.uuid4()))
                until(lambda: MODELS[0] in ModelFixture.requests)
                until(lambda: rpc(socket, "thread.snapshot", identity)["status"] == "Idle")
                first_usage = rpc(socket, "thread.settings", identity).get("context_usage")
                assert first_usage and first_usage.get("input_tokens") == 49_152, first_usage
                assert MODELS[1] not in ModelFixture.requests, "compacted before the next turn"

                rpc(socket, "thread.send", {**identity, "text": "Second fixture turn."}, str(uuid.uuid4()))
                try:
                    until(lambda: MODELS[1] in ModelFixture.requests, timeout=15)
                except AssertionError:
                    snapshot = rpc(socket, "thread.snapshot", identity)
                    thread_settings = rpc(socket, "thread.settings", identity)
                    print("fixture_models_seen", list(ModelFixture.requests))
                    print("fixture_request_tags", list(ModelFixture.request_tags))
                    print("fixture_thread_status", snapshot.get("status"))
                    print("fixture_context_usage", thread_settings.get("context_usage"))
                    print("fixture_error_present", bool(snapshot.get("agent_error")))
                    raise
                until(lambda: ModelFixture.requests.count(MODELS[0]) >= 2)
                until(lambda: rpc(socket, "thread.snapshot", identity)["status"] == "Idle")
                sequence = [model for model in ModelFixture.requests if model != MODELS[2]]
                assert sequence[:3] == [MODELS[0], MODELS[1], MODELS[0]], sequence
                print("PASS: native 64k thread auto-compacted with wide model before second turn")
        finally:
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=10)
            server.shutdown()
            server.server_close()


if __name__ == "__main__":
    main()
