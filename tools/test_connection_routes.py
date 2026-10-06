#!/usr/bin/env python3
"""Deterministic multi-route gateway and manager tests using loopback only."""

import json
import os
from pathlib import Path
import socket
import subprocess
import tempfile
import time

from test_gateway_transport import BINARY, ProbeFixture
import zedlink_manager as manager


def free_port() -> int:
    with socket.socket() as candidate:
        candidate.bind(("127.0.0.1", 0))
        return candidate.getsockname()[1]


def generate_certificate(root: Path) -> tuple[Path, Path]:
    cert = root / "cert.pem"
    key = root / "key.pem"
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-keyout", str(key), "-out", str(cert), "-days", "1",
         "-subj", "/CN=localhost", "-addext", "subjectAltName=DNS:localhost"],
        check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    os.chmod(key, 0o600)
    return cert, key


def request_identity(cert: Path, port: int) -> str:
    response = subprocess.check_output(
        ["curl", "--silent", "--show-error", "--fail", "--noproxy", "*",
         "--cacert", str(cert), f"https://localhost:{port}/v1/gateway"],
        text=True, timeout=5)
    return json.loads(response)["gateway_id"]


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="zedlink-routes.") as temporary:
        root = Path(temporary)
        project = root / "project"
        project.mkdir()
        state = root / "state"
        state.mkdir(mode=0o700)
        (state / "gateway").mkdir(mode=0o700)
        probe_dir = root / "probe"
        probe_dir.mkdir(mode=0o700)
        probe = ProbeFixture(probe_dir / "zedlink.sock")
        cert, key = generate_certificate(root)
        first, second = free_port(), free_port()
        legacy = {
            "project_root": str(project), "state_dir": str(state),
            "bind": f"127.0.0.1:{first}", "url": f"https://localhost:{first}",
            "cert": str(cert), "key": str(key), "zed_user_data_dir": "",
        }
        migrated = manager.validate(legacy)
        assert migrated["version"] == 2
        assert migrated["routes"][0]["id"] == "primary"
        migrated["routes"].append({
            "id": "loopback-two", "label": "Second loopback", "provider": "custom",
            "kind": "direct_tls", "bind": f"127.0.0.1:{second}",
            "url": f"https://localhost:{second}", "cert": str(cert), "key": str(key),
            "enabled": True,
        })
        configured = manager.validate(migrated)
        listener_file = manager.write_listener_file(configured)
        assert listener_file.stat().st_mode & 0o077 == 0
        listeners = json.loads(listener_file.read_text())
        assert [entry["id"] for entry in listeners["listeners"]] == ["primary", "loopback-two"]

        server = subprocess.Popen(
            [str(BINARY), "serve-routes", str(listener_file), str(probe.path),
             str(state / "gateway")], stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE, text=True)
        try:
            for _ in range(100):
                if (state / "gateway/admin.sock").exists():
                    try:
                        first_identity = request_identity(cert, first)
                        break
                    except subprocess.CalledProcessError:
                        pass
                if server.poll() is not None:
                    raise RuntimeError(f"gateway exited early: {server.stderr.read()}")
                time.sleep(0.05)
            else:
                raise RuntimeError("multi-route gateway did not become ready")
            second_identity = request_identity(cert, second)
            assert first_identity == second_identity
            duplicate = subprocess.run(
                [str(BINARY), "serve-routes", str(listener_file), str(probe.path),
                 str(state / "gateway")], capture_output=True, text=True, timeout=5)
            assert duplicate.returncode != 0
            assert "already owns this state directory" in duplicate.stderr
            admin = subprocess.check_output(
                [str(BINARY), "admin", str(state / "gateway"), "devices"],
                text=True, timeout=5)
            assert json.loads(admin)["gateway_id"] == first_identity
            stopped = subprocess.check_output(
                [str(BINARY), "admin", str(state / "gateway"), "shutdown"],
                text=True, timeout=5)
            assert json.loads(stopped)["stopping"] is True
            assert server.wait(timeout=5) == 0
        finally:
            if server.poll() is None:
                server.terminate()
                server.communicate(timeout=3)
            probe.close()

        proxy = dict(configured["routes"][0])
        proxy.update(id="cloudflare", label="Cloudflare", provider="cloudflare",
                     kind="proxy_tls", bind=f"127.0.0.1:{free_port()}",
                     url="https://zedlink.example.test", origin_tls_name="localhost")
        proxy = manager.validate_route(proxy)
        template = manager.write_frontend_template(proxy, state)
        assert template and "originServerName: localhost" in template.read_text()
        assert "noTLSVerify" not in template.read_text()

        invalid = dict(proxy, bind=f"192.168.1.5:{free_port()}")
        try:
            manager.validate_route(invalid)
        except ValueError as error:
            assert "loopback" in str(error)
        else:
            raise AssertionError("public frontend origin accepted a non-loopback bind")

    print("PASS: migration, two listeners, duplicate guard, graceful stop, and safe frontend templates")


if __name__ == "__main__":
    main()
