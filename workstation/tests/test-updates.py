"""Exercise real update dispatch with simulated installers and no privileged operations."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'desktop/niu.sh'
FUNCTIONS = SCRIPT.read_text().split('\nself=$(readlink', 1)[0]


@unittest.skipIf(os.getuid() == 0, 'Update dispatch requires a non-root desktop account')
class UpdateDispatchTests(unittest.TestCase):
    def invoke(self, target, fail_node=False, installed=True):
        with tempfile.TemporaryDirectory() as folder:
            stubs = r'''
base="$HOME/base"
mkdir -p "$base/mcp" "$base/novnc"
touch "$base/mcp/package.json" "$base/novnc/package.json"
dpkg-query() { echo installed; }
dpkg() { echo amd64; }
node() { :; }; uv() { :; }; codex() { :; }; claude() { :; }; code() { :; }
orca_installed() { INSTALLED; }
update_apt() { echo APT_EXECUTED; }
update_node() { echo NODE_EXECUTED; NODE_RESULT; }
update_uv() { echo UV_EXECUTED; }
update_ai_cli() { echo "CLI_EXECUTED $1"; }
update_mcp() { echo MCP_EXECUTED; }
update_novnc() { echo NOVNC_EXECUTED; }
update_orca() { echo ORCA_EXECUTED; }
update_software "$1" --yes
'''.replace('NODE_RESULT', 'return 7' if fail_node else 'return 0').replace('INSTALLED', 'true' if installed else 'false')
            return subprocess.run(['bash','-c',FUNCTIONS+stubs,'fixture',target], env=dict(os.environ,HOME=folder), capture_output=True,text=True)

    def test_single_orca_does_not_update_other_software(self):
        result = self.invoke('Orca Server')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('ORCA_EXECUTED', result.stdout)
        self.assertNotIn('APT_EXECUTED', result.stdout)
        self.assertIn('Succeeded: Orca Server', result.stdout)

    def test_batch_includes_orca_and_continues_after_individual_failure(self):
        result = self.invoke('all', fail_node=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('ORCA_EXECUTED', result.stdout)
        self.assertIn('MCP_EXECUTED', result.stdout)
        self.assertIn('Could not finish: Node.js and npm', result.stderr)
        self.assertIn('Update succeeded for Orca Server', result.stdout)
        self.assertEqual(result.stdout.count('APT_EXECUTED'), 1)

    def test_uninstalled_orca_is_refused(self):
        result = self.invoke('Orca Server', installed=False)
        self.assertEqual(result.returncode, 1)
        self.assertNotIn('ORCA_EXECUTED', result.stdout)

    def test_orca_restart_failure_restores_previous_release(self):
        with tempfile.TemporaryDirectory() as folder:
            home = Path(folder)
            releases = home/'.local/share/orca-server/releases'
            old = releases/'old'
            new = releases/'orca-server-2-linux-x64'
            for release in (old, new):
                (release/'bin').mkdir(parents=True)
                binary = release/'bin/orca-ide'
                binary.write_text('#!/bin/sh\nexit 0\n')
                binary.chmod(0o755)
            (releases.parent/'current').symlink_to(old)
            script = FUNCTIONS + r"""
require_admin() { :; }
latest_tag() { echo v2; }
uname() { echo x86_64; }
orca_service_state() { echo RUNNING; }
counter=0
sudo() {
    readlink -f "$orca_root/current" >> "$HOME/restarts"
    counter=$((counter+1))
    [[ $counter != 1 ]]
}
update_orca
"""
            result = subprocess.run(['bash','-c',script], env=dict(os.environ,HOME=folder), capture_output=True,text=True)
            self.assertEqual(result.returncode,1,result.stderr)
            self.assertEqual((releases.parent/'current').resolve(),old)
            self.assertEqual((home/'restarts').read_text().splitlines(),[str(new),str(old)])

    def test_permission_failure_precedes_any_package_change(self):
        with tempfile.TemporaryDirectory() as folder:
            command = FUNCTIONS + '\nsudo() { return 1; }; apt_stub() { echo SHOULD_NOT_RUN; }; apt=(apt_stub); run_action update_apt; exit "$action_status"\n'
            result = subprocess.run(['bash','-c',command],env=dict(os.environ,HOME=folder),text=True,capture_output=True)
        self.assertNotEqual(result.returncode,0)
        self.assertNotIn('SHOULD_NOT_RUN',result.stdout)
        self.assertIn('no permissions were changed',result.stderr)


if __name__ == '__main__':
    unittest.main()
