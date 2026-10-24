#!/usr/bin/env python3
import importlib.util
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('desktop_guard', ROOT / 'runtime/desktop-guard.py')
GUARD = importlib.util.module_from_spec(spec)
spec.loader.exec_module(GUARD)


class DesktopGuardTests(unittest.TestCase):
    def test_only_current_user_and_display_are_detected(self):
        with tempfile.TemporaryDirectory() as folder:
            proc = Path(folder)
            for pid, name, display in [(1, 'xfce4-session', ':1'), (2, 'xfwm4', ':2'),
                                       (3, 'xfce4-panel', ':1'), (4, 'unrelated', ':1')]:
                path = proc / str(pid)
                path.mkdir()
                (path / 'comm').write_text(name + '\n')
                (path / 'environ').write_bytes(f'DISPLAY={display}\0LANG=en_US.UTF-8\0'.encode())
            (proc / 'vanished').mkdir()
            (proc / '5').mkdir()  # A process can disappear between /proc reads.
            with patch.dict(os.environ, {'DISPLAY': ':1'}):
                self.assertEqual(set(GUARD.processes(proc)), {'xfce4-session', 'xfce4-panel'})
                with patch.object(GUARD.os, 'getuid', return_value=os.getuid() + 1):
                    self.assertEqual(GUARD.processes(proc), {})

    def run_guard(self, snapshots, times, start=None):
        child = Mock()
        child.poll.return_value = 0
        with patch.object(GUARD, 'processes', side_effect=snapshots), \
             patch.object(GUARD.time, 'monotonic', side_effect=times), \
             patch.object(GUARD.time, 'sleep', side_effect=[None] * (len(times) - 1) + [StopIteration]), \
             patch.object(GUARD.subprocess, 'Popen', side_effect=start, return_value=child) as popen, \
             patch.object(GUARD.Path, 'exists', return_value=True), \
             patch('builtins.print'):
            with self.assertRaises(StopIteration):
                GUARD.main()
        return popen

    def test_waits_for_session_and_preserves_existing_components(self):
        current = {'xfce4-session': [(1, {'DISPLAY': ':1'})],
                   'xfwm4': [(2, {})], 'xfce4-panel': [(3, {})]}
        popen = self.run_guard([{}, current, current], [0, 2, 8])
        popen.assert_not_called()

    def test_retries_are_bounded_and_use_the_session_environment(self):
        current = {'xfce4-session': [(12, {'DISPLAY': ':1', 'LANG': 'zh_TW.UTF-8'})]}
        popen = self.run_guard([current] * 5, [0, 6, 8, 12, 16])
        self.assertEqual(popen.call_count, 4)  # Both missing; attempts at 6s and 16s.
        self.assertEqual(popen.call_args_list[0].args[0], ['xfwm4', '--compositor=off'])
        env = popen.call_args_list[0].kwargs['env']
        self.assertEqual(env['LANG'], 'zh_TW.UTF-8')
        self.assertIn('/tmp/.ICE-unix/12', env['SESSION_MANAGER'])

    def test_new_session_gets_a_new_startup_grace_period(self):
        old = {'xfce4-session': [(12, {'DISPLAY': ':1'})]}
        new = {'xfce4-session': [(30, {'DISPLAY': ':1'})]}
        popen = self.run_guard([old, old, {}, new, new, new], [0, 6, 8, 10, 12, 16])
        self.assertEqual(popen.call_count, 4)
        self.assertIn('/tmp/.ICE-unix/30', popen.call_args.kwargs['env']['SESSION_MANAGER'])

    def test_launch_errors_do_not_disable_recovery(self):
        current = {'xfce4-session': [(12, {'DISPLAY': ':1'})]}
        popen = self.run_guard([current] * 3, [0, 6, 16], OSError('not available'))
        self.assertEqual(popen.call_count, 4)

    def test_healthcheck_rejects_a_missing_or_zombie_window_manager(self):
        for wm in ('', 'xfwm4 Z\n'):
            connection = Mock()
            connection.__enter__ = Mock(return_value=connection)
            connection.__exit__ = Mock(return_value=False)
            connection.recv.side_effect = [b'SSH-2.0-fixture', b'RFB 003.008\n']
            states = 'xfce4-session S\nxfdesktop Sl\nxfce4-panel Sl\n' + wm
            with self.subTest(wm=wm), \
                 patch('socket.create_connection', return_value=connection), \
                 patch('pathlib.Path.exists', return_value=True), \
                 patch('subprocess.check_output', return_value=states):
                with self.assertRaisesRegex(AssertionError, 'xfwm4 is not running'):
                    runpy.run_path(str(ROOT / 'runtime/healthcheck.py'))


if __name__ == '__main__':
    unittest.main()
