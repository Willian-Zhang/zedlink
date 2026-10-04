#!/usr/bin/env python3
"""TLS terminal client for a paired ZedLink gateway. Never disables TLS verification."""
import argparse
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        return None


def endpoint(base):
    parsed = urllib.parse.urlsplit(base)
    if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("A plain HTTPS base URL without credentials, query, or fragment is required")
    return base.rstrip("/")


def opener(ca_file):
    context = ssl.create_default_context(cafile=ca_file)
    context.check_hostname = True
    context.verify_mode = ssl.CERT_REQUIRED
    return urllib.request.build_opener(urllib.request.HTTPSHandler(context=context), NoRedirect())


def request(http, base, path, method="GET", payload=None, token=None):
    address = base + path
    headers = {"Accept": "application/json"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    if token is not None:
        headers["Authorization"] = "Bearer " + token
    data = json.dumps(payload, separators=(",", ":")).encode() if payload is not None else None
    req = urllib.request.Request(address, data=data, headers=headers, method=method)
    try:
        with http.open(req, timeout=10) as response:
            if response.status != 200:
                raise ValueError(f"HTTP {response.status}")
            body = response.read(1024 * 1024 + 1)
    except urllib.error.HTTPError as error:
        if 300 <= error.code < 400:
            raise ValueError("Redirect refused; verify the selected endpoint") from None
        raise ValueError(f"Gateway returned HTTP {error.code}") from None
    if len(body) > 1024 * 1024:
        raise ValueError("Gateway response exceeds limit")
    return json.loads(body)


def read_token(path):
    token_file = Path(path)
    if token_file.stat().st_mode & 0o077:
        raise ValueError("Device token file must be private (mode 0600)")
    data = json.loads(token_file.read_text())
    if not all(data.get(field) for field in ("gateway_id", "device_id", "token")):
        raise ValueError("Invalid device token file")
    return data


def save_token(path, data):
    path = Path(path)
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w") as output:
        json.dump(data, output)
        output.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", required=True)
    parser.add_argument("--ca-file", help="CA/certificate PEM for a trusted local gateway")
    parser.add_argument("--token-file")
    parser.add_argument("--code-file", help="Private file containing a one-use pairing code")
    parser.add_argument("--device-name")
    parser.add_argument("--expected-gateway-id")
    parser.add_argument("--request-id")
    parser.add_argument("--after-sequence", type=int, default=0)
    parser.add_argument("operation", choices=("info", "pair", "rpc", "watch"))
    parser.add_argument("method_or_thread", nargs="?")
    parser.add_argument("params_json", nargs="?")
    args = parser.parse_args()

    base = endpoint(args.base_url)
    http = opener(args.ca_file)
    info = request(http, base, "/v1/gateway")
    gateway_id = info["gateway_id"]
    if args.expected_gateway_id and gateway_id != args.expected_gateway_id:
        raise ValueError("Gateway identity changed; no credential sent")
    if args.operation == "info":
        print(json.dumps(info, indent=2))
        return 0
    if not args.token_file:
        parser.error("--token-file is required for pair, rpc, and watch")
    if args.operation == "pair":
        if not args.code_file or not args.device_name or not args.expected_gateway_id:
            parser.error("pair requires --code-file, --device-name, and --expected-gateway-id")
        code_path = Path(args.code_file)
        if code_path.stat().st_mode & 0o077:
            raise ValueError("Pair code file must be private (mode 0600)")
        code = code_path.read_text().strip()
        if len(code) != 64:
            raise ValueError("Invalid pair code length")
        paired = request(http, base, "/v1/pair", "POST",
                         {"code": code, "device_name": args.device_name})
        if paired["gateway_id"] != gateway_id:
            raise ValueError("Pair response gateway identity mismatch")
        save_token(args.token_file, paired)
        print(json.dumps({"gateway_id": gateway_id, "device_id": paired["device_id"],
                          "token_file": args.token_file}, indent=2))
        return 0

    token = read_token(args.token_file)
    if token["gateway_id"] != gateway_id:
        raise ValueError("Gateway identity changed; no credential sent")
    if args.operation == "rpc":
        if not args.method_or_thread or not args.params_json:
            parser.error("rpc requires METHOD and PARAMS_JSON")
        params = json.loads(args.params_json)
        if not isinstance(params, dict):
            raise ValueError("RPC params must be an object")
        if args.method_or_thread == "thread.send" and not args.request_id:
            parser.error("thread.send requires a stable --request-id")
        envelope = {"version": 1, "request_id": args.request_id or str(uuid.uuid4()),
                    "method": args.method_or_thread, "params": params}
        response = request(http, base, "/v1/rpc", "POST", envelope, token["token"])
        if response.get("request_id") != envelope["request_id"]:
            raise ValueError("Response request ID mismatch")
        print(json.dumps(response, indent=2))
        return 0 if "result" in response else 1
    if args.operation == "watch":
        if not args.method_or_thread or args.params_json or args.after_sequence < 0:
            parser.error("watch requires THREAD_ID and nonnegative --after-sequence")
        sequence = args.after_sequence
        while True:
            envelope = {"version": 1, "request_id": str(uuid.uuid4()),
                        "method": "thread.events",
                        "params": {"thread_id": args.method_or_thread, "after_sequence": sequence}}
            response = request(http, base, "/v1/rpc", "POST", envelope, token["token"])
            if "error" in response:
                print(json.dumps(response, indent=2))
                return 1
            result = response["result"]
            for event in result["events"]:
                print(json.dumps(event), flush=True)
            sequence = result["last_sequence"]
            time.sleep(0.25)
    return 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, urllib.error.URLError) as error:
        print(f"Gateway client: {error}", file=sys.stderr)
        sys.exit(2)
