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


def receive_pairing_status(websocket, expected: str) -> dict:
    for _ in range(10):
        event = json.loads(websocket.recv(timeout=5))
        if event.get("status") == expected:
            return event
    raise AssertionError(f"pairing WebSocket did not report {expected}")


class ProbeFixture:
    def __init__(self, path):
        self.path = path
        self.seen_sends = {}
        self.created_requests = {}
        self.accepted = 0
        self.entries = ['<img src=x onerror="window.syntheticXss=1">']
        self.sequence = 0
        self.extra_thread = False
        self.no_threads = False
        self.created_thread = False
        self.exposed_primary = True
        self.renamed_title = None
        self.truncated = False
        self.activity_truncated = False
        self.transcript_page_size = None
        self.active_turn_id = None
        self.agent_error = None
        self.image_recovery = None
        self.retry_status = None
        self.cancelled = 0
        self.profile_id = "write"
        self.thinking_enabled = True
        self.settings_updates = 0
        self.elicitations = []
        self.elicitation_responses = []
        self.queued_messages = []
        self.edit_review = None
        self.edit_review_responses = []
        self.approvals = []
        self.approval_decisions = 0
        self.approval_responses = []
        self.subagent_cancellations = 0
        self.subagents = [
            {"session_id": "fixture-child-running", "tool_call_id": "spawn-running",
             "label": "Inspect transport tests", "title": "Transport investigator",
             "status": "Generating", "current_turn_id": 31,
             "message_start_index": 0, "message_end_index": None,
             "entries_markdown": ["## Assistant\n\n<thinking>\nChecking concurrent gateway behavior\n</thinking>\n\nReviewing the transport fixture.\n\n"],
             "entries_truncated": False,
             "pending_approvals": [{"approval_id": "child-approval", "turn_id": 31,
                                      "subagent_id": "fixture-child-running", "tool_name": "terminal",
                                      "display": "Save modified fixture", "raw_input": {"path": "fixture.txt"},
                                      "details_truncated": False, "authorization_kind": "action_choice",
                                      "permission_options": {"presentation": "flat", "patterns": [], "decisions": [
                                          {"option_id": "save", "label": "Save", "option_kind": "unknown",
                                           "choice_index": None, "action": None},
                                          {"option_id": "discard", "label": "Discard", "option_kind": "unknown",
                                           "choice_index": None, "action": None},
                                          {"option_id": "keep", "label": "Keep", "option_kind": "unknown",
                                           "choice_index": None, "action": None},
                                      ]}, "can_approve_once": False, "can_deny_once": False}]},
            {"session_id": "fixture-child-complete", "tool_call_id": "spawn-complete",
             "label": "Review browser layout", "title": "UI reviewer",
             "status": "Completed", "current_turn_id": None,
             "message_start_index": 1, "message_end_index": 2,
             "entries_markdown": ["## Assistant\n\nThe layout review is complete.\n\n"],
             "entries_truncated": False, "pending_approvals": []},
        ]
        self.change_operations = {}
        self.terminal_inputs = {}
        self.task_stops = {}
        self.task_runs = {}
        self.debugger_launches = {}
        self.debugger_controls = {}
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
                    threads = ([{"thread_id": "fixture-thread", "title": self.renamed_title or "Synthetic test thread",
                                "agent": {"id": "zed-agent", "name": "Zed Agent", "kind": "zed"},
                                "status": "Generating" if self.active_turn_id is not None else "Idle",
                                "current_turn_id": self.active_turn_id,
                                "had_error": self.agent_error is not None,
                                "agent_error": self.agent_error,
                                "retry_status": self.retry_status}] if self.exposed_primary else [])
                    if self.extra_thread:
                        threads.append({"thread_id": "fixture-second", "title": "Second synthetic thread",
                                        "agent": {"id": "codex-acp", "name": "Codex", "kind": "external_acp"},
                                        "status": "Idle"})
                    if self.created_thread:
                        threads.append({"thread_id": "fixture-created", "title": "Created from browser",
                                        "agent": {"id": "zed-agent", "name": "Zed Agent", "kind": "zed"},
                                        "status": "Idle"})
                    if self.no_threads:
                        threads = []
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "threads": threads}
                elif method == "thread.create":
                    key = request["request_id"]
                    creation = {"title": params.get("title"), "agent_id": params.get("agent_id")}
                    if key in self.created_requests and self.created_requests[key] != creation:
                        error = {"code": "REQUEST_CONFLICT"}
                    else:
                        self.created_requests[key] = creation
                        self.created_thread = True
                        result = {"outcome": "ready", "thread_id": "fixture-created"}
                elif method == "thread.create.options":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "project": "fixture-project", "agents": [
                                  {"id": "zed-agent", "name": "Zed Agent", "kind": "zed"},
                                  {"id": "codex-acp", "name": "Codex", "kind": "external_acp"},
                              ]}
                elif method == "thread.rename":
                    if params.get("thread_id") != "fixture-thread" or not params.get("title", "").strip():
                        error = {"code": "INVALID_REQUEST"}
                    else:
                        self.renamed_title = params["title"].strip()
                        result = {"thread_id": "fixture-thread", "title": self.renamed_title,
                                  "outcome": "requested"}
                elif method == "thread.unexpose":
                    if params.get("thread_id") != "fixture-thread" or not self.exposed_primary:
                        error = {"code": "THREAD_NOT_EXPOSED"}
                    else:
                        self.exposed_primary = False
                        result = {"thread_id": "fixture-thread", "outcome": "unexposed"}
                elif method == "thread.snapshot":
                    page_size = self.transcript_page_size or params.get("tail_entry_count") or len(self.entries)
                    page_start = max(0, len(self.entries) - page_size)
                    page = list(self.entries[page_start:])
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": params["thread_id"],
                              "agent": ({"id": "codex-acp", "name": "Codex", "kind": "external_acp"}
                                        if params["thread_id"] == "fixture-second"
                                        else {"id": "zed-agent", "name": "Zed Agent", "kind": "zed"}),
                              "title": ("Second synthetic thread" if params["thread_id"] == "fixture-second"
                                        else "Created from browser" if params["thread_id"] == "fixture-created"
                                        else "Synthetic test thread"),
                              "status": "Generating" if self.active_turn_id is not None else "Idle",
                              "current_turn_id": self.active_turn_id, "truncated": self.truncated,
                              "had_error": self.agent_error is not None,
                              "agent_error": self.agent_error, "retry_status": self.retry_status,
                              "image_recovery": self.image_recovery,
                              "rewind_points": [],
                              "entries_markdown": page,
                              "entry_start_index": page_start,
                              "entry_end_index": len(self.entries),
                              "total_entries": len(self.entries),
                              "has_older_entries": page_start > 0,
                              "activity_entries_markdown": list(self.entries[-8:]),
                              "activity_truncated": self.activity_truncated, "pending_approvals": list(self.approvals),
                              "subagents": list(self.subagents),
                              "last_sequence": self.sequence}
                elif method == "thread.history":
                    before = params.get("before_entry_index", len(self.entries))
                    page_size = self.transcript_page_size or 128
                    start = max(0, before - page_size)
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "thread_id": params["thread_id"],
                              "entries_markdown": list(self.entries[start:before]),
                              "entry_start_index": start, "entry_end_index": before,
                              "total_entries": len(self.entries), "has_older_entries": start > 0,
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
                    external = params["thread_id"] == "fixture-second"
                    if method == "thread.settings.update" and external:
                        error = {"code": "UNSUPPORTED_CAPABILITY"}
                    elif method == "thread.settings.update":
                        if "profile_id" in params:
                            self.profile_id = params["profile_id"]
                        if "thinking_enabled" in params:
                            self.thinking_enabled = params["thinking_enabled"]
                        self.settings_updates += 1
                    result = {
                        "thread_id": params["thread_id"],
                        "agent": ({"id": "codex-acp", "name": "Codex", "kind": "external_acp"}
                                  if external else {"id": "zed-agent", "name": "Zed Agent", "kind": "zed"}),
                        "status": "Generating" if self.active_turn_id is not None else "Idle",
                        "model": None if external else {"id": "glm-local", "name": "Local GLM fixture", "provider_id": "openai-compatible"},
                        "models": [] if external else [{"id": "glm-local", "name": "Local GLM fixture", "provider_id": "openai-compatible", "supports_images": False, "supports_thinking": True}],
                        "context_usage": None if external else {"used_tokens": 1200, "max_tokens": 131072, "input_tokens": 1100, "output_tokens": 100, "remaining_tokens": 129872},
                        "profile_id": None if external else self.profile_id,
                        "profiles": [] if external else [{"id": "write", "name": "Write"}, {"id": "ask", "name": "Ask"}],
                        "thinking_enabled": None if external else self.thinking_enabled,
                        "supports_images": None if external else False,
                        "thinking_supported": False if external else True,
                        "thinking_can_disable": False if external else True,
                        "editable": not external,
                        "configuration_owner": "external_agent" if external else "zed",
                    }
                elif method == "thread.elicitations":
                    result = {"thread_id": params["thread_id"], "elicitations": list(self.elicitations)}
                elif method == "elicitation.respond":
                    self.elicitation_responses.append(dict(params)); self.elicitations = []
                    result = {"thread_id": params["thread_id"], "outcome": "resolved"}
                elif method == "thread.queue":
                    result = {"thread_id": params["thread_id"], "entries": list(self.queued_messages), "count": len(self.queued_messages)}
                elif method == "thread.queue.clear":
                    removed = len(self.queued_messages); self.queued_messages = []
                    result = {"thread_id": params["thread_id"], "outcome": "cleared", "removed": removed}
                elif method == "thread.edit_review":
                    result = {"thread_id": params["thread_id"], "pending": self.edit_review is not None,
                              **(self.edit_review or {"changed_files": 0, "lines_added": 0, "lines_removed": 0})}
                elif method == "thread.edit_review.respond":
                    self.edit_review_responses.append(params["action"]); self.edit_review = None
                    result = {"thread_id": params["thread_id"], "outcome": "requested", "action": params["action"]}
                elif method == "terminal.list":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch", "terminals": [
                        {"terminal_id": "fixture-terminal", "title": "ZedLink fixture task",
                         "working_directory": "/tmp/zedlink-fixture", "pid": "4242",
                         "task": {"id": "fixture-task", "label": "Fixture task",
                                  "status": {"state": "running"}}}
                    ]}
                elif method == "terminal.snapshot":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "terminal": {"terminal_id": "fixture-terminal", "title": "ZedLink fixture task",
                                           "working_directory": "/tmp/zedlink-fixture", "pid": "4242",
                                           "task": {"id": "fixture-task", "label": "Fixture task",
                                                    "status": {"state": "running"}}},
                              "content": "$ printf ready\\nready\\n", "truncated": False,
                              "total_lines": 2, "viewport_lines": 24}
                elif method == "terminal.input":
                    payload = json.dumps(params, sort_keys=True)
                    duplicate = request["request_id"] in self.terminal_inputs
                    if duplicate and self.terminal_inputs[request["request_id"]] != payload:
                        error = {"code": "REQUEST_ID_CONFLICT"}
                    else:
                        self.terminal_inputs[request["request_id"]] = payload
                        result = {"outcome": "accepted", "duplicate": duplicate}
                elif method == "task.list":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch", "tasks": [
                        {"terminal_id": "fixture-terminal", "task_id": "fixture-task",
                         "label": "Fixture task", "command_label": "printf ready",
                         "status": {"state": "running"}}
                    ]}
                elif method == "task.stop":
                    payload = json.dumps(params, sort_keys=True)
                    duplicate = request["request_id"] in self.task_stops
                    if duplicate and self.task_stops[request["request_id"]] != payload:
                        error = {"code": "REQUEST_ID_CONFLICT"}
                    else:
                        self.task_stops[request["request_id"]] = payload
                        result = {"outcome": "requested", "duplicate": duplicate}
                elif method == "task.catalog":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch", "tasks": [
                        {"task_id": "configured-fixture-task", "label": "Build fixture", "source": "project"}
                    ]}
                elif method == "task.run":
                    allowed = {"instance_id", "epoch", "task_id"}
                    if set(params) - allowed or params.get("task_id") != "configured-fixture-task":
                        error = {"code": "INVALID_REQUEST"}
                    else:
                        payload = json.dumps(params, sort_keys=True)
                        duplicate = request["request_id"] in self.task_runs
                        if duplicate and self.task_runs[request["request_id"]] != payload:
                            error = {"code": "REQUEST_ID_CONFLICT"}
                        else:
                            self.task_runs[request["request_id"]] = payload
                            result = {"outcome": "requested", "duplicate": duplicate}
                elif method == "debugger.catalog":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch", "scenarios": [
                        {"scenario_id": "configured-fixture-debugger", "label": "Debug fixture", "adapter": "fixture-dap", "source": "project"}
                    ]}
                elif method == "debugger.launch":
                    allowed = {"instance_id", "epoch", "scenario_id"}
                    if set(params) - allowed or params.get("scenario_id") != "configured-fixture-debugger":
                        error = {"code": "INVALID_REQUEST"}
                    else:
                        payload = json.dumps(params, sort_keys=True)
                        duplicate = request["request_id"] in self.debugger_launches
                        if duplicate and self.debugger_launches[request["request_id"]] != payload:
                            error = {"code": "REQUEST_ID_CONFLICT"}
                        else:
                            self.debugger_launches[request["request_id"]] = payload
                            result = {"outcome": "requested", "duplicate": duplicate}
                elif method == "debugger.snapshot":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch", "sessions": [
                        {"session_id": "fixture-debugger", "label": "Debug fixture", "adapter": "fixture-dap",
                         "terminated": False,
                         "capabilities": {"restart": True, "step_back": False, "single_thread": True},
                         "threads": [{"thread_id": 7, "name": "main", "status": "stopped"}]}
                    ]}
                elif method == "debugger.control":
                    allowed = {"instance_id", "epoch", "session_id", "action", "thread_id"}
                    actions = {"pause", "continue", "step_over", "step_in", "step_out", "step_back", "restart", "stop"}
                    if (set(params) - allowed or params.get("session_id") != "fixture-debugger"
                            or params.get("action") not in actions):
                        error = {"code": "INVALID_REQUEST"}
                    else:
                        payload = json.dumps(params, sort_keys=True)
                        duplicate = request["request_id"] in self.debugger_controls
                        if duplicate and self.debugger_controls[request["request_id"]] != payload:
                            error = {"code": "REQUEST_ID_CONFLICT"}
                        else:
                            self.debugger_controls[request["request_id"]] = payload
                            result = {"outcome": "requested", "duplicate": duplicate}
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
                elif method == "project.search":
                    if params.get("query", "").casefold() == "println":
                        result = {"outcome": "ready", "matches": [
                            {"path": "src/main.rs", "line": 1, "column": 13,
                             "preview": "fn main() { println!(\"ready\"); }"},
                        ], "truncated": False}
                    else:
                        result = {"outcome": "ready", "matches": [], "truncated": False}
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
                    available = list(self.approvals)
                    for subagent in self.subagents:
                        available.extend(subagent.get("pending_approvals", []))
                    matching = [item for item in available
                                if item["approval_id"] == params.get("approval_id")
                                and item["turn_id"] == params.get("turn_id")
                                and item.get("subagent_id") == params.get("subagent_id")]
                    if not matching:
                        error = {"code": "APPROVAL_EXPIRED"}
                    else:
                        approval = matching[0]
                        decisions = approval.get("permission_options", {}).get("decisions", [])
                        if decisions and not any(
                                item.get("option_id") == params.get("option_id")
                                and item.get("choice_index") == params.get("choice_index")
                                for item in decisions):
                            error = {"code": "INVALID_PERMISSION_OPTION"}
                        else:
                            self.approval_responses.append(dict(params))
                            if params.get("subagent_id"):
                                for subagent in self.subagents:
                                    if subagent["session_id"] == params["subagent_id"]:
                                        subagent["pending_approvals"] = []
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
                elif method == "subagent.cancel":
                    matching = [agent for agent in self.subagents
                                if agent["session_id"] == params.get("subagent_id")]
                    if not matching:
                        error = {"code": "SUBAGENT_NOT_FOUND"}
                    elif matching[0]["current_turn_id"] != params.get("turn_id"):
                        error = {"code": "STALE_TURN"}
                    else:
                        matching[0]["current_turn_id"] = None
                        matching[0]["status"] = "Canceled"
                        self.subagent_cancellations += 1
                        self.sequence += 1
                        result = {"outcome": "requested", "subagent_id": params["subagent_id"],
                                  "turn_id": params["turn_id"]}
                elif method == "thread.rewind_image":
                    if params.get("expected_last_sequence") != self.sequence:
                        error = {"code": "STALE_SEQUENCE"}
                    elif not self.image_recovery or params.get("client_user_message_id") != self.image_recovery["client_user_message_id"]:
                        error = {"code": "STALE_SEQUENCE"}
                    else:
                        self.entries = self.entries[:self.image_recovery["entry_index"]]
                        self.image_recovery = None
                        self.agent_error = None
                        self.sequence += 1
                        result = {"outcome": "succeeded", "provisional": False}
                elif method == "thread.rewind":
                    result = {"outcome": "succeeded", "provisional": False}
                elif method == "instance.info":
                    result = {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                              "project": "fixture-project",
                              "capabilities": ["thread.list", "thread.create", "thread.create.options", "thread.rename", "thread.unexpose", "thread.snapshot", "thread.history", "thread.events",
                                               "thread.commands", "thread.settings", "thread.settings.update",
                                               "thread.elicitations", "elicitation.respond", "thread.queue", "thread.queue.clear",
                                               "thread.edit_review", "thread.edit_review.respond",
                                               "thread.send", "thread.attachments", "thread.cancel",
                                               "thread.subagents", "subagent.cancel",
                                               "thread.rewind_image",
                                               "thread.rewind",
                                               "thread.approvals", "approval.respond", "project.files",
                                               "project.file", "project.search", "changes.snapshot", "changes.diff",
                                               "terminal.list", "terminal.snapshot", "terminal.input", "task.list", "task.stop",
                                               "task.catalog", "task.run", "debugger.catalog", "debugger.launch", "debugger.snapshot", "debugger.control",
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
        offline_probe_dir = root / "offline-probe"
        offline_probe_dir.mkdir(mode=0o700)
        listeners = root / "listeners.json"
        targets = root / "targets.json"
        listeners.write_text(json.dumps({"version": 1, "listeners": [{
            "id": "fixture", "bind": f"127.0.0.1:{port}", "cert": str(cert), "key": str(key),
            "url": f"https://localhost:{port}",
        }]}))
        targets.write_text(json.dumps({"version": 1, "targets": [
            {"id": "primary", "label": "Fixture Zed", "probe": str(probe.path)},
            {"id": "offline", "label": "Offline Zed", "probe": str(offline_probe_dir / "zedlink.sock")},
        ]}))
        os.chmod(listeners, 0o600)
        os.chmod(targets, 0o600)
        server = subprocess.Popen([str(BINARY), "serve-targets", str(listeners), str(targets), str(state)],
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
            assert info["route_origins"] == [base]
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
            replaced_challenge = admin(state, "pair-short-code")
            pairing_websocket_url = (
                f"wss://localhost:{port}/v1/pairing-events?pairing_id="
                + replaced_challenge["pairing_id"]
            )
            with connect(
                pairing_websocket_url,
                ssl=context,
                subprotocols=["zedlink-pairing-v1",
                              "zedlink-pairing-token-" + replaced_challenge["watch_token"]],
                open_timeout=5,
                close_timeout=2,
            ) as pairing_websocket:
                active = receive_pairing_status(pairing_websocket, "active")
                assert active["status"] == "active" and active["expires_seconds"] <= 300
                live_challenge = admin(state, "pair-short-code")
                replaced = receive_pairing_status(pairing_websocket, "replaced")
                assert replaced["status"] == "replaced"
            live_pairing_url = (
                f"wss://localhost:{port}/v1/pairing-events?pairing_id="
                + live_challenge["pairing_id"]
            )
            with connect(
                live_pairing_url,
                ssl=context,
                subprotocols=["zedlink-pairing-v1",
                              "zedlink-pairing-token-" + live_challenge["watch_token"]],
                open_timeout=5,
                close_timeout=2,
            ) as pairing_websocket:
                assert receive_pairing_status(pairing_websocket, "active")["status"] == "active"
                wrong_live_code = ("0" * 10 if live_challenge["code"] != "0" * 10 else "1" * 10)
                status, _ = http(base, context, "/v1/pair", "POST",
                                 {"code": wrong_live_code, "device_name": "wrong live code"})
                assert status == 403
                failed = receive_pairing_status(pairing_websocket, "attempt_failed")
                assert failed["status"] == "attempt_failed" and failed["attempts_remaining"] == 4
                status, watched_device = http(
                    base, context, "/v1/pair", "POST",
                    {"code": live_challenge["code"], "device_name": "live pairing fixture"},
                )
                assert status == 200
                paired = receive_pairing_status(pairing_websocket, "paired")
                assert paired["status"] == "paired"
            assert admin(state, "revoke", watched_device["device_id"])["revoked"]
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
            instance_request = {"version": 1, "request_id": "instances", "method": "instance.list", "params": {}}
            status, instances = http(base, context, "/v1/rpc", "POST", instance_request, token1)
            assert status == 200
            assert [(item["target_id"], item["available"]) for item in instances["result"]["targets"]] == [
                ("primary", True), ("offline", False)]
            targeted = {"version": 1, "request_id": "targeted", "method": "thread.list",
                        "target_id": "primary", "params": {}}
            status, targeted_result = http(base, context, "/v1/rpc", "POST", targeted, token1)
            assert status == 200 and targeted_result["result"]["threads"][0]["thread_id"] == "fixture-thread"
            unknown = dict(targeted, request_id="unknown-target", target_id="missing")
            status, unknown_result = http(base, context, "/v1/rpc", "POST", unknown, token1)
            assert status == 503 and unknown_result["error"] == "INSTANCE_UNAVAILABLE"
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
            terminal_list = {"version": 1, "request_id": "terminal-list", "method": "terminal.list",
                             "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch"}}
            status, terminal_listing = http(base, context, "/v1/rpc", "POST", terminal_list, token1)
            assert status == 200 and terminal_listing["result"]["terminals"][0]["terminal_id"] == "fixture-terminal"
            terminal_snapshot = {"version": 1, "request_id": "terminal-snapshot", "method": "terminal.snapshot",
                                 "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                            "terminal_id": "fixture-terminal"}}
            status, snapshot_result = http(base, context, "/v1/rpc", "POST", terminal_snapshot, token1)
            assert status == 200 and "ready" in snapshot_result["result"]["content"]
            terminal_input = {"version": 1, "request_id": "terminal-input", "method": "terminal.input",
                              "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                         "terminal_id": "fixture-terminal", "input": "status\n"}}
            for duplicate in (False, True):
                status, input_result = http(base, context, "/v1/rpc", "POST", terminal_input, token1)
                assert status == 200 and input_result["result"]["duplicate"] is duplicate
            assert len(probe.terminal_inputs) == 1
            task_list = {"version": 1, "request_id": "task-list", "method": "task.list", "params": {}}
            status, task_result = http(base, context, "/v1/rpc", "POST", task_list, token1)
            assert status == 200 and task_result["result"]["tasks"][0]["status"]["state"] == "running"
            task_stop = {"version": 1, "request_id": "task-stop", "method": "task.stop",
                         "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                    "terminal_id": "fixture-terminal"}}
            for duplicate in (False, True):
                status, stop_result = http(base, context, "/v1/rpc", "POST", task_stop, token1)
                assert status == 200 and stop_result["result"]["duplicate"] is duplicate
            assert len(probe.task_stops) == 1
            task_catalog = {"version": 1, "request_id": "task-catalog", "method": "task.catalog",
                            "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch"}}
            status, catalog_result = http(base, context, "/v1/rpc", "POST", task_catalog, token1)
            assert status == 200 and catalog_result["result"]["tasks"][0]["task_id"] == "configured-fixture-task"
            task_run = {"version": 1, "request_id": "task-run", "method": "task.run",
                        "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                   "task_id": "configured-fixture-task"}}
            for duplicate in (False, True):
                status, run_result = http(base, context, "/v1/rpc", "POST", task_run, token1)
                assert status == 200 and run_result["result"]["duplicate"] is duplicate
            assert len(probe.task_runs) == 1
            smuggled_task = dict(task_run, request_id="task-run-smuggled",
                                 params={**task_run["params"], "command": "touch /tmp/never"})
            status, smuggled_result = http(base, context, "/v1/rpc", "POST", smuggled_task, token1)
            assert status == 200 and smuggled_result["error"]["code"] == "INVALID_REQUEST"
            debugger_catalog = {"version": 1, "request_id": "debugger-catalog", "method": "debugger.catalog",
                                "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch"}}
            status, debug_catalog_result = http(base, context, "/v1/rpc", "POST", debugger_catalog, token1)
            assert status == 200 and debug_catalog_result["result"]["scenarios"][0]["scenario_id"] == "configured-fixture-debugger"
            debugger_launch = {"version": 1, "request_id": "debugger-launch", "method": "debugger.launch",
                               "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                          "scenario_id": "configured-fixture-debugger"}}
            for duplicate in (False, True):
                status, launch_result = http(base, context, "/v1/rpc", "POST", debugger_launch, token1)
                assert status == 200 and launch_result["result"]["duplicate"] is duplicate
            assert len(probe.debugger_launches) == 1
            smuggled_debugger = dict(debugger_launch, request_id="debugger-launch-smuggled",
                                     params={**debugger_launch["params"], "program": "/tmp/never"})
            status, smuggled_debugger_result = http(base, context, "/v1/rpc", "POST", smuggled_debugger, token1)
            assert status == 200 and smuggled_debugger_result["error"]["code"] == "INVALID_REQUEST"
            debugger_snapshot = {"version": 1, "request_id": "debugger-snapshot",
                                 "method": "debugger.snapshot",
                                 "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch"}}
            status, debugger_result = http(base, context, "/v1/rpc", "POST", debugger_snapshot, token1)
            assert status == 200 and debugger_result["result"]["sessions"][0]["threads"][0]["status"] == "stopped"
            debugger_control = {"version": 1, "request_id": "debugger-control", "method": "debugger.control",
                                "params": {"instance_id": "fixture-instance", "epoch": "fixture-epoch",
                                           "session_id": "fixture-debugger", "thread_id": 7,
                                           "action": "continue"}}
            for duplicate in (False, True):
                status, control_result = http(base, context, "/v1/rpc", "POST", debugger_control, token1)
                assert status == 200 and control_result["result"]["duplicate"] is duplicate
            assert len(probe.debugger_controls) == 1
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
            server = subprocess.Popen([str(BINARY), "serve-targets", str(listeners), str(targets), str(state)],
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
                try:
                    wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Synthetic test thread")
                except TimeoutException:
                    print("initial browser state:", browser.execute_script(
                        "return {title:document.getElementById('thread-title').textContent,"
                        "notice:document.getElementById('notice').textContent,"
                        "connection:document.getElementById('connection').textContent,"
                        "threads:document.getElementById('thread-list').textContent,"
                        "target:document.getElementById('target-select').value}"
                    ))
                    raise
                assert "Choose a session" not in browser.page_source
                assert browser.find_element(By.ID, "thread-count").text == "1"
                assert browser.find_element(By.ID, "ui-build").get_attribute("textContent") == "2026.10.12.4"
                assert base in browser.find_element(By.ID, "gateway-route-addresses").get_attribute("textContent")
                selected_target = browser.find_element(By.ID, "target-select").get_attribute("value")
                if selected_target != "primary":
                    options = [(option.get_attribute("value"), option.text, option.is_enabled())
                               for option in Select(browser.find_element(By.ID, "target-select")).options]
                    raise AssertionError(f"target selector value {selected_target!r}; options {options!r}")
                assert "Fixture Zed" in browser.find_element(By.ID, "connection-target").get_attribute("textContent")
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
                wait.until(lambda driver: len(Select(driver.find_element(By.ID, "new-session-agent")).options) == 2)
                Select(browser.find_element(By.ID, "new-session-agent")).select_by_value("codex-acp")
                browser.find_element(By.ID, "new-session-title").send_keys("Created from browser")
                browser.find_element(By.ID, "create-session").click()
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Created from browser")
                assert browser.find_element(By.ID, "thread-count").text == "2"
                assert len(probe.created_requests) == 1
                assert next(iter(probe.created_requests.values()))["agent_id"] == "codex-acp"
                search = browser.find_element(By.ID, "session-search")
                search.send_keys("no such session")
                assert not browser.find_elements(By.CSS_SELECTOR, ".thread-item")
                assert "No sessions match" in browser.find_element(By.ID, "thread-list").text
                search.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item"))
                assert browser.find_element(By.CSS_SELECTOR, ".thread-badge").text == "ZED AGENT"
                browser.execute_script("document.querySelector('.thread-item').click()")
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Synthetic test thread")
                wait.until(lambda driver: "Zed connected · live updates" in driver.find_element(By.ID, "connection").get_attribute("textContent"))
                browser.find_element(By.ID, "show-actions").click()
                browser.find_element(By.ID, "action-delegate").click()
                prompt = browser.find_element(By.ID, "prompt")
                assert "native spawn_agent tool" in prompt.get_attribute("value")
                assert "Task:" in prompt.get_attribute("value")
                prompt.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                wait.until(lambda driver: len(driver.find_elements(By.CSS_SELECTOR, "#subagents .subagent")) == 2)
                assert "2 total" in browser.find_element(By.CSS_SELECTOR, ".subagents-head").text
                assert "Checking concurrent gateway behavior" in browser.find_element(By.ID, "subagents").get_attribute("textContent")
                assert browser.find_element(By.CSS_SELECTOR, ".subagent.active").get_attribute("open") == "true"
                assert "parallel agent" in browser.find_element(By.ID, "approvals").text.casefold()
                assert "Save modified fixture" in browser.find_element(By.ID, "approvals").text
                browser.find_element(By.CSS_SELECTOR, "#approvals .primary").click()
                wait.until(lambda driver: probe.approval_decisions == 1)
                assert probe.approval_responses[-1]["option_id"] == "save"
                assert "decision" not in probe.approval_responses[-1]
                browser.find_element(By.CSS_SELECTOR, ".subagent.active .subagent-stop").click()
                wait.until(lambda driver: probe.subagent_cancellations == 1)
                wait.until(lambda driver: not driver.find_elements(By.CSS_SELECTOR, ".subagent.active"))
                probe.elicitations = [{"elicitation_id": "fixture-input", "status": "pending", "request": {
                    "message": "Choose a release channel", "mode": "form",
                    "requestedSchema": {"type": "object", "required": ["channel"],
                                        "properties": {"channel": {"type": "string", "title": "Channel"}}}}}]
                probe.queued_messages = [{"index": 0, "preview": "Run the follow-up checks", "steer": False}]
                probe.edit_review = {"changed_files": 2, "lines_added": 12, "lines_removed": 3}
                wait.until(lambda driver: driver.find_element(By.ID, "elicitations").is_displayed())
                field = browser.find_element(By.CSS_SELECTOR, "#elicitations input")
                field.send_keys("stable")
                browser.find_element(By.CSS_SELECTOR, "#elicitations button.primary").click()
                wait.until(lambda driver: len(probe.elicitation_responses) == 1)
                assert probe.elicitation_responses[-1]["content"]["channel"] == "stable"
                wait.until(lambda driver: driver.find_element(By.ID, "edit-review").is_displayed())
                assert not browser.find_element(By.CSS_SELECTOR, "#edit-review .edit-review-menu").is_displayed()
                assert browser.find_element(By.ID, "edit-review-count").text == "2"
                browser.find_element(By.CSS_SELECTOR, "#edit-review > summary").click()
                wait.until(lambda driver: driver.find_element(By.CSS_SELECTOR, "#edit-review .edit-review-menu").is_displayed())
                browser.find_element(By.CSS_SELECTOR, "#edit-review button.primary").click()
                wait.until(lambda driver: probe.edit_review_responses == ["keep_all"])
                wait.until(lambda driver: driver.find_element(By.ID, "queue-review").is_displayed())
                browser.find_element(By.CSS_SELECTOR, "#queue-review button").click()
                wait.until(lambda driver: not probe.queued_messages)
                browser.find_element(By.ID, "open-settings").click()
                wait.until(lambda driver: "Local GLM fixture" in Select(driver.find_element(By.ID, "zed-model")).first_selected_option.text)
                assert "Local GLM fixture" in browser.find_element(By.ID, "header-model").text
                assert "1,200 / 131,072" in browser.find_element(By.ID, "zed-context-usage").text
                assert Select(browser.find_element(By.ID, "zed-profile")).first_selected_option.get_attribute("value") == "write"
                Select(browser.find_element(By.ID, "zed-profile")).select_by_value("ask")
                browser.find_element(By.ID, "zed-thinking").click()
                browser.find_element(By.ID, "save-zed-settings").click()
                wait.until(lambda driver: probe.settings_updates == 1)
                assert probe.profile_id == "ask" and probe.thinking_enabled is False
                assert "updated" in browser.find_element(By.ID, "notice").text
                title_input = browser.find_element(By.ID, "session-title-input")
                title_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                title_input.send_keys("Renamed from browser")
                browser.find_element(By.ID, "rename-session").click()
                wait.until(lambda driver: probe.renamed_title == "Renamed from browser")
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Renamed from browser")
                title_input = browser.find_element(By.ID, "session-title-input")
                title_input.send_keys(Keys.CONTROL, "a", Keys.DELETE)
                title_input.send_keys("Synthetic test thread")
                browser.find_element(By.ID, "rename-session").click()
                wait.until(lambda driver: probe.renamed_title == "Synthetic test thread")
                browser.save_screenshot("/tmp/zedlink-browser-settings.png")
                browser.find_element(By.ID, "settings-back").click()
                assert browser.find_element(By.ID, "sessions-panel").is_displayed()
                browser.find_element(By.ID, "show-context").click()
                wait.until(lambda driver: driver.find_element(By.ID, "context-panel").is_displayed())
                wait.until(lambda driver: "src/main.rs" in driver.find_element(By.ID, "file-list").text)
                browser.find_element(By.ID, "project-search").send_keys("println")
                browser.find_element(By.ID, "project-search-form").submit()
                wait.until(lambda driver: "src/main.rs" in driver.find_element(By.ID, "project-search-results").text)
                assert "1 match" in browser.find_element(By.ID, "project-search-status").text
                browser.find_element(By.CSS_SELECTOR, "#project-search-results .search-result").click()
                wait.until(lambda driver: "println" in driver.find_element(By.ID, "file-preview-content").text)
                assert browser.find_element(By.CSS_SELECTOR, "#file-preview .review-code").get_attribute("class").endswith("wrap")
                assert browser.find_elements(By.CSS_SELECTOR, "#file-preview-content .syntax-keyword")
                assert browser.find_elements(By.CSS_SELECTOR, "#file-preview-content .focus-line")
                browser.find_element(By.ID, "expand-file").click()
                wait.until(lambda driver: driver.find_element(By.ID, "code-review").is_displayed())
                assert browser.find_element(By.ID, "code-review-title").text == "src/main.rs"
                assert browser.find_elements(By.CSS_SELECTOR, "#code-review-content .code-line-number")
                assert browser.find_elements(By.CSS_SELECTOR, "#code-review-content .syntax-keyword")
                browser.find_element(By.ID, "code-review-query").send_keys("ready")
                assert browser.find_element(By.ID, "code-review-count").text == "1 match"
                assert browser.find_elements(By.CSS_SELECTOR, "#code-review-content .search-hit")
                browser.save_screenshot("/tmp/zedlink-browser-code-review.png")
                browser.find_element(By.ID, "close-code-review").click()
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
                assert browser.find_elements(By.CSS_SELECTOR, "#git-diff .syntax-diff-add")
                assert "wrap" in browser.find_element(By.ID, "git-diff").get_attribute("class")
                browser.find_element(By.ID, "diff-search").send_keys("println")
                assert browser.find_element(By.ID, "diff-search-count").text == "1 match"
                browser.find_element(By.ID, "expand-diff").click()
                wait.until(lambda driver: driver.find_element(By.ID, "code-review").is_displayed())
                assert browser.find_element(By.ID, "code-review-title").text == "Working tree diff"
                assert browser.find_elements(By.CSS_SELECTOR, "#code-review-content .syntax-diff-add")
                browser.find_element(By.ID, "close-code-review").click()
                browser.find_element(By.CSS_SELECTOR, "#changes-list .change-action").click()
                wait.until(lambda driver: len(probe.change_operations) == 1)
                browser.find_element(By.ID, "context-terminal-tab").click()
                wait.until(lambda driver: driver.find_element(By.ID, "terminal-mode").text == "INTERACTIVE")
                browser.find_element(By.CSS_SELECTOR, "#task-launcher > summary").click()
                wait.until(lambda driver: "Build fixture" in driver.find_element(By.ID, "task-select").text)
                assert browser.find_element(By.ID, "terminal-select").is_displayed()
                assert not browser.find_element(By.ID, "run-task").get_attribute("disabled")
                browser.find_element(By.ID, "run-task").click()
                wait.until(lambda driver: len(probe.task_runs) >= 1)
                assert "ready" in browser.find_element(By.ID, "terminal-output").text
                browser.find_element(By.CSS_SELECTOR, "#task-launcher > summary").click()
                terminal_input = browser.find_element(By.ID, "terminal-input")
                terminal_input.send_keys("echo terminal-ui")
                browser.find_element(By.CSS_SELECTOR, "#terminal-input-form button").click()
                wait.until(lambda driver: any(json.loads(row).get("input") == "echo terminal-ui\n"
                                              for row in probe.terminal_inputs.values()))
                assert browser.find_element(By.ID, "terminal-preview").value_of_css_property("background-color") in (
                    "rgb(2, 3, 3)", "rgba(2, 3, 3, 1)")
                browser.save_screenshot("/tmp/zedlink-browser-terminal.png")
                browser.find_element(By.ID, "context-debug-tab").click()
                wait.until(lambda driver: "Debug fixture" in driver.find_element(By.ID, "debugger-select").text)
                launches_before_browser = len(probe.debugger_launches)
                assert not browser.find_element(By.ID, "launch-debugger").get_attribute("disabled")
                browser.find_element(By.ID, "launch-debugger").click()
                wait.until(lambda driver: len(probe.debugger_launches) == launches_before_browser + 1)
                wait.until(lambda driver: "Debug fixture" in driver.find_element(By.ID, "debugger-list").text)
                assert "STOPPED" in browser.find_element(By.ID, "debugger-list").text
                next(button for button in browser.find_elements(By.CSS_SELECTOR, "#debugger-list button")
                     if button.text == "Continue").click()
                wait.until(lambda driver: len(probe.debugger_controls) >= 1)
                browser.find_element(By.ID, "close-context").click()
                upload = root / "browser-note.txt"
                upload.write_text("browser upload fixture\n")
                browser.find_element(By.ID, "upload-file").send_keys(str(upload))
                wait.until(lambda driver: "browser-note.txt" in driver.find_element(By.ID, "attachment-strip").text)
                assert not browser.find_elements(By.CSS_SELECTOR, "#messages img")
                assert browser.execute_script("return window.syntheticXss || 0") == 0
                browser.find_element(By.ID, "prompt").send_keys("Browser fixture prompt")
                browser.execute_script("const original = window.matchMedia; window.matchMedia = () => ({matches:false}); const prompt = document.getElementById('prompt'); prompt.dispatchEvent(new KeyboardEvent('keydown', {key:'Enter', bubbles:true, cancelable:true})); window.matchMedia = original;")
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
                user_message = browser.find_elements(By.CSS_SELECTOR, ".message.user")[-1]
                assert user_message.get_attribute("aria-label") == "Your message"
                assert not user_message.find_elements(By.CSS_SELECTOR, ".message-label")
                assert user_message.find_element(By.CSS_SELECTOR, ".message-copy-compact").get_attribute("textContent") == "⧉"
                user_style = browser.execute_script(
                    "const style=getComputedStyle(arguments[0]); const box=arguments[0].getBoundingClientRect(); "
                    "return {width: box.width, border: style.borderTopWidth, radius: style.borderTopLeftRadius};",
                    user_message,
                )
                assert user_style["width"] < 400 and user_style["border"] == "0px"
                assert user_style["radius"] == "12px"
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
                wait.until(lambda driver: "Working" in driver.execute_script(
                    "return document.querySelector('.thread-status.busy')?.textContent || ''"))
                browser.save_screenshot("/tmp/zedlink-browser-active-session.png")
                wait.until(lambda driver: "Checking the fixture stream" in driver.find_element(By.ID, "transcript-entries").text)
                progress = browser.find_element(By.ID, "thread-state")
                assert progress.is_displayed()
                wait.until(lambda driver: "working" in driver.find_element(By.ID, "thread-state").get_attribute("class"))
                progress = browser.find_element(By.ID, "thread-state")
                assert progress.text == "GENERATING"
                assert "Generating a response in desktop Zed" in progress.get_attribute("title")
                assert browser.find_element(By.ID, "send").get_attribute("data-mode") == "stop"
                assert not browser.find_element(By.ID, "activity").is_displayed()
                assert browser.find_element(By.CSS_SELECTOR, ".message.assistant details.thinking-block").get_attribute("open") == "true"
                probe.activity_truncated = True
                probe.sequence += 1
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
                probe.sequence += 1
                wait.until(lambda driver: driver.execute_script(
                    "return [...document.querySelectorAll('.message.tool .tool-output')].some(item => item.textContent.includes('line three'))"
                ))
                assert browser.find_element(By.CSS_SELECTOR, ".message.tool .tool-details").get_attribute("open") is None
                assert browser.execute_script(
                    "return [...document.querySelectorAll('.message.tool .tool-output')].some(item => item.textContent.includes('line three'))"
                )
                probe.transcript_page_size = 2
                browser.execute_script("selectThread('fixture-thread')")
                wait.until(lambda driver: driver.find_element(By.ID, "load-history").is_displayed())
                assert "remaining" in browser.find_element(By.ID, "load-history").text
                for _ in range(20):
                    history_button = browser.find_element(By.ID, "load-history")
                    if not history_button.is_displayed():
                        break
                    prior_label = history_button.text
                    browser.execute_script("arguments[0].click()", history_button)
                    wait.until(lambda driver: not driver.find_element(By.ID, "load-history").is_displayed()
                               or driver.find_element(By.ID, "load-history").text != prior_label)
                assert not browser.find_element(By.ID, "load-history").is_displayed()
                assert len(browser.find_elements(By.CSS_SELECTOR, "#transcript-entries .message")) == len(probe.entries)
                assert not browser.find_elements(By.ID, "snapshot-warning")
                probe.transcript_page_size = None
                probe.sequence += 1
                wait.until(lambda driver: "conversation entries" in driver.find_element(By.ID, "thread-meta").text)
                probe.approvals = [{"approval_id": "fixture-approval", "turn_id": 8,
                                    "tool_name": "fetch", "display": "Fetch https://example.test/docs",
                                    "raw_input": {"url": "https://example.test/docs"},
                                    "details_truncated": False, "authorization_kind": "permission_grant",
                                    "permission_options": {"presentation": "dropdown", "patterns": [], "decisions": [
                                        {"option_id": "fetch-always-allow", "label": "Always for fetch",
                                         "option_kind": "allow_always", "choice_index": 0, "action": "allow"},
                                        {"option_id": "fetch-always-deny", "label": "Always for fetch",
                                         "option_kind": "reject_always", "choice_index": 0, "action": "deny"},
                                        {"option_id": "host-allow", "label": "For example.test",
                                         "option_kind": "allow_always", "choice_index": 1, "action": "allow"},
                                        {"option_id": "host-deny", "label": "For example.test",
                                         "option_kind": "reject_always", "choice_index": 1, "action": "deny"},
                                        {"option_id": "fetch-once-allow", "label": "Only this time",
                                         "option_kind": "allow_once", "choice_index": 2, "action": "allow"},
                                        {"option_id": "fetch-once-deny", "label": "Only this time",
                                         "option_kind": "reject_once", "choice_index": 2, "action": "deny"},
                                    ]}, "can_approve_once": True, "can_deny_once": True}]
                probe.sequence += 1
                wait.until(lambda driver: driver.find_element(By.ID, "approvals").is_displayed())
                assert "example.test/docs" in browser.find_element(By.ID, "approvals").text
                approval_scope = Select(browser.find_element(By.CSS_SELECTOR, "#approvals select"))
                assert len(approval_scope.options) == 3
                approval_scope.select_by_visible_text("For example.test")
                assert approval_scope.first_selected_option.get_attribute("value") == "1"
                browser.find_element(By.CSS_SELECTOR, "#approvals .primary").click()
                wait.until(lambda driver: probe.approval_decisions == 2)
                assert probe.approval_responses[-1]["option_id"] == "host-allow", probe.approval_responses[-1]
                assert probe.approval_responses[-1]["choice_index"] == 1, probe.approval_responses[-1]
                wait.until(lambda driver: not driver.find_element(By.ID, "approvals").is_displayed())
                probe.active_turn_id = None
                probe.sequence += 1
                wait.until(lambda driver: not driver.find_elements(By.CSS_SELECTOR, ".thread-item.running"))
                wait.until(lambda driver: "working" not in driver.find_element(By.ID, "thread-state").get_attribute("class"))
                assert browser.find_element(By.ID, "send").get_attribute("data-mode") == "send"
                probe.agent_error = {"kind": "other", "title": "Agent request failed",
                                     "message": "image input requires a supported vision checkpoint served with --vision",
                                     "retrying": True}
                image_entry_index = max(0, len(probe.entries) - 2)
                probe.image_recovery = {"client_user_message_id": "fixture-image-message",
                                        "entry_index": image_entry_index,
                                        "entries_removed": len(probe.entries) - image_entry_index}
                assert browser.execute_async_script(
                    "const done=arguments[0]; loadThreads().then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: driver.find_element(By.ID, "agent-health").is_displayed())
                assert browser.find_element(By.ID, "agent-health").find_element(By.XPATH, "..").get_attribute("id") == "messages"
                assert browser.find_element(By.ID, "agent-health-title").text == "Image input unavailable"
                assert "supported vision checkpoint" in browser.find_element(By.ID, "agent-health-message").text
                assert "CONVERSATION ITEMS WILL BE REMOVED" in browser.find_element(By.ID, "agent-health-recovery").text
                assert browser.find_element(By.ID, "rewind-image").is_displayed()
                assert browser.find_element(By.ID, "thread-state").text == "REQUEST FAILED"
                assert "request failed" in browser.find_element(By.ID, "header-model").text.casefold()
                assert "error" in browser.find_element(By.ID, "header-model").get_attribute("class")
                wait.until(lambda driver: driver.find_elements(By.CSS_SELECTOR, ".thread-item.error"))
                rewind_button = browser.find_element(By.ID, "rewind-image")
                browser.execute_script("arguments[0].scrollIntoView({block:'center'})", rewind_button)
                browser.execute_script("arguments[0].click()", rewind_button)
                wait.until(lambda driver: driver.switch_to.alert)
                browser.switch_to.alert.accept()
                wait.until(lambda driver: probe.image_recovery is None)
                wait.until(lambda driver: not driver.find_element(By.ID, "agent-health").is_displayed())
                assert len(probe.entries) == image_entry_index
                probe.retry_status = {"last_error": "Local model connection refused", "attempt": 2,
                                      "max_attempts": 5, "next_attempt_in_ms": 3000}
                probe.agent_error = {"kind": "provider_error", "title": "Agent request failed",
                                     "message": "Local model connection refused", "retrying": True}
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
                composer = browser.execute_script("const box=document.getElementById('composer-form').getBoundingClientRect(); const workspace=document.querySelector('.workspace').getBoundingClientRect(); const add=document.getElementById('show-actions').getBoundingClientRect(); const send=document.getElementById('send').getBoundingClientRect(); return {width:box.width,height:box.height,radius:getComputedStyle(document.getElementById('composer-form')).borderRadius,addWidth:add.width,sendWidth:send.width,centerDelta:Math.abs((box.left+box.width/2)-(workspace.left+workspace.width/2))}")
                assert composer["width"] <= 922 and composer["height"] <= 54, composer
                assert composer["radius"] == "14px" and composer["addWidth"] == 40 and composer["sendWidth"] == 40 and composer["centerDelta"] <= 1, composer
                browser.find_element(By.ID, "show-sessions").click()
                collapsed = browser.execute_script("return {sidebarHidden:getComputedStyle(document.querySelector('.sidebar')).visibility==='hidden', workspaceWidth:document.querySelector('.workspace').getBoundingClientRect().width, width:innerWidth}")
                assert collapsed["sidebarHidden"] and collapsed["workspaceWidth"] >= collapsed["width"] - 20, collapsed
                assert browser.find_element(By.ID, "show-sessions").get_attribute("aria-label") == "Show sessions"
                browser.save_screenshot("/tmp/zedlink-browser-fixture-wide-collapsed.png")
                browser.find_element(By.ID, "show-sessions").click()
                assert browser.find_element(By.ID, "show-sessions").get_attribute("aria-label") == "Hide sessions"
                browser.save_screenshot("/tmp/zedlink-browser-fixture-wide.png")
                browser.set_window_size(393, 852)
                wait.until(lambda driver: driver.execute_script("return Math.abs(parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--app-height')) - Math.min(innerHeight, visualViewport.height + visualViewport.offsetTop)) <= 1"))
                offset_viewport_height = browser.execute_script("syncVisualViewport({height: 700, offsetTop: 59}); const value=parseFloat(getComputedStyle(document.documentElement).getPropertyValue('--app-height')); syncVisualViewport(); return value")
                assert offset_viewport_height == 759, offset_viewport_height
                standalone_heights = browser.execute_script("return {resting:appViewportHeight({height:700,offsetTop:59},true,false,852),keyboard:appViewportHeight({height:700,offsetTop:59},true,true,852),browser:appViewportHeight({height:700,offsetTop:59},false,false,852)}")
                assert standalone_heights == {"resting": 852, "keyboard": 759, "browser": 759}, standalone_heights
                layout = browser.execute_script("return {width:innerWidth, pageWidth:document.documentElement.scrollWidth, composerBottom:document.getElementById('composer-form').getBoundingClientRect().bottom, height:innerHeight, visibleBottom:visualViewport.height + visualViewport.offsetTop, messagesHeight:document.getElementById('messages').getBoundingClientRect().height, sidebarHidden:getComputedStyle(document.querySelector('.sidebar')).display==='none'}")
                assert layout["pageWidth"] <= layout["width"] + 1
                assert layout["composerBottom"] <= layout["visibleBottom"] + 1
                assert not browser.find_element(By.ID, "tab-sessions").is_displayed()
                assert not browser.find_element(By.CSS_SELECTOR, ".topbar").is_displayed()
                browser.save_screenshot("/tmp/zedlink-browser-fixture-mobile.png")
                assert layout["messagesHeight"] >= 390 and layout["sidebarHidden"], layout
                assert browser.find_element(By.ID, "prompt").is_displayed()
                assert browser.find_element(By.ID, "send").is_displayed()
                back = browser.find_element(By.ID, "back-sessions")
                assert back.is_displayed() and back.get_attribute("aria-label") == "Back to sessions"
                assert not browser.find_element(By.ID, "thread-state").is_displayed()
                assert browser.find_element(By.ID, "mobile-session-meta").text == "Local GLM fixture · Live"
                assert browser.find_element(By.ID, "show-context").get_attribute("aria-label") == "Open project context"
                mobile_header = browser.execute_script("const title=document.getElementById('thread-title').getBoundingClientRect(); const context=document.getElementById('show-context').getBoundingClientRect(); return {titleWidth:title.width,titleHeight:title.height,contextWidth:context.width,pageWidth:document.documentElement.scrollWidth,viewport:innerWidth}")
                assert mobile_header["titleWidth"] >= 150 and mobile_header["titleHeight"] <= 42 and mobile_header["contextWidth"] == 38, mobile_header
                assert mobile_header["pageWidth"] <= mobile_header["viewport"] + 1, mobile_header
                mobile_composer = browser.execute_script("const box=document.getElementById('composer-form').getBoundingClientRect(); return {width:box.width,height:box.height,radius:getComputedStyle(document.getElementById('composer-form')).borderRadius,viewport:innerWidth}")
                assert mobile_composer["width"] <= mobile_composer["viewport"] - 16 and mobile_composer["height"] <= 54 and mobile_composer["radius"] == "13px", mobile_composer
                browser.find_element(By.ID, "show-context").click()
                browser.find_element(By.ID, "context-terminal-tab").click()
                wait.until(lambda driver: driver.find_element(By.ID, "terminal-mode").text == "INTERACTIVE")
                mobile_terminal = browser.execute_script("const panel=document.getElementById('context-panel').getBoundingClientRect(); const consoleBox=document.getElementById('terminal-preview').getBoundingClientRect(); return {left:panel.left,right:panel.right,width:innerWidth,pageWidth:document.documentElement.scrollWidth,consoleWidth:consoleBox.width}")
                assert mobile_terminal["left"] >= 0 and mobile_terminal["right"] <= mobile_terminal["width"] + 1, mobile_terminal
                assert mobile_terminal["right"] - mobile_terminal["left"] >= mobile_terminal["width"] - 1, mobile_terminal
                assert mobile_terminal["pageWidth"] <= mobile_terminal["width"] + 1 and mobile_terminal["consoleWidth"] <= mobile_terminal["width"], mobile_terminal
                browser.save_screenshot("/tmp/zedlink-browser-terminal-mobile.png")
                browser.find_element(By.ID, "close-context").click()
                probe.edit_review = {"changed_files": 3, "lines_added": 18, "lines_removed": 4}
                probe.sequence += 1
                wait.until(lambda driver: driver.find_element(By.ID, "edit-review").is_displayed())
                collapsed_review = browser.execute_script("const review=document.getElementById('edit-review'); const control=review.getBoundingClientRect(); const composer=document.getElementById('composer-form').getBoundingClientRect(); return {controlWidth:control.width, controlHeight:control.height, composerBottom:composer.bottom, visibleBottom:visualViewport.height + visualViewport.offsetTop, menuVisible:review.open}")
                assert collapsed_review["controlWidth"] <= 38 and collapsed_review["controlHeight"] <= 38, collapsed_review
                assert not collapsed_review["menuVisible"] and collapsed_review["composerBottom"] <= collapsed_review["visibleBottom"] + 1, collapsed_review
                browser.find_element(By.CSS_SELECTOR, "#edit-review > summary").click()
                wait.until(lambda driver: driver.find_element(By.CSS_SELECTOR, "#edit-review .edit-review-menu").is_displayed())
                open_review = browser.execute_script("const menu=document.querySelector('.edit-review-menu').getBoundingClientRect(); const composer=document.getElementById('composer-form').getBoundingClientRect(); return {left:menu.left,right:menu.right,bottom:menu.bottom,width:innerWidth,composerBottom:composer.bottom,visibleBottom:visualViewport.height + visualViewport.offsetTop}")
                assert open_review["left"] >= 0 and open_review["right"] <= open_review["width"] + 1 and open_review["bottom"] <= open_review["visibleBottom"] + 1, open_review
                assert open_review["composerBottom"] <= open_review["visibleBottom"] + 1, open_review
                browser.find_element(By.CSS_SELECTOR, "#edit-review button.primary").click()
                wait.until(lambda driver: len(probe.edit_review_responses) == 2)
                assert not browser.find_elements(By.ID, "toggle-compose")
                assert browser.find_element(By.ID, "send").get_attribute("aria-label") == "Send message"
                browser.execute_script("openCodeReview('src/main.rs', 'fn main() { println!(\\\"ready\\\"); }\\n', 'rust', 1)")
                mobile_review = browser.execute_script("const panel=document.getElementById('code-review').getBoundingClientRect(); return {left:panel.left, right:panel.right, bottom:panel.bottom, width:innerWidth, height:innerHeight, pageWidth:document.documentElement.scrollWidth, wrapped:document.querySelector('#code-review .review-code').classList.contains('wrap')}")
                assert mobile_review["left"] >= 0 and mobile_review["right"] <= mobile_review["width"] + 1
                assert mobile_review["bottom"] >= mobile_review["height"] - 1
                assert mobile_review["pageWidth"] <= mobile_review["width"] + 1 and mobile_review["wrapped"], mobile_review
                assert browser.find_elements(By.CSS_SELECTOR, "#code-review-content .syntax-keyword")
                browser.save_screenshot("/tmp/zedlink-browser-code-review-mobile.png")
                browser.find_element(By.ID, "close-code-review").click()
                browser.find_element(By.ID, "back-sessions").click()
                assert browser.find_element(By.ID, "sessions-panel").is_displayed()
                assert browser.find_element(By.CSS_SELECTOR, ".topbar").is_displayed()
                assert browser.find_element(By.ID, "tab-sessions").is_displayed()
                mobile_icons = browser.execute_script("return [...document.querySelectorAll('.mobile-tab-icon')].map(icon => { const box=icon.getBoundingClientRect(); const style=getComputedStyle(icon); return {width:box.width,height:box.height,fontSize:style.fontSize,lineHeight:style.lineHeight}; })")
                assert len(mobile_icons) == 3 and len({tuple(icon.values()) for icon in mobile_icons}) == 1, mobile_icons
                assert "\ufe0e" in browser.find_element(By.CSS_SELECTOR, "#tab-settings .mobile-tab-icon").get_attribute("textContent")
                browser.execute_script("document.querySelector('.thread-item').click()")
                wait.until(lambda driver: driver.find_element(By.CSS_SELECTOR, ".workspace").is_displayed())
                assert not browser.find_element(By.ID, "activity-content").is_displayed()
                browser.find_element(By.ID, "back-sessions").click()
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
                assert browser.find_element(By.ID, "thread-agent-kind").get_attribute("textContent") == "EXTERNAL ACP AGENT"
                assert browser.find_element(By.ID, "prompt").get_attribute("placeholder") == "Message Codex…"
                assert browser.find_element(By.CSS_SELECTOR, ".message.assistant .message-label").get_attribute("textContent") == "Codex"
                browser.find_element(By.ID, "back-sessions").click()
                browser.find_element(By.ID, "tab-settings").click()
                wait.until(lambda driver: Select(driver.find_element(By.ID, "zed-model")).first_selected_option.text == "Managed by Codex")
                assert browser.find_element(By.ID, "settings-agent-kind").get_attribute("textContent") == "EXTERNAL ACP AGENT"
                assert not browser.find_element(By.ID, "save-zed-settings").is_enabled()
                assert "owns its model" in browser.find_element(By.ID, "zed-settings-help").text
                browser.find_element(By.ID, "settings-back").click()
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
                browser.set_window_size(1440, 900)
                probe.no_threads = True
                assert browser.execute_async_script(
                    "const done=arguments[0]; loadThreads().then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: driver.find_element(By.ID, "empty-state").is_displayed())
                assert not browser.find_element(By.ID, "subagents").is_displayed()
                assert not browser.find_element(By.ID, "approvals").is_displayed()
                browser.refresh()
                wait.until(lambda driver: driver.find_element(By.ID, "empty-state").is_displayed())
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").get_attribute("textContent") == "No remote sessions")
                wait.until(lambda driver: driver.find_element(By.ID, "thread-state").get_attribute("textContent") == "Connected")
                assert "no agent thread" in browser.find_element(By.ID, "empty-description").text
                wait.until(lambda driver: driver.find_element(By.ID, "empty-create").is_enabled())
                assert browser.execute_script(
                    "return getComputedStyle(document.querySelector('.composer-wrap')).display"
                ) == "none"
                browser.find_element(By.CSS_SELECTOR, "#empty-help summary").click()
                assert "/remote-control" in browser.find_element(By.ID, "empty-help").text
                browser.save_screenshot("/tmp/zedlink-browser-empty.png")
                probe.no_threads = False
                probe.extra_thread = True
                assert browser.execute_async_script(
                    "const done=arguments[0]; loadThreads().then(() => selectThread('fixture-second')).then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Second synthetic thread")
                assert browser.execute_async_script(
                    "const done=arguments[0]; selectThread('fixture-thread').then(() => done('ok'), error => done(String(error)))"
                ) == "ok"
                wait.until(lambda driver: driver.find_element(By.ID, "thread-title").text == "Synthetic test thread")
                browser.find_element(By.ID, "open-settings").click()
                wait.until(lambda driver: driver.find_element(By.ID, "settings-panel").is_displayed())
                browser.find_element(By.ID, "unexpose-session").click()
                browser.switch_to.alert.accept()
                wait.until(lambda driver: not probe.exposed_primary)
                wait.until(lambda driver: driver.find_element(By.ID, "thread-count").text == "2")
                assert "Synthetic test thread" not in browser.find_element(By.ID, "thread-list").text
                assert "Second synthetic thread" in browser.find_element(By.ID, "thread-list").text
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
                terminal_helper = subprocess.run(
                    ["python3", str(ROOT / "tools/pair_phone.py"), base, str(state),
                     "--mode", "terminal"],
                    capture_output=True, text=True, check=True, timeout=5,
                )
                assert "ZedLink private device pairing" in terminal_helper.stdout
                assert "\x1b[40m" in terminal_helper.stdout and "\x1b[47m" in terminal_helper.stdout
                assert "One-time code:" in terminal_helper.stdout and "Gateway ID:" in terminal_helper.stdout
                helper = subprocess.run(["python3", str(ROOT / "tools/pair_phone.py"), base,
                                         str(state), "--mode", "browser", "--no-open"],
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
                assert '<title>Pair a device · ZedLink</title>' in pairing_html
                assert "/v1/pairing-events" in pairing_html
                assert "zedlink-pairing-token-" in pairing_html
                assert 'id="live-status"' in pairing_html
                assert 'class="topbar"' in pairing_html and 'class="mark"' in pairing_html
                assert "Using the iPhone home-screen app?" in pairing_html
                assert "--panel:#0d0e10" in pairing_html and "border-radius:0" in pairing_html
                assert (f'<span>Gateway ID</span><code>{info["gateway_id"]}</code>'
                        in pairing_html)
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
                try:
                    first_page = subprocess.run(chromium_command + [chromium_link], check=True,
                                                capture_output=True, text=True, timeout=40).stdout
                    assert re.search(r'<section class="panel hidden" id="pair-panel">', first_page)
                    assert re.search(r'<section class="panel" id="sessions-panel">', first_page)
                    chromium_device = next(device for device in admin(state, "devices")["devices"]
                                           if device["name"] == "Chrome on Linux")
                    second_page = subprocess.run(chromium_command + [base + "/"], check=True,
                                                 capture_output=True, text=True, timeout=40).stdout
                    assert re.search(r'<section class="panel" id="sessions-panel">', second_page)
                    assert admin(state, "revoke", chromium_device["id"])["revoked"]
                except subprocess.TimeoutExpired:
                    print("SKIP: Chromium browser check (headless Chromium timed out)")
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
