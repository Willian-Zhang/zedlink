#!/usr/bin/env python3
"""Production mobile layout in Chromium frames; synthetic content, not iOS/WebKit validation."""
import functools
import http.server
import json
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import threading

ROOT = Path(__file__).resolve().parents[1]
chromium = shutil.which('chromium')
if not chromium:
    raise SystemExit('NOT RUN: existing Chromium required')
source = (ROOT / 'gateway/web/app.js').read_text()
viewport = source[source.index('function appViewportHeight('):source.index('window.addEventListener("keydown", (event) => {', source.index('function appViewportHeight('))]
html = (ROOT / 'gateway/web/index.html').read_text()
html = html.replace('<script src="/app.js" defer></script>', '')
html = html.replace('<script src="/ui.js" defer></script>', '')
fixture_script = '''
const UI_BUILD = 'layout-test';
window.addEventListener('error', event => { document.body.dataset.result = 'ERROR: '+event.message; });
const params = new URLSearchParams(location.search);
document.documentElement.style.setProperty('--test-top', params.get('top')+'px');
document.documentElement.style.setProperty('--test-bottom', params.get('bottom')+'px');
document.documentElement.style.fontSize = params.get('font')+'px';
const allocatedHeight = innerHeight;
Object.defineProperty(window, 'innerHeight', {value: allocatedHeight - (params.get('stale') === '0' ? 0 : 80)});
Object.defineProperty(navigator, 'standalone', {value: params.get('installed') !== '0'});
// Physical screen larger than the allocated app viewport reproduces the old sizing bug.
Object.defineProperty(window, 'screen', {value: {height: 1200}});
document.body.className = 'mobile-sessions';
document.getElementById('pair-panel').classList.add('hidden');
document.getElementById('sessions-panel').classList.remove('hidden');
document.getElementById('header-model').textContent = 'Model · Demo model · request failed';
document.getElementById('header-notifications').textContent = 'Notifications · Off';
document.getElementById('connection').textContent = 'Zed · Live';
document.getElementById('thread-list').innerHTML = Array.from({length:8}, (_,i) =>
  '<div class="session-row"><button class="thread-item"><span class="thread-badge">Zed Agent</span><span class="thread-status">Ready</span><strong>Disposable project session '+i+' — long title for viewport testing</strong></button></div>').join('');
'''
verify = '''
setTimeout(() => {
 const sidebar = document.querySelector('.sidebar');
 const tabs = document.querySelector('.mobile-tabs');
 const errors = [];
 const safeTop = Number(params.get('top'));
 const expectedTop = navigator.standalone ? Math.max(16, safeTop) : safeTop;
 if (parseFloat(getComputedStyle(document.querySelector('.topbar')).paddingTop) !== 6 + expectedTop) errors.push('wrong home-screen header clearance');
 if (document.querySelector('.brand').getBoundingClientRect().top < expectedTop) errors.push('brand in obscured top edge');
 if (Math.abs(tabs.getBoundingClientRect().bottom - allocatedHeight) > 1) errors.push('dead space below tabs');
 if (Math.abs(document.body.getBoundingClientRect().height - allocatedHeight) > 1) errors.push('body does not fill allocated viewport');
 if (sidebar.getBoundingClientRect().bottom > tabs.getBoundingClientRect().top + 1) errors.push('sidebar under tabs');
 const actions = document.querySelector('#sessions-panel #refresh').getBoundingClientRect();
 const heading = document.querySelector('#sessions-panel h1').getBoundingClientRect();
 if (actions.right > sidebar.getBoundingClientRect().right - 8 || heading.right > actions.left - 4) errors.push('session header controls overlap');
 if (document.querySelector('.session-search-field').getBoundingClientRect().right > sidebar.getBoundingClientRect().right - 8) errors.push('session search exceeds rail');
 const filters = [...document.querySelectorAll('#session-filters button')].map(button => button.getBoundingClientRect());
 if (filters.some(box => Math.abs(box.top - filters[0].top) > 1)) errors.push('mobile filters stack vertically');
 if (getComputedStyle(document.querySelector('.session-search-field')).borderBottomWidth === '0px') errors.push('session search has no visible focus line');
 if (document.querySelector('.sidebar-project')) errors.push('duplicate project tools occupy session list');
 if (getComputedStyle(document.querySelector('.sidebar-footer')).display !== 'none') errors.push('duplicate navigation occupies session list');
 if (document.querySelectorAll('.mobile-tabs .mobile-tab-icon svg').length !== 3) errors.push('mobile tab icons missing');
 if (allocatedHeight >= 500 && document.querySelector('.thread-item').getBoundingClientRect().top > tabs.getBoundingClientRect().top - 75) errors.push('session list starts below visible area');
 if (document.documentElement.scrollWidth > innerWidth + 1) errors.push('sessions overflow viewport horizontally');
 document.querySelectorAll('.thread-item')[1].scrollIntoView({block:'end'});
 if (document.querySelectorAll('.thread-item')[1].getBoundingClientRect().bottom > tabs.getBoundingClientRect().top) errors.push('recent sessions inaccessible');
 sidebar.scrollTop = sidebar.scrollHeight;
 if (document.querySelector('.sidebar-footer').getBoundingClientRect().bottom > tabs.getBoundingClientRect().top - 4) errors.push('last content obscured');
 for (const page of ['mobile-connections','mobile-settings']) {
  document.body.className = page;
  if (sidebar.getBoundingClientRect().bottom > tabs.getBoundingClientRect().top + 1) errors.push(page+' under tabs');
 }
 document.body.className = 'thread-open';
 document.getElementById('thread-title').textContent = 'Review cross-platform project configuration and improve a very long disposable session title without hiding any words';
 document.getElementById('edit-review').classList.remove('hidden');
 document.getElementById('thread-state').classList.add('working');
 const title = document.getElementById('thread-title');
 const toolbar = document.querySelector('.conversation-toolbar');
 const back = document.getElementById('back-sessions');
 if (title.scrollHeight > title.clientHeight + 1) errors.push('title is line clamped');
 if (title.getBoundingClientRect().top < back.getBoundingClientRect().bottom) errors.push('title overlaps controls');
 if (title.getBoundingClientRect().bottom > toolbar.getBoundingClientRect().bottom) errors.push('title exceeds header');
 const headerActions = ['back-sessions','context-budget','edit-review','thread-search','show-context'].map(id => document.getElementById(id).getBoundingClientRect());
 if (headerActions.some((box, index) => box.left < 0 || box.right > innerWidth + 1 || (index && box.left < headerActions[index-1].right - 1))) errors.push('chat header actions overlap or clip');
 if (toolbar.getBoundingClientRect().top < 0) errors.push('header outside viewport');
 if (getComputedStyle(toolbar).flexShrink !== '0') errors.push('header can shrink');
 if (parseFloat(getComputedStyle(toolbar).paddingTop) !== 8 + expectedTop) errors.push('wrong chat header clearance');

 if (document.querySelector('.workspace').getBoundingClientRect().bottom > allocatedHeight + 1) errors.push('chat exceeds viewport');
 const keyboardHeight = appViewportHeight({height:350, offsetTop:0}, true, true, innerHeight);
 if (keyboardHeight !== Math.min(350,innerHeight)) errors.push('keyboard viewport');
 document.body.className = 'pairing';
 document.getElementById('pair-panel').classList.remove('hidden');
 document.getElementById('sessions-panel').classList.add('hidden');
 document.getElementById('pair-origin').textContent = 'https://private.example.test';
 document.getElementById('gateway-id').textContent = 'private-identity-never-in-report';
 document.getElementById('pair-code').value = '1234567890';
 document.getElementById('device-name').value = 'private-device-name-never-in-report';
 for (const height of [allocatedHeight,350]) {
  document.documentElement.style.setProperty('--app-height',height+'px');
  sidebar.scrollTop = sidebar.scrollHeight;
  const button = document.getElementById('pair-button');
  button.scrollIntoView({block:'end'});
  if (button.getBoundingClientRect().bottom > sidebar.getBoundingClientRect().bottom + 1) errors.push('pair button inaccessible at '+height);
  if (button.getBoundingClientRect().top < sidebar.getBoundingClientRect().top) errors.push('pair button above scroll viewport');
  if (sidebar.getBoundingClientRect().bottom > height + 1) errors.push('pair page exceeds viewport');
 }
 const reportButton = document.querySelector('#pair-panel .layout-report');
 reportButton.click();
 const report = document.querySelector('#pair-panel .layout-report-output');
 if (report.classList.contains('hidden') || !JSON.parse(report.value).bounds.sidebar) errors.push('missing diagnostics');
 if (/private\\.example|private-identity|1234567890|private-device|Disposable project/.test(report.value)) errors.push('diagnostics contain private data');
 document.body.dataset.result = errors.length ? errors.join('; ') : 'PASS';
}, 200);
'''
with tempfile.TemporaryDirectory(prefix='zedlink-mobile-layout-') as directory:
    root = Path(directory)
    css = (ROOT / 'gateway/web/style.css').read_text().replace('env(safe-area-inset-top)', 'var(--test-top, 0px)').replace('env(safe-area-inset-bottom)', 'var(--test-bottom, 0px)')
    (root / 'style.css').write_text(css)
    (root / 'fixture.html').write_text(html.replace('</body>', '<script>'+fixture_script+viewport+verify+'</script></body>'))
    frames = ''.join(f'<iframe width="{width}" height="{height}" src="/fixture.html?top={top}&bottom={bottom}&font={font}"></iframe>'
                     for width,height,top,bottom,font in [(393,760,59,34,16),(393,760,59,34,20),(320,568,20,20,16),(700,360,0,21,16)])
    # Actual supplied iPhone report: 393x793 web viewport, zero safe-area insets.
    frames += ''.join(f'<iframe width="393" height="793" src="/fixture.html?top=0&bottom=0&font=16&stale=0&installed={installed}"></iframe>' for installed in [1,0])
    (root / 'index.html').write_text('<!doctype html>'+frames+'''<script>
setTimeout(() => {
 const results = [...document.querySelectorAll('iframe')].map(f => f.contentDocument.body.dataset.result || 'NO RESULT');
 document.body.dataset.result = results.every(r=>r==='PASS')?'PASS':JSON.stringify(results);
}, 1500);
</script>''')
    class QuietHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args): pass
    server = http.server.ThreadingHTTPServer(('127.0.0.1',0), functools.partial(QuietHandler,directory=directory))
    thread = threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    try:
        result = subprocess.run([chromium,'--headless','--no-sandbox','--disable-gpu',f'--user-data-dir={root / "profile"}',
                                 '--window-size=1100,900','--virtual-time-budget=2500','--dump-dom',
                                 f'http://127.0.0.1:{server.server_port}/'],capture_output=True,text=True,timeout=30)
        assert result.returncode == 0, result.stderr[-1000:]
        marker = re.search(r'<body[^>]*data-result="([^"]*)"',result.stdout)
        assert marker and marker.group(1)=='PASS', marker.group(1) if marker else 'missing layout result'
        print('PASS: mobile navigation, long chat titles, pairing button scrolling with keyboard, private layout report, safe areas, large text and landscape (Chromium fixture only)')
    finally:
        server.shutdown(); server.server_close(); thread.join()
