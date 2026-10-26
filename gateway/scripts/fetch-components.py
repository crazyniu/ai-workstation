#!/usr/bin/env python3
"""Fetch pinned assets for one architecture, replacing stale seeds safely."""
import argparse
import hashlib
import json
import shutil
import sys
import tempfile
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from releases import architecture, discover, install_asset, download


def fetch(root, arch, refresh=False):
    arch = architecture(arch)
    lock = root / 'components.lock.json'
    value = json.loads(lock.read_text())
    if refresh:
        manifests = {c: discover(c, arch) for c in ('mihomo', 'adguard', 'tailscale', 'panel')}
        value.setdefault('architectures', {})[arch] = manifests
        if arch == value['arch']:
            value['components'] = manifests
        lock.write_text(json.dumps(value, indent=2) + '\n')
    manifests = value.get('architectures', {value['arch']: value['components']})[arch]
    seed = root / 'seed'
    seed.mkdir(exist_ok=True)
    for component, manifest in manifests.items():
        dest = seed / component
        receipt = dest / 'version.json'
        if receipt.is_file() and json.loads(receipt.read_text()) == manifest:
            print(component, arch, 'already downloaded')
            continue
        with tempfile.TemporaryDirectory(dir=seed) as folder:
            staged = Path(folder) / component
            install_asset(manifest, staged)
            if dest.exists():
                shutil.rmtree(dest)
            staged.rename(dest)
        print(component, arch, manifest['version'], 'verified')
    pinned = value['filters']['adguard-dns']
    folder = seed / 'filters'
    folder.mkdir(exist_ok=True)
    dest = folder / 'adguard-dns.txt'
    content = dest.read_bytes() if dest.exists() else download(pinned['url'], 20*1024*1024)
    if hashlib.sha256(content).hexdigest() != pinned['sha256']:
        raise ValueError('AdGuard DNS filter SHA256 mismatch')
    if not dest.exists():
        dest.write_bytes(content)
    (folder / 'manifest.json').write_text(json.dumps(pinned, indent=2) + '\n')
    (seed / 'architecture').write_text(arch + '\n')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('arch', nargs='?', default=architecture())
    parser.add_argument('--refresh', action='store_true')
    args = parser.parse_args()
    fetch(Path(__file__).resolve().parents[1], args.arch, args.refresh)
