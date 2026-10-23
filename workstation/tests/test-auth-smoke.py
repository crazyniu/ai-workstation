#!/usr/bin/env python3
"""Credential-source regressions for the isolated SSH/VNC authentication checks."""
import importlib.util
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location('workstation_auth_smoke', Path(__file__).with_name('auth-smoke.py'))
AUTH = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(AUTH)


class AuthenticationFixtureTests(unittest.TestCase):
    def test_environment_credential(self):
        with patch.dict(os.environ, {'VNC_PASSWORD': 'fixture'}, clear=True):
            self.assertEqual(AUTH.runtime_secret('VNC_PASSWORD'), 'fixture')

    def test_file_precedes_environment_and_trims_line_ending(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'password'
            path.write_bytes(b'file-fixture\r\n')
            with patch.dict(os.environ, {'DEV_PASSWORD': 'unused-env', 'DEV_PASSWORD_FILE': str(path)}, clear=True):
                self.assertEqual(AUTH.runtime_secret('DEV_PASSWORD'), 'file-fixture')

    def test_missing_credential_fails(self):
        with patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, 'DEV_PASSWORD or DEV_PASSWORD_FILE'):
                AUTH.runtime_secret('DEV_PASSWORD')

    def test_empty_file_does_not_fall_back_to_environment(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'password'
            path.touch()
            with patch.dict(os.environ, {'DEV_PASSWORD': 'unused-env', 'DEV_PASSWORD_FILE': str(path)}, clear=True):
                with self.assertRaises(ValueError):
                    AUTH.runtime_secret('DEV_PASSWORD')

    def check_askpass(self, environment, password):
        def run(command, **options):
            askpass = Path(options['env']['SSH_ASKPASS'])
            self.assertEqual(stat.S_IMODE(askpass.stat().st_mode), 0o700)
            self.assertNotIn(password, askpass.read_text())
            self.assertNotIn(password, '\n'.join(command))
            self.assertEqual(options['env']['WORKSTATION_TEST_SSH_PASSWORD'], password)
            self.assertEqual(options['env']['SSH_ASKPASS_REQUIRE'], 'force')
            self.assertIn('PreferredAuthentications=password', command)
            return SimpleNamespace(stdout=b'WORKSTATION_SSH_AUTH_PASS\n')
        with patch.dict(os.environ, environment, clear=True), patch.object(AUTH.subprocess, 'run', side_effect=run) as called:
            AUTH.ssh_login()
            called.assert_called_once()

    def test_ssh_askpass_uses_environment_without_writing_password(self):
        self.check_askpass({'DEV_PASSWORD': 'env-fixture-sensitive'}, 'env-fixture-sensitive')

    def test_ssh_askpass_supports_file_without_writing_password(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder)/'password'
            path.write_text('file-fixture-sensitive\n')
            self.check_askpass({'DEV_PASSWORD_FILE': str(path)}, 'file-fixture-sensitive')


if __name__ == '__main__':
    unittest.main()
