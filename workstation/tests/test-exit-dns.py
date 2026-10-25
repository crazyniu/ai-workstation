"""Resolver identity, release integrity, and opt-in installation boundaries."""
import configparser
import ctypes.util
import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('exit_dns', ROOT / 'workstation/scripts/configure-exit-dns.py')
dns = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dns)


class ResolverTests(unittest.TestCase):
    def test_only_literal_ip_https_upstreams_and_no_dns_fallback(self):
        config = dns.configuration('192.0.2.51', '192.0.2.50', 5354, 'test-hash')
        self.assertEqual(config['dns']['upstream_dns'],
                         ['https://1.1.1.1/dns-query', 'https://8.8.8.8/dns-query'])
        self.assertEqual(config['dns']['bootstrap_dns'], [])
        self.assertEqual(config['dns']['fallback_dns'], [])
        self.assertFalse(config['dns']['use_private_ptr_resolvers'])
        self.assertFalse(config['dns']['use_http3_upstreams'])
        self.assertEqual(config['dns']['allowed_clients'], ['192.0.2.50/32', '127.0.0.1/32'])
        self.assertEqual(config['http']['address'], '127.0.0.1:3001')
        self.assertEqual(config['users'][0]['password'], 'test-hash')
        self.assertFalse(config['querylog']['enabled'])
        self.assertFalse(config['filtering']['protection_enabled'])

    def test_invalid_addresses_and_ports_fail_before_installation(self):
        for source, gateway, port in [('127.0.0.1', '192.0.2.50', 5354),
                                     ('192.0.2.51', '192.0.2.51', 5354),
                                     ('::1', '192.0.2.50', 5354),
                                     ('192.0.2.51', '0.0.0.0', 5354),
                                     ('192.0.2.51', '192.0.2.50', 53)]:
            with self.subTest(source=source, gateway=gateway, port=port):
                with self.assertRaises(ValueError):
                    dns.configuration(source, gateway, port, 'hash')

    def archive(self, symlink=False):
        stream = io.BytesIO()
        with tarfile.open(fileobj=stream, mode='w:gz') as tar:
            for name, body in [('AdGuardHome', b'public executable'), ('LICENSE.txt', b'GPL fixture')]:
                member = tarfile.TarInfo('./AdGuardHome/' + name)
                if symlink and name == 'AdGuardHome':
                    member.type = tarfile.SYMTYPE
                    member.linkname = '/etc/shadow'
                    tar.addfile(member)
                else:
                    member.size = len(body)
                    tar.addfile(member, io.BytesIO(body))
        return stream.getvalue()

    def test_release_archive_and_executable_are_both_verified(self):
        archive = self.archive()
        with patch.object(dns, 'ARCHIVE_SHA256', hashlib.sha256(archive).hexdigest()), \
             patch.object(dns, 'BINARY_SHA256', hashlib.sha256(b'public executable').hexdigest()):
            self.assertEqual(dns.verified_artifacts(archive)['LICENSE.txt'], b'GPL fixture')
            with self.assertRaisesRegex(ValueError, 'archive SHA256'):
                dns.verified_artifacts(archive + b'corrupt')
        with patch.object(dns, 'ARCHIVE_SHA256', hashlib.sha256(archive).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'executable SHA256'):
                dns.verified_artifacts(archive)

    def test_archive_cannot_install_a_symlink(self):
        archive = self.archive(symlink=True)
        with patch.object(dns, 'ARCHIVE_SHA256', hashlib.sha256(archive).hexdigest()):
            with self.assertRaisesRegex(ValueError, 'release member'):
                dns.verified_artifacts(archive)

    def test_existing_state_blocks_all_install_commands_and_downloads(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            program, data, service = root / 'program', root / 'data', root / 'service'
            program.mkdir()
            (program / 'keep').write_text('existing data')
            with patch.object(dns, 'PROGRAM', program), patch.object(dns, 'DATA', data), \
                 patch.object(dns, 'SERVICE', service), patch.object(dns.os, 'getuid', return_value=0), \
                 patch.object(dns.platform, 'system', return_value='Linux'), \
                 patch.object(dns.platform, 'machine', return_value='x86_64'), \
                 patch.object(dns.subprocess, 'run') as run, \
                 patch.object(dns.urllib.request, 'urlopen') as download:
                with self.assertRaisesRegex(ValueError, 'Existing resolver'):
                    dns.install('192.0.2.51', '192.0.2.50', 5354)
                run.assert_not_called()
                download.assert_not_called()
                self.assertEqual((program / 'keep').read_text(), 'existing data')
                self.assertFalse(data.exists())

    def test_supervisor_control_is_root_only_and_service_is_unprivileged(self):
        config = configparser.RawConfigParser()
        config.read(ROOT / 'workstation/runtime/supervisord.conf')
        self.assertEqual(config['unix_http_server']['chmod'], '0600')
        self.assertEqual(config['include']['files'], '/etc/supervisor/conf.d/*.conf')
        service = configparser.RawConfigParser()
        service.read_string(dns.supervisor_configuration())
        self.assertEqual(service['program:workstation-exit-dns']['user'], 'nobody')
        self.assertEqual(service['program:workstation-exit-dns']['autorestart'], 'true')

    @unittest.skipUnless(ctypes.util.find_library('crypt'), 'Linux libcrypt required')
    def test_runtime_management_hashes_are_valid_and_unique(self):
        first, second = dns.password_hash(), dns.password_hash()
        self.assertRegex(first, r'^\$2b\$12\$.{53}$')
        self.assertNotEqual(first, second)


if __name__ == '__main__':
    unittest.main()
