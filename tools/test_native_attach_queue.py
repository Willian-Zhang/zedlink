#!/usr/bin/env python3
"""Exercise remote attach, live project_roots and per-message queue controls in real Zed.

Runs a patched Zed binary in a disposable profile and project. ZED_STATELESS skips the
single-instance handshake, so a running ZedLink of the same channel is left alone (release
builds ignore a runtime ZED_RELEASE_CHANNEL). The model is the deterministic
loopback fixture, not the user's local LLM. SSH waiting is not covered here.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer

import deterministic_model_fixture as model
from test_native_fixture import rpc

ROOT = Path(__file__).resolve().parents[1]


def until(check, timeout=30, message='Native fixture state did not arrive before timeout'):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = check()
        if result:
            return result
        time.sleep(0.2)
    raise AssertionError(message)


def expect_error(socket_path, method, params, code):
    try:
        rpc(socket_path, method, params)
    except RuntimeError as error:
        assert code in str(error), str(error)
    else:
        raise AssertionError(f'{method} unexpectedly succeeded')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--zed', type=Path, default=ROOT / 'zed-source/target/release/zed')
    parser.add_argument('--fixture-parent', type=Path,
                        help='Short disposable parent directory (Unix socket paths are limited to 104 bytes)')
    parser.add_argument('--keep', action='store_true', help='Keep the fixture directory for inspection')
    args = parser.parse_args()
    if sys.platform != 'darwin' and not os.environ.get('DISPLAY') and not os.environ.get('WAYLAND_DISPLAY'):
        raise SystemExit('NOT RUN: a graphical session is required')
    if not args.zed.is_file():
        raise SystemExit(f'NOT RUN: patched Zed binary missing: {args.zed}')
    fixture = Path(tempfile.mkdtemp(prefix='zl-attach-', dir=args.fixture_parent)).resolve()
    first, second, profile, state = (fixture / name for name in ('first', 'second', 'profile', 'state'))
    for directory in (first, second, profile / 'config'):
        directory.mkdir(parents=True)
    state.mkdir(mode=0o700)
    (first / 'README.md').write_text('disposable attach fixture\n')
    (second / 'README.md').write_text('disposable second root\n')
    model.FIXTURE_ROOT = first
    server = ThreadingHTTPServer(('127.0.0.1', 0), model.Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f'http://127.0.0.1:{server.server_port}'
    settings_path = profile / 'config/settings.json'
    settings = {
        'zedlink': {'enabled': True, 'state_directory': str(state), 'project_roots': [str(first)],
                    'start_gateway_on_launch': False, 'allow_session_creation': True,
                    'allow_remote_attach': False},
        'session': {'trust_all_worktrees': True},
        'agent': {'default_model': {'provider': 'openai', 'model': 'zedlink-fixture'},
                  'default_profile': 'write', 'tool_permissions': {'default': 'confirm'}},
        'language_models': {'openai': {'api_url': url + '/v1', 'available_models': [{
            'name': 'zedlink-fixture', 'max_tokens': 131072, 'max_output_tokens': 2048,
            'capabilities': {'chat_completions': True, 'images': False},
        }]}},
    }

    def write_settings():
        settings_path.write_text(json.dumps(settings))

    write_settings()
    environment = {key: value for key, value in os.environ.items()
                   if not key.startswith('ZEDLINK_PROBE_')}
    environment.update({'ZED_RELEASE_CHANNEL': 'dev', 'ZED_STATELESS': '1',
                        'OPENAI_API_KEY': 'disposable-fixture'})
    socket_path = str(state / 'probe/zedlink.sock')
    process = None
    try:
        with (fixture / 'zed.log').open('w') as log:
            process = subprocess.Popen([str(args.zed), '--user-data-dir', str(profile), str(first)],
                                       env=environment, stdout=log, stderr=log)
            until(lambda: Path(socket_path).exists(), timeout=60)

            def ready_info():
                try:
                    return rpc(socket_path, 'instance.info', {})
                except RuntimeError as error:
                    if 'INSTANCE_UNAVAILABLE' in str(error):
                        return None
                    raise
            info = until(ready_info)
            base = {'instance_id': info['instance_id'], 'epoch': info['epoch']}
            capabilities = info['capabilities']
            assert 'thread.attach' not in capabilities and 'thread.attachable' not in capabilities
            assert 'thread.queue.update' in capabilities
            expect_error(socket_path, 'thread.attachable', base, 'UNSUPPORTED_CAPABILITY')
            expect_error(socket_path, 'thread.attach', {**base, 'thread_id': 'x'}, 'UNSUPPORTED_CAPABILITY')
            print('PASS: attach is off by default and refused while off')

            def create(title):
                request_id = str(uuid.uuid4())
                def attempt():
                    try:
                        result = rpc(socket_path, 'thread.create', {**base, 'title': title}, request_id)
                    except RuntimeError as error:
                        # The window's Agent panel may still be loading.
                        if 'INSTANCE_UNAVAILABLE' in str(error):
                            return None
                        raise
                    return result.get('thread_id')
                return until(attempt, timeout=60)
            exposed_id = create('Exposed fixture')
            hidden_id = create('Hidden fixture')
            assert rpc(socket_path, 'thread.unexpose', {**base, 'thread_id': hidden_id})['outcome'] == 'unexposed'
            listed = {thread['thread_id'] for thread in rpc(socket_path, 'thread.list', {})['threads']}
            assert exposed_id in listed and hidden_id not in listed

            settings['zedlink']['allow_remote_attach'] = True
            write_settings()
            until(lambda: 'thread.attach' in rpc(socket_path, 'instance.info', {})['capabilities'],
                  message='allow_remote_attach did not apply live')
            attachable = rpc(socket_path, 'thread.attachable', base)['threads']
            ids = {thread['thread_id'] for thread in attachable}
            assert hidden_id in ids and exposed_id not in ids, ids
            row = next(thread for thread in attachable if thread['thread_id'] == hidden_id)
            assert row['waiting'] is None and row['pending'] is False
            assert row['project_group']['label'] == first.name, row['project_group']
            expect_error(socket_path, 'thread.attach', {**base, 'thread_id': 'no-such-thread'}, 'THREAD_UNAVAILABLE')
            expect_error(socket_path, 'thread.attach', {**base, 'epoch': 'obsolete', 'thread_id': hidden_id},
                         'INSTANCE_UNAVAILABLE')
            assert rpc(socket_path, 'thread.attach', {**base, 'thread_id': hidden_id})['outcome'] == 'attached'
            assert rpc(socket_path, 'thread.attach', {**base, 'thread_id': hidden_id})['outcome'] == 'already_attached'
            listed = {thread['thread_id'] for thread in rpc(socket_path, 'thread.list', {})['threads']}
            assert {exposed_id, hidden_id} <= listed
            assert hidden_id not in {thread['thread_id'] for thread in rpc(socket_path, 'thread.attachable', base)['threads']}
            print('PASS: allow_remote_attach applies live; attachable lists only unexposed threads; attach is idempotent')

            settings['zedlink']['project_roots'] = [str(second)]
            write_settings()
            until(lambda: not rpc(socket_path, 'thread.list', {})['threads'],
                  message='removing the root did not revoke exposure')
            assert rpc(socket_path, 'thread.attachable', base)['threads'] == []
            settings['zedlink']['project_roots'] = [str(first)]
            write_settings()
            until(lambda: len(rpc(socket_path, 'thread.attachable', base)['threads']) >= 2,
                  message='restoring the root did not make threads attachable')
            assert rpc(socket_path, 'thread.list', {})['threads'] == [], 'revoked threads reappeared without consent'
            for thread_id in (exposed_id, hidden_id):
                assert rpc(socket_path, 'thread.attach', {**base, 'thread_id': thread_id})['outcome'] == 'attached'
            assert rpc(socket_path, 'instance.info', {})['instance_id'] == base['instance_id']
            print('PASS: project_roots changes apply live; removal revokes exposure and re-adding needs a new attach')

            identity = {**base, 'thread_id': exposed_id}
            until(lambda: rpc(socket_path, 'thread.snapshot', identity)['status'] == 'Idle', timeout=30)
            rpc(socket_path, 'thread.send', {**identity, 'text': 'ZEDLINK_FIXTURE_BROWSER_STOP long turn'})
            until(lambda: rpc(socket_path, 'thread.snapshot', identity)['status'] == 'Generating', timeout=30)
            first_request, second_request = str(uuid.uuid4()), str(uuid.uuid4())
            queued_first = rpc(socket_path, 'thread.send', {**identity, 'text': 'queued one'}, first_request)
            queued_second = rpc(socket_path, 'thread.send', {**identity, 'text': 'queued two'}, second_request)
            assert queued_first['outcome'] == 'queued' and queued_second['outcome'] == 'queued'
            queue = rpc(socket_path, 'thread.queue', identity)
            assert queue['count'] == 2, queue['count']
            entry_one, entry_two = queue['entries']
            assert entry_one['id'] == queued_first['queue_entry_id'] and entry_one['editable'] and entry_one['remote']
            assert entry_one['text'] == 'queued one' and entry_one['steer'] is False

            def update(entry, action, **extra):
                return rpc(socket_path, 'thread.queue.update',
                           {**identity, 'queue_entry_id': entry['id'], 'action': action, **extra})['outcome']
            marker = 'edited ' + uuid.uuid4().hex
            assert update(entry_one, 'edit', text=marker) == 'updated'
            assert update(entry_one, 'steer', steer=True) == 'updated'
            assert update(entry_one, 'steer', steer=True) == 'updated'
            queue = rpc(socket_path, 'thread.queue', identity)
            assert queue['entries'][0]['text'] == marker and queue['entries'][0]['steer'] is True
            assert update(entry_two, 'remove') == 'removed'
            assert update(entry_two, 'remove') == 'not_queued'
            status = rpc(socket_path, 'request.status', {**base, 'original_request_id': second_request})
            assert status['outcome'] == 'removed', status
            expect_error(socket_path, 'thread.queue.update',
                         {**identity, 'queue_entry_id': entry_one['id'], 'action': 'edit', 'text': '  '}, 'INVALID_REQUEST')
            expect_error(socket_path, 'thread.queue.update',
                         {**identity, 'queue_entry_id': entry_one['id'], 'action': 'explode'}, 'INVALID_REQUEST')
            expect_error(socket_path, 'thread.queue.update',
                         {**base, 'thread_id': 'hidden', 'queue_entry_id': 0, 'action': 'remove'}, 'THREAD_NOT_EXPOSED')
            assert rpc(socket_path, 'thread.snapshot', identity)['status'] == 'Generating'
            assert update(entry_one, 'send_now') == 'sent'
            assert update(entry_one, 'send_now') == 'not_queued'
            assert rpc(socket_path, 'thread.queue', identity)['count'] == 0

            def delivered():
                snapshot = rpc(socket_path, 'thread.snapshot', {**identity, 'tail_entry_count': 16})
                return snapshot['status'] == 'Idle' and marker in json.dumps(snapshot)
            until(delivered, timeout=40, message='Send now did not deliver the edited message')
            snapshot = json.dumps(rpc(socket_path, 'thread.snapshot', {**identity, 'tail_entry_count': 16}))
            assert 'queued two' not in snapshot, 'removed queue entry was sent'
            assert 'queued one' not in snapshot, 'pre-edit text was sent'
            print('PASS: queue edit, set-steer, remove (with request.status), send now interrupting the turn, retries are no-ops')

            # History: let Zed unload idle threads immediately, then connect to one that
            # was unloaded.
            settings['agent']['max_idle_retained_threads'] = 0
            write_settings()
            time.sleep(1)
            hidden = {**base, 'thread_id': hidden_id}

            def idle(params):
                return rpc(socket_path, 'thread.snapshot', params)['status'] == 'Idle'
            history_marker = 'history ' + uuid.uuid4().hex
            rpc(socket_path, 'thread.send', {**hidden, 'text': 'ZEDLINK_FIXTURE_STREAM ' + history_marker})
            until(lambda: history_marker in json.dumps(rpc(socket_path, 'thread.snapshot', {**hidden, 'tail_entry_count': 16}))
                  and idle(hidden), timeout=40)
            # Exposed and idle: the turn just ended, which runs Zed's unload check.
            assert hidden_id in {thread['thread_id'] for thread in rpc(socket_path, 'thread.list', {})['threads']}, \
                'an exposed idle thread was unloaded'
            assert rpc(socket_path, 'thread.unexpose', hidden)['outcome'] == 'unexposed'
            rpc(socket_path, 'thread.send', {**identity, 'text': 'ZEDLINK_FIXTURE_STREAM trigger unload'})
            until(lambda: idle(identity), timeout=40)

            def unloaded_row():
                rows = rpc(socket_path, 'thread.attachable', base)['threads']
                return next((row for row in rows if row['thread_id'] == hidden_id and not row['loaded']), None)
            row = until(unloaded_row, timeout=30, message='the unexposed idle thread was not offered from history')
            assert row['status'] == 'Unloaded' and row['updated_at'] and row['title'] == 'Hidden fixture', row
            assert row['agent']['kind'] == 'zed' and row['project_group']['label'] == first.name, row
            assert exposed_id in {thread['thread_id'] for thread in rpc(socket_path, 'thread.list', {})['threads']}, \
                'the exposed thread was unloaded'
            assert rpc(socket_path, 'thread.attach', hidden)['outcome'] == 'pending'
            until(lambda: hidden_id in {thread['thread_id'] for thread in rpc(socket_path, 'thread.list', {})['threads']},
                  timeout=60, message='the history thread was not exposed after loading')
            assert rpc(socket_path, 'thread.attach', hidden)['outcome'] == 'already_attached'
            until(lambda: history_marker in json.dumps(rpc(socket_path, 'thread.snapshot', {**hidden, 'tail_entry_count': 16})),
                  timeout=30, message='the reloaded thread lost its transcript')
            assert hidden_id not in {row['thread_id'] for row in rpc(socket_path, 'thread.attachable', base)['threads']}
            rpc(socket_path, 'thread.send', {**identity, 'text': 'ZEDLINK_FIXTURE_STREAM trigger unload again'})
            until(lambda: idle(identity), timeout=40)
            time.sleep(1)
            assert hidden_id in {thread['thread_id'] for thread in rpc(socket_path, 'thread.list', {})['threads']}, \
                'the reconnected thread was unloaded while exposed'
            print('PASS: unloaded history threads are listed, load in the background on attach, and exposed threads stay loaded')
    finally:
        if process and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        server.shutdown()
        if args.keep:
            print(f'Fixture kept at {fixture}')
        else:
            shutil.rmtree(fixture, ignore_errors=True)


if __name__ == '__main__':
    main()
