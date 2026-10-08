#!/usr/bin/env python3
"""Terminal client for the opt-in pinned-Zed local probe."""

import argparse
import base64
import json
import mimetypes
import socket
import sys
import time
import uuid
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--socket", required=True, help="Path to the private zedlink.sock")
    parser.add_argument("--request-id", help="Stable ID to retry a send without duplicating it")
    parser.add_argument("--original-request-id", help="Prior send request ID for status lookup")
    parser.add_argument("--instance-id", help="Instance ID from thread.list, required for send/cancel")
    parser.add_argument("--epoch", help="Epoch from thread.list, required for send/cancel")
    parser.add_argument("--turn-id", type=int, help="Current turn ID from thread.snapshot for cancel")
    parser.add_argument("--approval-id", help="Exact pending approval ID from thread.approvals")
    parser.add_argument("--decision", choices=("approve_once", "deny_once"))
    parser.add_argument("--option-id", help="Exact native permission option ID from thread.approvals")
    parser.add_argument("--choice-index", type=int, help="Native dropdown choice index for --option-id")
    parser.add_argument("--pattern-index", type=int, action="append", help="Checked terminal permission pattern; repeat as needed")
    parser.add_argument("--subagent-id", help="Owning subagent ID for a nested approval")
    parser.add_argument("--after-sequence", type=int, default=0, help="Event cursor for events")
    parser.add_argument("--title", help="Optional title for a new native Zed Agent session")
    parser.add_argument("--profile-id", help="Native Agent profile ID for update-settings")
    parser.add_argument("--thinking-enabled", choices=("true", "false"), help="Native model thinking state for update-settings")
    parser.add_argument("--path", action="append", help="Project or repository relative path; repeat for Git operations")
    parser.add_argument("--revision", help="Expected repository revision from changes")
    parser.add_argument("--query", help="Text to search for inside exposed project files")
    parser.add_argument("--case-sensitive", action="store_true", help="Use case-sensitive project search")
    parser.add_argument("--context-path", action="append", help="Project relative file to attach to send; repeat as needed")
    parser.add_argument("--upload-file", action="append", help="Text or image file to upload with send; repeat as needed")
    parser.add_argument("operation", choices=("info", "list", "create", "snapshot", "events", "watch", "commands", "settings", "update-settings", "files", "file", "search", "changes", "diff", "stage", "unstage", "send", "cancel", "status", "approvals", "respond"))
    parser.add_argument("thread_id", nargs="?")
    parser.add_argument("text", nargs="?")
    args = parser.parse_args()

    if args.operation in ("info", "list", "create") and (args.thread_id or args.text):
        parser.error(f"{args.operation} does not accept a thread_id or text")
    if args.operation == "status" and (args.thread_id or args.text or not args.original_request_id):
        parser.error("status requires --original-request-id and no positional arguments")
    if args.operation in ("snapshot", "events", "watch", "commands", "settings", "update-settings", "files", "file", "search", "changes", "diff", "stage", "unstage", "approvals") and (not args.thread_id or args.text):
        parser.error(f"{args.operation} requires only a thread_id")
    if args.operation == "send" and (not args.thread_id or not args.text):
        parser.error("send requires a thread_id and text")
    if args.operation == "cancel" and (not args.thread_id or args.text or args.turn_id is None):
        parser.error("cancel requires only a thread_id and --turn-id")
    if args.operation == "respond" and (not args.thread_id or args.text or args.turn_id is None
                                         or not args.approval_id or bool(args.decision) == bool(args.option_id)):
        parser.error("respond requires thread_id, --turn-id, --approval-id, and exactly one of --option-id or legacy --decision")
    identified = ("create", "send", "cancel", "status", "respond", "commands", "settings", "update-settings", "files", "file", "search", "changes", "diff", "stage", "unstage")
    if args.operation in identified and (not args.instance_id or not args.epoch):
        parser.error(f"{args.operation} requires --instance-id and --epoch from thread.list")
    if args.operation in ("create", "send", "cancel", "respond", "stage", "unstage") and not args.request_id:
        parser.error(f"{args.operation} requires a stable --request-id")
    if args.operation not in ("create", "send", "cancel", "respond", "stage", "unstage") and args.request_id:
        parser.error("--request-id is unavailable for this operation")
    if args.operation not in identified and (args.instance_id or args.epoch):
        parser.error("--instance-id and --epoch are not available for this operation")
    if args.operation in ("commands", "settings", "update-settings") and (not args.instance_id or not args.epoch):
        parser.error(f"{args.operation} requires --instance-id and --epoch from thread.list")
    if args.operation not in ("cancel", "respond") and args.turn_id is not None:
        parser.error("--turn-id is only available for cancel or respond")
    if args.operation != "respond" and (args.approval_id or args.decision or args.option_id
                                         or args.choice_index is not None or args.pattern_index or args.subagent_id):
        parser.error("approval selection arguments are only available for respond")
    if args.operation == "respond" and args.option_id and args.choice_index is None and args.pattern_index:
        parser.error("--pattern-index requires --choice-index")
    if args.operation == "respond" and args.choice_index is not None and not args.option_id:
        parser.error("--choice-index requires --option-id")
    if args.operation != "status" and args.original_request_id:
        parser.error("--original-request-id is only available for status")
    if args.operation != "create" and args.title:
        parser.error("--title is only available for create")
    if args.operation != "update-settings" and (args.profile_id or args.thinking_enabled):
        parser.error("--profile-id and --thinking-enabled are only available for update-settings")
    if args.operation == "update-settings" and not (args.profile_id or args.thinking_enabled):
        parser.error("update-settings requires --profile-id or --thinking-enabled")
    if args.operation == "file" and (not args.path or len(args.path) != 1):
        parser.error("file requires exactly one --path")
    if args.operation == "search" and (not args.query or len(args.query.strip()) < 2):
        parser.error("search requires --query with at least two characters")
    if args.operation in ("stage", "unstage") and (not args.path or not args.revision):
        parser.error(f"{args.operation} requires one or more --path values and --revision")
    if args.operation == "diff" and (not args.revision or args.path):
        parser.error("diff requires --revision and no --path")
    if args.operation not in ("file", "stage", "unstage") and args.path:
        parser.error("--path is only available for file, stage, or unstage")
    if args.operation != "search" and (args.query or args.case_sensitive):
        parser.error("--query and --case-sensitive are only available for search")
    if args.operation not in ("diff", "stage", "unstage") and args.revision:
        parser.error("--revision is only available for diff, stage, or unstage")
    if args.operation != "send" and args.context_path:
        parser.error("--context-path is only available for send")
    if args.operation != "send" and args.upload_file:
        parser.error("--upload-file is only available for send")
    if args.operation in ("cancel", "respond") and args.turn_id < 0:
        parser.error("--turn-id must be nonnegative")
    if args.after_sequence < 0 or (
        args.operation not in ("events", "watch") and args.after_sequence
    ):
        parser.error("--after-sequence must be nonnegative and is only for events or watch")

    def call(method: str, params: dict, request_id: str) -> dict:
        request = {
            "version": 1,
            "request_id": request_id,
            "method": method,
            "params": params,
        }
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as connection:
            connection.settimeout(8)
            connection.connect(args.socket)
            connection.sendall(json.dumps(request, separators=(",", ":")).encode() + b"\n")
            with connection.makefile("rb") as response_stream:
                response = response_stream.readline(1024 * 1024 + 1)

        if not response or len(response) > 1024 * 1024:
            raise ValueError("Missing or oversized probe response")
        payload = json.loads(response)
        if payload.get("request_id") != request_id:
            raise ValueError("Probe response request ID mismatch")
        return payload

    params = {"thread_id": args.thread_id} if args.thread_id else {}
    if args.operation == "watch":
        sequence = args.after_sequence
        while True:
            payload = call(
                "thread.events",
                {"thread_id": args.thread_id, "after_sequence": sequence},
                str(uuid.uuid4()),
            )
            if "error" in payload:
                print(json.dumps(payload, indent=2))
                return 1
            result = payload["result"]
            for event in result["events"]:
                print(json.dumps(event), flush=True)
            sequence = result["last_sequence"]
            time.sleep(0.25)
    if args.operation == "events":
        params["after_sequence"] = args.after_sequence
    if args.operation == "send":
        params.update(
            text=args.text,
            instance_id=args.instance_id,
            epoch=args.epoch,
        )
        if args.context_path:
            params["context_paths"] = args.context_path
        if args.upload_file:
            uploads = []
            for raw_path in args.upload_file:
                path = Path(raw_path)
                data = path.read_bytes()
                if len(data) > 1024 * 1024:
                    parser.error(f"upload exceeds 1 MiB: {path}")
                uploads.append({
                    "name": path.name,
                    "mime_type": mimetypes.guess_type(path.name)[0] or "text/plain",
                    "data": base64.b64encode(data).decode(),
                })
            params["uploads"] = uploads
    if args.operation == "create":
        params.update(title=args.title, instance_id=args.instance_id, epoch=args.epoch)
    if args.operation == "commands":
        params.update(instance_id=args.instance_id, epoch=args.epoch)
    if args.operation in ("settings", "update-settings"):
        params.update(instance_id=args.instance_id, epoch=args.epoch)
    if args.operation in ("files", "file", "search", "changes", "diff", "stage", "unstage"):
        params.update(instance_id=args.instance_id, epoch=args.epoch)
    if args.operation == "file":
        params["path"] = args.path[0]
    if args.operation == "search":
        params.update(query=args.query, case_sensitive=args.case_sensitive)
    if args.operation == "diff":
        params["revision"] = args.revision
    if args.operation in ("stage", "unstage"):
        params.update(paths=args.path, revision=args.revision)
    if args.operation == "update-settings":
        if args.profile_id:
            params["profile_id"] = args.profile_id
        if args.thinking_enabled:
            params["thinking_enabled"] = args.thinking_enabled == "true"
    if args.operation == "cancel":
        params.update(
            turn_id=args.turn_id,
            instance_id=args.instance_id,
            epoch=args.epoch,
        )
    if args.operation == "status":
        params.update(
            original_request_id=args.original_request_id,
            instance_id=args.instance_id,
            epoch=args.epoch,
        )
    if args.operation == "respond":
        params.update(
            approval_id=args.approval_id,
            turn_id=args.turn_id,
            instance_id=args.instance_id,
            epoch=args.epoch,
        )
        if args.decision:
            params["decision"] = args.decision
        else:
            params["option_id"] = args.option_id
            if args.choice_index is not None:
                params["choice_index"] = args.choice_index
            if args.pattern_index:
                params["selected_pattern_indices"] = args.pattern_index
        if args.subagent_id:
            params["subagent_id"] = args.subagent_id
    payload = call(
        {"info": "instance.info", "status": "request.status", "respond": "approval.respond",
         "settings": "thread.settings", "update-settings": "thread.settings.update",
         "files": "project.files", "file": "project.file", "search": "project.search", "changes": "changes.snapshot",
         "diff": "changes.diff", "stage": "changes.stage", "unstage": "changes.unstage"}.get(
            args.operation, f"thread.{args.operation}"
        ),
        params,
        args.request_id or str(uuid.uuid4()),
    )
    print(json.dumps(payload, indent=2))
    return 0 if "result" in payload else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, json.JSONDecodeError) as error:
        print(f"Probe unavailable: {error}", file=sys.stderr)
        sys.exit(2)
