#!/usr/bin/env python3
"""Native slash/skill checks with a disposable project, profile and loopback model.
Run under a fresh Xvfb display; never sends conversation feedback externally.
"""
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import time
import uuid
from http.server import ThreadingHTTPServer

import deterministic_model_fixture as model
from test_native_agent_smoke import until
from test_native_fixture import rpc

ROOT = Path(__file__).resolve().parents[1]


def main():
    if os.environ.get('ZEDLINK_SLASH_ISOLATED_DISPLAY') != '1' or not os.environ.get('DISPLAY'):
        raise SystemExit('NOT RUN: use ZEDLINK_SLASH_ISOLATED_DISPLAY=1 under a new Xvfb display')
    markers = []

    class Handler(model.Handler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers.get('Content-Length', '0')))
            payload = json.loads(raw)
            markers.append('isolated-skill-body-marker' in json.dumps(payload.get('messages', [])))
            self.rfile = io.BytesIO(raw)
            super().do_POST()

    with tempfile.TemporaryDirectory(prefix='zedlink-slash-native-') as directory:
        root = Path(directory)
        project, profile, probe = root / 'Orbit Notes', root / 'profile', root / 'probe'
        skill = project / '.agents/skills/review/SKILL.md'
        skill.parent.mkdir(parents=True)
        skill.write_text('---\nname: review\ndescription: Disposable review skill\n---\n\nisolated-skill-body-marker\n')
        (project / 'README.md').write_text('# Disposable project\n')
        subprocess.run(['git', 'init', '-q', str(project)], check=True)
        (profile / 'config').mkdir(parents=True)
        probe.mkdir(mode=0o700)
        server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        settings = {
            'zedlink': {'allow_session_creation': True, 'start_gateway_on_launch': False},
            'telemetry': {'metrics': False, 'diagnostics': False},
            'session': {'trust_all_worktrees': True},
            'agent': {'enable_feedback': False, 'default_model': {'provider': 'openai', 'model': 'zedlink-fixture'}, 'default_profile': 'write'},
            'language_models': {'openai': {'api_url': f'http://127.0.0.1:{server.server_port}/v1', 'available_models': [
                {'name': 'zedlink-fixture', 'max_tokens': 131072, 'max_output_tokens': 2048,
                 'capabilities': {'chat_completions': True, 'images': False}}]}},
        }
        (profile / 'config/settings.json').write_text(json.dumps(settings))
        environment = {key: value for key, value in os.environ.items() if not key.startswith('ZEDLINK_') and key not in ('WAYLAND_DISPLAY', 'OPENAI_API_KEY', 'ANTHROPIC_API_KEY')}
        environment.update(ZED_RELEASE_CHANNEL='dev', ZED_ALLOW_EMULATED_GPU='1', OPENAI_API_KEY='disposable-fixture',
                           ZEDLINK_PROBE_DIR=str(probe), ZEDLINK_PROBE_PROJECT_ROOT=str(project))
        process = None
        try:
            with (root / 'zed.log').open('w') as log:
                process = subprocess.Popen([str(ROOT / 'zed-source/target/debug/zed'), '--user-data-dir', str(profile), str(project)], env=environment, cwd=ROOT / 'zed-source', stdout=log, stderr=log)
                socket = str(probe / 'zedlink.sock')
                until(lambda: Path(socket).exists())
                info = rpc(socket, 'instance.info', {})
                base = {'instance_id': info['instance_id'], 'epoch': info['epoch']}
                creation = str(uuid.uuid4())
                def create():
                    try:
                        return rpc(socket, 'thread.create', {**base, 'title': 'Isolated slash checks'}, creation).get('thread_id')
                    except RuntimeError as error:
                        if 'INSTANCE_UNAVAILABLE' in str(error): return None
                        raise
                thread = until(create)
                identity = {**base, 'thread_id': thread}
                commands = until(lambda: [row for row in rpc(socket, 'thread.commands', identity)['commands'] if row['category'] == 'skill'])
                scoped = next(row for row in commands if row['name'].endswith(':review'))
                assert 'Orbit Notes' in scoped['name'], 'Fixture must exercise a skill scope containing spaces'
                catalog = rpc(socket, 'thread.commands', identity)['commands']
                assert not any(row['name'] in ('helpful', 'not-helpful') for row in catalog), 'Feedback must remain disabled in this fixture'
                assert any(row['name'] == 'compact' and row['execution'] == 'prompt' for row in catalog)
                request = str(uuid.uuid4())
                params = {**identity, 'text': '/' + scoped['name'] + ' Explain this fixture.'}
                rpc(socket, 'thread.send', params, request)
                until(lambda: any(markers))
                until(lambda: rpc(socket, 'thread.snapshot', identity)['status'] == 'Idle')
                time.sleep(0.5)
                count = len(markers)
                rpc(socket, 'thread.send', params, request)
                time.sleep(0.5)
                assert len(markers) == count, 'Replay must not create another model request'
                subprocess.run(['python3', str(ROOT / 'tools/test_native_browser_commands.py'),
                                '--fixture-socket', socket, '--expected-thread-id', thread, '--command', scoped['name']], check=True)
                settings['zedlink']['allow_session_creation'] = False
                (profile / 'config/settings.json').write_text(json.dumps(settings))
                until(lambda: 'thread.unexpose' not in rpc(socket, 'instance.info', {})['capabilities'])
                assert not any(row['name'] == 'remote-control' for row in rpc(socket, 'thread.commands', identity)['commands'])
                try: rpc(socket, 'thread.send', {**identity, 'text': '/remote-control', 'local_confirmed': True})
                except RuntimeError as error: assert 'UNSUPPORTED_CAPABILITY' in str(error)
                else: raise AssertionError('Local command bypassed the exposure permission')
                settings['zedlink']['allow_session_creation'] = True
                (profile / 'config/settings.json').write_text(json.dumps(settings))
                until(lambda: 'thread.unexpose' in rpc(socket, 'instance.info', {})['capabilities'])
                for params in ({**identity, 'text': '/missing-command'}, {**identity, 'text': '/remote-control'}):
                    try: rpc(socket, 'thread.send', params)
                    except RuntimeError as error: assert 'UNSUPPORTED_CAPABILITY' in str(error) or 'INVALID_REQUEST' in str(error)
                    else: raise AssertionError('Unadvertised or unconfirmed action was accepted')
                assert rpc(socket, 'thread.list', {})['threads'], 'Unconfirmed remote-control must leave exposure intact'
                result = rpc(socket, 'thread.send', {**identity, 'text': '/remote-control', 'local_confirmed': True})
                assert result['outcome'] == 'local_completed'
                assert not rpc(socket, 'thread.list', {})['threads']
                print('PASS: real native scoped skill with spaces, model context marker, request replay, disabled feedback, unknown-command rejection and confirmed stop exposure')
        except Exception:
            # Preserve only this fixture's startup diagnostics; never inspect the active desktop profile.
            diagnostics = root / 'zed.log'
            native_logs = list((profile / 'logs').glob('*.log')) if (profile / 'logs').exists() else []
            text = diagnostics.read_text(errors='replace') + '\n'.join(path.read_text(errors='replace') for path in native_logs)
            Path('/tmp/zedlink-slash-isolated-zed.log').write_text(text)
            raise
        finally:
            if process is not None:
                process.terminate()
                try: process.wait(timeout=10)
                except subprocess.TimeoutExpired: process.kill(); process.wait()
            server.shutdown(); server.server_close(); worker.join(timeout=5)


if __name__ == '__main__':
    main()
