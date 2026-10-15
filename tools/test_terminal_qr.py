#!/usr/bin/env python3
"""Verify packed terminal QR modules and sizing without a real pairing secret."""
import contextlib
import io
import os
import re
import tempfile
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pair_phone
import zed_task_installer


# Deterministic synthetic identity, never read from a gateway or user profile.
TEST_ID = str(uuid.UUID(int=1, version=4))


def main():
    with patch('builtins.input', side_effect=AssertionError('Default must not prompt in a terminal')):
        assert pair_phone.choose_mode(None) == 'terminal'
        assert pair_phone.choose_mode('terminal') == 'terminal'
    link = ('https://demo.example.ts.net:44679/#v=1&gateway=' +
            TEST_ID + '&pair=1234567890')
    cells = pair_phone.qr_cells(link)
    width = len(cells)
    height = (width + 1) // 2
    color = '\x1b[0;38;2;0;0;0;48;2;255;255;255m'
    raw = pair_phone.qr_terminal(link)
    rows = raw.splitlines()
    assert len(rows) == height
    decoded = []
    modules = {' ': (False, False), '▀': (True, False), '▄': (False, True), '█': (True, True)}
    for row in rows:
        assert row.startswith(color) and row.endswith('\x1b[0m')
        blocks = row[len(color):-len('\x1b[0m')]
        assert len(blocks) == width
        decoded.extend([[modules[block][half] for block in blocks] for half in (0, 1)])
    assert decoded[:width] == cells, 'Terminal output changed the QR modules'
    assert not any(decoded[-1]), 'Odd final module row must pad with white'
    assert all(not value for row in cells[:4] + cells[-4:] for value in row)
    assert all(not value for row in cells for value in row[:4] + row[-4:])
    fitted = pair_phone.qr_terminal(link, columns=width + 9, lines=height + 12)
    assert all(len(re.sub(r'\x1b\[[0-9;]*m', '', row)) < width + 9 for row in fitted.splitlines())
    for columns, lines in [(width, height + 12), (width + 1, height + 11), (20, 10)]:
        try:
            pair_phone.qr_terminal(link, columns=columns, lines=lines)
        except ValueError as error:
            assert 'press Enter' in str(error) and 'columns' in str(error)
        else:
            raise AssertionError('Clipped or wrapped QR allowed')

    # Exercise the actual CLI branch, using a disposable state path and mocked admin.
    with tempfile.TemporaryDirectory(prefix='zedlink-qr-test-') as state_dir:
        with patch.object(pair_phone, 'open_pairing_terminal', return_value=True), \
             patch.object(pair_phone, 'admin') as requests, \
             patch.object(pair_phone, 'open_pairing_window') as browser, \
             contextlib.redirect_stdout(io.StringIO()), \
             patch('sys.argv', ['pair_phone.py', 'https://demo.example.test', state_dir, '--mode', 'terminal']):
            pair_phone.main()
        requests.assert_not_called()  # Only the terminal child creates the challenge.
        browser.assert_not_called()
        replies = [{'gateway_id': TEST_ID},
                   {'code': '1234567890', 'pairing_id': TEST_ID,
                    'watch_token': 'a' * 64, 'expires_seconds': 300}]
        for size, fits in [(os.terminal_size((100, 60)), True), (os.terminal_size((40, 20)), False)]:
            capture = io.StringIO()
            with contextlib.redirect_stdout(capture), patch.object(capture, 'isatty', return_value=True), \
                 patch.object(pair_phone.shutil, 'get_terminal_size', return_value=size), \
                 patch.object(pair_phone, 'admin', side_effect=replies) as requests, \
                 patch.object(pair_phone, 'open_pairing_terminal', return_value=False), \
                 patch.object(pair_phone.sys.stdin, 'isatty', return_value=False), \
                 patch.object(pair_phone, 'open_pairing_window', return_value=True) as browser, \
                 patch('sys.argv', ['pair_phone.py', 'https://demo.example.ts.net:44679', state_dir, '--mode', 'terminal']):
                pair_phone.main()
            output = capture.getvalue()
            assert ('QR does not fit' not in output) == fits
            assert (color in output) == fits
            assert 'One-time code: 12345 67890' in output
            assert requests.call_count == 2, 'Fallback must not create a second challenge'
            browser.assert_not_called()
            assert not (Path(state_dir) / 'pairing-ui/pair.html').exists()
    with patch.object(pair_phone.sys, 'platform', 'linux'), \
         patch.dict(pair_phone.os.environ, {'DISPLAY': ':fixture'}), \
         patch.object(pair_phone.shutil, 'which', return_value='/usr/bin/xterm'), \
         patch.object(pair_phone.subprocess, 'Popen') as launch:
        assert pair_phone.open_pairing_terminal('https://demo.example.test', Path('/tmp/demo-state'), False)
        command = launch.call_args.args[0]
        assert command[:3] == ['/usr/bin/xterm', '-geometry', '90x50']
        assert '--in-terminal-window' in command
        assert command[-3:] == ['--mode', 'terminal', '--in-terminal-window']
    # Check known desktop launchers request a window, without opening a browser.
    page = Path('/tmp/disposable-pairing.html')
    with patch.object(pair_phone.sys, 'platform', 'linux'), \
         patch.object(pair_phone.shutil, 'which', side_effect=lambda name: '/usr/bin/'+name), \
         patch.object(pair_phone.subprocess, 'run', return_value=SimpleNamespace(stdout='firefox-esr.desktop\n')), \
         patch.object(pair_phone.webbrowser.Mozilla, 'open', return_value=True) as launch:
        assert pair_phone.open_pairing_window(page)
        launch.assert_called_once_with(page.as_uri(), new=1)
    with patch.object(pair_phone.sys, 'platform', 'darwin'), \
         patch.object(pair_phone.webbrowser, 'open', return_value=False) as launch:
        assert not pair_phone.open_pairing_window(page)
        launch.assert_called_once_with(page.as_uri(), new=1)
    tasks = {task['label']: task for task in zed_task_installer.zedlink_tasks()}
    assert tasks['ZedLink: Pair a device']['reveal'] == 'never'
    assert tasks['ZedLink: Pair a device']['hide'] == 'on_success'
    assert tasks['ZedLink: Pair in terminal']['reveal'] == 'always'
    print('PASS: compact QR, terminal-only default/fallback, dedicated terminal launch, explicit browser mode and task visibility')


if __name__ == '__main__':
    main()
