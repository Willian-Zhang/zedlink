#!/usr/bin/env python3
"""Create a one-use ZedLink pairing challenge in a terminal or live browser page."""

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


PAIR_TTL_SECONDS = 300


def admin(binary: pathlib.Path, state_dir: pathlib.Path, method: str) -> dict:
    result = subprocess.run(
        [str(binary), "admin", str(state_dir), method], check=True,
        capture_output=True, text=True,
    )
    return json.loads(result.stdout)


def qr_cells(value: str) -> list[list[bool]]:
    try:
        import qrcode
    except ImportError as error:
        raise SystemExit("Install the local QR helper with: python3 -m pip install qrcode") from error
    qr = qrcode.QRCode(border=4, box_size=8)
    qr.add_data(value)
    qr.make(fit=True)
    return qr.get_matrix()


def qr_svg(value: str) -> str:
    cells = qr_cells(value)
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


def qr_terminal(value: str) -> str:
    """Render a camera-readable QR using explicit terminal background colors."""
    rows = []
    for row in qr_cells(value):
        runs = []
        prior = None
        for black in row:
            if black != prior:
                runs.append("\x1b[40m" if black else "\x1b[47m")
                prior = black
            runs.append("  ")
        runs.append("\x1b[0m")
        rows.append("".join(runs))
    return "\n".join(rows)


def choose_mode(requested: str | None) -> str:
    if requested:
        return requested
    if not os.isatty(0):
        return "browser"
    print("\nHow should ZedLink show this one-use pairing challenge?")
    print("  1. Live browser page with QR and status")
    print("  2. Terminal QR")
    choice = input("Select [1]: ").strip()
    return "terminal" if choice == "2" else "browser"


def validate_challenge(challenge: dict) -> tuple[str, str, str, int]:
    code = challenge.get("code", "")
    pairing_id = challenge.get("pairing_id", "")
    watch_token = challenge.get("watch_token", "")
    expires_seconds = challenge.get("expires_seconds", PAIR_TTL_SECONDS)
    if len(code) != 10 or not code.isdecimal():
        raise SystemExit("gateway returned an invalid short pairing code")
    try:
        uuid.UUID(pairing_id)
    except (ValueError, TypeError) as error:
        raise SystemExit("gateway returned an invalid pairing challenge ID") from error
    if len(watch_token) != 64:
        raise SystemExit("gateway returned an invalid pairing watch token")
    try:
        bytes.fromhex(watch_token)
    except ValueError as error:
        raise SystemExit("gateway returned an invalid pairing watch token") from error
    if not isinstance(expires_seconds, int) or not 1 <= expires_seconds <= PAIR_TTL_SECONDS:
        raise SystemExit("gateway returned an invalid pairing expiration")
    return code, pairing_id, watch_token, expires_seconds


def pairing_page(*, base: str, identity: str, code: str, pairing_id: str,
                 watch_token: str, expires_seconds: int, link: str,
                 manual_link: str, manual_code: bool, expires: datetime) -> str:
    instructions = ("Open the manual page or scan the QR, then enter the code shown here."
                    if manual_code else
                    "Use the button for a new browser, or type the code into an installed home-screen app.")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#000000"><title>Pair a device · ZedLink</title>
<style>
:root{{color-scheme:dark;font-family:Inter,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;--bg:#000;--bar:#030303;--panel:#0d0e10;--raised:#151719;--line:#2b2d30;--strong:#505257;--ink:#f3f3f1;--muted:#a2a5aa;--subtle:#797c82;--online:#79c79b;--warning:#e2bc80;--error:#e4a2a2;background:var(--bg);color:var(--ink)}}
*{{box-sizing:border-box}}html,body{{min-height:100%;margin:0;background:var(--bg);color:var(--ink)}}button{{font:inherit}}a:focus-visible,button:focus-visible{{outline:2px solid #d5e7ff;outline-offset:2px}}
.topbar{{display:flex;align-items:center;justify-content:space-between;gap:16px;min-height:68px;padding:12px clamp(18px,3vw,38px);background:var(--bar);border-bottom:1px solid var(--line)}}
.brand{{display:flex;align-items:center;gap:12px;min-width:0}}.mark{{display:grid;place-items:center;width:32px;height:32px;flex:none;border:1px solid var(--ink);font:italic 21px/1 Georgia,serif}}.brand strong{{display:block;font-size:.78rem;font-weight:760;letter-spacing:.19em;text-transform:uppercase}}.brand small{{display:block;margin-top:3px;color:var(--subtle);font-size:.68rem;letter-spacing:.04em}}
.top-state{{display:flex;align-items:center;gap:9px;color:var(--warning);font-size:.75rem;white-space:nowrap}}.top-state::before{{content:"";width:6px;height:6px;background:var(--warning)}}.top-state[data-state="paired"]{{color:var(--online)}}.top-state[data-state="paired"]::before{{background:var(--online)}}.top-state[data-state="expired"],.top-state[data-state="replaced"]{{color:var(--error)}}.top-state[data-state="expired"]::before,.top-state[data-state="replaced"]::before{{background:var(--error)}}
.shell{{width:min(100%,1080px);margin:0 auto;padding:clamp(38px,7vh,78px) clamp(20px,5vw,56px) max(48px,env(safe-area-inset-bottom))}}
.eyebrow{{margin:0;color:var(--subtle);font:600 .64rem/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.15em;text-transform:uppercase}}h1{{margin:10px 0 12px;font-size:clamp(2.5rem,6vw,4.7rem);font-weight:500;letter-spacing:-.055em;line-height:.98}}.intro{{max-width:680px;margin:0;color:var(--muted);font-size:.95rem;line-height:1.65}}
.pair-grid{{display:grid;grid-template-columns:minmax(270px,380px) minmax(330px,1fr);margin-top:38px;border:1px solid var(--line);background:var(--line);gap:1px}}.qr-pane,.pair-pane{{min-width:0;background:var(--bg);padding:clamp(22px,3vw,32px)}}.qr-pane{{display:flex;flex-direction:column;justify-content:space-between}}.section-title{{margin:7px 0 22px;font-size:1.15rem;font-weight:600;letter-spacing:-.025em}}.qr-frame{{width:100%;max-width:330px;margin:auto;background:#fff;padding:10px}}svg{{display:block;width:100%;height:auto;background:#fff}}.scan-note{{margin:20px 0 0;color:var(--subtle);font-size:.73rem;line-height:1.55}}
.code-label{{margin-bottom:8px}}.code{{font:650 clamp(2rem,5vw,3.25rem)/1.1 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.1em;white-space:nowrap}}.expiry{{margin:9px 0 0;color:var(--subtle);font-size:.73rem}}
#live-status{{display:flex;align-items:center;gap:10px;margin:24px 0 0;padding:14px 0;border-block:1px solid var(--line);color:var(--muted);font-size:.8rem;line-height:1.45}}#live-status::before{{content:"";width:7px;height:7px;flex:none;background:var(--warning)}}#live-status[data-state="paired"]{{color:var(--online)}}#live-status[data-state="paired"]::before{{background:var(--online)}}#live-status[data-state="expired"],#live-status[data-state="replaced"]{{color:var(--error)}}#live-status[data-state="expired"]::before,#live-status[data-state="replaced"]::before{{background:var(--error)}}
.details{{display:grid;margin:18px 0 0;border-top:1px solid var(--line)}}.detail-row{{display:grid;grid-template-columns:110px minmax(0,1fr);gap:14px;padding:10px 0;border-bottom:1px solid var(--line);font-size:.7rem}}.detail-row span{{color:var(--subtle)}}.detail-row code{{color:var(--ink);font:inherit ui-monospace,SFMono-Regular,Menlo,monospace;overflow-wrap:anywhere}}
.actions{{display:grid;grid-template-columns:1fr 1fr;gap:8px;margin-top:20px}}a,button{{display:grid;place-items:center;min-height:46px;padding:10px 14px;border:1px solid var(--strong);border-radius:0;background:transparent;color:var(--ink);font-size:.76rem;font-weight:650;text-align:center;text-decoration:none;cursor:pointer}}a:hover,button:hover{{border-color:var(--ink);background:var(--raised)}}a.primary{{grid-column:1/-1;border-color:var(--ink);background:var(--ink);color:var(--bg)}}a.primary:hover{{background:#fff}}#copy-status{{min-height:1.4em;margin:9px 0 0;color:var(--online);font-size:.7rem}}.secret-note{{display:block;margin-top:13px;color:var(--subtle);font-size:.69rem;line-height:1.5}}
.installed{{display:grid;grid-template-columns:minmax(180px,.55fr) 1fr;gap:24px;margin-top:18px;padding:20px 0;border-block:1px solid var(--line)}}.installed strong{{font-size:.82rem}}.installed p{{margin:0;color:var(--muted);font-size:.76rem;line-height:1.6}}.foot{{display:flex;justify-content:space-between;gap:24px;margin-top:21px;color:var(--subtle);font-size:.68rem;line-height:1.5}}.foot span:last-child{{text-align:right}}
@media(max-width:720px){{.topbar{{padding:calc(10px + env(safe-area-inset-top)) 14px 10px}}.brand small{{display:none}}.top-state{{font-size:.66rem}}.shell{{padding:34px 18px max(38px,env(safe-area-inset-bottom))}}h1{{font-size:2.55rem}}.pair-grid{{grid-template-columns:1fr;margin-top:28px}}.qr-pane,.pair-pane{{padding:22px 18px}}.qr-frame{{max-width:300px}}.code{{font-size:clamp(1.85rem,10vw,2.7rem)}}.actions{{grid-template-columns:1fr}}a.primary{{grid-column:auto}}.installed{{grid-template-columns:1fr;gap:8px}}.foot{{display:block}}.foot span{{display:block;margin-top:7px}}.foot span:last-child{{text-align:left}}}}
</style></head><body>
<header class="topbar"><div class="brand"><span class="mark" aria-hidden="true">Z</span><div><strong>ZedLink</strong><small>Native Agent / remote access</small></div></div><div id="pairing-state" class="top-state" data-state="active">Pairing active</div></header>
<main class="shell"><header><p class="eyebrow">PRIVATE DEVICE PAIRING</p><h1>Connect ZedLink</h1><p class="intro">{html.escape(instructions)} The new device will control only Agent threads explicitly exposed from desktop Zed.</p></header>
<section class="pair-grid" aria-label="Pair a ZedLink device"><article class="qr-pane"><div><p class="eyebrow">SCAN WITH YOUR DEVICE</p><h2 class="section-title">Open the trusted gateway</h2></div><div class="qr-frame">{qr_svg(link)}</div><p class="scan-note">Use the camera on the device you are pairing. Check that it opens the HTTPS address shown here and never continue through a certificate warning.</p></article>
<article class="pair-pane"><p class="eyebrow code-label">ONE-TIME CODE</p><div class="code">{html.escape(code[:5])} {html.escape(code[5:])}</div><p class="expiry">One use · expires {expires.strftime('%H:%M UTC')}</p>
<p id="live-status" data-state="active" role="status" aria-live="polite">Waiting for a trusted device…</p>
<div class="details"><div class="detail-row"><span>HTTPS address</span><code>{html.escape(base)}</code></div><div class="detail-row"><span>Gateway ID</span><code>{html.escape(identity)}</code></div></div>
<div class="actions"><a class="primary" href="{html.escape(link, quote=True)}">Pair this browser</a><button id="copy-link" type="button">Copy pairing link</button><a class="secondary" href="{html.escape(manual_link, quote=True)}">Enter code manually</a></div><p id="copy-status" role="status"></p>
<small class="secret-note">{'The QR contains no pairing code; enter the displayed digits after opening the page.' if manual_code else 'The QR and copied link contain this single-use code. Share them only with the device you are pairing.'}</small></article></section>
<aside class="installed"><strong>Using the iPhone home-screen app?</strong><p>Keep the installed ZedLink app open and type the 10-digit code there. Scanning the QR opens the phone’s default browser instead of an existing home-screen app.</p></aside>
<footer class="foot"><span>Pairing expires automatically and allows at most five attempts.</span><span>Model credentials and Agent execution remain in desktop Zed.</span></footer>
</main><script>
const pairingLink={json.dumps(link)};
const gatewayOrigin={json.dumps(base)};
const pairingId={json.dumps(pairing_id)};
const watchToken={json.dumps(watch_token)};
const initialLifetime={expires_seconds};
const liveStatus=document.getElementById("live-status");
const pairingState=document.getElementById("pairing-state");
let terminal=false;
function statusText(event){{
 if(event.status==="paired")return "Device paired. You can close this page.";
 if(event.status==="expired")return "This pairing code expired. Start Pair a device again.";
 if(event.status==="replaced")return "A newer pairing code replaced this one.";
 if(event.status==="attempt_failed")return `Incorrect code received. ${{event.attempts_remaining}} attempts remain.`;
 const seconds=Number.isFinite(event.expires_seconds)?event.expires_seconds:initialLifetime;
 return `Waiting for a trusted device… ${{seconds}} seconds remaining.`;
}}
function setPairingStatus(event){{
 liveStatus.dataset.state=event.status;liveStatus.textContent=statusText(event);pairingState.dataset.state=event.status;
 pairingState.textContent=event.status==="paired"?"Device paired":event.status==="expired"?"Pairing expired":event.status==="replaced"?"Code replaced":"Pairing active";
 terminal=["paired","expired","replaced"].includes(event.status)
}}
function watchPairing(){{
 if(terminal)return;
 const endpoint=new URL("/v1/pairing-events",gatewayOrigin);endpoint.protocol="wss:";endpoint.searchParams.set("pairing_id",pairingId);
 const socket=new WebSocket(endpoint,["zedlink-pairing-v1",`zedlink-pairing-token-${{watchToken}}`]);
 socket.addEventListener("message",event=>{{try{{setPairingStatus(JSON.parse(event.data))}}catch{{}}}});
 socket.addEventListener("close",()=>{{if(!terminal){{liveStatus.dataset.state="reconnecting";liveStatus.textContent="Live pairing status disconnected. Reconnecting…";pairingState.dataset.state="reconnecting";pairingState.textContent="Reconnecting";setTimeout(watchPairing,1000)}}}});
 socket.addEventListener("error",()=>socket.close());
}}
watchPairing();
document.getElementById("copy-link").addEventListener("click",async()=>{{
 let copied=false;try{{await navigator.clipboard.writeText(pairingLink);copied=true}}catch{{
  const area=document.createElement("textarea");area.value=pairingLink;document.body.append(area);area.select();copied=document.execCommand("copy");area.remove()
 }}document.getElementById("copy-status").textContent=copied?"Pairing link copied. Open it on the device you trust.":"Copy failed. Use the QR or manual code instead."
}});
</script></html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("url", help="trusted HTTPS gateway URL opened by the client browser")
    parser.add_argument("state_dir", type=pathlib.Path, help="private gateway state directory")
    parser.add_argument("--mode", choices=("browser", "terminal"),
                        help="where to show the QR; prompts in an interactive terminal")
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
    challenge = admin(binary, state_dir, "pair-short-code")
    code, pairing_id, watch_token, expires_seconds = validate_challenge(challenge)
    base = f"https://{parsed.netloc}/"
    manual_link = base + "#" + urllib.parse.urlencode({"gateway": identity})
    link = (manual_link if args.manual_code else base + "#" + urllib.parse.urlencode(
        {"v": "1", "gateway": identity, "pair": code}))
    expires = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    mode = choose_mode(args.mode)
    if mode == "terminal":
        print("\nZedLink private device pairing")
        print("Scan this QR from the trusted device:\n")
        print(qr_terminal(link))
        print(f"\nOne-time code: {code[:5]} {code[5:]}")
        print(f"HTTPS address: {base}")
        print(f"Gateway ID: {identity}")
        print(f"Expires: {expires.strftime('%H:%M UTC')} · one use · at most five attempts")
        print("The challenge remains active after this task exits.")
        return

    page = pairing_page(base=base, identity=identity, code=code, pairing_id=pairing_id,
                        watch_token=watch_token, expires_seconds=expires_seconds, link=link,
                        manual_link=manual_link, manual_code=args.manual_code, expires=expires)
    directory = state_dir / "pairing-ui"
    directory.mkdir(mode=0o700, exist_ok=True)
    os.chmod(directory, 0o700)
    descriptor, temporary_name = tempfile.mkstemp(prefix="pair-", suffix=".html", dir=directory)
    temporary = pathlib.Path(temporary_name)
    path = directory / "pair.html"
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as output:
            output.write(page)
        os.chmod(temporary, 0o600)
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()
    print(f"Private pairing page: {path}")
    print(f"Open it on this workstation. Its live status follows this challenge over WSS. Expires {expires.strftime('%H:%M UTC')}.")
    if not args.no_open:
        webbrowser.open(path.as_uri())


if __name__ == "__main__":
    main()
