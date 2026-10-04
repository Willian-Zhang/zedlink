#!/usr/bin/env python3
"""Isolated Moshi scanner control for a disposable HTTP server and ZedLink HTTPS."""

import json
import os
import socket
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from test_gateway_transport import BINARY, ProbeFixture


class Control(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        self.wfile.write(b"<title>ZedLink disposable HTTP control</title>")

    def log_message(self, *_args):
        pass


def scan(environment, port):
    result = subprocess.run(["moshi-hook", "servers"], env=environment,
                            capture_output=True, text=True, timeout=15, check=True)
    payload = json.loads(result.stdout)
    return any(server.get("port") == port for server in payload.get("servers", []))


def main():
    with tempfile.TemporaryDirectory(prefix="zedlink-moshi-discovery.") as temporary:
        root = Path(temporary)
        config = root / "moshi-config"
        environment = dict(os.environ, XDG_CONFIG_HOME=str(config))
        control = ThreadingHTTPServer(("127.0.0.1", 0), Control)
        port = control.server_address[1]
        subprocess.run(["moshi-hook", "set", "scan-ports", str(port)], env=environment,
                       capture_output=True, text=True, timeout=5, check=True)
        setting = subprocess.run(["moshi-hook", "set", "scan-ports"], env=environment,
                                 capture_output=True, text=True, timeout=5, check=True)
        if str(port) not in setting.stdout or str(config) not in setting.stdout:
            raise RuntimeError("Moshi scanner was not confined to the disposable test port")
        worker = threading.Thread(target=control.serve_forever, daemon=True)
        worker.start()
        try:
            http_found = scan(environment, port)
        finally:
            control.shutdown()
            control.server_close()
            worker.join()
        if not http_found:
            raise RuntimeError("Moshi did not discover the plain-HTTP control")

        probe_dir = root / "probe"
        probe_dir.mkdir(mode=0o700)
        probe = ProbeFixture(probe_dir / "zedlink.sock")
        cert, key, state = root / "cert.pem", root / "key.pem", root / "gateway-state"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
        environment["SSL_CERT_FILE"] = str(cert)
        server = subprocess.Popen([str(BINARY), "serve", f"127.0.0.1:{port}", str(cert), str(key),
                                   str(probe.path), str(state)], stdout=subprocess.DEVNULL,
                                  stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if (state / "admin.sock").exists():
                    break
                if server.poll() is not None:
                    raise RuntimeError("disposable gateway exited")
                time.sleep(0.05)
            else:
                raise RuntimeError("disposable gateway did not start")
            with socket.create_connection(("127.0.0.1", port), timeout=3):
                pass
            https_found = scan(environment, port)
            print(json.dumps({"moshi_version": subprocess.check_output(
                ["moshi-hook", "--version"], text=True).strip(),
                "isolated_http_control_discovered": http_found,
                "zedlink_https_discovered_with_ssl_cert_file": https_found,
                "global_moshi_config_changed": False}, indent=2))
        finally:
            server.terminate()
            server.communicate(timeout=3)
            probe.close()


if __name__ == "__main__":
    main()
