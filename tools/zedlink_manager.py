#!/usr/bin/env python3
"""Local, terminal-backed setup actions for Zed's task picker."""

import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parent.parent
GATEWAY = ROOT / "gateway/target/debug/zedlink-gateway"
ZED = ROOT / "zed-source/target/debug/zed"


def config_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "zedlink/config.json"


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


def validate(data: dict) -> dict:
    project = Path(data["project_root"]).expanduser().resolve(strict=True)
    if not project.is_dir():
        raise ValueError("project root must be an existing directory")
    state = Path(data["state_dir"]).expanduser().resolve()
    if not state.is_absolute():
        raise ValueError("state directory must be absolute")
    host, separator, port = data["bind"].rpartition(":")
    if not separator or not port.isdigit() or not 1 <= int(port) <= 65535:
        raise ValueError("bind must be PRIVATE_IP:PORT")
    address = ipaddress.ip_address(host.strip("[]"))
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
    parsed = urlsplit(data["url"])
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or
            parsed.password or parsed.path not in ("", "/") or parsed.query or
            parsed.fragment or not parsed.port):
        raise ValueError("URL must be a trusted HTTPS origin with an explicit port")
    if parsed.port != int(port):
        raise ValueError("URL and bind port must match")
    if not str(data.get("cert", "")).strip():
        raise ValueError("TLS certificate path is required")
    if not str(data.get("key", "")).strip():
        raise ValueError("TLS private key path is required")
    cert = Path(data["cert"]).expanduser().resolve(strict=True)
    key = Path(data["key"]).expanduser().resolve(strict=True)
    if not cert.is_file() or not key.is_file():
        raise ValueError("certificate and key must be files")
    if key.stat().st_mode & 0o077:
        raise ValueError("TLS key must be mode 0600 or stricter")
    profile = data.get("zed_user_data_dir", "")
    if profile:
        profile = str(Path(profile).expanduser().resolve(strict=True))
        if not Path(profile).is_dir():
            raise ValueError("Zed user data directory must exist")
    return dict(project_root=str(project), state_dir=str(state), bind=data["bind"],
                url=data["url"].rstrip("/"), cert=str(cert), key=str(key),
                zed_user_data_dir=profile)


def ensure_tailscale_certificate(cert_path: Path, key_path: Path, hostname: str) -> None:
    if cert_path.is_file() and key_path.is_file():
        return
    if cert_path.exists() or key_path.exists():
        raise ValueError("only one TLS file exists; remove or repair the incomplete certificate pair")
    print("\nThe TLS certificate files do not exist yet.")
    print(f"ZedLink can request a certificate for {hostname} with Tailscale.")
    print("Certificate issuance publishes this hostname in public Certificate Transparency logs.")
    create = input("Create the certificate and key now? [Y/n]: ").strip().lower()
    if create not in ("", "y", "yes"):
        raise ValueError("TLS certificate setup was cancelled; create the files and run setup again")
    if cert_path.parent != key_path.parent:
        raise ValueError("automatic certificate creation requires certificate and key in the same directory")
    private_directory(config_path().parent)
    private_directory(cert_path.parent)
    subprocess.run(["tailscale", "cert", "--cert-file", str(cert_path),
                    "--key-file", str(key_path), hostname], check=True)
    os.chmod(cert_path, 0o600)
    os.chmod(key_path, 0o600)
    print(f"Created TLS certificate: {cert_path}")
    print(f"Created private TLS key: {key_path}")


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
        old = read_config()
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
    data = {}
    for field, label in prompts.items():
        current = old.get(field, defaults[field])
        print(f"\n{label}")
        print(f"  {help_text[field]}")
        while True:
            suffix = f" [{current}]" if current else ""
            answer = input(f"{label}{suffix}: ").strip() or current
            if field == "project_root" and not answer:
                print("  A project path is required. Example: /home/you/Documents/my-project")
                continue
            data[field] = answer
            break
    cert_path = Path(data["cert"]).expanduser()
    key_path = Path(data["key"]).expanduser()
    if tailscale_hostname:
        ensure_tailscale_certificate(cert_path, key_path, tailscale_hostname)
    save_config(data)


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
        data = dict(
            project_root=str(project),
            state_dir=str(Path.home() / ".local/state/zedlink"),
            bind=f"{address}:44679",
            url=f"https://{hostname}:44679",
            cert=str(cert_path),
            key=str(key_path),
            zed_user_data_dir="",
        )
    else:
        data["project_root"] = str(project)
    save_config(data)
    subprocess.run([sys.executable, str(ROOT / "tools/zed_task_installer.py"), "install"],
                   check=True)
    print(f"\nZedLink is configured for this Zed project: {project}")
    print("Global ZedLink tasks are installed and available from any Zed project.")
    print("Next: run 'ZedLink: Start patched Zed', then use /remote-control in its Agent thread.")


def admin(state: Path, action: str, identifier: str | None = None) -> dict:
    if not GATEWAY.is_file():
        raise ValueError("build the gateway first (ZedLink: Install / build)")
    command = [str(GATEWAY), "admin", str(state / "gateway"), action]
    if identifier:
        command.append(identifier)
    return json.loads(subprocess.check_output(command, text=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("quick-setup", "configure", "status", "start-zed",
                                           "start-gateway", "pair", "devices", "revoke"))
    parser.add_argument("project_root", nargs="?")
    args = parser.parse_args()
    try:
        if args.action == "configure":
            configure()
            return
        if args.action == "quick-setup":
            if not args.project_root:
                raise ValueError("quick setup requires the current Zed worktree path")
            quick_setup(args.project_root)
            return
        if not config_path().exists():
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
        if args.action == "status":
            print(f"Project: {data['project_root']}\nGateway: {data['url']} ({data['bind']})")
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
            print(f"Gateway binary: {'built' if GATEWAY.is_file() else 'not built'}")
            try:
                result = admin(state, "devices")
                print(f"Gateway admin: online; paired devices: {len(result['devices'])}")
            except (OSError, subprocess.CalledProcessError, ValueError):
                print("Gateway admin: offline")
        elif args.action == "start-zed":
            if not ZED.is_file():
                raise ValueError("build patched Zed first (ZedLink: Install / build)")
            for directory in (state, state / "probe"):
                private_directory(directory)
            environment = os.environ.copy()
            environment.update(ZEDLINK_PROBE_DIR=str(state / "probe"),
                               ZEDLINK_PROBE_PROJECT_ROOT=data["project_root"],
                               ZED_RELEASE_CHANNEL="dev")
            command = [str(ZED)]
            if data["zed_user_data_dir"]:
                command += ["--user-data-dir", data["zed_user_data_dir"]]
            command.append(data["project_root"])
            print("Starting patched Zed as a separate Zed Dev instance.", flush=True)
            print("Use /remote-control only in the Zed Dev window; ordinary Zed does not contain it.",
                  flush=True)
            os.execve(str(ZED), command, environment)
        elif args.action == "start-gateway":
            if not GATEWAY.is_file():
                raise ValueError("build gateway first (ZedLink: Install / build)")
            for directory in (state, state / "gateway"):
                private_directory(directory)
            os.execv(str(GATEWAY), [str(GATEWAY), "serve", data["bind"], data["cert"],
                                    data["key"], str(socket_path), str(state / "gateway")])
        elif args.action == "pair":
            subprocess.run([sys.executable, str(ROOT / "tools/pair_phone.py"), data["url"],
                            str(state / "gateway")], check=True)
        elif args.action == "devices":
            result = admin(state, "devices")
            print(f"Gateway {result['gateway_id']}")
            for device in result["devices"]:
                print(f"{device['id']}  {device['name']}")
            if not result["devices"]:
                print("No paired devices.")
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
