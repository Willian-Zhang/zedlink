#!/usr/bin/env python3
"""Chromium rendering fixture for the production terminal CSS/text renderer.

This verifies rendering only; authenticated transport and native terminal behavior
are covered separately. No hosted build or browser-driver download is required.
"""
import functools
import http.server
import json
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
chromium = shutil.which('chromium') or shutil.which('google-chrome')
if not chromium:
    raise SystemExit('NOT RUN: Chromium is unavailable')
app = (ROOT / 'gateway/web/app.js').read_text()
renderer = app[app.index('function appendTerminalText('):app.index('function renderTerminalSnapshot()')]
rows = '\n'.join([
    '$ ls --color=always',
    '\uf07b builds              \uf07b packaging           \uf48a README.md',
    '\uf07b data                \ue7a8 rust                \U000f0219 build.sh',
    '\uf07b docs                \uf07b tools               \U000f08c6 zedlink.log',
    '$ ',
])
with tempfile.TemporaryDirectory(prefix='zedlink-render-') as directory:
    fixture = Path(directory)
    shutil.copytree(ROOT / 'gateway/web/fonts', fixture / 'fonts')
    shutil.copyfile(ROOT / 'gateway/web/style.css', fixture / 'style.css')
    (fixture / 'index.html').write_text('''<!doctype html><meta charset="utf-8">
<link rel="stylesheet" href="/style.css"><title>Disposable terminal rendering fixture</title>
<div class="terminal-preview" style="width:900px;height:600px"><header>Rendering fixture — synthetic output</header><pre id="output"></pre></div>
<script>''' + renderer + '\nconst output=document.getElementById("output");\nappendTerminalText(output,' + json.dumps(rows) + ''');
output.style.color='#55ff55';
document.fonts.ready.then(() => {
 const glyphs=[...output.querySelectorAll('.terminal-glyph')];
 const sample=document.createElement('span'); sample.textContent='X'.repeat(240); output.append(document.createTextNode('\\n'),sample);
 const row=sample.getBoundingClientRect();
 const metrics=document.createElement('span'); metrics.textContent='X X'; output.append(metrics); const widths=[0,1,2].map(i=>{const range=document.createRange();range.setStart(metrics.firstChild,i);range.setEnd(metrics.firstChild,i+1);return range.getBoundingClientRect().width}); metrics.remove();
 const valid=widths.every(w=>Math.abs(w-widths[0])<0.1) && getComputedStyle(output).whiteSpace==='pre' && row.height < parseFloat(getComputedStyle(output).lineHeight)*1.5 && output.scrollWidth>output.clientWidth && glyphs.length===9 && glyphs.every(g=>g.getBoundingClientRect().width>=5 && g.getBoundingClientRect().width<=10) && document.fonts.check('12px "ZedLink Terminal Icons"','\\uf48a\\ue7a8\\u{f0219}\\u{f08c6}');
 sample.remove(); document.body.dataset.result=valid?'PASS':'FAIL';
});
</script>''')
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args):
            pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), functools.partial(QuietHandler, directory=directory))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        result = subprocess.run([chromium, '--headless', '--no-sandbox', '--disable-gpu',
                                 f'--user-data-dir={fixture / "profile"}', '--window-size=1100,750',
                                 '--virtual-time-budget=6000', '--dump-dom',
                                 '--screenshot=/tmp/zedlink-chromium-terminal.png',
                                 f'http://127.0.0.1:{server.server_port}/'], capture_output=True, text=True, timeout=40)
        assert result.returncode == 0, result.stderr
        assert re.search(r'<body[^>]*data-result="PASS"', result.stdout), result.stdout
        print('PASS: Chromium terminal glyph cells, licensed font loading, native rows without wrapping; screenshot /tmp/zedlink-chromium-terminal.png')
    finally:
        server.shutdown()
        server.server_close()
        thread.join()
