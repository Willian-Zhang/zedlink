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
            info = rpc(socket_path, 'instance.info', {})
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
                subprocess.run(['python3', str(ROOT / 'tools' / script), '--socket', socket_path,
                                '--fixture-url', url], check=True, timeout=60)
            identity = {**base, 'thread_id': thread_id}
            sentinel = project / 'approval_sentinel.txt'
            for decision in ['deny_once', 'approve_once']:
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
