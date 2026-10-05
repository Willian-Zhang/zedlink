#!/usr/bin/env python3
"""Loopback OpenAI Chat Completions fixture for disposable Zed profiles only."""
import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

MAX_BODY = 1024 * 1024
COUNTERS = {"stream": 0, "delay": 0, "approval": 0, "approval_followup": 0, "fallback": 0}
COUNTER_LOCK = threading.Lock()
TOOL_SHAPES = []
FIXTURE_ROOT = None


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_args):
        pass

    def do_GET(self):
        if self.path == "/v1/models":
            self.respond_json({"object": "list", "data": [
                {"id": "zedlink-fixture", "object": "model", "owned_by": "fixture"}
            ]})
        elif self.path == "/fixture/counters":
            with COUNTER_LOCK:
                self.respond_json(dict(COUNTERS))
        elif self.path == "/fixture/tools":
            with COUNTER_LOCK:
                self.respond_json(list(TOOL_SHAPES))
        else:
            self.send_error(404)

    def do_POST(self):
        if self.path != "/v1/chat/completions":
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            self.send_error(400)
            return
        if length < 1 or length > MAX_BODY:
            self.send_error(413)
            return
        try:
            request = json.loads(self.rfile.read(length))
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_error(400)
            return
        if request.get("model") != "zedlink-fixture":
            self.send_error(400)
            return
        shapes = []
        for tool in request.get("tools", [])[:50]:
            function = tool.get("function", {}) if isinstance(tool, dict) else {}
            parameters = function.get("parameters", {}) if isinstance(function, dict) else {}
            shapes.append({
                "name": function.get("name"),
                "required": parameters.get("required", []),
                "property_names": sorted(parameters.get("properties", {})),
            })
        with COUNTER_LOCK:
            TOOL_SHAPES[:] = shapes
        messages = request.get("messages", [])
        if not isinstance(messages, list):
            self.send_error(400)
            return
        last_user_index = next((index for index in range(len(messages) - 1, -1, -1)
                                if isinstance(messages[index], dict) and messages[index].get("role") == "user"), 0)
        current_turn = messages[last_user_index:]
        # Case markers are checked in memory. Prompts and tool arguments are never logged.
        serialized = json.dumps(current_turn, ensure_ascii=False)
        names = {tool["name"] for tool in shapes}
        has_tool_result = any(isinstance(message, dict) and message.get("role") == "tool"
                              for message in current_turn)
        if "ZEDLINK_FIXTURE_APPROVAL" in serialized and has_tool_result:
            case, pieces, pause = "approval_followup", ["Sentinel operation resolved."], 0
        elif "ZEDLINK_FIXTURE_APPROVAL" in serialized and FIXTURE_ROOT and "terminal" in names:
            case, pieces, pause = "approval", [], 0
        elif "ZEDLINK_FIXTURE_DELAY" in serialized:
            case, pieces, pause = "delay", ["Delayed fixture ", "response complete."], 1.5
        elif "ZEDLINK_FIXTURE_STREAM" in serialized:
            case, pieces, pause = "stream", ["Fixture stream ", "response complete."], 0.3
        else:
            case, pieces, pause = "fallback", ["Fixture ready."], 0
        with COUNTER_LOCK:
            COUNTERS[case] += 1
        if request.get("stream") is not True:
            self.respond_json({
                "id": "zedlink-fixture-response", "object": "chat.completion",
                "created": 0, "model": "zedlink-fixture",
                "choices": [{"index": 0, "message": {"role": "assistant", "content": "".join(pieces)},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": len(pieces), "total_tokens": len(pieces)+1},
            })
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            if case == "approval":
                command = "python3 -c 'from pathlib import Path; Path(\"approval_sentinel.txt\").write_text(\"approved\")'"
                arguments = json.dumps({"command": command, "cd": str(FIXTURE_ROOT), "timeout_ms": 5000})
                event = {"choices": [{"index": 0, "delta": {"tool_calls": [
                    {"index": 0, "id": "zedlink-fixture-" + uuid.uuid4().hex,
                     "function": {"name": "terminal", "arguments": arguments}}
                ]}, "finish_reason": None}], "usage": None}
                self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
                self.wfile.flush()
                event = {"choices": [{"index": 0, "delta": {}, "finish_reason": "tool_calls"}], "usage": None}
                self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
                self.wfile.write(b"data: [DONE]\n\n")
                self.wfile.flush()
                return
            for piece in pieces:
                event = {"choices": [{"index": 0, "delta": {"content": piece}, "finish_reason": None}],
                         "usage": None}
                self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
                self.wfile.flush()
                if pause:
                    time.sleep(pause)
            event = {"choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}], "usage": None}
            self.wfile.write(b"data: " + json.dumps(event).encode() + b"\n\n")
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass

    def respond_json(self, payload):
        encoded = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)


def main():
    global FIXTURE_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--project-root", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("--port must be a valid TCP port")
    if args.project_root:
        if not args.project_root.is_absolute() or not args.project_root.is_dir():
            parser.error("--project-root must be an existing absolute disposable directory")
        FIXTURE_ROOT = args.project_root.resolve()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"fixture listening on 127.0.0.1:{args.port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
