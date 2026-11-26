"""AI installation plan: confirmed country and LAN addresses. Docker is faked."""
import contextlib
import importlib.util
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest import mock


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('ai_install_plan', ROOT / 'scripts' / 'ai-install-plan.py')
plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plan)


def compose_config(role):
    """What `docker compose config` returns: the shell environment wins over .env."""
    env = os.environ.get
    gateway, workstation = env('GATEWAY_ADDRESS', '192.168.1.250'), env('WORKSTATION_ADDRESS', '192.168.1.251')
    services, networks = {}, {}
    if role in ('gateway', 'all'):
        services['gateway'] = {'image': 'ghcr.io/crazyniu/ai-workstation-gateway:latest', 'environment': {
            'GATEWAY_LAN_ADDRESS': f'{gateway}/{env("LAN_PREFIX", "24")}',
            'GATEWAY_LAN_ROUTER': env('LAN_ROUTER', '192.168.1.1'),
            'GATEWAY_BLOCK_DIRECT_CLIENTS': workstation,
            'GATEWAY_LOCALE': env('GATEWAY_LOCALE', 'C.UTF-8'), 'GATEWAY_TIMEZONE': env('GATEWAY_TIMEZONE', 'UTC')}}
    if role in ('workstation', 'all'):
        services['workstation'] = {'image': 'ghcr.io/crazyniu/ai-workstation:latest',
                                   'environment': {key: env(key, '') for key in
                                                   ('WORKSTATION_COUNTRY', 'WORKSTATION_LANGUAGE', 'WORKSTATION_TIMEZONE')},
                                   'networks': {'workstation_lan': {'ipv4_address': workstation}}}
        networks['workstation_lan'] = {'ipam': {'config': [{'subnet': env('LAN_SUBNET', '192.168.1.0/24'), 'gateway': gateway}]}}
    return {'services': services, 'networks': networks}


class AddressConfirmationTests(unittest.TestCase):
    def run_plan(self, role, env, dotenv=''):
        with tempfile.TemporaryDirectory() as folder:
            Path(folder, '.env').write_text(dotenv)
            def docker(*args):
                return 'linux/Ubuntu 24.04' if args[0] == 'info' else json.dumps(compose_config(role))
            clean = {key: value for key, value in os.environ.items()
                     if not key.startswith(('AI_INSTALL_', 'GATEWAY_', 'WORKSTATION_', 'LAN_'))}
            stderr, cwd = io.StringIO(), os.getcwd()
            os.chdir(folder)
            try:
                with mock.patch.dict(os.environ, {**clean, 'AI_INSTALL_COUNTRY': 'TW', **env}, clear=True), \
                        mock.patch.object(plan, 'docker', docker), mock.patch('sys.stdin', io.StringIO()), \
                        contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(stderr):
                    try:
                        plan.main('compose.yaml' if role == 'all' else f'compose.{role}.yaml', role)
                        error = None
                    except SystemExit as exit:
                        error = str(exit.code)
            finally:
                os.chdir(cwd)
            return error, Path(folder, '.env').read_text()

    def addresses(self, gateway='192.168.1.250', workstation='192.168.1.251'):
        return {'AI_INSTALL_GATEWAY_ADDRESS': gateway, 'AI_INSTALL_WORKSTATION_ADDRESS': workstation}

    def test_unconfirmed_addresses_stop_a_non_interactive_install(self):
        error, dotenv = self.run_plan('gateway', {})
        self.assertIn('AI_INSTALL_GATEWAY_ADDRESS', error)
        self.assertIn('192.168.1.250', error)
        self.assertEqual(dotenv, '')

    def test_default_addresses_are_saved_with_the_region(self):
        error, dotenv = self.run_plan('all', self.addresses())
        self.assertIsNone(error)
        self.assertIn('GATEWAY_ADDRESS=192.168.1.250\n', dotenv)
        self.assertIn('WORKSTATION_ADDRESS=192.168.1.251\n', dotenv)
        self.assertIn('WORKSTATION_COUNTRY=TW\n', dotenv)

    def test_custom_addresses_replace_the_defaults_in_env(self):
        lan = 'LAN_SUBNET=10.0.5.0/24\nLAN_ROUTER=10.0.5.1\nGATEWAY_ADDRESS=192.168.1.250\n'
        for role in ('gateway', 'workstation', 'all'):
            with self.subTest(role=role):
                error, dotenv = self.run_plan(role, {**self.addresses('10.0.5.2', '10.0.5.3'),
                                                     'LAN_SUBNET': '10.0.5.0/24', 'LAN_ROUTER': '10.0.5.1'}, lan)
                self.assertIsNone(error)
                self.assertIn('GATEWAY_ADDRESS=10.0.5.2\n', dotenv)
                self.assertIn('WORKSTATION_ADDRESS=10.0.5.3\n', dotenv)
                self.assertNotIn('192.168.1.250', dotenv)

    def test_addresses_outside_the_lan_are_refused(self):
        error, _ = self.run_plan('workstation', self.addresses('10.0.5.2', '10.0.5.3'))
        self.assertIn('LAN_SUBNET', error)
        error, _ = self.run_plan('gateway', self.addresses('10.0.5.2', '10.0.5.3'))
        self.assertIn('LAN_ROUTER', error)

    def test_invalid_equal_or_overridden_addresses_are_refused(self):
        error, _ = self.run_plan('gateway', self.addresses('192.168.1.300'))
        self.assertIn('not an IPv4 address', error)
        error, _ = self.run_plan('gateway', self.addresses('192.168.1.250', '192.168.1.250'))
        self.assertIn('different', error)
        error, _ = self.run_plan('gateway', {**self.addresses(), 'GATEWAY_ADDRESS': '192.168.1.240'})
        self.assertIn('conflict', error)


if __name__ == '__main__':
    unittest.main()
