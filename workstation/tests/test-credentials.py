"""Credential initialization and migration use only isolated files and mocked commands."""
import importlib.util
import io
import os
from pathlib import Path
import runpy
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('entrypoint', ROOT/'runtime/entrypoint.py')
ENTRY = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ENTRY)


class CredentialsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        (self.root/'etc/workstation').mkdir(parents=True)
        self.shadow = self.root/'etc/shadow'
        self.shadow.write_text('dev:!:0:0:99999:7:::\nroot:*:0:0:99999:7:::\n')

    def initialize(self, native=False, env=None):
        with patch.dict(os.environ, env or {}, clear=True), patch.object(ENTRY.subprocess, 'run') as run:
            ENTRY.initialize_passwords(native, self.root)
        return run

    def test_fresh_container_initializes_once_then_preserves_changed_passwords(self):
        run = self.initialize()
        self.assertEqual(run.call_args.kwargs['input'], b'dev:dev\nroot:root\n')
        self.shadow.write_text('dev:$6$changed:0:\nroot:!$6$locked:0:\n')
        self.initialize(env={'DEV_PASSWORD_FILE':'/nonexistent'}).assert_not_called()
        marker = self.root/'etc/workstation/credentials-initialized'
        self.assertEqual(marker.stat().st_mode & 0o777, 0o600)

    def test_locked_distribution_placeholders_are_initialized(self):
        for placeholder in ('!*', '!!*', '!!'):
            with self.subTest(placeholder=placeholder):
                marker = self.root/'etc/workstation/credentials-initialized'
                marker.unlink(missing_ok=True)
                self.shadow.write_text('dev:'+placeholder+':0:\nroot:'+placeholder+':0:\n')
                run = self.initialize()
                self.assertEqual(run.call_args.kwargs['input'], b'dev:dev\nroot:root\n')

    def test_upgrade_without_marker_preserves_existing_and_locked_hashes(self):
        self.shadow.write_text('dev:$6$changed:0:\nroot:!$6$locked:0:\n')
        self.initialize().assert_not_called()

    def test_native_initializes_only_dev_and_never_changes_host_root(self):
        run = self.initialize(True, {'DEV_PASSWORD':'native-fixture'})
        self.assertEqual(run.call_args.kwargs['input'], b'dev:native-fixture\n')

    def test_failed_initialization_is_retryable(self):
        with patch.dict(os.environ, {}, clear=True), patch.object(ENTRY.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'chpasswd')):
            with self.assertRaises(subprocess.CalledProcessError):
                ENTRY.initialize_passwords(False, self.root)
        self.assertFalse((self.root/'etc/workstation/credentials-initialized').exists())

    def test_missing_native_password_refuses_without_marking_initialized(self):
        with self.assertRaises(ValueError):
            self.initialize(True)
        self.assertFalse((self.root/'etc/workstation/credentials-initialized').exists())

    def test_existing_vnc_password_is_preserved_and_missing_password_is_created(self):
        home = self.root/'home/dev'
        for relative in ('Desktop', '.codex', '.config/tigervnc'):
            (home/relative).mkdir(parents=True, exist_ok=True)
        for relative in ('.codex/config.toml', '.claude.json'):
            (home/relative).touch()
        target = home/'.config/tigervnc/passwd'
        target.write_bytes(b'user-selected-password')
        original_path = Path
        def mapped(value):
            return home if str(value) == '/home/dev' else original_path(value)
        for existing in (True, False):
            if not existing:
                target.unlink()
            with patch('pathlib.Path', side_effect=mapped), patch('os.getuid', return_value=1100), patch('sys.stdin', SimpleNamespace(buffer=io.BytesIO(b'fixture\n'))), patch('subprocess.run') as run:
                run.return_value.stdout = b'encoded-fixture'
                runpy.run_path(str(ROOT/'runtime/init-home.py'))
            encodes = [c for c in run.call_args_list if c.args[0][0] == 'tigervncpasswd']
            self.assertEqual(len(encodes), 0 if existing else 1)
            self.assertEqual(target.read_bytes(), b'user-selected-password' if existing else b'encoded-fixture')


if __name__ == '__main__':
    unittest.main()
