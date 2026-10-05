#!/usr/bin/env python3
"""Show a private desktop QR and short code for pairing a phone browser."""

import argparse
import html
import json
import os
import pathlib
import subprocess
import tempfile
import urllib.parse
import uuid
import webbrowser
from datetime import datetime, timedelta, timezone


def admin(binary: pathlib.Path, state_dir: pathlib.Path, method: str) -> dict:
    result = subprocess.run(
        [str(binary), "admin", str(state_dir), method],
        check=True,
        capture_output=True,
        text=True,
    )
    return json.loads(result.stdout)


def qr_svg(value: str) -> str:
    try:
        import qrcode
    except ImportError as error:
        raise SystemExit("Install the local QR helper with: python3 -m pip install qrcode") from error
    qr = qrcode.QRCode(border=4, box_size=8)
    qr.add_data(value)
    qr.make(fit=True)
    cells = qr.get_matrix()
    size = len(cells)
    paths = "".join(
        f"M{x},{y}h1v1h-1z" for y, row in enumerate(cells) for x, black in enumerate(row) if black
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {size} {size}" '
        f'role="img" aria-label="Scan to open ZedLink on your phone">'
        f'<rect width="{size}" height="{size}" fill="#fff"/>'
        f'<path d="{paths}" fill="#111827"/></svg>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="trusted HTTPS gateway URL opened by the phone")
    parser.add_argument("state_dir", type=pathlib.Path, help="private gateway state directory")
    parser.add_argument("--no-open", action="store_true", help="create the page without opening it")
    args = parser.parse_args()
    parsed = urllib.parse.urlsplit(args.url)
    if (parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password
            or parsed.query or parsed.fragment or parsed.path not in ("", "/")):
        parser.error("URL must be an HTTPS origin without credentials, path, query, or fragment")
    binary = pathlib.Path(__file__).resolve().parent.parent / "gateway/target/debug/zedlink-gateway"
    if not binary.is_file():
        parser.error("build the gateway first with cargo build --manifest-path gateway/Cargo.toml")
    state_dir = args.state_dir.resolve(strict=True)
    identity = admin(binary, state_dir, "devices")["gateway_id"]
    uuid.UUID(identity)
    code = admin(binary, state_dir, "pair-short-code")["code"]
    if len(code) != 10 or not code.isdecimal():
        raise SystemExit("gateway returned an invalid short pairing code")
    base = f"https://{parsed.netloc}/"
    link = base + "#" + urllib.parse.urlencode({"gateway": identity})
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair ZedLink phone</title>
<style>body{{font:18px system-ui;background:#101827;color:#f8fafc;max-width:540px;margin:4vh auto;padding:24px}}
main{{background:#1e293b;border-radius:20px;padding:24px;text-align:center}}svg{{width:min(80vw,320px);border-radius:12px}}
.code{{font-size:clamp(28px,8vw,52px);letter-spacing:.12em;font-weight:700;margin:18px 0}}
a{{color:#93c5fd;overflow-wrap:anywhere}}small{{color:#cbd5e1}}</style>
<main><h1>Pair your phone</h1><p>Scan this QR in the iPhone camera, then enter the code on the ZedLink page.</p>
{qr_svg(link)}<div class="code">{html.escape(code[:5])} {html.escape(code[5:])}</div>
<p><small>One use · expires {expires.strftime('%H:%M UTC')} · keep this window private</small></p>
<p><a href="{html.escape(link, quote=True)}">{html.escape(base)}</a></p>
<p><small>The QR carries the address and gateway identity. It does not carry the secret code.</small></p>
</main></html>"""
    directory = pathlib.Path(tempfile.mkdtemp(prefix="zedlink-pair-", dir=state_dir))
    path = directory / "pair.html"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(page)
    print(f"Private pairing page: {path}")
    print(f"Open it on this workstation; scan its QR with the iPhone camera. Expires {expires.strftime('%H:%M UTC')}.")
    if not args.no_open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
