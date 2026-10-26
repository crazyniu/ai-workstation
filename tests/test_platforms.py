"""Architecture selection, clean seed switching and native state preservation."""
import importlib.util
import hashlib
import json
import os
import subprocess
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

def module(name, file):
    spec = importlib.util.spec_from_file_location(name, ROOT/file)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

FETCH = module('fetch_platform_components', 'gateway/scripts/fetch-components.py')
RELEASES = module('platform_releases', 'gateway/app/releases.py')
NATIVE = module('native_install', 'install-native.py')


class ArchitectureTests(unittest.TestCase):
    def test_aliases_and_explicit_unsupported_vendor_platform(self):
        for alias, arch in [('x86', '386'), ('i686', '386'), ('x64', 'amd64'),
                            ('x86_64', 'amd64'), ('aarch64', 'arm64'), ('armhf', 'armv7'),
                            ('armel', 'armv5'), ('mips64le', 'mips64le'), ('riscv64', 'riscv64')]:
            self.assertEqual(RELEASES.architecture(alias), arch)
        with self.assertRaises(ValueError):
            RELEASES.architecture('unknown-vendor-cpu')

    def test_tailscale_network_mode_tracks_deployment_and_preserves_override(self):
        with tempfile.TemporaryDirectory() as folder:
            binary = Path(folder)/'components/current/tailscale/tailscaled'
            binary.parent.mkdir(parents=True)
            binary.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            binary.chmod(0o755)
            for extra, expected in [({}, 'tailscale0'), ({'GATEWAY_MODE': 'false'}, 'userspace-networking'),
                                    ({'GATEWAY_MODE': 'false', 'GATEWAY_TAILSCALE_TUN': 'custom0'}, 'custom0')]:
                env = {k:v for k,v in os.environ.items() if not k.startswith('GATEWAY_')}
                result = subprocess.check_output(['/bin/sh', str(ROOT/'gateway/runtime/service'), 'tailscale'],
                    env=dict(env, DATA_DIR=folder, **extra), text=True)
                self.assertIn('--tun='+expected, result.splitlines())

    def test_switching_architecture_replaces_old_seed_and_failed_fetch_preserves_it(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            seed = root/'seed/mihomo'
            seed.mkdir(parents=True)
            (seed/'version.json').write_text('{"arch":"amd64"}')
            (seed/'mihomo').write_bytes(b'old-amd64')
            pinned = {'component': 'mihomo', 'sha256': 'a'*64, 'version': 'v1', 'url': 'https://official.invalid/arm64'}
            (root/'components.lock.json').write_text(json.dumps({'arch': 'amd64', 'components': {},
                'architectures': {'arm64': {'mihomo': pinned}},
                'filters': {'adguard-dns': {'sha256': hashlib.sha256(b'filter').hexdigest()}}}))
            with patch.object(FETCH, 'install_asset', side_effect=ValueError('download failed')):
                with self.assertRaises(ValueError):
                    FETCH.fetch(root, 'arm64')
            self.assertEqual((seed/'mihomo').read_bytes(), b'old-amd64')
            def install(manifest, dest):
                dest.mkdir()
                (dest/'mihomo').write_bytes(b'new-arm64')
                (dest/'version.json').write_text(json.dumps(manifest))
            (root/'seed/filters').mkdir()
            (root/'seed/filters/adguard-dns.txt').write_bytes(b'filter')
            with patch.object(FETCH, 'install_asset', side_effect=install):
                FETCH.fetch(root, 'arm64')
            self.assertEqual((seed/'mihomo').read_bytes(), b'new-arm64')
            self.assertEqual((root/'seed/architecture').read_text(), 'arm64\n')


class NativeGuardTests(unittest.TestCase):
    def fixture(self, arch='arm64'):
        folder = tempfile.TemporaryDirectory()
        self.addCleanup(folder.cleanup)
        system = Path(folder.name)
        (system/'etc').mkdir()
        (system/'etc/os-release').write_text('ID=debian\nVERSION_ID="13"\n')
        self.enterContext(patch.object(NATIVE.platform, 'system', return_value='Linux'))
        self.enterContext(patch.object(NATIVE.subprocess, 'check_output', return_value=arch+'\n'))
        self.enterContext(patch.object(NATIVE.shutil, 'which', return_value=None))
        self.enterContext(patch.object(NATIVE.pwd, 'getpwnam', side_effect=KeyError))
        self.enterContext(patch.object(NATIVE.pwd, 'getpwuid', side_effect=KeyError))
        self.enterContext(patch.object(NATIVE.grp, 'getgrnam', side_effect=KeyError))
        self.enterContext(patch.object(NATIVE.grp, 'getgrgid', side_effect=KeyError))
        self.enterContext(patch.object(NATIVE.socket, 'socket'))
        return system

    def test_supported_host_preflight_is_read_only(self):
        system = self.fixture()
        before = list(system.rglob('*'))
        self.assertEqual(NATIVE.preflight('all', None, system), 'arm64')
        self.assertEqual(list(system.rglob('*')), before)

    def test_existing_home_or_program_refuses_without_mutation(self):
        for target in ('home/dev', 'opt/workstation', 'var/lib/ai-gateway'):
            with self.subTest(target=target):
                system = self.fixture()
                path = system/target
                path.mkdir(parents=True)
                (path/'keep').write_text('existing')
                with self.assertRaisesRegex(ValueError, 'preserved'):
                    NATIVE.preflight('all', None, system)
                self.assertEqual((path/'keep').read_text(), 'existing')

    def test_32bit_gateway_and_missing_workstation_vendor_releases(self):
        system = self.fixture('i386')
        self.assertEqual(NATIVE.preflight('gateway', None, system), '386')
        with self.assertRaisesRegex(ValueError, 'Codex and Claude'):
            NATIVE.preflight('workstation', None, system)

    def test_private_config_required(self):
        system = self.fixture()
        config = system/'private.env'
        config.write_text('DEV_PASSWORD=root\nVNC_PASSWORD=root\n')
        config.chmod(0o644)
        with self.assertRaisesRegex(ValueError, 'mode 600'):
            NATIVE.preflight('workstation', config, system)
        config.chmod(0o600)
        self.assertEqual(NATIVE.preflight('workstation', config, system), 'arm64')


if __name__ == '__main__':
    unittest.main()
