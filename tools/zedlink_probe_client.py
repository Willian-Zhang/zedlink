#!/usr/bin/env python3
"""Terminal client for the opt-in pinned-Zed local probe."""

import argparse
import json
import socket
import sys
import time
import uuid


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
    parser.add_argument("--after-sequence", type=int, default=0, help="Event cursor for events")
    parser.add_argument("--title", help="Optional title for a new native Zed Agent session")
    parser.add_argument("--profile-id", help="Native Agent profile ID for update-settings")
    parser.add_argument("--thinking-enabled", choices=("true", "false"), help="Native model thinking state for update-settings")
    parser.add_argument("operation", choices=("info", "list", "create", "snapshot", "events", "watch", "commands", "settings", "update-settings", "send", "cancel", "status", "approvals", "respond"))
    parser.add_argument("thread_id", nargs="?")
    parser.add_argument("text", nargs="?")
    args = parser.parse_args()

    if args.operation in ("info", "list", "create") and (args.thread_id or args.text):
        parser.error(f"{args.operation} does not accept a thread_id or text")
    if args.operation == "status" and (args.thread_id or args.text or not args.original_request_id):
        parser.error("status requires --original-request-id and no positional arguments")
    if args.operation in ("snapshot", "events", "watch", "commands", "settings", "update-settings", "approvals") and (not args.thread_id or args.text):
        parser.error(f"{args.operation} requires only a thread_id")
    if args.operation == "send" and (not args.thread_id or not args.text):
        parser.error("send requires a thread_id and text")
    if args.operation == "cancel" and (not args.thread_id or args.text or args.turn_id is None):
        parser.error("cancel requires only a thread_id and --turn-id")
    if args.operation == "respond" and (not args.thread_id or args.text or args.turn_id is None or not args.approval_id or not args.decision):
        parser.error("respond requires thread_id, --turn-id, --approval-id, and --decision")
    if args.operation in ("create", "send", "cancel", "status", "respond") and (not args.instance_id or not args.epoch):
        parser.error("create, send, cancel, status, and respond require --instance-id and --epoch from thread.list")
    if args.operation in ("create", "send", "cancel", "respond") and not args.request_id:
        parser.error("create, send, cancel, and respond require a stable --request-id")
    if args.operation not in ("create", "send", "cancel", "respond") and args.request_id:
        parser.error("--request-id is only available for create, send, cancel, or respond")
    if args.operation not in ("create", "send", "cancel", "status", "respond", "commands", "settings", "update-settings") and (args.instance_id or args.epoch):
        parser.error("--instance-id and --epoch are not available for this operation")
    if args.operation in ("commands", "settings", "update-settings") and (not args.instance_id or not args.epoch):
        parser.error(f"{args.operation} requires --instance-id and --epoch from thread.list")
    if args.operation not in ("cancel", "respond") and args.turn_id is not None:
        parser.error("--turn-id is only available for cancel or respond")
    if args.operation != "respond" and (args.approval_id or args.decision):
        parser.error("--approval-id and --decision are only available for respond")
    if args.operation != "status" and args.original_request_id:
        parser.error("--original-request-id is only available for status")
    if args.operation != "create" and args.title:
        parser.error("--title is only available for create")
    if args.operation != "update-settings" and (args.profile_id or args.thinking_enabled):
        parser.error("--profile-id and --thinking-enabled are only available for update-settings")
    if args.operation == "update-settings" and not (args.profile_id or args.thinking_enabled):
        parser.error("update-settings requires --profile-id or --thinking-enabled")
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
    if args.operation == "create":
        params.update(title=args.title, instance_id=args.instance_id, epoch=args.epoch)
    if args.operation == "commands":
        params.update(instance_id=args.instance_id, epoch=args.epoch)
    if args.operation in ("settings", "update-settings"):
        params.update(instance_id=args.instance_id, epoch=args.epoch)
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
            decision=args.decision,
            turn_id=args.turn_id,
            instance_id=args.instance_id,
            epoch=args.epoch,
        )
    payload = call(
        {"info": "instance.info", "status": "request.status", "respond": "approval.respond",
         "settings": "thread.settings", "update-settings": "thread.settings.update"}.get(
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
