#!/usr/bin/env python3
"""Show a private page for pairing any phone or desktop browser."""

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
        f'role="img" aria-label="Scan to open and pair ZedLink on another device">'
        f'<rect width="{size}" height="{size}" fill="#fff"/>'
        f'<path d="{paths}" fill="#111827"/></svg>'
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="trusted HTTPS gateway URL opened by the client browser")
    parser.add_argument("state_dir", type=pathlib.Path, help="private gateway state directory")
    parser.add_argument("--no-open", action="store_true", help="create the page without opening it")
    parser.add_argument("--manual-code", action="store_true", help="keep the one-time code out of the QR and enter it on the destination device")
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
    manual_link = base + "#" + urllib.parse.urlencode({"gateway": identity})
    link = (manual_link if args.manual_code else base + "#" + urllib.parse.urlencode(
        {"v": "1", "gateway": identity, "pair": code}))
    expires = datetime.now(timezone.utc) + timedelta(minutes=5)
    instructions = ("Open the manual page or scan the QR, then enter the code shown here."
                    if args.manual_code else "Use the button for a new browser, or type the code into an installed home-screen app.")
    page = f"""<!doctype html>
<html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pair a ZedLink device</title>
<style>
:root{{color-scheme:dark;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#000;color:#f3f3f1}}
*{{box-sizing:border-box}}body{{margin:0;background:#000}}main{{width:min(100%,760px);margin:0 auto;padding:clamp(32px,7vh,72px) 24px 48px}}
.eyebrow{{color:#797c82;font:600 11px ui-monospace,monospace;letter-spacing:.16em}}h1{{margin:10px 0;font-size:clamp(38px,7vw,64px);font-weight:500;letter-spacing:-.05em}}
.intro{{max-width:620px;color:#a2a5aa;line-height:1.6}}.pair-grid{{display:grid;grid-template-columns:minmax(240px,340px) 1fr;gap:32px;align-items:center;margin-top:30px;padding:28px 0;border-block:1px solid #2b2d30}}
.installed{{margin:24px 0 0;padding:15px;border:1px solid #505257;color:#d8d9da;line-height:1.55}}.installed strong{{display:block;margin-bottom:5px}}.details{{display:grid;gap:7px;margin:16px 0;color:#a2a5aa;font:12px ui-monospace,monospace}}.details code{{color:#f3f3f1;overflow-wrap:anywhere}}
svg{{width:100%;background:#fff}}.code{{font:700 clamp(28px,5vw,46px) ui-monospace,monospace;letter-spacing:.12em;margin:15px 0}}
.actions{{display:grid;gap:10px;margin:22px 0}}a,button{{display:grid;place-items:center;min-height:48px;padding:10px 15px;border:1px solid #f3f3f1;border-radius:0;font:700 15px system-ui;text-decoration:none;cursor:pointer}}
a.primary{{background:#f3f3f1;color:#000}}button{{background:transparent;color:#f3f3f1}}a.secondary{{border-color:#505257;color:#f3f3f1}}small{{color:#a2a5aa;line-height:1.5}}#copy-status{{min-height:1.5em;color:#79c79b;font-size:13px}}
@media(max-width:620px){{.pair-grid{{grid-template-columns:1fr}}}}
</style>
<main><p class="eyebrow">PRIVATE DEVICE PAIRING</p><h1>Connect ZedLink</h1><p class="intro">{html.escape(instructions)} The credential can be revoked later from ZedLink's paired-device task.</p>
<div class="installed"><strong>Already using the iPhone home-screen app?</strong>Keep ZedLink open there. Do not scan the QR—it opens the default browser. Compare the address and Gateway ID below, type the 10-digit code in the app, check the confirmation box, and tap <b>Connect ZedLink</b>.</div>
<div class="pair-grid"><div>{qr_svg(link)}</div><div><p class="eyebrow">ONE-TIME CODE</p><div class="code">{html.escape(code[:5])} {html.escape(code[5:])}</div>
<p><small>One use · expires {expires.strftime('%H:%M UTC')} · keep this page private</small></p>
<div class="details"><span>HTTPS address <code>{html.escape(base)}</code></span><span>Gateway ID <code>{html.escape(identity)}</code></span></div>
<div class="actions"><a class="primary" href="{html.escape(link, quote=True)}">Pair a new browser</a>
<button id="copy-link" type="button">Copy secure pairing link</button>
<a class="secondary" href="{html.escape(manual_link, quote=True)}">Open manual code entry</a></div><p id="copy-status" role="status"></p>
<p><small>{'The QR contains no pairing code; enter the displayed digits after opening the page.' if args.manual_code else 'The QR and copied link contain this single-use code. Share them only with the device you are pairing.'}</small></p></div></div>
</main><script>
const pairingLink={json.dumps(link)};
document.getElementById("copy-link").addEventListener("click",async()=>{{
 let copied=false;try{{await navigator.clipboard.writeText(pairingLink);copied=true}}catch{{
  const area=document.createElement("textarea");area.value=pairingLink;document.body.append(area);area.select();copied=document.execCommand("copy");area.remove()
 }}document.getElementById("copy-status").textContent=copied?"Pairing link copied. Open it on the device you trust.":"Copy failed. Use the QR or manual code instead."
}});
</script></html>"""
    directory = pathlib.Path(tempfile.mkdtemp(prefix="zedlink-pair-", dir=state_dir))
    path = directory / "pair.html"
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as output:
        output.write(page)
    print(f"Private pairing page: {path}")
    print(f"Open it on this workstation. Click to pair this browser, or scan/copy for another device. Expires {expires.strftime('%H:%M UTC')}.")
    if not args.no_open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
