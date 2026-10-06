#!/usr/bin/env python3
"""Verify the generated Linux application launcher without touching the user profile."""

from pathlib import Path
import subprocess
import tempfile

import zedlink_manager as manager


def main() -> None:
    with tempfile.TemporaryDirectory(prefix="zedlink-launcher.") as temporary:
        root = Path(temporary)
        cert = root / "test.crt"
        key = root / "test.key"
        cert.write_text("test certificate", encoding="utf-8")
        key.write_text("test key", encoding="utf-8")
        key.chmod(0o600)
        path = root / manager.DESKTOP_ENTRY_NAME
        installed = manager.install_desktop_launcher(path)
        assert installed == path
        assert path.stat().st_mode & 0o777 == 0o644
        contents = path.read_text(encoding="utf-8")
        assert "Name=ZedLink — Patched Zed" in contents
        assert "tools/launch_patched_zed.py" in contents
        assert f"TryExec={manager.ZED}" in contents
        assert "StartupWMClass=dev.zed.Zed-Dev" in contents
        assert "StartupNotify=false" in contents
        assert manager.DESKTOP_ENTRY_MARKER in contents
        validator = subprocess.run(
            ["desktop-file-validate", str(path)], capture_output=True, text=True)
        assert validator.returncode == 0, validator.stderr

        assert manager.install_desktop_launcher(path) == path
        assert manager.remove_desktop_launcher(path)
        assert not path.exists()
        assert not manager.remove_desktop_launcher(path)

        path.write_text("[Desktop Entry]\nName=Unrelated\n", encoding="utf-8")
        try:
            manager.install_desktop_launcher(path)
        except ValueError as error:
            assert "not managed by ZedLink" in str(error)
        else:
            raise AssertionError("unmanaged desktop entry was overwritten")

        path.unlink()
        path.symlink_to(Path(temporary) / "missing")
        try:
            manager.install_desktop_launcher(path)
        except ValueError as error:
            assert "symbolic link" in str(error)
        else:
            raise AssertionError("symbolic-link desktop entry was overwritten")

        cli = root / "bin" / "zed"
        data = {
            "version": 2,
            "project_root": str(root),
            "state_dir": str(root / "state"),
            "primary_route_id": "test",
            "routes": [{
                "id": "test", "label": "Test", "provider": "custom",
                "kind": "direct_tls", "bind": "127.0.0.1:44679",
                "url": "https://localhost:44679", "cert": str(cert),
                "key": str(key), "enabled": True,
            }],
            "zed_user_data_dir": "",
        }
        installed_cli = manager.install_cli_launcher(data, cli)
        cli_contents = installed_cli.read_text()
        assert manager.CLI_LAUNCHER_MARKER in cli_contents
        assert str(manager.ZED) in cli_contents
        assert str(root) in cli_contents
        assert installed_cli.stat().st_mode & 0o111
        assert manager.remove_cli_launcher(cli)

        cli.write_text("#!/bin/sh\n")
        try:
            manager.install_cli_launcher(data, cli)
        except ValueError as error:
            assert "not managed" in str(error)
        else:
            raise AssertionError("unmanaged zed command was overwritten")

    print("PASS: launcher validation, idempotent install/remove, and overwrite protection")


if __name__ == "__main__":
    main()
