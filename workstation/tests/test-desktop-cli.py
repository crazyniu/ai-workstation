#!/usr/bin/env python3
"""Regress desktop HOME, interactive TTY, proxy defaults, and safe error logs."""
from contextlib import redirect_stderr
import importlib.util
import io
import json
import os
from pathlib import Path
import stat
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1]/'runtime/desktop-cli.py'
SPEC = importlib.util.spec_from_file_location('desktop_cli', SOURCE)
CLI = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(CLI)


class DesktopCliTests(unittest.TestCase):
    def setUp(self):
        self.folder = tempfile.TemporaryDirectory()
        self.addCleanup(self.folder.cleanup)
        self.home = Path(self.folder.name)
        self.account = SimpleNamespace(pw_dir=str(self.home), pw_name='desktop-fixture')

    def launch(self, tool='codex', arguments=(), environment=None, run=None):
        with patch.object(CLI.os, 'getuid', return_value=1100), patch.object(CLI.pwd, 'getpwuid', return_value=self.account), \
             patch.dict(os.environ, environment or {}, clear=True), patch.object(CLI, 'with_proxy_file', side_effect=lambda env: env), \
             patch.object(CLI.subprocess, 'run', side_effect=run) as process, redirect_stderr(io.StringIO()) as output:
            code = CLI.launch(tool, arguments)
        return code, process, output.getvalue()

    def test_real_account_home_and_interactive_stdio_preserved(self):
        def run(command, **options):
            self.assertEqual(command, ['/usr/local/bin/codex', '--version'])
            self.assertEqual(options['env']['HOME'], str(self.home))
            self.assertEqual(options['env']['USER'], 'desktop-fixture')
            self.assertEqual(options['env']['LOGNAME'], 'desktop-fixture')
            self.assertEqual(options['env']['HTTPS_PROXY'], 'http://fixture.invalid:1234')
            self.assertEqual(options['cwd'], self.home/'Projects')
            self.assertFalse(set(options) & {'stdin', 'stdout', 'stderr', 'capture_output'})
            return SimpleNamespace(returncode=0)
        code, process, _ = self.launch(arguments=['--version'], environment={'HOME': '/root', 'HTTPS_PROXY': 'http://fixture.invalid:1234'}, run=run)
        self.assertEqual(code, 0)
        process.assert_called_once()
        self.assertFalse((self.home/'.local/state/workstation/launcher-errors.jsonl').exists())

    def test_failed_cli_keeps_only_safe_metadata(self):
        secret = 'fixture-secret-do-not-log'
        code, _, output = self.launch('claude', [secret], {'HTTPS_PROXY': 'http://user:'+secret+'@fixture.invalid:1234', 'ANTHROPIC_API_KEY': secret},
                                      run=lambda *args, **kwargs: SimpleNamespace(returncode=1))
        self.assertEqual(code, 1)
        log = self.home/'.local/state/workstation/launcher-errors.jsonl'
        text = log.read_text()
        self.assertNotIn(secret, text + output)
        event = json.loads(text)
        self.assertEqual(event['exit_code'], 1)
        self.assertEqual(event['tool'], 'claude')
        self.assertTrue(event['proxy_present']['HTTPS_PROXY'])
        self.assertEqual(stat.S_IMODE(log.stat().st_mode), 0o600)
        self.assertEqual(stat.S_IMODE(log.parent.stat().st_mode), 0o700)
        self.assertIn('退出碼 1', output)

    def test_startup_exception_does_not_log_raw_error(self):
        def run(*args, **kwargs):
            raise FileNotFoundError('sensitive-error-detail')
        code, _, output = self.launch(run=run)
        text = (self.home/'.local/state/workstation/launcher-errors.jsonl').read_text()
        self.assertEqual(code, 127)
        self.assertIn('FileNotFoundError', text)
        self.assertNotIn('sensitive-error-detail', text + output)

    def test_root_refused_before_process_or_home_writes(self):
        with patch.object(CLI.os, 'getuid', return_value=0), patch.object(CLI.subprocess, 'run') as process, redirect_stderr(io.StringIO()):
            self.assertEqual(CLI.launch('codex'), 1)
            process.assert_not_called()
        self.assertEqual(list(self.home.iterdir()), [])

    def test_proxy_file_allowlist_quotes_and_environment_precedence(self):
        proxy = self.home/'proxy.env'
        proxy.write_text('# comment\nHTTP_PROXY=http://default.invalid:1234\nHTTPS_PROXY="http://default.invalid:5678"\nexport NO_PROXY=localhost,127.0.0.1\nhttp_proxy=ignored-default\nHOME=/root\nOPENAI_API_KEY=do-not-import\nnot a valid line\n')
        result = CLI.with_proxy_file({'HTTP_PROXY': 'explicit-env', 'http_proxy': ''}, proxy)
        self.assertEqual(result, {'HTTP_PROXY': 'explicit-env', 'http_proxy': '', 'HTTPS_PROXY': 'http://default.invalid:5678', 'NO_PROXY': 'localhost,127.0.0.1'})

    def test_proxy_file_is_reloaded_without_shell_execution(self):
        proxy = self.home/'proxy.env'
        marker = self.home/'must-not-exist'
        proxy.write_text('ALL_PROXY=$(touch '+str(marker)+')\n')
        self.assertEqual(CLI.with_proxy_file({}, proxy)['ALL_PROXY'], '$(touch '+str(marker)+')')
        self.assertFalse(marker.exists())
        proxy.write_text('ALL_PROXY=socks5h://updated.invalid:1234\n')
        self.assertEqual(CLI.with_proxy_file({}, proxy)['ALL_PROXY'], 'socks5h://updated.invalid:1234')

    def test_missing_proxy_file_is_optional(self):
        self.assertEqual(CLI.with_proxy_file({'HOME': 'fixture'}, self.home/'missing.env'), {'HOME': 'fixture'})

    def test_desktop_entries_hold_terminal_and_delegate_home(self):
        desktop = SOURCE.parents[1]/'desktop/home-template/Desktop'
        for tool in ('codex', 'claude'):
            text = (desktop/(tool+'.desktop')).read_text()
            self.assertIn('--hold', text)
            self.assertIn('/etc/workstation/desktop-cli.py '+tool, text)
            self.assertNotIn('--working-directory=/home/dev', text)


if __name__ == '__main__':
    unittest.main()
