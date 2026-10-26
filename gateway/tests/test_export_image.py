"""Offline export must audit the exact archive before producing a bundle."""
import gzip
import hashlib
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

from test_image_audit import docker_image

EXPORT = Path(__file__).resolve().parents[1] / 'scripts/export-image.sh'
BUNDLE = 'gateway-local-1.0.0-amd64.tar.gz'
FAKE_DOCKER = '''#!/bin/sh
set -eu
case "$1 $2" in
  'image inspect') printf '%s\\n' "$FIXTURE_ARCH" ;;
  'image save')
    [ "$3" = --output ] || exit 99
    cp "$FIXTURE_IMAGE" "$4"
    exit "$FIXTURE_SAVE_EXIT"
    ;;
  *) exit 98 ;;
esac
'''


class OfflineImageExportTests(unittest.TestCase):
    def export(self, image, *, existing=False, arch='amd64', save_exit=0):
        with tempfile.TemporaryDirectory(prefix='offline export ') as folder:
            root = Path(folder)
            binary = root / 'bin'
            binary.mkdir()
            docker = binary / 'docker'
            docker.write_text(FAKE_DOCKER)
            docker.chmod(0o755)
            archive = root / 'fixture.tar'
            archive.write_bytes(image)
            output = root / 'output'
            output.mkdir()
            if existing:
                (output / BUNDLE).write_bytes(b'previous verified bundle')
                (output / (BUNDLE + '.sha256')).write_bytes(b'previous checksum')
            env = dict(os.environ, PATH=str(binary) + os.pathsep + os.environ.get('PATH', ''),
                       FIXTURE_IMAGE=str(archive), FIXTURE_ARCH=arch,
                       FIXTURE_SAVE_EXIT=str(save_exit), GATEWAY_IMAGE='fixture:test')
            result = subprocess.run(['/bin/sh', str(EXPORT), str(output)], cwd=root,
                                    env=env, capture_output=True, timeout=15)
            files = {p.name: p.read_bytes() for p in output.iterdir() if p.is_file()}
            self.assertFalse(list(output.glob('.export-*')), 'Unverified staging archive was retained')
            return result, files

    def test_clean_archive_is_exported_with_matching_checksum(self):
        archive = docker_image([{'etc/os-release': b'Ubuntu'}])
        result, files = self.export(archive)
        self.assertEqual(result.returncode, 0, result.stderr.decode())
        self.assertEqual(gzip.decompress(files[BUNDLE]), archive)
        self.assertEqual(files[BUNDLE + '.sha256'].decode(),
                         hashlib.sha256(files[BUNDLE]).hexdigest() + '  ' + BUNDLE + '\n')

    def test_private_archives_are_rejected_without_replacing_existing_bundle(self):
        images = [
            docker_image([{'data/mihomo/config.yaml': b'private fixture'}]),
            docker_image([{'home/dev/.codex/auth.json': b'{}'}]),
            docker_image([{'home/dev/.claude/.credentials.json': b'{}'}]),
            docker_image([{'root/.ssh/id_ed25519': b'fixture'},
                          {'root/.ssh/.wh.id_ed25519': b''}]),
            docker_image([{}], {'config': {'Env': ['GATEWAY_ADMIN_PASSWORD=fixture-only']}}),
        ]
        for archive in images:
            with self.subTest(archive_sha=hashlib.sha256(archive).hexdigest()):
                result, files = self.export(archive, existing=True)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(files, {BUNDLE: b'previous verified bundle',
                                         BUNDLE + '.sha256': b'previous checksum'})
                self.assertNotIn(b'fixture-only', result.stdout + result.stderr)

    def test_incomplete_archive_does_not_produce_a_bundle(self):
        for archive in [b'not an image archive', docker_image([{}], declared=['missing/layer.tar'])]:
            with self.subTest(size=len(archive)):
                result, files = self.export(archive)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(files, {})

    def test_failed_save_does_not_package_partial_output(self):
        result, files = self.export(docker_image([{}]), save_exit=42)
        self.assertEqual(result.returncode, 42)
        self.assertEqual(files, {})

    def test_arm64_clean_image_is_exported(self):
        result, files = self.export(docker_image([{}]), arch='arm64')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(BUNDLE.replace('amd64', 'arm64'), files)


if __name__ == '__main__':
    unittest.main()
