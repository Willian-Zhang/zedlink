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

        untrusted, detail = manager.certificate_health(
            health_cert, health_key, "workstation.example.ts.net", require_trust=True)
        assert not untrusted and "not trusted" in detail
        # An explicitly installed test CA verifies; trust is not silently bypassed.
        with patch.dict(manager.os.environ, {"SSL_CERT_FILE": str(health_cert)}):
            trusted, detail = manager.certificate_health(
                health_cert, health_key, "workstation.example.ts.net", require_trust=True)
            assert trusted, detail

        # Read-only readiness never mistakes a DNSName for an enabled MagicDNS flag.
        with patch.object(manager, "tailscale_preflight", return_value=(fixture_address, "workstation.example.ts.net")), \
             patch.object(manager, "tailscale_dns_preferences", return_value=(False, False)), \
             patch.object(manager.socket, "getaddrinfo", return_value=[(2, 1, 6, "", (fixture_address, 0))]):
            checks = manager.tailscale_connection_checks(None)
            assert checks["host_ready"] is False and checks["phone_verified"] is False
            assert next(row for row in checks["checks"] if row["check"] == "magicdns")["status"] == "fail"

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

        # Cancellation cannot issue certificates, change routes, reload or restart.
        with patch.object(manager, "tailscale_connection_checks", return_value={"checks": [], "host_ready": False}), \
             patch.object(manager, "tailscale_preflight", return_value=(fixture_address, "workstation.example.ts.net")), \
             patch.object(manager, "tailscale_dns_preferences", return_value=(True, True)), \
             patch.object(manager, "config_path", return_value=config), \
             patch("builtins.input", return_value="cancel"), \
             patch.object(manager, "ensure_tailscale_certificate") as issue_cert, \
             patch.object(manager, "save_config") as save, \
             patch.object(manager, "restart_gateway_detached") as restart:
            manager.repair_tailscale_connection(data)
            issue_cert.assert_not_called(); save.assert_not_called(); restart.assert_not_called()

        def install_fixture_certificate(destination_cert: Path, destination_key: Path, hostname: str) -> None:
            destination_cert.parent.mkdir(parents=True)
            destination_cert.write_bytes(health_cert.read_bytes())
            destination_key.write_bytes(health_key.read_bytes())
            destination_key.chmod(0o600)

        with patch.object(manager, "tailscale_connection_checks", return_value={"checks": [], "host_ready": False}), \
             patch.object(manager, "tailscale_preflight", return_value=(fixture_address, "workstation.example.ts.net")), \
             patch.object(manager, "tailscale_dns_preferences", return_value=(True, False)), \
             patch.object(manager, "config_path", return_value=config), \
             patch("builtins.input", side_effect=["n", "cancel"]), \
             patch.object(manager.subprocess, "run") as command:
            manager.repair_tailscale_connection(data)
            command.assert_not_called()

        with patch.object(manager, "tailscale_connection_checks", return_value={"checks": [], "host_ready": False}), \
             patch.object(manager, "tailscale_preflight", return_value=(fixture_address, "other.example.ts.net")), \
             patch.object(manager, "tailscale_dns_preferences", return_value=(True, True)), \
             patch.object(manager, "ensure_tailscale_certificate") as issue_cert, \
             patch.object(manager, "save_config") as save:
            try:
                manager.repair_tailscale_connection(data)
                raise AssertionError("repair selected a different host")
            except ValueError as error:
                assert "this computer's Tailscale hostname" in str(error)
            issue_cert.assert_not_called(); save.assert_not_called()

        # Only the selected matching route changes; approval/state/model identities are preserved.
        with patch.object(manager, "tailscale_connection_checks", return_value={"checks": [], "host_ready": True}), \
             patch.object(manager, "tailscale_preflight", return_value=(fixture_address, "workstation.example.ts.net")), \
             patch.object(manager, "tailscale_dns_preferences", return_value=(True, True)), \
             patch.object(manager, "config_path", return_value=config), \
             patch("builtins.input", side_effect=["REPAIR", "n"]), \
             patch.object(manager, "ensure_tailscale_certificate", side_effect=install_fixture_certificate) as issue_cert, \
             patch.object(manager, "save_config") as save, \
             patch.object(manager, "sync_zed_settings") as sync, \
             patch.object(manager, "restart_gateway_detached") as restart:
            manager.repair_tailscale_connection(data)
            repaired = save.call_args.args[0]
            assert repaired["state_dir"] == data["state_dir"]
            assert repaired["project_root"] == data["project_root"]
            assert repaired["routes"][0]["id"] == data["routes"][0]["id"]
            assert data["routes"][0]["cert"] == str(cert)
            issue_cert.assert_called_once(); sync.assert_called_once(); restart.assert_called_once()

        unit_directory = root / "systemd-user"
        with patch.object(manager, "IS_MACOS", False), \
             patch.object(manager, "systemd_user_directory", return_value=unit_directory), \
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

        agent_path = root / "LaunchAgents" / f"{manager.LAUNCH_AGENT_LABEL}.plist"
        with patch.object(manager, "IS_MACOS", True), \
             patch.object(manager, "launch_agent_path", return_value=agent_path), \
             patch.object(manager, "certificate_health", return_value=(
                 True, "valid for workstation.example.ts.net until 2099-01-01")), \
             patch.object(manager.subprocess, "run", return_value=SimpleNamespace(returncode=0)) as launchctl:
            manager.install_certificate_renewal(data)
            assert manager.renewal_schedule_state() == (True, True)
            manager.remove_certificate_renewal()
        assert not agent_path.exists()
        commands = [call.args[0] for call in launchctl.call_args_list]
        assert commands[0][:2] == ["launchctl", "bootout"]
        assert commands[1][:2] == ["launchctl", "bootstrap"]
        assert commands[1][3] == str(agent_path)
        assert commands[2][:2] == ["launchctl", "print"]
        assert commands[3][:2] == ["launchctl", "bootout"]

    print("PASS: Tailscale preflight, staged TLS install, live reload, and automatic renewal units")


if __name__ == "__main__":
    main()
