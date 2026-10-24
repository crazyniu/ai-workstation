#!/usr/bin/env python3
"""Check additive Unity MCP installation against existing user-owned settings."""
import importlib.util
import json
from pathlib import Path
import tempfile
import tomllib
import unittest

SOURCE = Path(__file__).resolve().parents[1] / 'scripts/configure-mcp.py'
SPEC = importlib.util.spec_from_file_location('configure_mcp', SOURCE)
MCP = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MCP)


class McpConfigTests(unittest.TestCase):
    def test_add_unity_only_preserves_existing_config_and_identity(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            original = {'userID': 'fixture-user', 'mcpServers': {'custom': {'command': '/custom/server'}}}
            (home / '.claude.json').write_text(json.dumps(original))
            (home / '.codex').mkdir()
            codex = 'model = "fixture-model"\n[mcp_servers.custom]\ncommand = "/custom/server"\n'
            (home / '.codex/config.toml').write_text(codex)
            MCP.configure(home, ['unity'])
            value = json.loads((home / '.claude.json').read_text())
            self.assertEqual(value['userID'], original['userID'])
            self.assertEqual(value['mcpServers']['custom'], original['mcpServers']['custom'])
            self.assertEqual(set(value['mcpServers']), {'custom', 'unity'})
            self.assertEqual(value['mcpServers']['unity']['command'], '/usr/local/bin/unity-mcp')
            self.assertEqual(value['mcpServers']['unity']['type'], 'stdio')
            value = tomllib.loads((home / '.codex/config.toml').read_text())
            self.assertEqual(value['model'], 'fixture-model')
            self.assertEqual(set(value['mcp_servers']), {'custom', 'unity'})
            self.assertEqual(value['mcp_servers']['custom']['command'], '/custom/server')

    def test_repeated_install_preserves_user_unity_override_byte_for_byte(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            original = {'mcpServers': {'unity': {'type': 'http', 'url': 'http://127.0.0.1:8123/mcp'}}}
            claude = home / '.claude.json'
            claude.write_text(json.dumps(original))
            (home / '.codex').mkdir()
            codex = home / '.codex/config.toml'
            codex.write_text('[mcp_servers.unity]\nurl = "http://127.0.0.1:8123/mcp"\n')
            before = (claude.read_bytes(), codex.read_bytes())
            MCP.configure(home, ['unity'])
            MCP.configure(home, ['unity'])
            self.assertEqual((claude.read_bytes(), codex.read_bytes()), before)

    def test_fresh_home_has_all_six_servers_and_private_file_permissions(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            MCP.configure(home)
            claude = home / '.claude.json'
            codex = home / '.codex/config.toml'
            self.assertEqual(set(json.loads(claude.read_text())['mcpServers']), set(MCP.servers()))
            self.assertEqual(set(tomllib.loads(codex.read_text())['mcp_servers']), set(MCP.servers()))
            self.assertEqual(claude.stat().st_mode & 0o777, 0o600)
            self.assertEqual(codex.stat().st_mode & 0o777, 0o600)
            before = (claude.read_bytes(), codex.read_bytes())
            MCP.configure(home)
            self.assertEqual((claude.read_bytes(), codex.read_bytes()), before)


if __name__ == '__main__':
    unittest.main()
