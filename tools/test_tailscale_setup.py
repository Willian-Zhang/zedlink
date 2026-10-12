#!/usr/bin/env python3
"""Deterministic first-run Tailscale and certificate setup checks."""

import json
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import zedlink_manager as manager


def main() -> None:
    fixture_address = ".".join(str(part) for part in (100, 100, 100, 10))
    status = {
        "BackendState": "Running",
        "Self": {
            "DNSName": "workstation.example.ts.net.",
            "TailscaleIPs": [fixture_address, "fd7a:115c:a1e0::10"],
        },
    }
    response = SimpleNamespace(stdout=json.dumps(status), stderr="")
    with patch.object(manager.shutil, "which", return_value="/usr/bin/tailscale"), \
         patch.object(manager.subprocess, "run", return_value=response):
        assert manager.tailscale_preflight() == (
            fixture_address, "workstation.example.ts.net")

    login = SimpleNamespace(stdout=json.dumps({"BackendState": "NeedsLogin"}), stderr="")
    with patch.object(manager.shutil, "which", return_value="/usr/bin/tailscale"), \
         patch.object(manager.subprocess, "run", return_value=login):
        try:
            manager.tailscale_preflight()
        except ValueError as error:
            assert "sudo tailscale up" in str(error)
        else:
            raise AssertionError("logged-out Tailscale client was accepted")

    assert manager.TAILSCALE_DNS_ADMIN_URL in manager.explain_tailscale_certificate_error(
        "HTTPS certificates are not enabled")
    assert "--operator=$USER" in manager.explain_tailscale_certificate_error(
        "permission denied")
    assert "do not repeatedly retry" in manager.explain_tailscale_certificate_error(
        "rate limit exceeded")

    with tempfile.TemporaryDirectory(prefix="zedlink-tailscale.") as temporary:
        root = Path(temporary)
        health_cert = root / "health.crt"
        health_key = root / "health.key"
        subprocess.run(
            ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
             "-keyout", str(health_key), "-out", str(health_cert), "-days", "2",
             "-subj", "/CN=workstation.example.ts.net",
             "-addext", "subjectAltName=DNS:workstation.example.ts.net"],
            check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        os_mode = health_key.stat().st_mode & 0o777
        health_key.chmod(os_mode & ~0o077)
        healthy, detail = manager.certificate_health(
            health_cert, health_key, "workstation.example.ts.net")
        assert healthy and "valid for workstation.example.ts.net" in detail
        wrong_host, detail = manager.certificate_health(
            health_cert, health_key, "wrong.example.ts.net")
        assert not wrong_host and "validation failed" in detail

        config = root / "config" / "config.json"
        cert = root / "tls" / "workstation.example.ts.net.crt"
        key = root / "tls" / "workstation.example.ts.net.key"

        def issue(command: list[str], **_: object) -> SimpleNamespace:
            assert command[:4] == ["tailscale", "cert", "--min-validity", "720h"]
            Path(command[command.index("--cert-file") + 1]).write_text("certificate")
            Path(command[command.index("--key-file") + 1]).write_text("private key")
            return SimpleNamespace(stdout="", stderr="")

        with patch.object(manager, "config_path", return_value=config), \
             patch.object(manager, "certificate_health", side_effect=[
                 (False, "certificate or private key is missing"),
                 (True, "valid for workstation.example.ts.net until 2099-01-01"),
             ]), patch("builtins.input", return_value=""), \
             patch.object(manager.subprocess, "run", side_effect=issue):
            manager.ensure_tailscale_certificate(
                cert, key, "workstation.example.ts.net", renew=True)
        assert cert.read_text() == "certificate"
        assert key.read_text() == "private key"
        assert cert.stat().st_mode & 0o077 == 0
        assert key.stat().st_mode & 0o077 == 0

        data = {
            "version": 2,
            "project_root": str(root),
            "state_dir": str(root / "state"),
            "primary_route_id": "tailscale",
            "routes": [{
                "id": "tailscale", "label": "Tailscale", "provider": "tailscale",
                "kind": "direct_tls", "enabled": True,
                "bind": f"{fixture_address}:44679",
                "url": "https://workstation.example.ts.net:44679",
                "cert": str(cert), "key": str(key),
            }],
            "zed_user_data_dir": "",
        }
        with patch.object(manager, "tailscale_preflight", return_value=(
                fixture_address, "workstation.example.ts.net")), \
             patch.object(manager, "certificate_health", return_value=(
                 True, "valid for workstation.example.ts.net until 2099-01-01")), \
             patch.object(manager, "certificate_needs_renewal", return_value=True), \
             patch.object(manager, "ensure_tailscale_certificate") as renew, \
             patch.object(manager, "admin", return_value={
                 "reloaded": True, "listeners": ["tailscale"]}) as reload_tls:
            assert manager.renew_tailscale_certificates(data) == 1
        renew.assert_called_once_with(
            cert, key, "workstation.example.ts.net", renew=True, confirm=False)
        reload_tls.assert_called_once_with(root / "state", "reload-tls")

        unit_directory = root / "systemd-user"
        with patch.object(manager, "systemd_user_directory", return_value=unit_directory), \
             patch.object(manager, "certificate_health", return_value=(
                 True, "valid for workstation.example.ts.net until 2099-01-01")), \
             patch.object(manager.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as systemctl:
            manager.install_certificate_renewal(data)
        service = (unit_directory / manager.RENEWAL_SERVICE).read_text()
        timer = (unit_directory / manager.RENEWAL_TIMER).read_text()
        assert "renew-certificates" in service
        assert "OnUnitActiveSec=12h" in timer
        assert "RandomizedDelaySec=1h" in timer
        assert systemctl.call_count == 2

    print("PASS: Tailscale preflight, staged TLS install, live reload, and automatic renewal units")


if __name__ == "__main__":
    main()
