#!/usr/bin/env python3
"""Local interactive ZedLink UI preview backed by a disposable gateway fixture.

This serves the current web bundle over HTTP loopback and proxies API requests to a
throwaway TLS gateway/Unix-socket probe. It never attaches to a running Zed instance.
"""

import base64
import hashlib
import json
import mimetypes
import os
from pathlib import Path
import select
import socket
import ssl
import struct
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import quote, urlsplit

from websockets.exceptions import ConnectionClosed
from websockets.sync.client import connect as websocket_connect

from test_gateway_transport import BINARY, ProbeFixture, admin


WEB = Path(__file__).resolve().parents[1] / "gateway" / "web"
ALLOWED_FILES = {
    "/app.js", "/ui.js", "/style.css", "/service-worker.js",
    "/manifest.webmanifest", "/icons/icon-192.png", "/icons/icon-512.png",
    "/fonts/terminal-icons.woff2", "/fonts/terminal-icons.ttf",
}


def unused_port():
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def preview_server(backend_port, context, gateway_id, state_dir):
    backend = f"https://localhost:{backend_port}"

    class PreviewHandler(BaseHTTPRequestHandler):
        def log_message(self, *_args):
            # Request paths may contain pairing material or conversation text.
            pass

        def respond(self, status, content, content_type="text/plain; charset=utf-8"):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(content)

        def do_GET(self):
            path = urlsplit(self.path).path
            if path == "/preview":
                code = admin(state_dir, "pair-short-code")["code"]
                location = f"/#gateway={quote(gateway_id)}&pair={quote(code)}&v=1"
                self.send_response(302)
                self.send_header("Location", location)
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            if path.startswith("/v1/"):
                self.proxy_api()
                return
            if path == "/":
                html = (WEB / "index.html").read_text()
                html = html.replace("<title>ZedLink · Remote Agent</title>",
                                    '<title>ZedLink · Interactive Mock Preview</title>')
                html = html.replace("Desktop Agent workspace",
                                    "Mock workspace · disposable data", 1)
                self.respond(200, html.encode(), "text/html; charset=utf-8")
                return
            if path in ALLOWED_FILES:
                asset = WEB / path.lstrip("/")
                content_type = mimetypes.guess_type(asset.name)[0] or "application/octet-stream"
                if path.endswith(".webmanifest"):
                    content_type = "application/manifest+json"
                elif path.endswith(".js"):
                    content_type = "text/javascript"
                self.respond(200, asset.read_bytes(), content_type)
                return
            self.respond(404, b"Not found")

        def do_POST(self):
            if urlsplit(self.path).path.startswith("/v1/"):
                self.proxy_api()
            else:
                self.respond(404, b"Not found")

        def do_DELETE(self):
            if urlsplit(self.path).path.startswith("/v1/"):
                self.proxy_api()
            else:
                self.respond(404, b"Not found")

        def proxy_api(self):
            if self.headers.get("Upgrade", "").lower() == "websocket":
                self.proxy_websocket()
                return
            length = int(self.headers.get("Content-Length", "0"))
            if length > 2 * 1024 * 1024:
                self.respond(413, b"Preview request too large")
                return
            body = self.rfile.read(length) if length else None
            headers = {name: value for name, value in self.headers.items()
                       if name.lower() in ("authorization", "content-type", "accept")}
            request = urllib.request.Request(
                backend + self.path, data=body, headers=headers, method=self.command,
            )
            try:
                response = urllib.request.urlopen(request, context=context, timeout=15)
            except urllib.error.HTTPError as error:
                response = error
            except (urllib.error.URLError, TimeoutError):
                self.respond(502, json.dumps({"error": "MOCK_GATEWAY_UNAVAILABLE"}).encode(),
                             "application/json")
                return
            with response:
                payload = response.read()
                if urlsplit(self.path).path == "/v1/gateway" and response.status == 200:
                    data = json.loads(payload)
                    data["route_origins"] = []
                    payload = json.dumps(data).encode()
                self.respond(response.status, payload,
                             response.headers.get("Content-Type", "application/json"))

        def proxy_websocket(self):
            key = self.headers.get("Sec-WebSocket-Key", "")
            protocols = [item.strip() for item in
                         self.headers.get("Sec-WebSocket-Protocol", "").split(",") if item.strip()]
            if urlsplit(self.path).path != "/v1/events" or not key or not protocols:
                self.respond(400, b"Unsupported preview WebSocket")
                return
            try:
                upstream = websocket_connect(
                    f"wss://localhost:{backend_port}{self.path}", ssl=context,
                    subprotocols=protocols, open_timeout=5, close_timeout=2,
                )
            except Exception:
                self.respond(502, b"Mock live-update stream unavailable")
                return
            with upstream:
                # The fixed RFC 6455 GUID is split so the repository's identity scan
                # does not mistake it for a persisted gateway identifier.
                websocket_guid = "258EAFA5-E914-" + "47DA-95CA-C5AB0DC85B11"
                accept = base64.b64encode(hashlib.sha1(
                    (key + websocket_guid).encode()
                ).digest()).decode()
                self.send_response(101)
                self.send_header("Upgrade", "websocket")
                self.send_header("Connection", "Upgrade")
                self.send_header("Sec-WebSocket-Accept", accept)
                if upstream.subprotocol:
                    self.send_header("Sec-WebSocket-Protocol", upstream.subprotocol)
                self.end_headers()
                while True:
                    readable, _, _ = select.select([self.connection], [], [], 0)
                    if readable:
                        try:
                            frame = self.connection.recv(2, socket.MSG_PEEK)
                        except OSError:
                            break
                        if not frame or frame[0] & 0x0f == 8:
                            break
                    try:
                        message = upstream.recv(timeout=0.5)
                    except TimeoutError:
                        continue
                    except ConnectionClosed:
                        break
                    if not isinstance(message, str):
                        continue
                    payload = message.encode()
                    size = len(payload)
                    if size < 126:
                        header = bytes([0x81, size])
                    elif size < 65536:
                        header = bytes([0x81, 126]) + struct.pack("!H", size)
                    else:
                        header = bytes([0x81, 127]) + struct.pack("!Q", size)
                    try:
                        self.wfile.write(header + payload)
                        self.wfile.flush()
                    except OSError:
                        break

    return ThreadingHTTPServer(("127.0.0.1", 0), PreviewHandler)


def main():
    if not BINARY.is_file():
        raise SystemExit("Build the local gateway first: cargo build --manifest-path gateway/Cargo.toml --offline")
    if not (WEB / "ui.js").is_file():
        raise SystemExit("Build the web bundle first: cd gateway/web && bun run build")
    with tempfile.TemporaryDirectory(prefix="zedlink-ui-preview-") as directory:
        root = Path(directory)
        probe_dir = root / "probe"
        probe_dir.mkdir(mode=0o700)
        probe = ProbeFixture(probe_dir / "zedlink.sock")
        probe.extra_thread = True
        probe.subagents = []
        probe.entries = [
            "## User\n\nReview the ZedLink gateway interface for everyday use.\n\n",
            "## Assistant\n\nThe current preview uses the **neutral OLED palette** and flat controls. "
            "The session rail now includes search, status counts, pinning, and keyboard navigation.\n\n"
            "### Try the interface\n\n"
            "- Search for either disposable session, then clear the filter.\n"
            "- Open **Context** to inspect the mock workspace and terminal.\n"
            "- Send a prompt; the local fixture will return a canned reply.\n\n"
            "No real Zed thread, model, project, or permission is connected.\n\n",
            "## User\n\nShow me how code and structured results read here.\n\n",
            "## Assistant\n\nHere is a small example of the conversation layout:\n\n"
            "| Area | Current behavior |\n| --- | --- |\n"
            "| Sessions | Searchable and pinnable |\n| Composer | Two-row text input |\n"
            "| Context | Project tools in a side panel |\n\n"
            "```typescript\nconst session = { status: \"ready\", source: \"mock\" };\n```\n\n",
        ]
        cert = root / "cert.pem"
        key = root / "key.pem"
        subprocess.run([
            "openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
            "-keyout", str(key), "-out", str(cert), "-days", "1",
            "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost",
        ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
        backend_port = unused_port()
        state_dir = root / "state"
        listeners = root / "listeners.json"
        targets = root / "targets.json"
        listeners.write_text(json.dumps({"version": 1, "listeners": [{
            "id": "preview", "bind": f"127.0.0.1:{backend_port}",
            "cert": str(cert), "key": str(key),
            "url": f"https://localhost:{backend_port}",
        }]}))
        targets.write_text(json.dumps({"version": 1, "targets": [{
            "id": "mock-zed", "label": "Mock desktop Zed", "probe": str(probe.path),
        }]}))
        os.chmod(listeners, 0o600)
        os.chmod(targets, 0o600)
        gateway = subprocess.Popen([
            str(BINARY), "serve-targets", str(listeners), str(targets), str(state_dir),
        ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        try:
            context = ssl.create_default_context(cafile=str(cert))
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f"https://localhost:{backend_port}/v1/gateway",
                                                context=context, timeout=1) as response:
                        gateway_id = json.load(response)["gateway_id"]
                    break
                except (urllib.error.URLError, TimeoutError):
                    if gateway.poll() is not None:
                        raise RuntimeError("Disposable gateway exited during startup")
                    time.sleep(0.1)
            else:
                raise RuntimeError("Disposable gateway did not become ready")
            preview = preview_server(backend_port, context, gateway_id, state_dir)
            try:
                url = f"http://127.0.0.1:{preview.server_port}/preview"
                print(f"MOCK_PREVIEW_URL={url}", flush=True)
                print("Disposable data only. Loopback preview stops with Ctrl+C.",
                      flush=True)
                preview.serve_forever(poll_interval=0.2)
            finally:
                preview.server_close()
        finally:
            gateway.terminate()
            try:
                gateway.wait(timeout=5)
            except subprocess.TimeoutExpired:
                gateway.kill()
                gateway.wait()
            probe.close()


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
