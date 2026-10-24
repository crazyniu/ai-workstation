"""First-deployment guard tests. Every Docker call uses an isolated fake binary."""
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
FAKE_DOCKER = '''#!/bin/sh
set -eu
printf '%s\\n' "$*" >> "$DOCKER_TEST_LOG"
if [ "$1" = compose ]; then shift; fi
if [ "$1" = --env-file ]; then shift 2; fi
if [ "$1" = -f ]; then shift 2; fi
case "$*" in
  'config --quiet')
    [ "$DOCKER_TEST_STATE" != configfail ] || exit 17
    ;;
  'ps --all --quiet')
    case "$DOCKER_TEST_STATE" in
      exists) printf 'running-container-id\\n' ;;
      stopped) printf 'stopped-container-id\\n' ;;
      checkfail) exit 19 ;;
    esac
    ;;
  'pull'|'up -d --wait --wait-timeout 240') ;;
  *) printf 'Unexpected fake Docker command\\n' >&2; exit 98 ;;
esac
'''


class DeploymentGuardTests(unittest.TestCase):
    def run_deploy(self, state, arguments=()):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            shutil.copyfile(ROOT / 'deploy.sh', root / 'deploy.sh')
            (root / '.env.example').write_text('WEB_PASSWORD=do-not-print-this-test-value\n')
            binary = root / 'bin'
            binary.mkdir()
            docker = binary / 'docker'
            docker.write_text(FAKE_DOCKER)
            docker.chmod(0o755)
            log = root / 'docker-calls.txt'
            # Only our fake Docker is reachable; ordinary shell utilities retain PATH.
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ.get('PATH', ''),
                       DOCKER_TEST_STATE=state, DOCKER_TEST_LOG=str(log))
            result = subprocess.run(['/bin/sh', str(root / 'deploy.sh'), *arguments], cwd=root,
                                    env=env, capture_output=True, text=True, timeout=10)
            self.assertNotIn('do-not-print-this-test-value', result.stdout + result.stderr)
            if (root / '.env').exists():
                self.assertEqual((root / '.env').stat().st_mode & 0o777, 0o600)
            calls = log.read_text().splitlines() if log.exists() else []
            return result, calls

    def compose_calls(self, *commands, file='compose.yaml'):
        return ['compose --env-file .env -f '+file+' '+command for command in commands]

    def test_fresh_environment_is_created_after_successful_checks(self):
        result, calls = self.run_deploy('fresh')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(calls, self.compose_calls('config --quiet', 'ps --all --quiet',
                                                  'pull', 'up -d --wait --wait-timeout 240'))

    def test_running_container_blocks_pull_and_recreation(self):
        result, calls = self.run_deploy('exists')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, self.compose_calls('config --quiet', 'ps --all --quiet'))
        self.assertIn('start or restart', result.stderr)
        self.assertIn('export its internal data', result.stderr)

    def test_stopped_container_also_blocks_pull_and_recreation(self):
        result, calls = self.run_deploy('stopped')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, self.compose_calls('config --quiet', 'ps --all --quiet'))
        self.assertIn('including stopped', result.stderr)

    def test_failed_container_inventory_does_not_start_deployment(self):
        result, calls = self.run_deploy('checkfail')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, self.compose_calls('config --quiet', 'ps --all --quiet'))
        self.assertIn('Unable to check', result.stderr)

    def test_invalid_compose_configuration_stops_before_inventory(self):
        result, calls = self.run_deploy('configfail')
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(calls, self.compose_calls('config --quiet'))

    def test_independent_roles_use_their_own_compose_and_existing_data_guard(self):
        for role, file in [('gateway', 'compose.gateway.yaml'),
                           ('workstation', 'compose.workstation.yaml'),
                           ('workstation-bridge', 'workstation/compose.yaml')]:
            for state in ('fresh', 'stopped'):
                with self.subTest(role=role, state=state):
                    result, calls = self.run_deploy(state, [role])
                    commands = ['config --quiet', 'ps --all --quiet']
                    if state == 'fresh':
                        commands += ['pull', 'up -d --wait --wait-timeout 240']
                    self.assertEqual(result.returncode == 0, state == 'fresh')
                    self.assertEqual(calls, self.compose_calls(*commands, file=file))

    def test_unknown_role_and_extra_arguments_are_rejected_before_docker(self):
        for arguments in (['unknown'], ['gateway', 'workstation']):
            result, calls = self.run_deploy('fresh', arguments)
            self.assertEqual(result.returncode, 2)
            self.assertEqual(calls, [])


if __name__ == '__main__':
    unittest.main()
