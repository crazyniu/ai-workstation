#!/usr/bin/env python3
import hashlib,json,sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'app'))
from releases import discover, install_asset, download
root = Path(__file__).resolve().parents[1]
arch = sys.argv[1] if len(sys.argv)>1 else 'amd64'
lock = root / 'components.lock.json'
if '--refresh' in sys.argv or not lock.exists():
    previous=json.loads(lock.read_text()) if lock.exists() else {}
    manifests = {c: discover(c, arch) for c in ('mihomo','adguard','tailscale','panel')}
    lock.write_text(json.dumps(dict(previous,arch=arch,components=manifests),indent=2)+'\n')
else:
    manifests = json.loads(lock.read_text())['components']
for component, manifest in manifests.items():
    dest = root / 'seed' / component
    if dest.exists():
        print(component, 'already downloaded'); continue
    install_asset(manifest, dest)
    print(component, manifest['version'], 'verified')
filter_manifest=json.loads(lock.read_text()).get('filters',{}).get('adguard-dns')
if not filter_manifest:
    raise ValueError('components.lock.json is missing the pinned AdGuard DNS filter')
folder=root/'seed/filters';folder.mkdir(parents=True,exist_ok=True)
dest=folder/'adguard-dns.txt'
content=dest.read_bytes() if dest.exists() else download(filter_manifest['url'],20*1024*1024)
if hashlib.sha256(content).hexdigest()!=filter_manifest['sha256']:
    raise ValueError('AdGuard DNS filter SHA256 mismatch')
if not dest.exists():dest.write_bytes(content)
(folder/'manifest.json').write_text(json.dumps(filter_manifest,indent=2)+'\n')
print('AdGuard DNS filter',filter_manifest['source_commit'],'verified')
