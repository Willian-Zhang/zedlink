#!/usr/bin/env python3
"""Local, terminal-backed setup actions for Zed's task picker."""

# Patched Zed runs plain `python3`, which on macOS can be the system Python 3.9;
# this keeps the `X | None` annotations from being evaluated there.
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
import os
from pathlib import Path
import plistlib
import re
import shutil
import socket
import ssl
import hashlib
import webbrowser
import subprocess
import sys
import tempfile
import time
import uuid
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
GATEWAY = ROOT / "gateway/target/debug/zedlink-gateway"
# On macOS, ~/Applications/ZedLink.app is created by tools/install_macos_app.py.
MACOS_APP = Path.home() / "Applications/ZedLink.app"
# Prefer the installed app, then the optimized build (macOS builds it as Nightly),
# then the debug build.
ZED = next((path for path in (MACOS_APP / "Contents/MacOS/zed",
                              ROOT / "zed-source/target/release/zed",
                              ROOT / "zed-source/target/debug/zed") if path.is_file()),
           ROOT / "zed-source/target/debug/zed")
PROVIDERS = {
    "tailscale": "Tailscale",
    "netbird": "NetBird",
    "wireguard": "WireGuard",
    "zerotier": "ZeroTier",
    "twingate": "Twingate",
    "headscale": "Headscale",
    "cloudflare": "Cloudflare Tunnel + Access",
    "ssh-reverse": "SSH reverse tunnel + VPS/Caddy",
    "ssh-local": "Direct SSH forwarding",
    "lan": "Local LAN HTTPS",
    "custom": "Custom private HTTPS",
}
PROXY_PROVIDERS = {"cloudflare", "ssh-reverse"}
DESKTOP_ENTRY_NAME = "dev.zed.Zed-Dev.desktop"
DESKTOP_ENTRY_MARKER = "X-ZedLink-Managed=true"
CLI_LAUNCHER_MARKER = "# ZedLink managed patched-Zed launcher"
TAILSCALE_DNS_ADMIN_URL = "https://login.tailscale.com/admin/dns"
TAILSCALE_CERT_RENEWAL_WINDOW = "720h"
TAILSCALE_CERT_RENEWAL_SECONDS = 30 * 24 * 60 * 60
RENEWAL_SERVICE = "zedlink-certificate-renewal.service"
RENEWAL_TIMER = "zedlink-certificate-renewal.timer"
IS_MACOS = sys.platform == "darwin"
LAUNCH_AGENT_LABEL = "dev.zedlink.certificate-renewal"
# launchd starts agents with a minimal PATH; tailscale and Homebrew OpenSSL live outside it.
LAUNCH_AGENT_PATH = "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zedlink/config.json"


def zed_settings_path(data: dict) -> Path:
    custom_data = str(data.get("zed_user_data_dir", "")).strip()
    if custom_data:
        return Path(custom_data) / "config/settings.json"
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zed/settings.json"


def sync_zed_settings(data: dict) -> bool:
    """Persist native bridge configuration in Zed's own settings file.

    Existing strict JSON settings are updated atomically. JSONC files with
    comments remain untouched because rewriting them would discard user text;
    the launcher retains its environment fallback for that case.
    """
    data = validate(data)
    path = zed_settings_path(data)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symbolic link: {path}")
    try:
        settings = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    except json.JSONDecodeError:
        print(f"Zed settings contain JSON comments or syntax ZedLink will not rewrite: {path}")
        print("Configure the ZedLink page in Zed Settings; launcher compatibility mode remains available.")
        return False
    if not isinstance(settings, dict):
        raise ValueError(f"Zed settings root must be an object: {path}")
    active_route = primary_route(data)
    existing_zedlink = settings.get("zedlink")
    if not isinstance(existing_zedlink, dict):
        existing_zedlink = {}
    desired = {
        "enabled": True,
        "state_directory": data["state_dir"],
        "project_root": data["project_root"],
        "start_gateway_on_launch": existing_zedlink.get("start_gateway_on_launch", True),
        "manager_path": str(Path(__file__).resolve()),
        "allow_remote_attach": existing_zedlink.get("allow_remote_attach", False),
        "allow_session_creation": existing_zedlink.get("allow_session_creation", True),
        "allow_attachments": existing_zedlink.get("allow_attachments", True),
        "allow_project_context": existing_zedlink.get("allow_project_context", True),
        "allow_git_changes": existing_zedlink.get("allow_git_changes", True),
        "allow_approval_decisions": existing_zedlink.get("allow_approval_decisions", True),
        "allow_agent_settings": existing_zedlink.get("allow_agent_settings", True),
        "allow_terminal_read": existing_zedlink.get("allow_terminal_read", False),
        "allow_terminal_input": existing_zedlink.get("allow_terminal_input", False),
        "allow_task_control": existing_zedlink.get("allow_task_control", False),
        "allow_task_start": existing_zedlink.get("allow_task_start", False),
        "allow_debugger_read": existing_zedlink.get("allow_debugger_read", False),
        "allow_debugger_start": existing_zedlink.get("allow_debugger_start", False),
        "allow_debugger_control": existing_zedlink.get("allow_debugger_control", False),
        "connection_id": active_route["id"],
        "connection_label": active_route["label"],
        "connection_provider": active_route["provider"],
        "connection_enabled": active_route["enabled"],
        "connection_bind": active_route["bind"],
        "connection_url": active_route["url"],
        "connection_tls_certificate": active_route["cert"],
        "connection_tls_private_key": active_route["key"],
        "connection_origin_tls_name": active_route.get("origin_tls_name", ""),
    }
    if settings.get("zedlink") == desired:
        return True
    settings["zedlink"] = desired
    descriptor, temporary_name = tempfile.mkstemp(prefix="settings-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Enabled the native ZedLink bridge in Zed Settings: {path}")
    return True


def has_native_zedlink_settings(data: dict) -> bool:
    """Return true when the selected Zed profile owns bridge configuration."""
    path = zed_settings_path(data)
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        return False
    return isinstance(settings, dict) and isinstance(settings.get("zedlink"), dict)


def desktop_launcher_path() -> Path:
    base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local/share"))
    return base / "applications" / DESKTOP_ENTRY_NAME


def cli_launcher_path() -> Path:
    """Return the conventional per-user CLI location used by Zed's installer.

    On macOS, ~/.local/bin usually precedes the official /usr/local/bin/zed on
    PATH, so the patched build gets its own name instead of shadowing it.
    """
    return Path.home() / (".local/bin/zedlink-zed" if IS_MACOS else ".local/bin/zed")


def install_cli_launcher(data: dict, path: Path | None = None) -> Path:
    """Install a guarded `zed` command that always starts the patched build."""
    data = validate(data)
    destination = path or cli_launcher_path()
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError(f"refusing to replace symbolic link: {destination}")
    if destination.exists() and CLI_LAUNCHER_MARKER not in destination.read_text(
            encoding="utf-8", errors="replace"):
        raise ValueError(f"zed command already exists and is not managed by ZedLink: {destination}")
    default_args = [data["project_root"]]
    user_data_dir = str(data.get("zed_user_data_dir", "")).strip()
    if IS_MACOS and MACOS_APP.is_dir():
        # Open through LaunchServices so the app isn't tied to (or killed with) the terminal.
        # With no arguments the app restores its last session instead of opening project_root.
        contents = "\n".join((
            "#!/usr/bin/env python3",
            CLI_LAUNCHER_MARKER,
            "import os",
            "import sys",
            f"app = {str(MACOS_APP)!r}",
            f"user_data_dir = {user_data_dir!r}",
            "arguments = [os.path.abspath(argument) for argument in sys.argv[1:]]",
            "if user_data_dir:",
            "    command = ['/usr/bin/open', '-n', '-a', app, '--args', '--user-data-dir', user_data_dir, *arguments]",
            "else:",
            "    command = ['/usr/bin/open', '-a', app, *arguments]",
            "os.execv(command[0], command)",
            "",
        ))
        return write_cli_launcher(destination, contents)
    contents = "\n".join((
        "#!/usr/bin/env python3",
        CLI_LAUNCHER_MARKER,
        "import os",
        "import sys",
        f"executable = {str(ZED)!r}",
        f"default_args = {default_args!r}",
        f"user_data_dir = {user_data_dir!r}",
        "arguments = sys.argv[1:] or default_args",
        "command = [executable]",
        "if user_data_dir:",
        "    command += ['--user-data-dir', user_data_dir]",
        "command += arguments",
        "environment = os.environ.copy()",
        "environment['ZED_RELEASE_CHANNEL'] = 'dev'",
        "os.execve(executable, command, environment)",
        "",
    ))
    return write_cli_launcher(destination, contents)


def write_cli_launcher(destination: Path, contents: str) -> Path:
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(contents)
        os.chmod(temporary, 0o755)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    return destination


def remove_cli_launcher(path: Path | None = None) -> bool:
    destination = path or cli_launcher_path()
    if not destination.exists():
        return False
    if destination.is_symlink() or CLI_LAUNCHER_MARKER not in destination.read_text(
            encoding="utf-8", errors="replace"):
        raise ValueError(f"refusing to remove zed command not managed by ZedLink: {destination}")
    destination.unlink()
    return True


def desktop_exec_argument(value: str) -> str:
    if any(character in value for character in ("\n", "\r", "\0")):
        raise ValueError("desktop launcher path contains an unsupported character")
    escaped = value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`").replace("$", "\\$")
    return f'"{escaped}"'


def refresh_desktop_database(directory: Path) -> None:
    updater = shutil.which("update-desktop-database")
    if updater:
        subprocess.run([updater, str(directory)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def install_desktop_launcher(path: Path | None = None) -> Path | None:
    if IS_MACOS and path is None:
        return None
    destination = path or desktop_launcher_path()
    destination.parent.mkdir(mode=0o755, parents=True, exist_ok=True)
    if destination.is_symlink():
        raise ValueError(f"refusing to replace symbolic link: {destination}")
    if destination.exists() and DESKTOP_ENTRY_MARKER not in destination.read_text(encoding="utf-8"):
        raise ValueError(f"desktop entry already exists and is not managed by ZedLink: {destination}")
    launcher = ROOT / "tools/launch_patched_zed.py"
    icon = ROOT / "gateway/web/icons/icon-512.png"
    contents = "\n".join((
        "[Desktop Entry]",
        "Version=1.0",
        "Type=Application",
        "Name=ZedLink — Patched Zed",
        "GenericName=Code Editor with ZedLink",
        "Comment=Open the patched Zed Dev build with native remote control",
        f"Exec={desktop_exec_argument(sys.executable)} {desktop_exec_argument(str(launcher))}",
        f"TryExec={ZED}",
        f"Icon={icon}",
        "Terminal=false",
        "Categories=Development;IDE;",
        "Keywords=zed;editor;agent;remote;zedlink;",
        "StartupNotify=false",
        "StartupWMClass=dev.zed.Zed-Dev",
        DESKTOP_ENTRY_MARKER,
        "",
    ))
    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{destination.name}.", dir=destination.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(contents)
        os.chmod(temporary, 0o644)
        temporary.replace(destination)
    finally:
        if temporary.exists():
            temporary.unlink()
    refresh_desktop_database(destination.parent)
    return destination


def remove_desktop_launcher(path: Path | None = None) -> bool:
    if IS_MACOS and path is None:
        return False
    destination = path or desktop_launcher_path()
    if not destination.exists():
        return False
    if destination.is_symlink() or DESKTOP_ENTRY_MARKER not in destination.read_text(encoding="utf-8"):
        raise ValueError(f"refusing to remove desktop entry not managed by ZedLink: {destination}")
    destination.unlink()
    refresh_desktop_database(destination.parent)
    return True


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=True)
    if path.is_symlink() or not path.is_dir() or path.stat().st_mode & 0o077:
        raise ValueError(f"directory must be private (0700): {path}")


def read_config() -> dict:
    path = config_path()
    if path.is_symlink() or path.stat().st_mode & 0o077:
        raise ValueError(f"configuration must be private (0600): {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def tailscale_defaults() -> tuple[str | None, str | None]:
    """Return private address and MagicDNS name when a local Tailscale is available."""
    try:
        address = subprocess.check_output(
            ["tailscale", "ip", "-4"], text=True, timeout=3,
            stderr=subprocess.DEVNULL).strip().splitlines()[0]
        status = json.loads(subprocess.check_output(
            ["tailscale", "status", "--json"], text=True, timeout=3,
            stderr=subprocess.DEVNULL))
        hostname = str(status.get("Self", {}).get("DNSName", "")).rstrip(".")
        ipaddress.ip_address(address)
        return address, hostname or None
    except (FileNotFoundError, IndexError, ValueError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired):
        return None, None


def tailscale_preflight() -> tuple[str, str]:
    """Return a connected Tailscale address and MagicDNS name with useful errors."""
    if not shutil.which("tailscale"):
        raise ValueError(
            "Tailscale is not installed. Install it, run 'sudo tailscale up', then retry")
    try:
        result = subprocess.run(
            ["tailscale", "status", "--json"], capture_output=True, text=True,
            timeout=5, check=True)
        status = json.loads(result.stdout)
    except subprocess.TimeoutExpired as error:
        raise ValueError("Tailscale did not respond; check that tailscaled is running") from error
    except subprocess.CalledProcessError as error:
        detail = (error.stderr or error.stdout or "tailscale status failed").strip()
        raise ValueError(f"Tailscale is unavailable: {detail}") from error
    except json.JSONDecodeError as error:
        raise ValueError("Tailscale returned an unreadable status response") from error

    backend = str(status.get("BackendState", "")).strip()
    if backend != "Running":
        hint = "run 'sudo tailscale up' and sign in" if backend in ("", "NeedsLogin", "Stopped") \
            else "open Tailscale and finish connecting this computer"
        raise ValueError(f"Tailscale is {backend or 'not connected'}; {hint}")
    self_status = status.get("Self", {})
    hostname = str(self_status.get("DNSName", "")).rstrip(".")
    addresses = self_status.get("TailscaleIPs", [])
    address = next((str(value) for value in addresses if ":" not in str(value)), "")
    if not address:
        try:
            address = subprocess.check_output(
                ["tailscale", "ip", "-4"], text=True, timeout=3,
                stderr=subprocess.DEVNULL).strip().splitlines()[0]
        except (IndexError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
            raise ValueError("Tailscale is connected but has no IPv4 address") from error
    try:
        ipaddress.ip_address(address)
    except ValueError as error:
        raise ValueError("Tailscale returned an invalid private address") from error
    if not hostname:
        raise ValueError(
            f"Tailscale has no MagicDNS name. Enable MagicDNS and HTTPS at {TAILSCALE_DNS_ADMIN_URL}")
    return address, hostname


def tailscale_dns_preferences() -> tuple[bool | None, bool | None]:
    magic = accepted = None
    for command, field in ((["tailscale", "status", "--json"], "magic"),
                           (["tailscale", "debug", "prefs"], "local")):
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=5, check=True)
            values = json.loads(result.stdout)
            value = values.get("CurrentTailnet", {}).get("MagicDNSEnabled") if field == "magic" else values.get("CorpDNS")
            if isinstance(value, bool):
                if field == "magic": magic = value
                else: accepted = value
        except (OSError, subprocess.SubprocessError, ValueError, AttributeError):
            pass
    return magic, accepted


def tailscale_route(data: dict, hostname: str) -> dict | None:
    enabled = [route for route in data["routes"] if route["enabled"] and route["kind"] == "direct_tls"]
    primary = next((route for route in enabled if route["id"] == data["primary_route_id"]), None)
    matches = [route for route in enabled if urlsplit(route["url"]).hostname == hostname]
    if primary in matches: return primary
    return next(iter(matches), None)


def tailscale_connection_checks(data: dict | None) -> dict:
    rows = []
    def report(key: str, status: str, detail: str) -> None:
        rows.append({"check": key, "status": status, "detail": detail})
    try:
        address, hostname = tailscale_preflight()
    except ValueError as error:
        report("tailscale", "fail", str(error))
        return {"checks": rows, "host_ready": False, "phone_verified": False}
    report("tailscale", "pass", "Connected to Tailscale")
    magic, accepted = tailscale_dns_preferences()
    report("magicdns", "pass" if magic is True else "fail" if magic is False else "unknown",
           "Enabled" if magic is True else "Enable MagicDNS in the Tailscale DNS administration page" if magic is False else "Tailnet setting could not be inspected; open Tailscale DNS settings")
    report("local_dns", "pass" if accepted is True else "warn" if accepted is False else "unknown",
           "Accepting Tailscale DNS" if accepted is True else "Local DNS acceptance is disabled" if accepted is False else "Local DNS preference unavailable")
    try:
        resolved = {item[4][0] for item in socket.getaddrinfo(hostname, None, type=socket.SOCK_STREAM)}
        report("dns", "pass" if address in resolved else "fail",
               "Hostname resolves to this Tailscale address" if address in resolved else "Hostname does not resolve to this Tailscale address")
    except OSError:
        report("dns", "fail", "Hostname lookup failed on this workstation")
    route = tailscale_route(data, hostname) if data else None
    if route is None:
        report("route", "fail", "No enabled connection matches this computer's Tailscale hostname; configure a Tailscale connection first")
        return {"checks": rows, "host_ready": False, "phone_verified": False}
    report("route", "pass", "Configured hostname matches this Tailscale computer")
    host = urlsplit(route["url"]).hostname
    port = urlsplit(route["url"]).port or 443
    bind_host, bind_port = split_bind(route["bind"])
    report("bind", "pass" if str(bind_host) == address and bind_port == port else "fail",
           "Listener uses the current private Tailscale address and client port" if str(bind_host) == address and bind_port == port else "Listener address/port differs from this Tailscale connection")
    healthy, detail = certificate_health(Path(route["cert"]), Path(route["key"]), hostname, require_trust=True)
    report("certificate_files", "pass" if healthy else "fail", detail)
    try:
        with socket.create_connection((host, port), timeout=5): pass
        report("tcp", "pass", "Gateway port is reachable from this workstation")
    except OSError:
        report("tcp", "fail", "Gateway port is unreachable from this workstation")
    try:
        with socket.create_connection((host, port), timeout=5) as raw:
            with ssl.create_default_context().wrap_socket(raw, server_hostname=host) as secure:
                served = secure.getpeercert(binary_form=True)
        report("served_tls", "pass", "Served certificate is trusted and matches the hostname")
        configured = subprocess.check_output(["openssl", "x509", "-in", route["cert"], "-outform", "DER"], timeout=5, stderr=subprocess.DEVNULL)
        same = hashlib.sha256(served).digest() == hashlib.sha256(configured).digest()
        report("loaded_certificate", "pass" if same else "fail",
               "Gateway is serving the configured certificate" if same else "Gateway still serves a different certificate; reload TLS or activate the configured route")
    except (OSError, subprocess.SubprocessError):
        report("served_tls", "fail", "Gateway TLS could not be verified; check trust, hostname and the active certificate")
    try:
        result = subprocess.run(["curl", "--silent", "--show-error", "--fail", "--noproxy", "*",
                                 "--connect-timeout", "5", "--max-time", "8", route["url"] + "/v1/gateway"],
                                check=True, capture_output=True, text=True, timeout=10)
        discovered = json.loads(result.stdout)
        actual = discovered["gateway_id"]
        if discovered.get("version") != 1 or not isinstance(actual, str): raise ValueError("invalid identity")
        uuid.UUID(actual)
        report("https", "pass", "HTTPS discovery returned a valid ZedLink gateway response")
        try:
            expected = admin(Path(data["state_dir"]), "devices")["gateway_id"]
            report("identity", "pass" if actual == expected else "fail",
                   "Gateway identity matches local paired-device state" if actual == expected else "Gateway identity differs; no pairing or credential sent")
        except (OSError, subprocess.SubprocessError, ValueError, KeyError):
            report("identity", "unknown", "Local gateway identity could not be verified")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        report("https", "fail", "HTTPS discovery failed; no pairing request was sent")
    try:
        timer, active = renewal_schedule_state()
        report("renewal", "pass" if timer and active else "warn",
               "Automatic renewal enabled and timer active" if timer and active else "Renewal timer enabled but inactive" if timer else "Automatic renewal not enabled")
    except (OSError, subprocess.SubprocessError): report("renewal", "unknown", "Renewal timer unavailable")
    required = {"tailscale", "magicdns", "dns", "route", "bind", "certificate_files", "tcp", "served_tls", "loaded_certificate", "https", "identity"}
    passed = {row["check"] for row in rows if row["status"] == "pass"}
    return {"checks": rows, "host_ready": required <= passed and not any(row["status"] == "fail" and row["check"] in required for row in rows), "phone_verified": False}


def print_tailscale_checks(result: dict) -> None:
    for row in result["checks"]: print(f"{row['status'].upper():7} {row['check']}: {row['detail']}")
    print("Host checks passed." if result["host_ready"] else "Host connection still needs attention.")
    print("Phone check pending: open the same HTTPS /v1/gateway URL on the phone, then Test HTTPS and pair. A host check cannot verify a phone's VPN route.")


def repair_tailscale_connection(data: dict | None) -> None:
    print_tailscale_checks(tailscale_connection_checks(data))
    address, hostname = tailscale_preflight()
    magic, accepted = tailscale_dns_preferences()
    if magic is not True:
        print(f"An administrator must enable MagicDNS and HTTPS at {TAILSCALE_DNS_ADMIN_URL}.")
        if input("Open that administration page? [y/N]: ").strip().lower() == "y":
            if not webbrowser.open(TAILSCALE_DNS_ADMIN_URL): print("Could not open the browser; use the printed URL.")
        input("Press Enter after the administrator finishes, or Ctrl-C to stop: ")
        magic, accepted = tailscale_dns_preferences()
        if magic is False: raise ValueError("MagicDNS is still disabled; repair stopped")
    if accepted is not True and input("Enable local Tailscale DNS acceptance? [y/N]: ").strip().lower() == "y":
        try:
            subprocess.run(["tailscale", "set", "--accept-dns=true"], check=True, capture_output=True, text=True, timeout=10)
        except (OSError, subprocess.SubprocessError) as error:
            raise ValueError("Could not enable local DNS acceptance. Check Tailscale operator permissions; no other VPN preferences were changed") from error
    route = tailscale_route(data, hostname) if data else None
    if route is None: raise ValueError("Configure an enabled connection using this computer's Tailscale hostname before repair")
    _, port = split_bind(route["bind"])
    port = urlsplit(route["url"]).port or port
    directory = config_path().parent / "tls"
    cert, key = directory / f"{hostname}.crt", directory / f"{hostname}.key"
    updated = json.loads(json.dumps(data))
    repaired = next(item for item in updated["routes"] if item["id"] == route["id"])
    repaired.update(provider="tailscale", bind=f"{address}:{port}", url=f"https://{hostname}:{port}", cert=str(cert), key=str(key))
    print(f"Repair plan for {route['label']}: private listener {repaired['bind']}, HTTPS {repaired['url']}")
    print(f"Certificate: {cert}\nPrivate key path: {key}")
    print("A trusted certificate will be requested if needed. Its hostname is published in Certificate Transparency logs. Gateway connections may briefly disconnect; native Zed agents remain running. Saved device authorization is preserved.")
    if input("Type REPAIR to apply this plan: ").strip() != "REPAIR":
        print("Repair cancelled; certificate and route configuration unchanged."); return
    ensure_tailscale_certificate(cert, key, hostname)
    updated = validate(updated)
    save_config(updated)
    sync_zed_settings(updated)
    changed = any(repaired[field] != route[field] for field in ("bind", "url", "cert", "key"))
    try:
        if changed: raise ValueError("Listener configuration changed")
        if admin(Path(updated["state_dir"]), "reload-tls").get("reloaded") is not True: raise ValueError("Reload rejected")
        print("Running gateway reloaded the validated certificate.")
    except (OSError, subprocess.SubprocessError, ValueError, KeyError):
        restart_gateway_detached()
        print("Gateway activation requested; checking readiness below.")
    if input("Enable automatic certificate renewal? [Y/n]: ").strip().lower() != "n":
        try: install_certificate_renewal(updated)
        except (OSError, subprocess.SubprocessError, ValueError) as error:
            print(f"Renewal could not be enabled: {error}. Run install-renewal after resolving the prerequisite.")
    result = tailscale_connection_checks(updated)
    for attempt in range(4):
        if result["host_ready"]: break
        print(f"Rechecking gateway readiness ({attempt + 1}/4)...", flush=True)
        time.sleep(0.5)
        result = tailscale_connection_checks(updated)
    print_tailscale_checks(result)


def certificate_health(cert_path: Path, key_path: Path, hostname: str, *, require_trust: bool = False) -> tuple[bool, str]:
    """Validate a PEM pair without printing private key material."""
    if not cert_path.is_file() or not key_path.is_file():
        return False, "certificate or private key is missing"
    if key_path.stat().st_mode & 0o077:
        return False, "private key permissions must be 0600"
    try:
        subprocess.run(
            ["openssl", "x509", "-in", str(cert_path), "-checkhost", hostname, "-noout"],
            capture_output=True, text=True, timeout=5, check=True)
        cert_public = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_path), "-pubkey", "-noout"],
            text=True, timeout=5)
        key_public = subprocess.check_output(
            ["openssl", "pkey", "-in", str(key_path), "-pubout"],
            text=True, timeout=5, stderr=subprocess.DEVNULL)
        if cert_public.strip() != key_public.strip():
            return False, "certificate and private key do not match"
        end_date = subprocess.check_output(
            ["openssl", "x509", "-in", str(cert_path), "-enddate", "-noout"],
            text=True, timeout=5).strip().removeprefix("notAfter=")
        expires = datetime.strptime(end_date, "%b %d %H:%M:%S %Y %Z").replace(tzinfo=timezone.utc)
    except FileNotFoundError:
        return False, "OpenSSL is required to validate the TLS certificate"
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, ValueError) as error:
        return False, f"certificate validation failed: {error}"
    if require_trust:
        try:
            # The PEM can contain intermediates. Keep roots in the system trust store.
            verified = subprocess.run(
                ["openssl", "verify", "-purpose", "sslserver", "-verify_hostname", hostname,
                 "-untrusted", str(cert_path), str(cert_path)],
                capture_output=True, text=True, timeout=5)
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False, "certificate chain verification could not be completed"
        if verified.returncode != 0:
            return False, "certificate chain is not trusted by this host; replace self-signed or incomplete certificates with a trusted Tailscale certificate"
    remaining = expires - datetime.now(timezone.utc)
    if remaining.total_seconds() <= 0:
        return False, f"certificate expired {expires.date().isoformat()}"
    return True, f"valid for {hostname} until {expires.date().isoformat()} ({remaining.days} days)"


def certificate_needs_renewal(cert_path: Path) -> bool:
    try:
        result = subprocess.run(
            ["openssl", "x509", "-in", str(cert_path), "-checkend",
             str(TAILSCALE_CERT_RENEWAL_SECONDS), "-noout"],
            capture_output=True, text=True, timeout=5)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return True
    return result.returncode != 0


def split_bind(bind: str) -> tuple[ipaddress.IPv4Address | ipaddress.IPv6Address, int]:
    host, separator, port = bind.rpartition(":")
    if not separator or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("bind must be PRIVATE_IP:PORT")
    try:
        address = ipaddress.ip_address(host.strip("[]"))
    except ValueError as error:
        raise ValueError("bind host must be a numeric private or loopback IP") from error
    allowed = (address.is_loopback or
               isinstance(address, ipaddress.IPv4Address) and (
                   address in ipaddress.ip_network("10.0.0.0/8") or
                   address in ipaddress.ip_network("172.16.0.0/12") or
                   address in ipaddress.ip_network("192.168.0.0/16") or
                   address in ipaddress.ip_network("100.64.0.0/10")) or
               isinstance(address, ipaddress.IPv6Address) and
               address in ipaddress.ip_network("fc00::/7"))
    if not allowed:
        raise ValueError("gateway must bind to a private or loopback IP")
    return address, int(port)


def validate_origin(url: str) -> tuple[str, int | None]:
    parsed = urlsplit(url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.path not in ("", "/") or parsed.query or
            parsed.fragment):
        raise ValueError("URL must be a trusted HTTPS origin without a path")
    return parsed.hostname, parsed.port


def validate_route(route: dict) -> dict:
    identifier = str(route.get("id", "")).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", identifier):
        raise ValueError("route id must use lowercase letters, numbers, and dashes")
    provider = str(route.get("provider", "custom")).strip()
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported route provider: {provider}")
    label = str(route.get("label", PROVIDERS[provider])).strip()
    if not label or len(label) > 80:
        raise ValueError("route label must contain 1 to 80 characters")
    bind = str(route.get("bind", "")).strip()
    address, bind_port = split_bind(bind)
    url = str(route.get("url", "")).strip().rstrip("/")
    _, url_port = validate_origin(url)
    kind = str(route.get("kind", "proxy_tls" if provider in PROXY_PROVIDERS else "direct_tls"))
    if kind not in ("direct_tls", "proxy_tls"):
        raise ValueError("route kind must be direct_tls or proxy_tls")
    if kind == "direct_tls" and (url_port or 443) != bind_port:
        raise ValueError("direct route URL and bind port must match")
    if kind == "proxy_tls" and not address.is_loopback:
        raise ValueError("proxy frontend origins must bind only to loopback")
    if not str(route.get("cert", "")).strip() or not str(route.get("key", "")).strip():
        raise ValueError("TLS certificate and private key paths are required")
    cert = Path(route["cert"]).expanduser().resolve(strict=True)
    key = Path(route["key"]).expanduser().resolve(strict=True)
    if not cert.is_file() or not key.is_file():
        raise ValueError("certificate and key must be files")
    if key.stat().st_mode & 0o077:
        raise ValueError("TLS key must be mode 0600 or stricter")
    origin_tls_name = str(route.get("origin_tls_name", "")).strip()
    if kind == "proxy_tls" and not origin_tls_name:
        raise ValueError("proxy route requires the TLS hostname served by its local certificate")
    if origin_tls_name and (len(origin_tls_name) > 253 or "/" in origin_tls_name):
        raise ValueError("invalid origin TLS hostname")
    return {
        "id": identifier,
        "label": label,
        "provider": provider,
        "kind": kind,
        "bind": bind,
        "url": url,
        "cert": str(cert),
        "key": str(key),
        "enabled": bool(route.get("enabled", True)),
        **({"origin_tls_name": origin_tls_name} if origin_tls_name else {}),
    }


def validate_target(target: dict, state: Path, project: Path) -> dict:
    identifier = str(target.get("id", "")).strip()
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", identifier):
        raise ValueError("target id must use lowercase letters, numbers, dashes, or underscores")
    label = str(target.get("label", "")).strip()
    if not label or len(label) > 80:
        raise ValueError("target label must contain 1 to 80 characters")
    probe_value = target.get("probe") or state / "probe/zedlink.sock"
    probe = Path(probe_value).expanduser().resolve()
    if not probe.is_absolute():
        raise ValueError("target probe path must be absolute")
    return {"id": identifier, "label": label, "probe": str(probe)}


def legacy_route(data: dict) -> dict:
    return {
        "id": "primary",
        "label": "Tailscale" if "ts.net" in str(data.get("url", "")) else "Primary route",
        "provider": "tailscale" if "ts.net" in str(data.get("url", "")) else "custom",
        "kind": "direct_tls",
        "bind": data["bind"],
        "url": data["url"],
        "cert": data["cert"],
        "key": data["key"],
        "enabled": True,
    }


def validate(data: dict) -> dict:
    project = Path(data["project_root"]).expanduser().resolve(strict=True)
    if not project.is_dir():
        raise ValueError("project root must be an existing directory")
    state = Path(data["state_dir"]).expanduser().resolve()
    if not state.is_absolute():
        raise ValueError("state directory must be absolute")
    raw_routes = data.get("routes")
    if raw_routes is None:
        raw_routes = [legacy_route(data)]
    if not isinstance(raw_routes, list) or not 1 <= len(raw_routes) <= 16:
        raise ValueError("configure between 1 and 16 routes")
    routes = [validate_route(route) for route in raw_routes]
    ids = [route["id"] for route in routes]
    binds = [route["bind"] for route in routes if route["enabled"]]
    if len(ids) != len(set(ids)):
        raise ValueError("route ids must be unique")
    if len(binds) != len(set(binds)):
        raise ValueError("enabled route bind addresses must be unique")
    if not any(route["enabled"] for route in routes):
        raise ValueError("at least one route must be enabled")
    primary_id = str(data.get("primary_route_id", routes[0]["id"]))
    if primary_id not in ids:
        raise ValueError("primary route does not exist")
    if not next(route for route in routes if route["id"] == primary_id)["enabled"]:
        raise ValueError("primary route must be enabled")
    profile = data.get("zed_user_data_dir", "")
    if profile:
        profile = str(Path(profile).expanduser().resolve(strict=True))
        if not Path(profile).is_dir():
            raise ValueError("Zed user data directory must exist")
    raw_targets = data.get("targets") or [{
        "id": "default", "label": project.name or "This Zed",
        "probe": str(state / "probe/zedlink.sock"),
    }]
    if not isinstance(raw_targets, list) or not 1 <= len(raw_targets) <= 16:
        raise ValueError("configure between 1 and 16 Zed targets")
    targets = [validate_target(target, state, project) for target in raw_targets]
    target_ids = [target["id"] for target in targets]
    if len(target_ids) != len(set(target_ids)):
        raise ValueError("Zed target ids must be unique")
    return dict(version=2, project_root=str(project), state_dir=str(state),
                primary_route_id=primary_id, routes=routes, targets=targets,
                zed_user_data_dir=profile)


def primary_route(data: dict) -> dict:
    return next(route for route in data["routes"] if route["id"] == data["primary_route_id"])


def connection_route_from_settings(settings: dict) -> dict:
    zedlink = settings.get("zedlink")
    if not isinstance(zedlink, dict):
        raise ValueError("ZedLink settings are unavailable; run 'ZedLink: Repair setup'")
    provider = str(zedlink.get("connection_provider", "")).strip()
    route = {
        "id": str(zedlink.get("connection_id", "")).strip(),
        "label": str(zedlink.get("connection_label", "")).strip(),
        "provider": provider,
        "kind": "proxy_tls" if provider in PROXY_PROVIDERS else "direct_tls",
        "bind": str(zedlink.get("connection_bind", "")).strip(),
        "url": str(zedlink.get("connection_url", "")).strip(),
        "cert": str(zedlink.get("connection_tls_certificate", "")).strip(),
        "key": str(zedlink.get("connection_tls_private_key", "")).strip(),
        "enabled": bool(zedlink.get("connection_enabled", True)),
    }
    origin_tls_name = str(zedlink.get("connection_origin_tls_name", "")).strip()
    if origin_tls_name and provider in PROXY_PROVIDERS:
        route["origin_tls_name"] = origin_tls_name
    return route


def read_zed_settings(data: dict) -> dict:
    path = zed_settings_path(data)
    try:
        settings = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise ValueError("Zed settings use JSON comments; save this connection through settings.json") from error
    if not isinstance(settings, dict):
        raise ValueError("Zed settings root must be an object")
    return settings


def write_zed_settings(data: dict, settings: dict) -> None:
    path = zed_settings_path(data)
    if path.is_symlink():
        raise ValueError(f"refusing to replace symbolic link: {path}")
    descriptor, temporary_name = tempfile.mkstemp(prefix="settings-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(settings, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def prepare_connection_settings(data: dict, settings: dict) -> dict:
    zedlink = settings.get("zedlink")
    if not isinstance(zedlink, dict):
        raise ValueError("ZedLink settings are unavailable; run 'ZedLink: Repair setup'")
    provider = str(zedlink.get("connection_provider", "")).strip()
    if provider not in PROVIDERS:
        raise ValueError(f"unsupported connection provider: {provider}")
    current = primary_route(data)
    try:
        _, port = split_bind(str(zedlink.get("connection_bind", "")))
    except ValueError:
        port = next_route_port(data)
    address = None
    hostname = None
    if provider in ("tailscale", "headscale"):
        address, hostname = tailscale_defaults()
    elif provider == "netbird":
        address, hostname = netbird_defaults()
    elif provider in PROXY_PROVIDERS or provider == "ssh-local":
        address = "127.0.0.1"
    if address is None:
        raise ValueError(
            "automatic address detection is available for Tailscale, Headscale, NetBird, "
            "Cloudflare, and SSH profiles; enter this provider's private IP and hostname manually")
    updated = json.loads(json.dumps(settings))
    draft = updated["zedlink"]
    draft["connection_label"] = PROVIDERS[provider]
    draft["connection_bind"] = f"{address}:{port}"
    if hostname:
        draft["connection_url"] = f"https://{hostname}:{port}"
    draft["connection_tls_certificate"] = current["cert"]
    draft["connection_tls_private_key"] = current["key"]
    draft["connection_origin_tls_name"] = (
        urlsplit(current["url"]).hostname or "" if provider in PROXY_PROVIDERS else "")
    return updated


def update_connection_from_settings(data: dict, settings: dict) -> dict:
    route = connection_route_from_settings(settings)
    routes = [dict(existing) for existing in data["routes"]]
    existing_index = next(
        (index for index, existing in enumerate(routes) if existing["id"] == route["id"]),
        None)
    if existing_index is None:
        if len(routes) >= 16:
            raise ValueError("a maximum of 16 connection profiles is supported")
        routes.append(route)
    else:
        routes[existing_index] = route
    updated = dict(data)
    updated["routes"] = routes
    updated["primary_route_id"] = route["id"]
    return validate(updated)


def select_connection_from_settings(data: dict, settings: dict) -> dict:
    zedlink = settings.get("zedlink")
    if not isinstance(zedlink, dict):
        raise ValueError("ZedLink settings are unavailable; run 'ZedLink: Repair setup'")
    identifier = str(zedlink.get("connection_id", "")).strip()
    route = next((route for route in data["routes"] if route["id"] == identifier), None)
    if route is None:
        raise ValueError(f"connection profile does not exist: {identifier}")
    if not route["enabled"]:
        raise ValueError("enable the connection before making it primary")
    updated = dict(data)
    updated["primary_route_id"] = identifier
    return validate(updated)


def launch_gateway_detached(action: str) -> None:
    if action not in ("start-gateway", "restart-gateway"):
        raise ValueError(f"unsupported detached gateway action: {action}")
    subprocess.Popen(
        [sys.executable, str(Path(__file__).resolve()), action],
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )


def restart_gateway_detached() -> None:
    launch_gateway_detached("restart-gateway")


def explain_tailscale_certificate_error(detail: str) -> str:
    lower = detail.lower()
    if "permission" in lower or "access denied" in lower:
        return (f"{detail}\nAllow this Linux user to request certificates with "
                "'sudo tailscale set --operator=$USER', then retry.")
    if "https" in lower or "cert domain" in lower or "not allowed" in lower:
        return (f"{detail}\nEnable MagicDNS and HTTPS at {TAILSCALE_DNS_ADMIN_URL}. "
                "A tailnet Owner, Admin, or Network admin may need to do this.")
    if "rate" in lower or "too many certificates" in lower:
        return f"{detail}\nCertificate issuance is rate limited; do not repeatedly retry."
    return detail


def ensure_tailscale_certificate(
        cert_path: Path, key_path: Path, hostname: str, *, renew: bool = False,
        confirm: bool = True) -> None:
    healthy, detail = certificate_health(cert_path, key_path, hostname, require_trust=True)
    if healthy and not renew:
        print(f"Tailscale TLS certificate: {detail}")
        return
    if cert_path.exists() or key_path.exists():
        if not cert_path.is_file() or not key_path.is_file():
            raise ValueError("only one TLS file exists; remove or repair the incomplete certificate pair")
        print(f"\nThe existing TLS certificate needs attention: {detail}")
    else:
        print("\nThe TLS certificate files do not exist yet.")
    print(f"ZedLink can request a certificate for {hostname} with Tailscale.")
    print("Certificate issuance publishes this hostname in public Certificate Transparency logs.")
    verb = "Renew" if cert_path.exists() and key_path.exists() else "Create"
    if confirm:
        create = input(f"{verb} the certificate and key now? [Y/n]: ").strip().lower()
        if create not in ("", "y", "yes"):
            raise ValueError("TLS certificate setup was cancelled; create the files and run setup again")
    else:
        print(f"{verb}ing the certificate automatically.")
    if cert_path.parent != key_path.parent:
        raise ValueError("automatic certificate creation requires certificate and key in the same directory")
    private_directory(config_path().parent)
    private_directory(cert_path.parent)
    with tempfile.TemporaryDirectory(prefix="tailscale-cert-", dir=cert_path.parent) as temporary:
        staged_cert = Path(temporary) / "certificate.pem"
        staged_key = Path(temporary) / "private-key.pem"
        try:
            subprocess.run(
                ["tailscale", "cert", "--min-validity", TAILSCALE_CERT_RENEWAL_WINDOW,
                 "--cert-file", str(staged_cert), "--key-file", str(staged_key), hostname],
                capture_output=True, text=True, timeout=60, check=True)
        except subprocess.CalledProcessError as error:
            message = (error.stderr or error.stdout or "tailscale cert failed").strip()
            raise ValueError(explain_tailscale_certificate_error(message)) from error
        except subprocess.TimeoutExpired as error:
            raise ValueError("Tailscale certificate request timed out; check tailscaled connectivity") from error
        os.chmod(staged_cert, 0o600)
        os.chmod(staged_key, 0o600)
        staged_ok, staged_detail = certificate_health(staged_cert, staged_key, hostname, require_trust=True)
        if not staged_ok:
            raise ValueError(f"Tailscale returned an unusable certificate: {staged_detail}")
        staged_cert.replace(cert_path)
        staged_key.replace(key_path)
    print(f"Saved TLS certificate: {cert_path}")
    print(f"Saved private TLS key: {key_path}")
    print(f"Certificate check: {staged_detail}")


def setup_tailscale_certificate() -> None:
    print("\nZedLink Tailscale setup")
    print("This checks the workstation connection, MagicDNS name, and browser-trusted HTTPS certificate.")
    address, hostname = tailscale_preflight()
    print(f"PASS  Tailscale connected: {address}")
    print(f"PASS  MagicDNS hostname: {hostname}")
    tls_directory = config_path().parent / "tls"
    cert_path = tls_directory / f"{hostname}.crt"
    key_path = tls_directory / f"{hostname}.key"
    healthy, detail = certificate_health(cert_path, key_path, hostname, require_trust=True)
    if healthy:
        print(f"PASS  HTTPS certificate: {detail}")
        renew = input("Renew it now anyway? [y/N]: ").strip().lower() in ("y", "yes")
        if renew:
            ensure_tailscale_certificate(cert_path, key_path, hostname, renew=True)
    else:
        ensure_tailscale_certificate(cert_path, key_path, hostname, renew=True)
    print("\nClient device check")
    print("1. Install Tailscale on the phone or computer.")
    print("2. Sign in to the same tailnet and leave Tailscale connected.")
    print(f"3. Open https://{hostname}:44679 after the ZedLink gateway starts.")
    print("4. Pair the browser or app with ZedLink; tailnet access alone is not authorization.")
    if config_path().is_file():
        enable_certificate_renewal_during_setup(validate(read_config()))
    else:
        print("Automatic renewal will be enabled when you run ZedLink project setup.")


def renew_tailscale_certificates(data: dict, *, force: bool = False) -> int:
    routes = [route for route in data["routes"]
              if route["enabled"] and route["provider"] == "tailscale"]
    if not routes:
        raise ValueError("no enabled Tailscale connection profile is configured")
    pending = []
    for route in routes:
        hostname = urlsplit(route["url"]).hostname or ""
        cert_path = Path(route["cert"])
        key_path = Path(route["key"])
        healthy, detail = certificate_health(cert_path, key_path, hostname, require_trust=True)
        if healthy and not force and not certificate_needs_renewal(cert_path):
            print(f"PASS  {route['label']}: {detail}; renewal is not needed")
        else:
            pending.append((route, hostname, cert_path, key_path, detail))
    if not pending:
        return 0
    address, detected_hostname = tailscale_preflight()
    print(f"Tailscale connected at {address} as {detected_hostname}.")
    renewed = 0
    for route, hostname, cert_path, key_path, detail in pending:
        if hostname != detected_hostname:
            raise ValueError(
                f"profile {route['id']} uses {hostname}, but this Tailscale client is "
                f"{detected_hostname}; update the profile instead of silently changing identity")
        print(f"RENEW {route['label']}: {detail}")
        ensure_tailscale_certificate(
            cert_path, key_path, hostname, renew=True, confirm=False)
        renewed += 1
    if renewed:
        state = Path(data["state_dir"])
        try:
            result = admin(state, "reload-tls")
            if result.get("reloaded") is not True:
                raise ValueError("gateway rejected the TLS reload")
            print(f"Reloaded TLS for {len(result.get('listeners', []))} running gateway listener(s).")
        except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
            print("Gateway is offline; it will load the renewed certificate on its next start.")
    return renewed


def systemd_user_directory() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd/user"


def systemd_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"') + '"'


def renewal_unit_paths() -> tuple[Path, Path]:
    directory = systemd_user_directory()
    return directory / RENEWAL_SERVICE, directory / RENEWAL_TIMER


def launch_agent_path() -> Path:
    return Path.home() / "Library/LaunchAgents" / f"{LAUNCH_AGENT_LABEL}.plist"


def launch_agent_target() -> str:
    return f"gui/{os.getuid()}/{LAUNCH_AGENT_LABEL}"


def renewal_schedule_state() -> tuple[bool, bool]:
    """Return whether automatic renewal is enabled and currently scheduled."""
    if IS_MACOS:
        enabled = launch_agent_path().is_file()
        active = subprocess.run(["launchctl", "print", launch_agent_target()],
                                capture_output=True, timeout=5).returncode == 0
        return enabled, active
    enabled = subprocess.run(["systemctl", "--user", "is-enabled", "--quiet", RENEWAL_TIMER],
                             capture_output=True, timeout=5).returncode == 0
    active = subprocess.run(["systemctl", "--user", "is-active", "--quiet", RENEWAL_TIMER],
                            capture_output=True, timeout=5).returncode == 0
    return enabled, active


def write_private_text(path: Path, content: str) -> None:
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(prefix=path.name + "-", dir=path.parent)
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            stream.write(content)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def install_certificate_renewal(data: dict) -> None:
    tailscale_routes = [route for route in data["routes"]
                        if route["enabled"] and route["provider"] == "tailscale"]
    if not tailscale_routes:
        raise ValueError("configure and enable a Tailscale connection before enabling renewal")
    for route in tailscale_routes:
        hostname = urlsplit(route["url"]).hostname or ""
        healthy, detail = certificate_health(Path(route["cert"]), Path(route["key"]), hostname, require_trust=True)
        if not healthy:
            raise ValueError(f"set up the {route['label']} certificate first: {detail}")
    if IS_MACOS:
        install_launch_agent(data)
        print_renewal_enabled()
        return
    service_path, timer_path = renewal_unit_paths()
    manager = systemd_quote(str(Path(__file__).resolve()))
    python = systemd_quote(sys.executable)
    service = f"""[Unit]
Description=Renew ZedLink Tailscale HTTPS certificates

[Service]
Type=oneshot
ExecStart={python} {manager} renew-certificates
NoNewPrivileges=true
PrivateTmp=true
"""
    timer = f"""[Unit]
Description=Check ZedLink Tailscale HTTPS certificates

[Timer]
OnBootSec=10m
OnUnitActiveSec=12h
RandomizedDelaySec=1h
Persistent=true
Unit={RENEWAL_SERVICE}

[Install]
WantedBy=timers.target
"""
    write_private_text(service_path, service)
    write_private_text(timer_path, timer)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", RENEWAL_TIMER], check=True)
    print_renewal_enabled()


def install_launch_agent(data: dict) -> None:
    state = Path(data["state_dir"])
    private_directory(state)
    log = str(state / "certificate-renewal.log")
    agent = {
        "Label": LAUNCH_AGENT_LABEL,
        "ProgramArguments": [sys.executable, str(Path(__file__).resolve()), "renew-certificates"],
        "EnvironmentVariables": {"PATH": LAUNCH_AGENT_PATH},
        "StartInterval": 12 * 60 * 60,
        "RunAtLoad": True,
        "ProcessType": "Background",
        "StandardOutPath": log,
        "StandardErrorPath": log,
    }
    path = launch_agent_path()
    write_private_text(path, plistlib.dumps(agent).decode("utf-8"))
    subprocess.run(["launchctl", "bootout", launch_agent_target()],
                   capture_output=True, text=True)
    subprocess.run(["launchctl", "bootstrap", f"gui/{os.getuid()}", str(path)], check=True)


def print_renewal_enabled() -> None:
    print("Automatic Tailscale certificate renewal is enabled.")
    print("ZedLink checks every 12 hours and renews only inside the final 30 days.")
    print("A running gateway reloads the validated certificate without losing pairings or sessions.")


def certificate_renewal_status(data: dict) -> None:
    enabled, active = renewal_schedule_state()
    print(f"Automatic renewal: {'enabled' if enabled else 'disabled'}")
    print(f"Renewal timer: {'active' if active else 'inactive'}")
    if IS_MACOS:
        print(f"Launch agent: {'installed' if launch_agent_path().is_file() else 'missing'}")
    else:
        service_path, timer_path = renewal_unit_paths()
        print(f"Service file: {'installed' if service_path.is_file() else 'missing'}")
        print(f"Timer file: {'installed' if timer_path.is_file() else 'missing'}")
    for route in data["routes"]:
        if route["enabled"] and route["provider"] == "tailscale":
            hostname = urlsplit(route["url"]).hostname or ""
            healthy, detail = certificate_health(Path(route["cert"]), Path(route["key"]), hostname, require_trust=True)
            state = "PASS" if healthy else "FAIL"
            due = "renewal due" if certificate_needs_renewal(Path(route["cert"])) else "renewal not due"
            print(f"{state}  {route['label']}: {detail}; {due}")


def remove_certificate_renewal() -> None:
    if IS_MACOS:
        subprocess.run(["launchctl", "bootout", launch_agent_target()],
                       capture_output=True, text=True)
        path = launch_agent_path()
        if path.exists():
            path.unlink()
        print("Automatic Tailscale certificate renewal is disabled.")
        return
    service_path, timer_path = renewal_unit_paths()
    subprocess.run(
        ["systemctl", "--user", "disable", "--now", RENEWAL_TIMER],
        capture_output=True, text=True)
    for path in (timer_path, service_path):
        if path.exists():
            path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    print("Automatic Tailscale certificate renewal is disabled.")


def enable_certificate_renewal_during_setup(data: dict) -> None:
    if not any(route["enabled"] and route["provider"] == "tailscale"
               for route in data["routes"]):
        return
    try:
        install_certificate_renewal(data)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        print(f"Automatic certificate renewal was not enabled: {error}")
        print("Run 'ZedLink: Enable automatic certificate renewal' after fixing that issue.")


def save_config(data: dict) -> None:
    data = validate(data)
    path = config_path()
    private_directory(path.parent)
    state = Path(data["state_dir"])
    for directory in (state, state / "probe", state / "gateway"):
        private_directory(directory)
    temporary = None
    try:
        descriptor, name = tempfile.mkstemp(prefix="config-", dir=path.parent)
        temporary = Path(name)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary and temporary.exists():
            temporary.unlink()
    print(f"Saved private configuration: {path}")
    print("No model settings or device credentials were changed.")


def configure() -> None:
    try:
        old = validate(read_config())
    except FileNotFoundError:
        old = {}

    tailscale_address, tailscale_hostname = tailscale_defaults()
    default_bind = f"{tailscale_address}:44679" if tailscale_address else "127.0.0.1:44679"
    default_url = (f"https://{tailscale_hostname}:44679" if tailscale_hostname
                   else "https://localhost:44679")
    tls_directory = config_path().parent / "tls"
    default_cert = str(tls_directory / f"{tailscale_hostname}.crt") if tailscale_hostname else ""
    default_key = str(tls_directory / f"{tailscale_hostname}.key") if tailscale_hostname else ""
    defaults = dict(project_root="",
                    state_dir=str(Path.home() / ".local/state/zedlink"),
                    bind=default_bind, url=default_url,
                    cert=default_cert, key=default_key, zed_user_data_dir="")
    prompts = dict(project_root="Project to open in patched Zed",
                   state_dir="Private state directory",
                   bind="Gateway bind address (private IP:port)",
                   url="Phone HTTPS origin matching certificate and port",
                   cert="TLS certificate PEM path", key="TLS private key PEM path",
                   zed_user_data_dir="Existing Zed user data directory (blank for default profile)")
    help_text = dict(
        project_root="Full path of the project containing the native Agent thread you want on the phone.",
        state_dir="Private local storage for the socket, gateway identity, and paired-device records.",
        bind="Use the workstation's private VPN address. Tailscale uses an address in 100.64.0.0/10.",
        url="Use the trusted certificate hostname, never a raw IP or an http:// address.",
        cert="Full path to the certificate for the HTTPS hostname above.",
        key="Full path to the matching private key; its permissions must be 0600.",
        zed_user_data_dir="Press Enter for your normal Zed profile. Close other Zed windows before starting patched Zed if they use that profile.",
    )
    print("\nZedLink connection setup")
    print("Press Enter to keep a value shown in [brackets].")
    print("This saves local paths and network settings; it does not copy model credentials.\n")
    if tailscale_address:
        print(f"Detected Tailscale address: {tailscale_address}")
    if tailscale_hostname:
        print(f"Detected Tailscale DNS name: {tailscale_hostname}")
    current_route = primary_route(old) if old else {}
    old_values = {
        "project_root": old.get("project_root", ""),
        "state_dir": old.get("state_dir", ""),
        "bind": current_route.get("bind", ""),
        "url": current_route.get("url", ""),
        "cert": current_route.get("cert", ""),
        "key": current_route.get("key", ""),
        "zed_user_data_dir": old.get("zed_user_data_dir", ""),
    }
    answers = {}
    prompt_fields = list(prompts)
    if tailscale_hostname:
        prompt_fields.remove("cert")
        prompt_fields.remove("key")
        old_route_hostname = urlsplit(current_route.get("url", "")).hostname
        answers["cert"] = (old_values.get("cert") if old_route_hostname == tailscale_hostname
                           else "") or defaults["cert"]
        answers["key"] = (old_values.get("key") if old_route_hostname == tailscale_hostname
                          else "") or defaults["key"]
        print("Certificate paths are managed automatically for the detected Tailscale hostname.")
        print(f"  Certificate: {answers['cert']}")
        print(f"  Private key: {answers['key']}")
    for field in prompt_fields:
        label = prompts[field]
        current = old_values.get(field) or defaults[field]
        print(f"\n{label}")
        print(f"  {help_text[field]}")
        while True:
            suffix = f" [{current}]" if current else ""
            answer = input(f"{label}{suffix}: ").strip() or current
            if field == "project_root" and not answer:
                print("  A project path is required. Example: /home/you/Documents/my-project")
                continue
            answers[field] = answer
            break
    route_hostname = urlsplit(answers["url"]).hostname
    if tailscale_hostname and route_hostname != tailscale_hostname:
        for field in ("cert", "key"):
            label = prompts[field]
            current = old_values.get(field, "")
            print(f"\n{label}")
            print(f"  {help_text[field]}")
            suffix = f" [{current}]" if current else ""
            answers[field] = input(f"{label}{suffix}: ").strip() or current
    cert_path = Path(answers["cert"]).expanduser()
    key_path = Path(answers["key"]).expanduser()
    if tailscale_hostname and route_hostname == tailscale_hostname:
        ensure_tailscale_certificate(cert_path, key_path, tailscale_hostname)
    route_id = current_route.get("id", "tailscale" if route_hostname == tailscale_hostname else "primary")
    updated_route = {
        "id": route_id,
        "label": current_route.get("label", "Tailscale" if route_hostname == tailscale_hostname else "Primary route"),
        "provider": current_route.get("provider", "tailscale" if route_hostname == tailscale_hostname else "custom"),
        "kind": current_route.get("kind", "direct_tls"),
        "bind": answers["bind"],
        "url": answers["url"],
        "cert": answers["cert"],
        "key": answers["key"],
        "enabled": True,
    }
    routes = [route for route in old.get("routes", []) if route["id"] != route_id]
    routes.insert(0, updated_route)
    data = {
        "version": 2,
        "project_root": answers["project_root"],
        "state_dir": answers["state_dir"],
        "primary_route_id": route_id,
        "routes": routes,
        "zed_user_data_dir": answers["zed_user_data_dir"],
    }
    save_config(data)
    sync_zed_settings(data)
    enable_certificate_renewal_during_setup(data)


def quick_setup(project_root: str) -> None:
    project = Path(project_root).expanduser().resolve(strict=True)
    if not project.is_dir():
        raise ValueError("current Zed worktree must be a directory")
    if not ZED.is_file() or not GATEWAY.is_file():
        print("Building the pinned patched Zed and gateway. The first build may take a while.")
        subprocess.run(["bash", str(ROOT / "tools/install_linux.sh")], check=True)
    try:
        data = validate(read_config())
    except FileNotFoundError:
        address, hostname = tailscale_defaults()
        if not address or not hostname:
            raise ValueError("automatic setup requires a connected Tailscale client; use 'ZedLink: Configure' for another route")
        tls_directory = config_path().parent / "tls"
        cert_path = tls_directory / f"{hostname}.crt"
        key_path = tls_directory / f"{hostname}.key"
        ensure_tailscale_certificate(cert_path, key_path, hostname)
        route = dict(
            id="tailscale", label="Tailscale", provider="tailscale", kind="direct_tls",
            enabled=True,
            bind=f"{address}:44679", url=f"https://{hostname}:44679",
            cert=str(cert_path), key=str(key_path),
        )
        data = dict(
            version=2,
            project_root=str(project),
            state_dir=str(Path.home() / ".local/state/zedlink"),
            primary_route_id="tailscale",
            routes=[route],
            zed_user_data_dir="",
        )
    else:
        data["project_root"] = str(project)
    save_config(data)
    sync_zed_settings(data)
    enable_certificate_renewal_during_setup(data)
    subprocess.run([sys.executable, str(ROOT / "tools/zed_task_installer.py"), "install"],
                   check=True)
    launcher = install_desktop_launcher()
    cli = install_cli_launcher(data)
    print(f"\nZedLink is configured for this Zed project: {project}")
    print("Global ZedLink tasks are installed and available from any Zed project.")
    if launcher:
        print(f"Application launcher installed: {launcher}")
    print(f"Patched Zed command installed: {cli}")
    if launcher:
        print("Next: open 'ZedLink — Patched Zed', then use /remote-control in its Agent thread.")
    else:
        print(f"Next: run '{cli.name}', then use /remote-control in its Agent thread.")


def netbird_defaults() -> tuple[str | None, str | None]:
    try:
        status = json.loads(subprocess.check_output(
            ["netbird", "status", "--json"], text=True, timeout=4,
            stderr=subprocess.DEVNULL))
        address = str(status.get("netbirdIp", "")).strip()
        hostname = str(status.get("fqdn", "")).rstrip(".")
        if address:
            ipaddress.ip_address(address)
            return address, hostname or None
    except (FileNotFoundError, ValueError, json.JSONDecodeError,
            subprocess.CalledProcessError, subprocess.TimeoutExpired):
        pass
    return None, None


def next_route_port(data: dict) -> int:
    used = {split_bind(route["bind"])[1] for route in data["routes"]}
    for port in range(44679, 44779):
        if port not in used:
            return port
    raise ValueError("no free ZedLink route port in the managed range")


def prompt_value(label: str, default: str = "", required: bool = True) -> str:
    while True:
        suffix = f" [{default}]" if default else ""
        value = input(f"{label}{suffix}: ").strip() or default
        if value or not required:
            return value
        print("  A value is required.")


def write_frontend_template(route: dict, state: Path) -> Path | None:
    if route["provider"] not in ("cloudflare", "ssh-reverse", "ssh-local"):
        return None
    directory = state / "frontends" / route["id"]
    private_directory(directory.parent)
    private_directory(directory)
    address, port = split_bind(route["bind"])
    public_hostname = urlsplit(route["url"]).hostname
    origin_name = route.get("origin_tls_name", public_hostname)
    if route["provider"] == "cloudflare":
        content = f"""# Replace the two placeholders after creating a named Cloudflare Tunnel.
# Protect {route['url']} with a Cloudflare Access self-hosted application.
tunnel: REPLACE_WITH_TUNNEL_UUID
credentials-file: /private/path/REPLACE_WITH_TUNNEL_UUID.json
ingress:
  - hostname: {public_hostname}
    service: https://{address}:{port}
    originRequest:
      originServerName: {origin_name}
      connectTimeout: 10s
  - service: http_status:404
"""
        path = directory / "cloudflared.yml"
    elif route["provider"] == "ssh-reverse":
        content = f"""# VPS Caddyfile. The reverse SSH port stays on VPS loopback.
{public_hostname} {{
    reverse_proxy https://127.0.0.1:{port} {{
        transport http {{
            tls_server_name {origin_name}
        }}
    }}
}}

# Workstation command template. Replace USER and VPS_HOST.
# ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \\
#   -o ServerAliveCountMax=3 -R 127.0.0.1:{port}:127.0.0.1:{port} USER@VPS_HOST
"""
        path = directory / "Caddyfile"
    else:
        content = f"""Open an SSH local forward from the client computer:

ssh -N -T -o ExitOnForwardFailure=yes -o ServerAliveInterval=30 \\
  -o ServerAliveCountMax=3 -L {port}:127.0.0.1:{port} USER@ZED_WORKSTATION

Map {public_hostname} to 127.0.0.1 on that client, then open {route['url']}.
The hostname must match the configured TLS certificate. Keep strict host-key checking enabled.
"""
        path = directory / "README.txt"
    path.write_text(content, encoding="utf-8")
    os.chmod(path, 0o600)
    return path


def add_route(data: dict) -> dict:
    print("\nConnection providers")
    keys = list(PROVIDERS)
    for index, key in enumerate(keys, 1):
        print(f"{index}. {PROVIDERS[key]}")
    choice = prompt_value("Provider number")
    if not choice.isdigit() or not 1 <= int(choice) <= len(keys):
        raise ValueError("invalid provider number")
    provider = keys[int(choice) - 1]
    existing = {route["id"] for route in data["routes"]}
    identifier = provider
    counter = 2
    while identifier in existing:
        identifier = f"{provider}-{counter}"
        counter += 1
    identifier = prompt_value("Route ID", identifier)
    label = prompt_value("Display name", PROVIDERS[provider])
    port = next_route_port(data)
    address = None
    hostname = None
    if provider in ("tailscale", "headscale"):
        address, hostname = tailscale_defaults()
    elif provider == "netbird":
        address, hostname = netbird_defaults()
    if provider in PROXY_PROVIDERS or provider == "ssh-local":
        address = "127.0.0.1"
    bind = prompt_value("Private or loopback listener IP:port",
                        f"{address}:{port}" if address else "")
    if provider in PROXY_PROVIDERS:
        url = prompt_value("Public trusted HTTPS origin")
    else:
        suggested_url = f"https://{hostname}:{port}" if hostname else ""
        url = prompt_value("Trusted HTTPS origin", suggested_url)
    primary = primary_route(data)
    cert = prompt_value("TLS certificate PEM path", primary["cert"])
    key = prompt_value("TLS private key PEM path", primary["key"])
    route = {
        "id": identifier,
        "label": label,
        "provider": provider,
        "kind": "proxy_tls" if provider in PROXY_PROVIDERS else "direct_tls",
        "bind": bind,
        "url": url,
        "cert": cert,
        "key": key,
        "enabled": True,
    }
    if provider in PROXY_PROVIDERS:
        route["origin_tls_name"] = prompt_value(
            "Hostname covered by the local origin certificate",
            urlsplit(primary["url"]).hostname or "")
    updated = dict(data)
    updated["routes"] = data["routes"] + [route]
    updated = validate(updated)
    template = write_frontend_template(
        next(item for item in updated["routes"] if item["id"] == identifier),
        Path(updated["state_dir"]))
    save_config(updated)
    print(f"Added enabled listener definition: {label}")
    print("The provider route remains unavailable until its VPN, connector, tunnel, or SSH path is configured.")
    if template:
        print(f"Frontend template: {template}")
    print("Run 'ZedLink: Restart gateway' to activate enabled listener changes.")
    return updated


def manage_routes(data: dict) -> None:
    print("\nConfigured ZedLink routes")
    for index, route in enumerate(data["routes"], 1):
        flags = []
        if route["id"] == data["primary_route_id"]:
            flags.append("primary")
        flags.append("enabled" if route["enabled"] else "disabled")
        print(f"{index}. {route['label']} [{route['provider']}] {route['url']} -> {route['bind']} ({', '.join(flags)})")
    print("\na. Add route\nt. Toggle enabled\np. Make primary\nr. Remove route\ng. Generate frontend template\nEnter. Exit")
    action = input("Action: ").strip().lower()
    if not action:
        return
    if action == "a":
        add_route(data)
        return
    if action not in ("t", "p", "r", "g"):
        raise ValueError("invalid route action")
    choice = prompt_value("Route number")
    if not choice.isdigit() or not 1 <= int(choice) <= len(data["routes"]):
        raise ValueError("invalid route number")
    index = int(choice) - 1
    route = data["routes"][index]
    updated = dict(data)
    updated["routes"] = [dict(item) for item in data["routes"]]
    if action == "t":
        updated["routes"][index]["enabled"] = not route["enabled"]
    elif action == "p":
        if not route["enabled"]:
            raise ValueError("enable the route before making it primary")
        updated["primary_route_id"] = route["id"]
    elif action == "r":
        if len(updated["routes"]) == 1:
            raise ValueError("cannot remove the only route")
        if input(f"Type REMOVE to delete {route['label']}: ").strip() != "REMOVE":
            return
        updated["routes"].pop(index)
        if updated["primary_route_id"] == route["id"]:
            enabled = next((item for item in updated["routes"] if item["enabled"]), None)
            if enabled is None:
                updated["routes"][0]["enabled"] = True
                enabled = updated["routes"][0]
            updated["primary_route_id"] = enabled["id"]
    else:
        template = write_frontend_template(route, Path(data["state_dir"]))
        if template is None:
            raise ValueError("this route does not use a generated frontend template")
        print(f"Frontend template: {template}")
        return
    save_config(updated)
    print("Route configuration updated. Run 'ZedLink: Restart gateway' to apply it.")


def write_listener_file(data: dict) -> Path:
    state = Path(data["state_dir"])
    directory = state / "gateway"
    private_directory(directory)
    path = directory / "listeners.json"
    payload = {
        "version": 1,
        "listeners": [
            {key: route[key] for key in ("id", "bind", "cert", "key", "url")}
            for route in data["routes"] if route["enabled"]
        ],
    }
    descriptor, name = tempfile.mkstemp(prefix="listeners-", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def write_target_file(data: dict) -> Path:
    state = Path(data["state_dir"])
    directory = state / "gateway"
    private_directory(directory)
    path = directory / "targets.json"
    payload = {"version": 1, "targets": data["targets"]}
    descriptor, name = tempfile.mkstemp(prefix="targets-", dir=directory)
    temporary = Path(name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2)
            stream.write("\n")
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return path


def manage_targets(data: dict) -> None:
    print("\nConfigured patched Zed targets")
    for index, target in enumerate(data["targets"], 1):
        print(f"{index}. {target['label']} [{target['id']}] -> {target['probe']}")
    print("\na. Add target\nr. Remove target\nEnter. Exit")
    action = input("Action: ").strip().lower()
    if not action:
        return
    updated = dict(data)
    updated["targets"] = [dict(target) for target in data["targets"]]
    if action == "a":
        identifier = prompt_value("Target id (lowercase)")
        label = prompt_value("Target label")
        probe = prompt_value("Absolute private probe socket path")
        updated["targets"].append({"id": identifier, "label": label, "probe": probe})
    elif action == "r":
        if len(updated["targets"]) == 1:
            raise ValueError("cannot remove the only Zed target")
        choice = prompt_value("Target number")
        if not choice.isdigit() or not 1 <= int(choice) <= len(updated["targets"]):
            raise ValueError("invalid target number")
        updated["targets"].pop(int(choice) - 1)
    else:
        raise ValueError("invalid target action")
    updated = validate(updated)
    save_config(updated)
    print("Zed target configuration updated. Restart the gateway to apply it.")


def choose_route(data: dict) -> dict:
    enabled = [route for route in data["routes"] if route["enabled"]]
    if len(enabled) == 1:
        return enabled[0]
    primary = primary_route(data)
    print("Choose the origin this device can reach:")
    for index, route in enumerate(enabled, 1):
        marker = " (default)" if route["id"] == primary["id"] else ""
        print(f"{index}. {route['label']} — {route['url']}{marker}")
    answer = input("Route number [default]: ").strip()
    if not answer:
        return primary
    if not answer.isdigit() or not 1 <= int(answer) <= len(enabled):
        raise ValueError("invalid route number")
    return enabled[int(answer) - 1]


def check_routes(data: dict) -> None:
    expected = None
    try:
        expected = admin(Path(data["state_dir"]), "devices")["gateway_id"]
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        pass
    for route in data["routes"]:
        if not route["enabled"]:
            print(f"SKIP {route['label']}: disabled")
            continue
        try:
            result = subprocess.run(
                ["curl", "--silent", "--show-error", "--fail", "--max-time", "8",
                 f"{route['url']}/v1/gateway"], check=True, capture_output=True, text=True)
            identity = json.loads(result.stdout)["gateway_id"]
            if expected and identity != expected:
                print(f"FAIL {route['label']}: gateway identity mismatch")
            else:
                print(f"PASS {route['label']}: TLS, HTTPS, and gateway identity")
        except (FileNotFoundError, subprocess.CalledProcessError, json.JSONDecodeError, KeyError) as error:
            detail = error.stderr.strip() if isinstance(error, subprocess.CalledProcessError) else str(error)
            print(f"FAIL {route['label']}: {detail}")


def check_selected_connection(data: dict, settings: dict) -> str:
    zedlink = settings.get("zedlink")
    if not isinstance(zedlink, dict):
        raise ValueError("ZedLink settings are unavailable; run 'ZedLink: Repair setup'")
    identifier = str(zedlink.get("connection_id", "")).strip()
    route = next((route for route in data["routes"] if route["id"] == identifier), None)
    if route is None:
        raise ValueError("save this connection before checking it")
    if not route["enabled"]:
        raise ValueError("enable and save this connection before checking it")

    try:
        expected_gateway_id = admin(Path(data["state_dir"]), "devices")["gateway_id"]
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError) as error:
        raise ValueError("the local ZedLink gateway is unavailable") from error

    try:
        result = subprocess.run(
            ["curl", "--silent", "--show-error", "--fail", "--max-time", "5",
             f"{route['url']}/v1/gateway"],
            check=True, capture_output=True, text=True)
        gateway_id = json.loads(result.stdout)["gateway_id"]
    except FileNotFoundError as error:
        raise ValueError("curl is required to check the connection") from error
    except subprocess.CalledProcessError as error:
        detail = error.stderr.strip() or "HTTPS request failed"
        raise ValueError(detail) from error
    except (json.JSONDecodeError, KeyError) as error:
        raise ValueError("endpoint did not return a ZedLink gateway identity") from error
    if gateway_id != expected_gateway_id:
        raise ValueError("endpoint belongs to a different ZedLink gateway")
    return f"{route['label']} passed trusted TLS, HTTPS, and gateway identity checks."


def stop_gateway(state: Path) -> bool:
    try:
        result = admin(state, "shutdown")
    except (OSError, subprocess.CalledProcessError, ValueError):
        return False
    if result.get("stopping") is not True:
        raise ValueError("gateway rejected the shutdown request")
    for _ in range(50):
        time.sleep(0.1)
        try:
            admin(state, "devices")
        except (OSError, subprocess.CalledProcessError, ValueError):
            return True
    raise ValueError("gateway did not stop within five seconds")


def admin(state: Path, action: str, identifier: str | None = None) -> dict:
    if not GATEWAY.is_file():
        raise ValueError("build the gateway first (ZedLink: Install / build)")
    command = [str(GATEWAY), "admin", str(state / "gateway"), action]
    if identifier:
        command.append(identifier)
    return json.loads(subprocess.check_output(command, text=True, stderr=subprocess.DEVNULL))


def paired_devices(state: Path) -> dict:
    result = admin(state, "devices")
    if not isinstance(result.get("gateway_id"), str) or not isinstance(result.get("devices"), list):
        raise ValueError("gateway returned an invalid paired-device response")
    return result


def revoke_device(state: Path, identifier: str) -> None:
    uuid.UUID(identifier)
    result = admin(state, "revoke", identifier)
    if result.get("revoked") is not True:
        raise ValueError("device is no longer paired")


def diagnose(data: dict) -> None:
    state = Path(data["state_dir"])
    failures = 0

    def report(ok: bool, label: str, detail: str) -> None:
        nonlocal failures
        print(f"{'PASS' if ok else 'FAIL'}  {label}: {detail}")
        if not ok:
            failures += 1

    report(Path(data["project_root"]).is_dir(), "Project", data["project_root"])
    report(state.is_dir() and not state.is_symlink() and state.stat().st_mode & 0o077 == 0,
           "Private state", "directory exists with private permissions")
    report(ZED.is_file(), "Patched Zed", str(ZED))
    report(GATEWAY.is_file(), "Gateway binary", str(GATEWAY))

    settings_path = zed_settings_path(data)
    try:
        native = json.loads(settings_path.read_text(encoding="utf-8")).get("zedlink", {})
        settings_ok = (
            native.get("enabled") is True
            and native.get("state_directory") == data["state_dir"]
            and native.get("project_root") == data["project_root"]
            and native.get("manager_path") == str(Path(__file__).resolve())
        )
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        settings_ok = False
    report(settings_ok, "Native settings", str(settings_path))

    for route in data["routes"]:
        if not route["enabled"]:
            continue
        certificate = Path(route["cert"])
        key = Path(route["key"])
        hostname = urlsplit(route["url"]).hostname or ""
        route_ok, route_detail = certificate_health(certificate, key, hostname, require_trust=route["provider"] == "tailscale")
        report(route_ok, f"TLS route {route['label']}", route_detail)

    socket_path = state / "probe/zedlink.sock"
    try:
        subprocess.run(
            [sys.executable, str(ROOT / "tools/zedlink_probe_client.py"),
             "--socket", str(socket_path), "info"],
            check=True, timeout=3, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        bridge_ok = True
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
        bridge_ok = False
    report(bridge_ok, "Native bridge", "patched Zed is connected")

    try:
        devices = admin(state, "devices")["devices"]
        gateway_detail = f"online with {len(devices)} paired device(s)"
        gateway_ok = True
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        gateway_detail = "offline"
        gateway_ok = False
    report(gateway_ok, "Gateway", gateway_detail)

    print("INFO  Model provider: owned and tested by the selected Agent thread inside Zed")
    if failures:
        raise ValueError(f"diagnostics found {failures} problem(s); run 'ZedLink: Repair setup'")


def repair(data: dict) -> None:
    state = Path(data["state_dir"])
    for directory in (state, state / "probe", state / "gateway"):
        private_directory(directory)
    if not sync_zed_settings(data):
        raise ValueError("native settings use JSON comments; update the ZedLink Settings page manually")
    subprocess.run([sys.executable, str(ROOT / "tools/zed_task_installer.py"), "install"],
                   check=True)
    install_desktop_launcher()
    install_cli_launcher(data)
    try:
        admin(state, "devices")
        gateway_started = False
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        subprocess.Popen(
            [sys.executable, str(Path(__file__).resolve()), "start-gateway"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            start_new_session=True)
        gateway_started = True
        for _ in range(50):
            time.sleep(0.1)
            try:
                admin(state, "devices")
                break
            except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
                continue
        else:
            raise ValueError("gateway did not become ready within five seconds")
    print("Repaired native settings, tasks, launchers, and private directories.")
    print("Started the configured gateway." if gateway_started else "Gateway was already running.")
    print("Restart patched Zed once if it was open so the updated bridge settings take effect.")


def gateway_status(data: dict) -> dict:
    state = Path(data["state_dir"])
    targets = []
    for target in data["targets"]:
        online = False
        try:
            subprocess.run(
                [sys.executable, str(ROOT / "tools/zedlink_probe_client.py"),
                 "--socket", target["probe"], "info"],
                check=True, timeout=2, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL)
            online = True
        except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
            pass
        targets.append({
            "label": target["label"],
            "probe": target["probe"],
            "online": online,
        })

    paired_devices = 0
    gateway_online = False
    try:
        devices = admin(state, "devices")["devices"]
        paired_devices = len(devices)
        gateway_online = True
    except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
        pass

    routes = []
    for route in data["routes"]:
        routes.append({
            "id": route["id"],
            "label": route["label"],
            "provider": route.get("provider", "custom"),
            "url": route["url"],
            "bind": route["bind"],
            "enabled": route["enabled"],
            "primary": route["id"] == data["primary_route_id"],
        })

    return {
        "configured": True,
        "project_root": data["project_root"],
        "state_dir": data["state_dir"],
        "targets": targets,
        "routes": routes,
        "gateway": {
            "online": gateway_online,
            "built": GATEWAY.is_file(),
            "paired_devices": paired_devices,
        },
        "patched_zed": {
            "built": ZED.is_file(),
            "executable": str(ZED),
            "launcher_installed": desktop_launcher_path().is_file(),
            "command_installed": cli_launcher_path().is_file(),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("quick-setup", "configure", "tailscale-setup",
                                           "tailscale-check", "tailscale-check-json", "tailscale-repair",
                                           "install-renewal", "renewal-status",
                                           "renew-certificates", "remove-renewal",
                                           "manage-routes", "manage-targets",
                                           "check-routes", "status", "status-json", "start-zed",
                                           "start-gateway", "restart-gateway", "stop-gateway",
                                           "start-gateway-detached", "restart-gateway-detached",
                                           "install-launcher", "remove-launcher",
                                           "install-cli", "remove-cli",
                                           "pair", "pair-browser", "pair-terminal", "pair-primary", "pair-primary-terminal",
                                           "devices", "devices-json", "revoke",
                                           "revoke-device", "diagnose", "repair",
                                           "save-connection", "select-connection",
                                           "detect-connection", "check-connection"))
    parser.add_argument("project_root", nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "configure":
            configure()
            return
        if args.action == "tailscale-setup":
            setup_tailscale_certificate()
            return
        if args.action in ("tailscale-check", "tailscale-check-json", "tailscale-repair"):
            data = validate(read_config()) if config_path().exists() else None
            if args.action == "tailscale-repair": repair_tailscale_connection(data)
            else:
                result = tailscale_connection_checks(data)
                if args.action == "tailscale-check-json": print(json.dumps(result))
                else:
                    print_tailscale_checks(result)
                    if not result["host_ready"]: sys.exit(1)
            return
        if args.action == "quick-setup":
            if not args.project_root:
                raise ValueError("quick setup requires the current Zed worktree path")
            quick_setup(args.project_root)
            return
        if not config_path().exists():
            if args.action == "status-json":
                print(json.dumps({
                    "configured": False,
                    "gateway": {"online": False, "built": GATEWAY.is_file(), "paired_devices": 0},
                    "patched_zed": {"built": ZED.is_file(), "executable": str(ZED),
                                    "launcher_installed": desktop_launcher_path().is_file(),
                                    "command_installed": cli_launcher_path().is_file()},
                    "project_root": "", "state_dir": "", "targets": [], "routes": [],
                }))
                return
            if args.action == "status":
                print("Setup: not configured")
                print("Next step: open Zed's task picker and run 'ZedLink: Configure'.")
                print(f"Patched Zed: {'built' if ZED.is_file() else 'not built'}")
                print(f"Gateway binary: {'built' if GATEWAY.is_file() else 'not built'}")
                return
            raise ValueError("setup is not configured; run 'ZedLink: Configure' first")
        data = validate(read_config())
        state = Path(data["state_dir"])
        socket_path = state / "probe/zedlink.sock"
        if args.action == "manage-routes":
            manage_routes(data)
        elif args.action == "install-renewal":
            install_certificate_renewal(data)
        elif args.action == "renewal-status":
            certificate_renewal_status(data)
        elif args.action == "renew-certificates":
            renewed = renew_tailscale_certificates(data)
            print(f"Renewed {renewed} Tailscale certificate(s).")
        elif args.action == "remove-renewal":
            remove_certificate_renewal()
        elif args.action == "manage-targets":
            manage_targets(data)
        elif args.action == "detect-connection":
            settings = prepare_connection_settings(data, read_zed_settings(data))
            write_zed_settings(data, settings)
            print("Detected provider defaults. Review the URL and TLS fields before saving.")
        elif args.action == "save-connection":
            updated = update_connection_from_settings(data, read_zed_settings(data))
            save_config(updated)
            sync_zed_settings(updated)
            restart_gateway_detached()
            route = primary_route(updated)
            print(f"Saved and activated {route['label']} ({route['provider']}).")
        elif args.action == "check-connection":
            print(check_selected_connection(data, read_zed_settings(data)))
        elif args.action == "select-connection":
            updated = select_connection_from_settings(data, read_zed_settings(data))
            save_config(updated)
            sync_zed_settings(updated)
            restart_gateway_detached()
            route = primary_route(updated)
            print(f"Activated {route['label']} ({route['provider']}).")
        elif args.action == "diagnose":
            diagnose(data)
        elif args.action == "repair":
            repair(data)
        elif args.action == "check-routes":
            check_routes(data)
        elif args.action == "status":
            print(f"Project: {data['project_root']}")
            print("Zed targets:")
            for target in data["targets"]:
                print(f"  {target['label']}: {target['probe']}")
            print("Gateway routes:")
            for route in data["routes"]:
                state_label = "enabled" if route["enabled"] else "disabled"
                primary_label = ", primary" if route["id"] == data["primary_route_id"] else ""
                print(f"  {route['label']}: {route['url']} -> {route['bind']} ({state_label}{primary_label})")
            try:
                subprocess.run(
                    [sys.executable, str(ROOT / "tools/zedlink_probe_client.py"),
                     "--socket", str(socket_path), "info"],
                    check=True, timeout=3, stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL)
                print("Patched Zed bridge: online (separate dev-channel instance)")
            except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired):
                print("Patched Zed bridge: offline")
            print(f"Patched Zed: {'built' if ZED.is_file() else 'not built'}")
            print(f"Patched Zed executable: {ZED}")
            print(f"Patched Zed launcher: {'installed' if desktop_launcher_path().is_file() else 'not installed'}")
            print(f"Patched Zed command: {'installed' if cli_launcher_path().is_file() else 'not installed'}")
            print(f"Gateway binary: {'built' if GATEWAY.is_file() else 'not built'}")
            try:
                result = admin(state, "devices")
                print(f"Gateway admin: online; paired devices: {len(result['devices'])}")
            except (OSError, subprocess.CalledProcessError, ValueError):
                print("Gateway admin: offline")
        elif args.action == "status-json":
            print(json.dumps(gateway_status(data)))
        elif args.action == "install-launcher":
            launcher = install_desktop_launcher()
            if launcher is None:
                print(f"macOS has no application launcher; use the '{cli_launcher_path().name}' command instead.")
            else:
                print(f"Installed application launcher: {launcher}")
                print("Open 'ZedLink — Patched Zed' from the application menu for future remote-control sessions.")
        elif args.action == "remove-launcher":
            removed = remove_desktop_launcher()
            print("Removed the ZedLink application launcher." if removed else "ZedLink application launcher is not installed.")
        elif args.action == "install-cli":
            cli = install_cli_launcher(data)
            print(f"Installed patched Zed command: {cli}")
            print(f"Use '{cli.name}', '{cli.name} .', or '{cli.name} path/to/file'.")
        elif args.action == "remove-cli":
            removed = remove_cli_launcher()
            print("Removed the ZedLink zed command." if removed else "ZedLink zed command is not installed.")
        elif args.action == "start-zed":
            if not ZED.is_file():
                raise ValueError("build patched Zed first (ZedLink: Install / build)")
            for directory in (state, state / "probe"):
                private_directory(directory)
            environment = os.environ.copy()
            environment["ZED_RELEASE_CHANNEL"] = "dev"
            if not has_native_zedlink_settings(data):
                environment.update(ZEDLINK_PROBE_DIR=str(state / "probe"),
                                   ZEDLINK_PROBE_PROJECT_ROOT=data["project_root"])
            command = [str(ZED)]
            if data["zed_user_data_dir"]:
                command += ["--user-data-dir", data["zed_user_data_dir"]]
            command.append(data["project_root"])
            print("Starting patched Zed as a separate Zed Dev instance.", flush=True)
            print(f"Executable: {ZED}", flush=True)
            print(f"Project: {data['project_root']}", flush=True)
            print("Use /remote-control only in the Zed Dev window; ordinary Zed does not contain it.",
                  flush=True)
            os.execve(str(ZED), command, environment)
        elif args.action in ("start-gateway", "restart-gateway"):
            if not GATEWAY.is_file():
                raise ValueError("build gateway first (ZedLink: Install / build)")
            for directory in (state, state / "gateway"):
                private_directory(directory)
            if args.action == "restart-gateway" and stop_gateway(state):
                print("Stopped the existing ZedLink gateway.")
            try:
                existing = admin(state, "devices")
                print(f"ZedLink gateway is already running with {len(existing['devices'])} paired devices.")
                print("Stop its existing Zed task before restarting it to apply route changes.")
                return
            except (OSError, subprocess.CalledProcessError, ValueError, KeyError):
                pass
            listener_file = write_listener_file(data)
            target_file = write_target_file(data)
            os.execv(str(GATEWAY), [str(GATEWAY), "serve-targets", str(listener_file),
                                    str(target_file), str(state / "gateway")])
        elif args.action in ("start-gateway-detached", "restart-gateway-detached"):
            foreground_action = args.action.removesuffix("-detached")
            launch_gateway_detached(foreground_action)
            print(f"ZedLink gateway {foreground_action.removesuffix('-gateway')} requested.")
        elif args.action == "stop-gateway":
            if stop_gateway(state):
                print("ZedLink gateway stopped.")
            else:
                print("ZedLink gateway is not running.")
        elif args.action in ("pair", "pair-browser", "pair-terminal"):
            route = choose_route(data) if args.action == "pair-terminal" else primary_route(data)
            command = [sys.executable, str(ROOT / "tools/pair_phone.py"), route["url"],
                       str(state / "gateway")]
            if args.action != "pair":
                command += ["--mode", args.action.removeprefix("pair-")]
            subprocess.run(command, check=True)
        elif args.action in ("pair-primary", "pair-primary-terminal"):
            route = primary_route(data)
            subprocess.run([sys.executable, str(ROOT / "tools/pair_phone.py"), route["url"],
                            str(state / "gateway"), "--mode",
                            "terminal" if args.action == "pair-primary-terminal" else "browser"], check=True)
        elif args.action == "devices":
            result = paired_devices(state)
            print(f"Gateway {result['gateway_id']}")
            for device in result["devices"]:
                print(f"{device['id']}  {device['name']}")
            if not result["devices"]:
                print("No paired devices.")
        elif args.action == "devices-json":
            print(json.dumps(paired_devices(state), separators=(",", ":")))
        elif args.action == "revoke-device":
            if not args.project_root:
                raise ValueError("revoke-device requires a device ID")
            revoke_device(state, args.project_root)
            print("Device revoked.")
        elif args.action == "revoke":
            devices = admin(state, "devices")["devices"]
            if not devices:
                print("No paired devices.")
                return
            for index, device in enumerate(devices, 1):
                print(f"{index}. {device['name']} ({device['id']})")
            choice = input("Number to revoke (blank cancels): ").strip()
            if not choice:
                return
            if not choice.isdigit() or not 1 <= int(choice) <= len(devices):
                raise ValueError("invalid device number")
            device = devices[int(choice) - 1]
            if input(f"Type REVOKE to remove {device['name']}: ").strip() != "REVOKE":
                return
            result = admin(state, "revoke", device["id"])
            if result.get("revoked") is not True:
                raise ValueError(f"revoke failed: {result.get('error', 'unknown error')}")
            print("Device revoked.")
    except (FileNotFoundError, ValueError, KeyError, OSError, subprocess.CalledProcessError) as error:
        parser.exit(1, f"ZedLink: {error}\n")


if __name__ == "__main__":
    main()
