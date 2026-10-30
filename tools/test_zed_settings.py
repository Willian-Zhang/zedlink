#!/usr/bin/env python3
"""Verify native ZedLink settings synchronization without touching a real profile."""

import json
import os
import sys
from pathlib import Path
import tempfile
from types import SimpleNamespace
from unittest.mock import patch

import zedlink_manager as manager


def configuration(root: Path) -> dict:
    project = root / "project"
    state = root / "state"
    profile = root / "zed-profile"
    project.mkdir()
    state.mkdir(mode=0o700)
    profile.mkdir()
    cert = root / "cert.pem"
    key = root / "key.pem"
    cert.write_text("fixture", encoding="utf-8")
    key.write_text("fixture", encoding="utf-8")
    os.chmod(key, 0o600)
    return {
        "version": 2,
        "project_root": str(project),
        "state_dir": str(state),
        "primary_route_id": "fixture",
        "routes": [{
            "id": "fixture",
            "label": "Fixture",
            "provider": "custom",
            "kind": "direct_tls",
            "bind": "127.0.0.1:44679",
            "url": "https://localhost:44679",
            "cert": str(cert),
            "key": str(key),
            "enabled": True,
        }],
        "zed_user_data_dir": str(profile),
    }


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="zedlink-settings.") as temporary:
        root = Path(temporary)
        data = configuration(root)
        settings_path = manager.zed_settings_path(data)
        settings_path.parent.mkdir(parents=True)
        settings_path.write_text('{"theme": "One Dark"}\n', encoding="utf-8")

        assert manager.sync_zed_settings(data)
        saved = json.loads(settings_path.read_text(encoding="utf-8"))
        assert saved["theme"] == "One Dark"
        assert saved["zedlink"] == {
            "enabled": True,
            "state_directory": data["state_dir"],
            "project_root": data["project_root"],
            "start_gateway_on_launch": True,
            "manager_path": str(Path(manager.__file__).resolve()),
            "allow_remote_attach": False,
            "allow_session_creation": True,
            "allow_attachments": True,
            "allow_project_context": True,
            "allow_git_changes": True,
            "allow_approval_decisions": True,
            "allow_agent_settings": True,
            "allow_terminal_read": False,
            "allow_terminal_input": False,
            "allow_task_control": False,
            "allow_task_start": False,
            "allow_debugger_read": False,
            "allow_debugger_start": False,
            "allow_debugger_control": False,
            "connection_id": "fixture",
            "connection_label": "Fixture",
            "connection_provider": "custom",
            "connection_enabled": True,
            "connection_bind": "127.0.0.1:44679",
            "connection_url": "https://localhost:44679",
            "connection_tls_certificate": str(root / "cert.pem"),
            "connection_tls_private_key": str(root / "key.pem"),
            "connection_origin_tls_name": "",
        }
        assert settings_path.stat().st_mode & 0o077 == 0
        before = settings_path.read_bytes()
        assert manager.sync_zed_settings(data)
        assert settings_path.read_bytes() == before
        assert manager.has_native_zedlink_settings(data)

        saved["zedlink"]["enabled"] = False
        saved["zedlink"]["allow_git_changes"] = False
        saved["zedlink"]["allow_task_start"] = True
        saved["zedlink"]["allow_debugger_read"] = True
        saved["zedlink"]["allow_debugger_start"] = True
        saved["zedlink"]["allow_debugger_control"] = True
        saved["zedlink"]["allow_remote_attach"] = True
        settings_path.write_text(json.dumps(saved), encoding="utf-8")
        assert manager.has_native_zedlink_settings(data)
        assert json.loads(settings_path.read_text())["zedlink"]["enabled"] is False
        assert manager.sync_zed_settings(data)
        repaired = json.loads(settings_path.read_text(encoding="utf-8"))["zedlink"]
        assert repaired["enabled"] is True
        assert repaired["allow_git_changes"] is False
        assert repaired["allow_task_start"] is True
        assert repaired["allow_debugger_read"] is True
        assert repaired["allow_debugger_start"] is True
        assert repaired["allow_debugger_control"] is True
        assert repaired["allow_remote_attach"] is True

        connection_settings = {"zedlink": dict(repaired)}
        connection_settings["zedlink"].update({
            "connection_id": "loopback-two",
            "connection_label": "Loopback two",
            "connection_provider": "ssh-local",
            "connection_bind": "127.0.0.1:44680",
            "connection_url": "https://localhost:44680",
        })
        updated = manager.update_connection_from_settings(data, connection_settings)
        assert updated["primary_route_id"] == "loopback-two"
        assert len(updated["routes"]) == 2
        assert updated["routes"][1]["provider"] == "ssh-local"
        connection_settings["zedlink"]["connection_id"] = "fixture"
        selected = manager.select_connection_from_settings(updated, connection_settings)
        assert selected["primary_route_id"] == "fixture"
        connection_settings["zedlink"].update({
            "connection_provider": "ssh-local",
            "connection_bind": "",
        })
        prepared = manager.prepare_connection_settings(data, connection_settings)
        assert prepared["zedlink"]["connection_bind"] == "127.0.0.1:44680"
        assert prepared["zedlink"]["connection_tls_private_key"] == str(root / "key.pem")
        connection_settings["zedlink"]["connection_origin_tls_name"] = "stale.example.test"
        assert "origin_tls_name" not in manager.connection_route_from_settings(connection_settings)
        connection_settings["zedlink"]["connection_bind"] = "8.8.8.8:44680"
        try:
            manager.update_connection_from_settings(data, connection_settings)
        except ValueError as error:
            assert "private or loopback" in str(error)
        else:
            raise AssertionError("public listener was accepted")

        checked_settings = {"zedlink": {"connection_id": "fixture"}}
        response = SimpleNamespace(stdout=json.dumps({"gateway_id": "gateway-fixture"}))
        with patch.object(manager, "admin", return_value={"gateway_id": "gateway-fixture"}), \
             patch.object(manager.subprocess, "run", return_value=response) as request:
            result = manager.check_selected_connection(data, checked_settings)
        assert "trusted TLS, HTTPS, and gateway identity" in result
        assert request.call_args.args[0][-1] == "https://localhost:44679/v1/gateway"

        mismatch = SimpleNamespace(stdout=json.dumps({"gateway_id": "other-gateway"}))
        with patch.object(manager, "admin", return_value={"gateway_id": "gateway-fixture"}), \
             patch.object(manager.subprocess, "run", return_value=mismatch):
            try:
                manager.check_selected_connection(data, checked_settings)
            except ValueError as error:
                assert "different ZedLink gateway" in str(error)
            else:
                raise AssertionError("gateway identity mismatch was accepted")

        device_id = "00000000-0000-0000-0000-000000000001"
        device_response = {
            "gateway_id": "gateway-fixture",
            "devices": [{"id": device_id, "name": "Safari on iPhone"}],
        }
        with patch.object(manager, "admin", return_value=device_response) as request:
            assert manager.paired_devices(Path(data["state_dir"])) == device_response
        request.assert_called_once_with(Path(data["state_dir"]), "devices")

        validated = manager.validate(data)
        probe_response = SimpleNamespace(returncode=0)
        with patch.object(manager, "admin", return_value=device_response), \
             patch.object(manager.subprocess, "run", return_value=probe_response):
            status = manager.gateway_status(validated)
        assert status["configured"] is True
        assert status["project_root"] == data["project_root"]
        assert status["targets"][0]["online"] is True
        assert status["routes"][0]["primary"] is True
        assert status["gateway"]["online"] is True
        assert status["gateway"]["paired_devices"] == 1
        json.dumps(status)

        with patch.object(manager, "admin", return_value={"revoked": True}) as request:
            manager.revoke_device(Path(data["state_dir"]), device_id)
        request.assert_called_once_with(Path(data["state_dir"]), "revoke", device_id)
        with patch.object(manager, "admin") as request:
            try:
                manager.revoke_device(Path(data["state_dir"]), "not-a-device-id")
            except ValueError:
                pass
            else:
                raise AssertionError("invalid device ID was accepted")
        request.assert_not_called()

        with patch.object(manager.subprocess, "Popen") as launch:
            manager.launch_gateway_detached("start-gateway")
            manager.launch_gateway_detached("restart-gateway")
        assert launch.call_count == 2
        assert launch.call_args_list[0].args[0][-1] == "start-gateway"
        assert launch.call_args_list[1].args[0][-1] == "restart-gateway"

        # Settings actions choose the primary route without prompting for a route.
        for action, mode in [("pair-primary", "browser"), ("pair-primary-terminal", "terminal"),
                             ("pair", None), ("pair-browser", "browser")]:
            with patch.object(sys, "argv", ["zedlink_manager.py", action]), \
                 patch.object(manager, "config_path", return_value=root / "configured.json"), \
                 patch.object(manager, "read_config", return_value=data), \
                 patch.object(manager, "choose_route", side_effect=AssertionError("Pairing window must not prompt in a hidden terminal")), \
                 patch.object(manager.subprocess, "run") as launch:
                (root / "configured.json").write_text("{}")
                manager.main()
                if mode:
                    assert launch.call_args.args[0][-2:] == ["--mode", mode]
                else:
                    assert "--mode" not in launch.call_args.args[0]
                assert launch.call_args.args[0][2] == data["routes"][0]["url"]

        settings_source = (manager.ROOT / "zed-source/crates/settings_ui/src/page_data.rs").read_text()
        for control in ("Gateway Control", "Native Zed bridge", "Active connection",
                        "Run Diagnostics", "Paired Devices", "Pair New Device",
                        "Show Terminal QR", "Open Browser QR",
                        "View or Revoke Paired Devices", "Tailscale HTTPS",
                        "Enable Automatic Renewal", "Check for Renewal Now"):
            assert control in settings_source

        settings_path.write_text("{\n  // keep this comment\n}\n", encoding="utf-8")
        assert not manager.sync_zed_settings(data)
        assert not manager.has_native_zedlink_settings(data)
        assert "keep this comment" in settings_path.read_text(encoding="utf-8")

    print("PASS: native Zed settings sync, runtime controls, device management, and JSONC preservation")


if __name__ == "__main__":
    main()
