#!/usr/bin/env python3
"""Reusable regression fixtures for manifest-complete, streaming image audits."""
import hashlib
import gzip
import io
import json
from pathlib import Path
import subprocess
import sys
import tarfile
import unittest

AUDITOR = Path(__file__).with_name('audit-image.py')


def archive(entries):
    stream = io.BytesIO()
    with tarfile.open(fileobj=stream, mode='w') as output:
        for name, body in entries.items():
            entry = tarfile.TarInfo(name)
            entry.size = len(body)
            output.addfile(entry, io.BytesIO(body))
    return stream.getvalue()


def docker_image(layers, config=None, declared=None):
    entries = {f'{number}/layer.tar': archive(layer) for number, layer in enumerate(layers)}
    entries['config.json'] = json.dumps(config or {}).encode()
    entries['manifest.json'] = json.dumps([{
        'Config': 'config.json', 'RepoTags': ['fixture:test'],
        'Layers': list(entries)[:-1] if declared is None else declared,
    }]).encode()
    return archive(entries)


def oci_image(layers, omit_layer=None, invalid_layer=None, omit_manifest=False, manifest_last=False):
    entries = {}
    descriptors = []
    for number, body in enumerate(layers):
        digest = hashlib.sha256(body).hexdigest()
        descriptors.append({'mediaType': 'application/vnd.oci.image.layer.v1.tar', 'digest': 'sha256:' + digest, 'size': len(body)})
        if number != omit_layer:
            entries['blobs/sha256/' + digest] = b'not a tar' if number == invalid_layer else body
    config = b'{"config":{"Env":["LANG=zh_TW.UTF-8"]}}'
    digest = hashlib.sha256(config).hexdigest()
    entries['blobs/sha256/' + digest] = config
    manifest = json.dumps({'schemaVersion': 2, 'config': {'digest': 'sha256:' + digest, 'size': len(config)}, 'layers': descriptors}).encode()
    digest = hashlib.sha256(manifest).hexdigest()
    manifest_name = 'blobs/sha256/' + digest
    index = json.dumps({'schemaVersion': 2, 'manifests': [{'digest': 'sha256:' + digest, 'size': len(manifest)}]}).encode()
    if not omit_manifest:
        entries[manifest_name] = manifest
    if manifest_last:
        entries['index.json'] = index
    else:
        entries = {'index.json': index, **entries}
    return archive(entries)


class ImageAuditTests(unittest.TestCase):
    def check_audit(self, image, success, message=None):
        result = subprocess.run([sys.executable, str(AUDITOR)], input=image, capture_output=True, timeout=10)
        self.assertEqual(result.returncode == 0, success, result.stdout.decode() + result.stderr.decode())
        if message:
            self.assertIn(message, (result.stdout + result.stderr).decode())
        return result

    def test_clean_locked_accounts(self):
        self.check_audit(docker_image([{'etc/shadow': b'root:!:0:0:99999:7:::\ndev:!:0:0:99999:7:::\n'}],
                                     {'config': {'Env': ['LANG=zh_TW.UTF-8']}}), True, 'all 1 manifest-declared')

    def test_private_key_in_earlier_deleted_layer(self):
        self.check_audit(docker_image([{'root/.ssh/id_ed25519': b'private'}, {'root/.ssh/.wh.id_ed25519': b''}]),
                         False, 'private state in layer')

    def test_baked_password_environment(self):
        self.check_audit(docker_image([{}], {'config': {'Env': ['DEV_PASSWORD=unsafe']}}),
                         False, 'credential environment baked')

    def test_baked_build_proxy_environment(self):
        for name in ('HTTP_PROXY', 'https_proxy', 'ALL_PROXY'):
            with self.subTest(name=name):
                self.check_audit(docker_image([{}], {'config': {'Env': [name + '=http://temporary-build-proxy:8080']}}),
                                 False, 'credential environment baked')

    def test_unlocked_password(self):
        self.check_audit(docker_image([{'etc/shadow': b'dev:$6$salt$hash:0:0:99999:7:::\n'}]),
                         False, 'unlocked password baked')

    def test_github_login_state(self):
        self.check_audit(docker_image([{'home/dev/.config/gh/hosts.yml': b'github.com: {}\n'}]),
                         False, 'private state in layer')

    def test_ssh_host_key(self):
        self.check_audit(docker_image([{'etc/ssh/ssh_host_ed25519_key': b'private'}]),
                         False, 'private state in layer')

    def test_docker_missing_layer(self):
        self.check_audit(docker_image([{}], declared=['0/layer.tar', 'missing/layer.tar']),
                         False, 'declared image layer missing')

    def test_docker_unreadable_layer(self):
        self.check_audit(archive({'0/layer.tar': archive({}), '1/layer.tar': b'not a tar',
                                 'manifest.json': b'[{"Layers":["0/layer.tar","1/layer.tar"]}]'}),
                         False, 'declared image layer unreadable')

    def test_valid_oci_and_progress(self):
        result = self.check_audit(oci_image([archive({}), archive({'etc/example.txt': b'public'})], manifest_last=True),
                                  True, 'all 2 manifest-declared')
        self.assertEqual(result.stderr.count(b'AUDIT layer start:'), 2)
        self.assertEqual(result.stderr.count(b'AUDIT layer end:'), 2)

    def test_oci_missing_layer(self):
        self.check_audit(oci_image([archive({}), archive({'etc/example.txt': b'public'})], omit_layer=1),
                         False, 'declared image layer missing')

    def test_gzip_oci_layer(self):
        self.check_audit(oci_image([gzip.compress(archive({'etc/example.txt': b'public'}))]),
                         True, 'all 1 manifest-declared')

    def test_large_streamed_layer(self):
        self.check_audit(oci_image([archive({'usr/share/public.bin': bytes(2 * 1024 * 1024)})]),
                         True, 'all 1 manifest-declared')

    def test_oci_unreadable_layer(self):
        self.check_audit(oci_image([archive({}), archive({'etc/example.txt': b'public'})], invalid_layer=1),
                         False, 'declared image layer unreadable')

    def test_oci_layer_is_json_instead_of_tar(self):
        self.check_audit(oci_image([archive({}), b'{"config": {}}']),
                         False, 'declared image layer missing or not a readable tar layer')

    def test_oci_missing_manifest(self):
        self.check_audit(oci_image([archive({})], omit_manifest=True),
                         False, 'declared OCI manifest missing or unreadable')

    def test_layers_without_manifest_fail_closed(self):
        self.check_audit(archive({'0/layer.tar': archive({})}), False, 'audit coverage cannot be established')

    def test_truncated_declared_layer(self):
        # A valid first header with missing file data must not count as a completed scan.
        body = archive({'etc/example.json': b'{"message":"public"}'})[:520]
        self.check_audit(archive({'0/layer.tar': archive({}), '1/layer.tar': body,
                                 'manifest.json': b'[{"Layers":["0/layer.tar","1/layer.tar"]}]'}),
                         False, 'declared image layer unreadable')


if __name__ == '__main__':
    unittest.main()
