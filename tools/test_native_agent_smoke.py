#!/usr/bin/env python3
"""Exercise native Zed streaming, cancellation and approvals in an isolated profile.

The model is a deterministic loopback fixture, not the user's local LLM.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer

import deterministic_model_fixture as model
from test_native_fixture import rpc

ROOT = Path(__file__).resolve().parents[1]


def until(check, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.1)
    raise AssertionError('Native fixture state did not arrive before timeout')


def clipboard_browser_round_trip(fixture, socket_path, identity):
    # This function runs only under the opt-in virtual-display clipboard fixture.
    import socket
    import ssl
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.firefox.options import Options
    from selenium.webdriver.firefox.service import Service
    from selenium.webdriver.support.ui import WebDriverWait
    from test_gateway_transport import http, admin
    state = fixture / 'clipboard-gateway'
    state.mkdir(mode=0o700)
    cert, key = fixture / 'clipboard-cert.pem', fixture / 'clipboard-key.pem'
    subprocess.run(['openssl', 'req', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
                    '-subj', '/CN=localhost', '-addext', 'subjectAltName=DNS:localhost',
                    '-keyout', str(key), '-out', str(cert)], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    key.chmod(0o600)
    with socket.socket() as listener:
        listener.bind(('127.0.0.1', 0)); port = listener.getsockname()[1]
    with (fixture / 'clipboard-gateway.log').open('w') as log:
        gateway = subprocess.Popen([str(ROOT / 'gateway/target/debug/zedlink-gateway'), 'serve',
                                    f'127.0.0.1:{port}', str(cert), str(key), socket_path, str(state)],
                                   stdout=log, stderr=log)
        browser = None
        try:
            until(lambda: (state / 'admin.sock').exists())
            context = ssl.create_default_context(cafile=str(cert))
            base = f'https://localhost:{port}'
            status, info = http(base, context, '/v1/gateway')
            assert status == 200
            code = admin(state, 'pair-short-code')['code']
            options = Options(); options.add_argument('-headless'); options.accept_insecure_certs = True
            options.set_preference('network.proxy.type', 0)
            browser = webdriver.Firefox(service=Service('/usr/bin/geckodriver'), options=options)
            browser.set_window_size(393, 852)
            browser.get(base + '/#gateway=' + info['gateway_id'])
            wait = WebDriverWait(browser, 15)
            wait.until(lambda driver: driver.find_element(By.ID, 'gateway-id').text == info['gateway_id'])
            browser.find_element(By.ID, 'pair-code').send_keys(code)
            browser.find_element(By.ID, 'pair-button').click()
            wait.until(lambda driver: driver.find_element(By.ID, 'prompt').is_enabled())
            wait.until(lambda driver: driver.find_element(By.ID, 'show-actions').is_enabled())
            before = rpc(socket_path, 'thread.snapshot', identity)['entries_markdown']
            browser.find_element(By.ID, 'show-actions').click()
            browser.find_element(By.ID, 'action-clipboard').click()
            browser.find_element(By.ID, 'clipboard-read').click()
            wait.until(lambda driver: driver.find_element(By.ID, 'clipboard-text').get_attribute('value') == 'isolated clipboard fixture 🧪')
            preview = browser.find_element(By.ID, 'clipboard-text')
            preview.clear(); preview.send_keys('paired native clipboard round trip')
            browser.find_element(By.ID, 'clipboard-write').click()
            until(lambda: rpc(socket_path, 'clipboard.read', identity)['text'] == 'paired native clipboard round trip')
            browser.find_element(By.ID, 'clipboard-prompt').click()
            assert browser.find_element(By.ID, 'prompt').get_attribute('value') == 'paired native clipboard round trip'
            assert rpc(socket_path, 'thread.snapshot', identity)['entries_markdown'] == before
            print('PASS: paired mobile-width browser → TLS gateway → native Zed clipboard read/write, prompt staged without submission')
        finally:
            if browser is not None: browser.quit()
            gateway.terminate()
            try: gateway.wait(timeout=10)
            except subprocess.TimeoutExpired: gateway.kill(); gateway.wait()


def main():
    if not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        raise SystemExit('NOT RUN: a graphical session is required')
    fixture = Path(tempfile.mkdtemp(prefix='zedlink-native-agent-smoke-'))
    project, profile, probe = (fixture / name for name in ('project', 'profile', 'probe'))
    project.mkdir()
    (project / 'aaa').mkdir()
    for index in range(1005):
        (project / 'aaa' / f'{index:04d}.txt').write_text('bounded listing fixture')
    (project / 'zfolder').mkdir()
    (project / 'zfolder' / 'example.rs').write_text('fn main() { println!("fixture"); }\n')
    (project / '.env').write_text('excluded fixture')
    (fixture / 'outside.txt').write_text('outside exposed root')
    (project / 'escape.txt').symlink_to(fixture / 'outside.txt')
    (profile / 'config').mkdir(parents=True)
    probe.mkdir(mode=0o700)
    model.FIXTURE_ROOT = project
    server = ThreadingHTTPServer(('127.0.0.1', 0), model.Handler)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    url = f'http://127.0.0.1:{server.server_port}'
    (profile / 'config/settings.json').write_text(json.dumps({
        'zedlink': {'allow_session_creation': True, 'allow_approval_decisions': True},
        'session': {'trust_all_worktrees': True},
        'agent': {'default_model': {'provider': 'openai', 'model': 'zedlink-fixture'},
                  'default_profile': 'write', 'tool_permissions': {'default': 'confirm'}},
        'language_models': {'openai': {'api_url': url + '/v1', 'available_models': [{
            'name': 'zedlink-fixture', 'max_tokens': 131072, 'max_output_tokens': 2048,
            'capabilities': {'chat_completions': True, 'images': False},
        }]}},
    }))
    environment = {**os.environ, 'ZED_RELEASE_CHANNEL': 'dev', 'OPENAI_API_KEY': 'disposable-fixture',
                   'ZEDLINK_PROBE_DIR': str(probe), 'ZEDLINK_PROBE_PROJECT_ROOT': str(project)}
    process = None
    try:
        with (fixture / 'zed.log').open('w') as log:
            process = subprocess.Popen([str(ROOT / 'zed-source/target/debug/zed'),
                                        '--user-data-dir', str(profile), str(project)],
                                       env=environment, stdout=log, stderr=log)
            socket_path = str(probe / 'zedlink.sock')
            until(lambda: Path(socket_path).exists())
            def ready_info():
                try: return rpc(socket_path, 'instance.info', {})
                except RuntimeError as error:
                    if 'INSTANCE_UNAVAILABLE' in str(error): return None
                    raise
            info = until(ready_info)
            base = {'instance_id': info['instance_id'], 'epoch': info['epoch']}
            time.sleep(1)
            request_id = str(uuid.uuid4())
            def create():
                nonlocal base
                try:
                    result = rpc(socket_path, 'thread.create', {**base, 'title': 'Disposable agent smoke'}, request_id)
                except RuntimeError as error:
                    if 'INSTANCE_UNAVAILABLE' not in str(error):
                        raise
                    current = rpc(socket_path, 'instance.info', {})
                    base = {'instance_id': current['instance_id'], 'epoch': current['epoch']}
                    return None
                return result.get('thread_id')
            thread_id = until(create)
            identity = {**base, 'thread_id': thread_id}
            if os.environ.get('ZEDLINK_TEST_CLIPBOARD') == '1':
                assert 'clipboard.read' not in rpc(socket_path, 'instance.info', {})['capabilities']
                config_path = profile / 'config/settings.json'
                settings = json.loads(config_path.read_text())
                settings['zedlink']['allow_remote_clipboard'] = True
                config_path.write_text(json.dumps(settings))
                until(lambda: 'clipboard.write' in rpc(socket_path, 'instance.info', {})['capabilities'])
                clipboard_id = str(uuid.uuid4())
                payload = {**identity, 'text': 'isolated clipboard fixture 🧪'}
                written = rpc(socket_path, 'clipboard.write', payload, clipboard_id)
                assert written['outcome'] == 'accepted' and not written['duplicate']
                assert rpc(socket_path, 'clipboard.read', identity)['text'] == payload['text']
                assert rpc(socket_path, 'clipboard.write', payload, clipboard_id)['duplicate']
                for method, params, expected, request_id in [
                    ('clipboard.write', {**identity, 'text': 'different'}, 'REQUEST_ID_CONFLICT', clipboard_id),
                    ('clipboard.write', {**identity, 'text': 'x' * 65537}, 'INVALID_REQUEST', None),
                    ('clipboard.read', {**identity, 'thread_id': 'hidden'}, 'THREAD_NOT_EXPOSED', None),
                    ('clipboard.read', {**identity, 'epoch': 'obsolete'}, 'INSTANCE_UNAVAILABLE', None),
                ]:
                    try: rpc(socket_path, method, params, request_id)
                    except RuntimeError as error: assert expected in str(error), str(error)
                    else: raise AssertionError('Clipboard invalid scope/payload was accepted')
                clipboard_browser_round_trip(fixture, socket_path, identity)
                settings['zedlink']['allow_remote_clipboard'] = False
                config_path.write_text(json.dumps(settings))
                until(lambda: 'clipboard.read' not in rpc(socket_path, 'instance.info', {})['capabilities'])
                try: rpc(socket_path, 'clipboard.read', identity)
                except RuntimeError as error: assert 'UNSUPPORTED_CAPABILITY' in str(error)
                else: raise AssertionError('Disabled clipboard read was accepted')
                print('PASS: isolated native clipboard transfers, opt-in/hot-disable, duplicate/conflict, size and scope rejection')

            root = until(lambda: (result if any(entry['path'] == 'zfolder' for entry in result['entries']) else None)
                         if (result := rpc(socket_path, 'project.directory', {**identity, 'path': ''})) else None)
            assert all('/' not in entry['path'] for entry in root['entries'])
            flat = rpc(socket_path, 'project.files', identity)
            assert flat['truncated'], 'Global fixture listing should exceed the limit'
            folder = rpc(socket_path, 'project.directory', {**identity, 'path': 'zfolder'})
            assert [entry['path'] for entry in folder['entries']] == ['zfolder/example.rs']
            file = rpc(socket_path, 'project.file', {**identity, 'path': 'zfolder/example.rs'})
            assert 'println!' in file['content'] and not file['truncated']
            for path in ['../outside.txt', '.env', 'escape.txt']:
                try:
                    rpc(socket_path, 'project.file', {**identity, 'path': path})
                except RuntimeError:
                    pass
                else:
                    raise AssertionError('Unsafe file access was accepted')
            try:
                rpc(socket_path, 'project.directory', {**identity, 'path': '../'})
            except RuntimeError:
                pass
            else:
                raise AssertionError('Unsafe directory access was accepted')
            print('PASS: native per-folder browsing beyond global limit, file contents and hidden/traversal/symlink exclusions')
            for script in ['test_native_fixture.py', 'test_native_cancel.py']:
                if script == 'test_native_cancel.py':
                    until(lambda: rpc(socket_path, 'thread.snapshot', identity)['status'] == 'Idle', timeout=30)
                subprocess.run(['python3', str(ROOT / 'tools' / script), '--socket', socket_path,
                                '--fixture-url', url], check=True, timeout=60)
            identity = {**base, 'thread_id': thread_id}
            sentinel = project / 'approval_sentinel.txt'
            initial_page = rpc(socket_path, 'thread.snapshot', {**identity, 'tail_entry_count': 16})
            delta_params = {**identity, 'tail_entry_count': 16,
                            'after_sequence': initial_page['last_sequence'],
                            'entry_start_index': initial_page['entry_start_index'],
                            'entry_end_index': initial_page['entry_end_index']}
            unchanged = rpc(socket_path, 'thread.snapshot', delta_params)
            assert unchanged['delta'] and unchanged['entries_markdown'] == []
            stale = rpc(socket_path, 'thread.snapshot', {**delta_params, 'after_sequence': 999999})
            assert not stale['delta']
            for decision in ['deny_once', 'approve_once']:
                before_page = rpc(socket_path, 'thread.snapshot', {**identity, 'tail_entry_count': 16})
                rpc(socket_path, 'thread.send', {**identity, 'text': 'ZEDLINK_FIXTURE_APPROVAL ' + str(uuid.uuid4())})
                def pending():
                    return rpc(socket_path, 'thread.approvals', identity)['approvals']
                approvals = until(pending)
                assert not sentinel.exists(), 'Tool executed before approval'
                approval = approvals[0]
                assert approval['authorization_kind'] == 'permission_grant'
                assert approval['permission_options']['decisions']
                rpc(socket_path, 'approval.respond', {**identity, 'approval_id': approval['approval_id'],
                    'turn_id': approval['turn_id'], 'decision': decision})
                until(lambda: rpc(socket_path, 'thread.snapshot', identity)['status'] == 'Idle')
                delta_page = rpc(socket_path, 'thread.snapshot', {
                    **identity, 'tail_entry_count': 16, 'after_sequence': before_page['last_sequence'],
                    'entry_start_index': before_page['entry_start_index'],
                    'entry_end_index': before_page['entry_end_index']})
                full_page = rpc(socket_path, 'thread.snapshot', {**identity, 'tail_entry_count': 128})
                assert delta_page['delta'] and delta_page['entries_markdown']
                assert delta_page['entry_start_index'] <= before_page['entry_end_index']
                assert delta_page['entries_markdown'][-1] == full_page['entries_markdown'][-1]
                assert sentinel.exists() == (decision == 'approve_once'), 'Native decision was not respected'
            assert sentinel.read_text() == 'approved'
            print('PASS: isolated native Zed stream/replay, cancellation and deny/allow tool authorization')
    finally:
        if process:
            process.terminate()
            try:
                process.wait(timeout=8)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
        server.shutdown()
        server.server_close()
        worker.join()
        shutil.rmtree(fixture)


if __name__ == '__main__':
    main()
