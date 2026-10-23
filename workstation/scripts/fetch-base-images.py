#!/usr/bin/env python3
"""Fetch official Docker Hub linux/amd64 bases as verified docker-load archives.

Requires Python 3 and curl, no Docker daemon or registry credentials. Downloaded
blobs are checked against registry SHA256 descriptors; uncompressed layers are
checked against config rootfs.diff_ids. Output SHA256 also protects transfer.
This verifies integrity, not publisher signatures. Cache/output default to /tmp.
"""
import argparse
import gzip
import hashlib
import io
import json
import pathlib
import re
import shutil
import subprocess
import tarfile
import tempfile

ACCEPT = ', '.join(('application/vnd.oci.image.index.v1+json',
    'application/vnd.docker.distribution.manifest.list.v2+json',
    'application/vnd.oci.image.manifest.v1+json',
    'application/vnd.docker.distribution.manifest.v2+json'))


def digest_file(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return 'sha256:' + h.hexdigest()


def checked(path, digest):
    if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
        raise ValueError('Only SHA256 descriptors are supported')
    if digest_file(path) != digest:
        raise ValueError(f'Hash mismatch: {path}')


def download(url, path, headers=()):
    partial = path.with_name(path.name + '.partial')
    cmd = ['curl', '--fail', '--silent', '--show-error', '--location',
           '--proto', '=https', '--proto-redir', '=https', '--retry', '3',
           '--connect-timeout', '20', '--max-time', '900', '-o', str(partial)]
    for header in headers:
        cmd.extend(['-H', header])
    subprocess.run(cmd + [url], check=True)
    partial.replace(path)


def fetch(image, cache, output):
    # Scope deliberately limited to Docker Official Images, no arbitrary URL input.
    if not re.fullmatch(r'[a-z0-9][a-z0-9_.-]*:[A-Za-z0-9_.-]+', image):
        raise ValueError('Expected official image:tag (for example ubuntu:26.04)')
    name, tag = image.split(':')
    repo = 'library/' + name
    with tempfile.TemporaryDirectory(prefix='workstation-registry-') as tmp:
        temp = pathlib.Path(tmp)
        token_path = temp / 'token.json'
        download(f'https://auth.docker.io/token?service=registry.docker.io&scope=repository:{repo}:pull', token_path)
        token = json.loads(token_path.read_text())['token']
        auth = 'Authorization: Bearer ' + token
        base = 'https://registry-1.docker.io/v2/' + repo
        index_path = temp / 'index.json'
        download(base + '/manifests/' + tag, index_path, (auth, 'Accept: ' + ACCEPT))
        index = json.loads(index_path.read_bytes())
        if 'manifests' in index:
            candidates = [m for m in index['manifests'] if m.get('platform', {}).get('os') == 'linux'
                          and m['platform'].get('architecture') == 'amd64']
            if len(candidates) != 1:
                raise ValueError(f'Expected one linux/amd64 manifest, found {len(candidates)}')
            manifest_digest = candidates[0]['digest']
            manifest_path = temp / 'manifest.json'
            download(base + '/manifests/' + manifest_digest, manifest_path, (auth, 'Accept: ' + ACCEPT))
            checked(manifest_path, manifest_digest)
            manifest = json.loads(manifest_path.read_bytes())
        else:
            manifest = index
            manifest_digest = digest_file(index_path)

        def blob(descriptor):
            digest = descriptor['digest']
            if not re.fullmatch(r'sha256:[0-9a-f]{64}', digest):
                raise ValueError('Unsupported blob digest')
            path = cache / digest.replace(':', '-')
            if path.exists() and digest_file(path) != digest:
                path.unlink()
            if not path.exists():
                download(base + '/blobs/' + digest, path, (auth,))
            checked(path, digest)
            if path.stat().st_size != descriptor['size']:
                raise ValueError('Blob size mismatch')
            return path

        config_path = blob(manifest['config'])
        config = json.loads(config_path.read_bytes())
        if (config.get('os'), config.get('architecture')) != ('linux', 'amd64'):
            raise ValueError('Config platform mismatch')
        layers = manifest['layers']
        diffs = config['rootfs']['diff_ids']
        if len(layers) != len(diffs):
            raise ValueError('Layer count mismatch')
        expanded = []
        for i, (descriptor, diff) in enumerate(zip(layers, diffs)):
            source = blob(descriptor)
            target = temp / f'layer-{i}.tar'
            media = descriptor['mediaType']
            if media.endswith('+gzip') or media.endswith('.gzip'):
                with gzip.open(source, 'rb') as src, target.open('wb') as dst:
                    shutil.copyfileobj(src, dst)
            elif media.endswith('.tar'):
                shutil.copyfile(source, target)
            else:
                raise ValueError(f'Unsupported layer media type: {media}')
            checked(target, diff)
            expanded.append((diff.split(':')[1] + '/layer.tar', target))
        config_name = manifest['config']['digest'].split(':')[1] + '.json'
        archive_manifest = [{'Config': config_name, 'RepoTags': [image],
                             'Layers': [name for name, _ in expanded]}]
        archive = output / (image.replace(':', '-') + '-linux-amd64.tar')
        partial = archive.with_suffix('.tar.partial')
        with tarfile.open(partial, 'w') as tar:
            tar.add(config_path, arcname=config_name)
            for layer_name, path in expanded:
                tar.add(path, arcname=layer_name)
            raw = json.dumps(archive_manifest).encode()
            member = tarfile.TarInfo('manifest.json')
            member.size = len(raw)
            tar.addfile(member, io.BytesIO(raw))
        partial.replace(archive)
        sha = digest_file(archive).split(':')[1]
        archive.with_suffix('.tar.sha256').write_text(f'{sha}  {archive.name}\n')
        receipt = {'image': image, 'platform': 'linux/amd64', 'manifest': manifest_digest,
                   'config': manifest['config']['digest'], 'archive_sha256': sha,
                   'layers': [d['digest'] for d in layers]}
        archive.with_suffix('.tar.receipt.json').write_text(json.dumps(receipt, indent=2) + '\n')
        print(json.dumps({'archive': str(archive), **receipt}), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('images', nargs='*', default=['node:24.22.1-bookworm-slim', 'ubuntu:26.04'])
    parser.add_argument('--cache', type=pathlib.Path, default=pathlib.Path('/tmp/workstation-base-cache'))
    parser.add_argument('--output', type=pathlib.Path, default=pathlib.Path('/tmp/workstation-base-images'))
    args = parser.parse_args()
    args.cache.mkdir(parents=True, exist_ok=True)
    args.output.mkdir(parents=True, exist_ok=True)
    for image in args.images:
        fetch(image, args.cache, args.output)


if __name__ == '__main__':
    main()
