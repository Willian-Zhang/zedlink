#!/usr/bin/env python3
"""Install the official Zed Nightly remote server that matches the patched build.

Patched Zed has no published remote server, so for SSH projects it downloads the
*latest* official Nightly server, whose protocol drifts away from the fork's base
commit. The fork doesn't change the remote protocol crates, so the official
Nightly server built from the fork's upstream base commit is a matching server.
This script places that server on each SSH host under the file name the patched
client looks for (`~/.zed_server/zed-remote-server-nightly-<version>+nightly.<sha>`),
so the client uses it instead of downloading a newer one.

Run it after every rebuild, because the client's commit, and so the file name,
changes each time.
"""

from __future__ import annotations

import argparse
import gzip
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "zed-source"
NIGHTLY_HOST = "https://zed-nightly-host.nyc3.digitaloceanspaces.com"
CACHE = Path.home() / "Library/Caches/zedlink/remote-servers"
ARCHES = {"aarch64": "aarch64", "arm64": "aarch64", "x86_64": "x86_64", "amd64": "x86_64"}
PROTOCOL_PATHS = ["crates/proto", "crates/rpc", "crates/remote", "crates/remote_server"]


def run(command: list[str], **kwargs) -> str:
    return subprocess.run(command, check=True, capture_output=True, text=True, **kwargs).stdout.strip()


def git(source: Path, *args: str) -> str:
    return run(["git", "-C", str(source), *args])


def upstream_base(source: Path) -> str:
    message = git(source, "log", "-1", "--format=%H %s", "--grep=^Merge upstream Zed main at ")
    match = re.search(r"Merge upstream Zed main at ([0-9a-f]{7,40})", message)
    if not match:
        raise SystemExit("couldn't find the fork's 'Merge upstream Zed main at <sha>' commit; pass --upstream-sha")
    return match.group(1)


def crate_version(source: Path) -> str:
    for line in (source / "crates/zed/Cargo.toml").read_text(encoding="utf-8").splitlines():
        match = re.match(r'version\s*=\s*"([^"]+)"', line)
        if match:
            return match.group(1)
    raise SystemExit("couldn't read the zed crate version")


def asset_url(version: str, run_number: int, sha: str, arch: str) -> str:
    release = urllib.parse.quote(f"{version}+nightly.{run_number}.{sha}")
    return f"{NIGHTLY_HOST}/{release}/zed-remote-server-linux-{arch}.gz"


def asset_exists(url: str) -> bool:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, method="HEAD"), timeout=20) as response:
            return response.status == 200
    except OSError:
        return False


def nightly_runs(sha: str) -> list[int]:
    output = run(["gh", "run", "list", "-R", "zed-industries/zed", "--workflow=release_nightly.yml",
                  "--commit", sha, "--status", "success", "--limit", "10",
                  "--json", "number", "--jq", ".[].number"])
    return sorted((int(number) for number in output.split()), reverse=True)


def download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if destination.is_file():
        return
    with tempfile.NamedTemporaryFile(dir=destination.parent, delete=False) as temporary:
        with urllib.request.urlopen(url, timeout=120) as response:
            shutil.copyfileobj(response, temporary)
    Path(temporary.name).replace(destination)


def ssh(host: str, script: str) -> str:
    return run(["ssh", "-o", "BatchMode=yes", host, "bash", "-s"], input=script)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("hosts", nargs="+", help="SSH host names, as used by Zed")
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE, help="patched Zed checkout")
    parser.add_argument("--client-sha", action="append",
                        help="client commit(s) to install for (default: the checkout's HEAD)")
    parser.add_argument("--upstream-sha", help="fork's upstream base commit (default: detected)")
    parser.add_argument("--restart", action="store_true",
                        help="stop running Nightly remote servers so clients reconnect to the matching one")
    args = parser.parse_args()

    source = args.source.resolve()
    base = git(source, "rev-parse", args.upstream_sha or upstream_base(source))
    changed = git(source, "diff", "--stat", base, "HEAD", "--", *PROTOCOL_PATHS)
    if changed:
        raise SystemExit(f"the fork changes remote protocol crates since {base[:10]}; "
                         f"an official server won't match:\n{changed}")
    client_shas = [git(source, "rev-parse", sha) for sha in (args.client_sha or ["HEAD"])]
    version = crate_version(source)

    runs = nightly_runs(base)
    if not runs:
        raise SystemExit(f"no successful official Nightly run found for {base[:10]}")

    for host in args.hosts:
        arch = ARCHES.get(ssh(host, "uname -m"))
        if not arch:
            raise SystemExit(f"{host}: unsupported architecture")
        url = next((asset_url(version, number, base, arch) for number in runs
                    if asset_exists(asset_url(version, number, base, arch))), None)
        if not url:
            raise SystemExit(f"no published linux-{arch} remote server for {base[:10]}")
        archive = CACHE / f"{version}+nightly.{base}" / f"zed-remote-server-linux-{arch}.gz"
        download(url, archive)
        binary = archive.with_suffix("")
        if not binary.is_file():
            with gzip.open(archive, "rb") as compressed, open(binary, "wb") as output:
                shutil.copyfileobj(compressed, output)

        staging = f".zed_server/zedlink-upload-{base[:12]}"
        run(["ssh", "-o", "BatchMode=yes", host, "mkdir -p .zed_server"])
        run(["scp", "-q", "-o", "BatchMode=yes", str(binary), f"{host}:{staging}"])
        names = [f"zed-remote-server-nightly-{version}+nightly.{sha}" for sha in client_shas]
        script = ["set -euo pipefail", "cd ~/.zed_server", f"chmod 755 {staging.split('/')[-1]}"]
        for name in names:
            script += [f"cp {staging.split('/')[-1]} {name}.new", f"mv -f {name}.new {name}"]
        script += [f"rm -f {staging.split('/')[-1]}", f"./{names[0]} version"]
        if args.restart:
            script += ["pkill -f 'zed-remote-server-nightly-' || true"]
        reported = ssh(host, "\n".join(script) + "\n")
        print(f"{host}: installed official server {reported.splitlines()[0]} (base {base[:10]}) as:")
        for name in names:
            print(f"  ~/.zed_server/{name}")
        if args.restart:
            print(f"{host}: stopped running Nightly remote servers; open SSH windows reconnect to the new one")
    return 0


if __name__ == "__main__":
    sys.exit(main())
