#!/usr/bin/env python3
"""Disposable local Tailscale-interface HTTPS bind check; no remote peer or Zed model."""

import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path

from test_gateway_transport import BINARY, ProbeFixture


def main():
    ip = subprocess.check_output(["tailscale", "ip", "-4"], text=True, timeout=5).strip()
    with tempfile.TemporaryDirectory(prefix="zedlink-tailnet-bind.") as temporary:
        root = Path(temporary)
        probe_dir = root / "probe"
        probe_dir.mkdir(mode=0o700)
        probe = ProbeFixture(probe_dir / "zedlink.sock")
        cert, key, state = root / "cert.pem", root / "key.pem", root / "state"
        subprocess.run(["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-keyout", str(key), "-out", str(cert), "-days", "1",
                        "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os.chmod(key, 0o600)
        with socket.socket() as candidate:
            candidate.bind((ip, 0))
            port = candidate.getsockname()[1]
        server = subprocess.Popen([str(BINARY), "serve", f"{ip}:{port}", str(cert), str(key),
                                   str(probe.path), str(state)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if (state / "admin.sock").exists():
                    break
                if server.poll() is not None:
                    raise RuntimeError("gateway exited before binding")
                time.sleep(0.05)
            else:
                raise RuntimeError("gateway did not bind")
            response = subprocess.check_output([
                "curl", "--silent", "--show-error", "--fail", "--noproxy", "*",
                "--cacert", str(cert), "--resolve", f"localhost:{port}:{ip}",
                f"https://localhost:{port}/v1/gateway",
            ], text=True, timeout=5)
            assert json.loads(response)["gateway_id"]
            print("PASS: gateway TLS request on local Tailscale IPv4 using a synthetic probe; no remote peer tested")
        finally:
            server.terminate()
            server.communicate(timeout=3)
            probe.close()


if __name__ == "__main__":
    main()
