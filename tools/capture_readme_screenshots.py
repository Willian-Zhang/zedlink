#!/usr/bin/env python3
"""Capture the production browser UI with synthetic data, never a user's workspace.

Requires a built gateway and the same local dependencies as test_gateway_transport.py.
These captures illustrate presentation; they are not native integration evidence.
"""
import json
import os
from pathlib import Path
import socket
import ssl
import subprocess
import tempfile
import time

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from test_gateway_transport import BINARY, ROOT, ProbeFixture, admin, http


def main(record=False):
    output = ROOT / 'assets/screenshots'
    with tempfile.TemporaryDirectory(prefix='zedlink-readme-demo.') as temporary:
        root = Path(temporary)
        root.chmod(0o700)
        project = root / 'zedlink-demo'
        (project / 'src').mkdir(parents=True)
        (project / 'src/main.rs').write_text('''use std::time::Duration;

/// A small, disposable reconnect example for the documentation.
fn retry_delay(attempt: u32) -> Duration {
    let seconds = 2_u64.pow(attempt.min(5));
    Duration::from_secs(seconds)
}

fn main() {
    for attempt in 0..3 {
        println!("Reconnect attempt {}: {:?}", attempt, retry_delay(attempt));
    }
}
''')
        (project / 'README.md').write_text('# ZedLink demo\nA disposable documentation project.\n')
        probe = ProbeFixture(root / 'zedlink.sock')
        probe.subagents = []
        probe.entries = [
            '## User\n\nReview the gateway reconnect flow and explain what happens if my phone disconnects.\n\n',
            '## Assistant\n\n<thinking>\nTracing the connection state and request reconciliation paths.\n</thinking>\n\n'
            '### Your agent keeps working\n\n'
            'The conversation stays in desktop Zed while your phone is disconnected. '
            'When you reconnect, ZedLink refreshes the same exposed thread.\n\n'
            '- **Same conversation:** prompts and responses belong to the desktop thread.\n'
            '- **Review before execution:** pending approvals stay visible.\n'
            '- **Recover safely:** an uncertain request is reconciled before retrying.\n\n'
            'You can also open **Workspace** to browse files, review changes, or use an enabled Zed terminal.\n\n'
        ]
        def presentation(method, params, result):
            if method == 'thread.list':
                for thread in result['threads']:
                    thread['title'] = 'Reconnect review · demo'
            elif method == 'thread.snapshot':
                result['title'] = 'Reconnect review · demo'
            elif method == 'instance.info':
                result['project'] = 'zedlink-demo'
            elif method == 'terminal.list':
                for terminal in result['terminals']:
                    terminal['title'] = 'zedlink-demo · shell'
                    terminal['task'] = None
            elif method == 'terminal.snapshot':
                result['terminal']['title'] = 'zedlink-demo · shell'
                result['terminal']['task'] = None
                result['styled_runs'] = [
                    {'text': 'demo@workstation:~/zedlink-demo$ ', 'foreground': '#6ac79e'},
                    {'text': 'ls\n', 'foreground': '#ededed'},
                    {'text': 'README.md  Cargo.toml  src/\n\n', 'foreground': '#74b4ec'},
                    {'text': 'demo@workstation:~/zedlink-demo$ ', 'foreground': '#6ac79e'},
                    {'text': 'cargo run\n', 'foreground': '#ededed'},
                    {'text': '   Finished dev profile\n', 'foreground': '#6ac79e'},
                    {'text': 'Reconnect attempt 0: 1s\nReconnect attempt 1: 2s\nReconnect attempt 2: 4s\n\n', 'foreground': '#ededed'},
                    {'text': 'demo@workstation:~/zedlink-demo$ ', 'foreground': '#6ac79e'},
                ]
                result['content'] = ''.join(run['text'] for run in result['styled_runs'])
            elif method == 'project.file' and params.get('path') == 'src/main.rs':
                result['content'] = (project / 'src/main.rs').read_text()
            return result
        probe.response_transform = presentation
        cert, key = root / 'cert.pem', root / 'key.pem'
        subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes',
                        '-keyout', str(key), '-out', str(cert), '-days', '1',
                        '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost'],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        key.chmod(0o600)
        with socket.socket() as candidate:
            candidate.bind(('127.0.0.1', 0))
            port = candidate.getsockname()[1]
        state = root / 'state'
        base = f'https://localhost:{port}'
        server = subprocess.Popen([str(BINARY), 'serve', f'127.0.0.1:{port}',
                                   str(cert), str(key), str(probe.path), str(state)],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        browser = None
        video = None
        try:
            context = ssl.create_default_context(cafile=str(cert))
            for _ in range(100):
                try:
                    _, gateway = http(base, context, '/v1/gateway')
                    break
                except OSError:
                    time.sleep(.05)
            else:
                raise RuntimeError('Disposable gateway failed to start')
            options = Options()
            options.add_argument('-headless')
            options.accept_insecure_certs = True  # Disposable localhost certificate only.
            options.set_preference('network.proxy.type', 0)
            browser = webdriver.Firefox(service=Service('/usr/bin/geckodriver'), options=options)
            wait = WebDriverWait(browser, 10)
            browser.set_window_size(1440, 900)
            browser.get(base + '/#gateway=' + gateway['gateway_id'])
            wait.until(lambda d: d.find_element(By.ID, 'gateway-id').text == gateway['gateway_id'])
            browser.find_element(By.ID, 'pair-code').send_keys(admin(state, 'pair-short-code')['code'])
            browser.find_element(By.ID, 'pair-button').click()
            wait.until(lambda d: 'Your agent keeps working' in d.find_element(By.ID, 'transcript-entries').text)
            wait.until(lambda d: d.find_element(By.ID, 'show-actions').is_enabled())
            wait.until(lambda d: 'live updates' in d.find_element(By.ID, 'connection').text)
            browser.save_screenshot(str(output / 'desktop-conversation.png'))
            if record:
                from demo_video import DemoVideo
                video = DemoVideo(ROOT / 'assets/recordings')
                video.scene(browser, 'Continue the same exposed conversation')
                browser.find_element(By.CSS_SELECTOR, '.thinking-block > summary').click()
                video.scene(browser, 'Expand thinking without leaving the conversation')
                browser.find_element(By.CSS_SELECTOR, '.thinking-block > summary').click()
            browser.set_window_size(393, 852)
            time.sleep(.3)
            browser.save_screenshot(str(output / 'mobile-conversation.png'))
            if video:
                video.scene(browser, 'A compact conversation on your phone')
            browser.execute_script("openContextPanel('terminal')")
            wait.until(lambda d: d.find_element(By.ID, 'terminal-output').text)
            browser.save_screenshot(str(output / 'mobile-terminal.png'))
            if video:
                video.scene(browser, 'Terminal output and mobile keyboard controls', 5)
                browser.find_element(By.ID, 'terminal-input').send_keys('cargo test')
                video.scene(browser, 'Review a command before sending it', 3)
                browser.find_element(By.ID, 'terminal-input').clear()
            browser.set_window_size(1440, 900)
            browser.execute_script("openContextPanel('files'); navigateProjectDirectory('src')")
            wait.until(lambda d: d.find_elements(By.CSS_SELECTOR, '#file-list [data-path="src/main.rs"]'))
            browser.find_element(By.CSS_SELECTOR, '#file-list [data-path="src/main.rs"]').click()
            wait.until(lambda d: 'retry_delay' in d.find_element(By.ID, 'file-preview-content').text)
            browser.save_screenshot(str(output / 'file-browser.png'))
            if video:
                video.scene(browser, 'Browse source files and read highlighted code', 5)
            browser.find_element(By.ID, 'close-context').click()
            probe.no_threads = True
            probe.sequence += 1
            browser.execute_script('loadThreads()')
            wait.until(lambda d: d.find_element(By.ID, 'empty-state').is_displayed())
            browser.save_screenshot(str(output / 'no-sessions.png'))
            if video:
                video.scene(browser, 'A clear starting point when no sessions are exposed', 3)
                video.still(output / 'zed-settings.png', 'Configure providers inside patched Zed · isolated profile')
            print('Captured current browser UI with synthetic data; not native integration evidence.')
        finally:
            if video:
                print(f'Encoded {video.close():.0f}s isolated UI walkthrough.')
            if browser:
                browser.quit()
            server.terminate()
            server.wait(timeout=5)
            probe.close()


def capture_native_settings():
    """Run only under a fresh Xvfb display, with a new Zed user-data directory."""
    if not os.environ.get('ZEDLINK_SCREENSHOT_ISOLATED_DISPLAY'):
        raise SystemExit('Use the documented Xvfb command; never capture the active desktop.')
    with tempfile.TemporaryDirectory(prefix='zedlink-settings-demo.') as temporary:
        root = Path(temporary)
        project = root / 'zedlink-demo'
        project.mkdir()
        (project / 'README.md').write_text('# ZedLink demo\nDisposable screenshot project.\n')
        profile = root / 'profile'
        (profile / 'config').mkdir(parents=True)
        (profile / 'config/settings.json').write_text(json.dumps({
            'theme': 'One Dark', 'session': {'trust_all_worktrees': True},
            'zedlink': {'enabled': False, 'start_gateway_on_launch': False,
                        'project_root': str(project), 'state_directory': str(root / 'state'),
                        'connection_id': 'tailscale', 'connection_label': 'Demo workstation',
                        'connection_provider': 'tailscale'},
        }))
        environment = {name: value for name, value in os.environ.items()
                       if not name.startswith('ZEDLINK_') and name not in ('WAYLAND_DISPLAY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')}
        environment['ZED_RELEASE_CHANNEL'] = 'dev'
        environment['ZED_ALLOW_EMULATED_GPU'] = '1'
        with (root / 'zed.log').open('w') as log:
            zed = subprocess.Popen([str(ROOT / 'zed-source/target/debug/zed'),
                                    '--user-data-dir', str(profile), str(project)],
                                   env=environment, stdout=log, stderr=log)
            settings_process = None
            try:
                for _ in range(100):
                    windows = subprocess.run(['xdotool', 'search', '--onlyvisible', '--class', 'dev.zed.Zed'],
                                             capture_output=True, text=True)
                    if windows.returncode == 0:
                        break
                    if zed.poll() is not None:
                        raise RuntimeError('Isolated Zed exited before screenshot')
                    time.sleep(.2)
                else:
                    raise RuntimeError('Isolated Zed window unavailable')
                window = windows.stdout.splitlines()[0]
                subprocess.run(['xdotool', 'windowsize', window, '1280', '960'], check=True)
                subprocess.run(['xdotool', 'windowfocus', window], check=True)
                time.sleep(6)
                settings_process = subprocess.Popen([str(ROOT / 'zed-source/target/debug/zed'),
                    '--user-data-dir', str(profile), 'zed://settings/zedlink.connection_provider'],
                    env=environment, stdout=log, stderr=log)
                time.sleep(6)
                subprocess.run(['import', '-window', 'root',
                                str(ROOT / 'assets/screenshots/zed-settings.png')], check=True)
                print('Captured native settings from new Zed profile and disposable project; bridge/gateway startup disabled.')
            finally:
                if settings_process and settings_process.poll() is None:
                    settings_process.terminate()
                    try:
                        settings_process.wait(timeout=8)
                    except subprocess.TimeoutExpired:
                        settings_process.kill()
                        settings_process.wait()
                zed.terminate()
                try:
                    zed.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    zed.kill()
                    zed.wait()


if __name__ == '__main__':
    import sys
    if '--native-settings' in sys.argv:
        capture_native_settings()
    else:
        main(record='--record' in sys.argv)
