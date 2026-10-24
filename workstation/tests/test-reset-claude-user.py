"""Claude identity cleanup only uses isolated temporary HOME fixtures."""
from contextlib import redirect_stdout
import importlib.util
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[1] / 'scripts/reset-claude-user.py'
spec = importlib.util.spec_from_file_location('reset_claude', SCRIPT)
RESET = importlib.util.module_from_spec(spec)
spec.loader.exec_module(RESET)


class ResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.home = Path(self.temp.name).resolve()
        self.config = self.home / '.claude'
        self.config.mkdir()

    def tearDown(self):
        self.temp.cleanup()

    def put(self, name, value):
        path = self.home / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))
        return path

    def invoke(self, apply=False, env=None, running=False, home=None):
        args = [str(SCRIPT), '--home', str(home or self.home)]
        if apply:
            args.append('--apply')
        environment = {k: v for k, v in os.environ.items()
                       if k not in RESET.AUTH_ENV and k != 'CLAUDE_CONFIG_DIR'}
        environment.update(env or {})
        output = io.StringIO()
        with patch.object(sys, 'argv', args), patch.dict(os.environ, environment, clear=True), \
                patch.object(RESET, 'active_claude', return_value=running), redirect_stdout(output):
            RESET.main()
        return output.getvalue()

    def test_preserves_mcp_credentials_plugins_skills_proxy_and_project_files(self):
        account = self.put('.claude.json', {
            'userID': 'fixture-user', 'machineID': 'fixture-machine',
            'oauthAccount': {'email': 'fixture@example.invalid'},
            'mcpServers': {'tool': {'command': 'keep'}}, 'theme': 'dark',
            'projects': {'/repo': {'lastSessionId': 'private', 'mcpServers': {'p': {}},
                                   'enabledMcpjsonServers': ['p']}}})
        credentials = self.put('.claude/.credentials.json', {
            'claudeAiOauth': {'accessToken': 'fixture-secret'},
            'trustedDeviceToken': 'fixture-secret', 'mcpOAuth': {'tool': 'keep'},
            'pluginSecrets': {'x': 'keep'}})
        settings = self.put('.claude/settings.json', {
            'env': {'ANTHROPIC_API_KEY': 'fixture-secret', 'HTTP_PROXY': 'keep',
                    'ANTHROPIC_BASE_URL': 'keep'}, 'apiKeyHelper': 'fixture-helper',
            'permissions': {'allow': ['Read']}})
        retained = [self.put('.claude/plugins/installed_plugins.json', {'keep': True}),
                    self.put('.claude/skills/tool/config.json', {'keep': True}),
                    self.put('actual-project/code.json', {'keep': True})]
        history = self.put('.claude/projects/session.jsonl', {'private': True})
        backup = self.put('.claude/backups/old.json', {'private': True})
        output = self.invoke(apply=True)
        self.assertNotIn('fixture-secret', output)
        self.assertNotIn('fixture@example.invalid', output)
        clean = json.loads(account.read_text())
        self.assertNotIn('userID', clean)
        self.assertNotIn('oauthAccount', clean)
        self.assertEqual(clean['mcpServers'], {'tool': {'command': 'keep'}})
        self.assertEqual(clean['projects']['/repo'], {'mcpServers': {'p': {}},
                                                    'enabledMcpjsonServers': ['p']})
        self.assertEqual(json.loads(credentials.read_text()), {
            'mcpOAuth': {'tool': 'keep'}, 'pluginSecrets': {'x': 'keep'}})
        self.assertEqual(json.loads(settings.read_text())['env'], {
            'HTTP_PROXY': 'keep', 'ANTHROPIC_BASE_URL': 'keep'})
        self.assertTrue(all(path.exists() for path in retained))
        self.assertFalse(history.exists())
        self.assertFalse(backup.exists())

    def test_preview_does_not_modify_account_or_history(self):
        account = self.put('.claude.json', {'userID': 'fixture'})
        history = self.put('.claude/sessions/a.json', {'private': True})
        before = account.read_bytes()
        self.assertIn('PREVIEW', self.invoke())
        self.assertEqual(account.read_bytes(), before)
        self.assertTrue(history.exists())

    def test_invalid_json_prevents_partial_cleanup(self):
        account = self.put('.claude.json', {'userID': 'fixture'})
        history = self.put('.claude/sessions/a.json', {'private': True})
        (self.config / 'settings.json').write_text('{')
        with self.assertRaises(ValueError):
            self.invoke(apply=True)
        self.assertIn('userID', json.loads(account.read_text()))
        self.assertTrue(history.exists())

    def test_symlink_refuses_cleanup(self):
        outside = self.home / 'actual-project'
        outside.mkdir()
        guard = outside / 'keep'
        guard.write_text('keep')
        (self.config / 'projects').symlink_to(outside)
        with self.assertRaises(ValueError):
            self.invoke(apply=True)
        self.assertEqual(guard.read_text(), 'keep')

    def test_shell_edits_only_standalone_auth_assignments(self):
        text = 'export ANTHROPIC_API_KEY="fixture"\nexport HTTP_PROXY="shared"\n'
        self.assertEqual(RESET.clean_shell(text), 'export HTTP_PROXY="shared"\n')
        self.assertEqual(RESET.clean_shell('ANTHROPIC_AUTH_TOKEN="two words" # comment\n'), '')
        for line in ('export ANTHROPIC_API_KEY=$(other-command)\n',
                     'ANTHROPIC_API_KEY=fixture run-other-command\n',
                     'export ANTHROPIC_API_KEY=fixture; keep-this-command\n'):
            with self.subTest(line=line), self.assertRaises(ValueError):
                RESET.clean_shell(line)

    def test_repeated_apply_is_idempotent(self):
        self.put('.claude.json', {'userID': 'old', 'mcpServers': {'keep': {}}})
        self.invoke(apply=True)
        self.assertIn('0 config edits, 0 residue paths', self.invoke(apply=True))

    def test_running_claude_prevents_writes(self):
        account = self.put('.claude.json', {'userID': 'fixture'})
        with self.assertRaisesRegex(ValueError, 'Close all Claude'):
            self.invoke(apply=True, running=True)
        self.assertIn('userID', json.loads(account.read_text()))

    def test_inherited_auth_refuses_without_disclosing_value(self):
        with self.assertRaises(ValueError) as error:
            self.invoke(apply=True, env={'ANTHROPIC_API_KEY': 'fixture-private-value'})
        self.assertIn('ANTHROPIC_API_KEY', str(error.exception))
        self.assertNotIn('fixture-private-value', str(error.exception))

    def test_unsafe_config_or_home_paths_are_refused(self):
        for value in (str(self.home), str(self.config / '../../outside'), 'relative-config'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                self.invoke(apply=True, env={'CLAUDE_CONFIG_DIR': value})
        with self.assertRaises(ValueError):
            self.invoke(apply=True, home=self.home / '..')

    def test_dedicated_custom_config_directory(self):
        self.put('.claude-other/.credentials.json', {'claudeAiOauth': {'token': 'fixture'},
                                                   'mcpOAuth': {'keep': {}}})
        self.invoke(apply=True, env={'CLAUDE_CONFIG_DIR': str(self.home / '.claude-other')})
        self.assertEqual(json.loads((self.home / '.claude-other/.credentials.json').read_text()),
                         {'mcpOAuth': {'keep': {}}})

    @unittest.skipUnless(Path('/proc/self/cmdline').exists(), 'Linux /proc process detection')
    def test_real_running_process_detection(self):
        executable = self.home / 'claude'
        executable.symlink_to('/bin/sleep')
        process = subprocess.Popen([str(executable), '10'])
        try:
            self.assertTrue(RESET.active_claude(os.getuid()))
        finally:
            process.terminate()
            process.wait()


if __name__ == '__main__':
    unittest.main()
