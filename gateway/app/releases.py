"""Official release discovery and bounded, digest-verified asset extraction."""
import gzip
import hashlib
import io
import json
import platform
import subprocess
import tempfile
import tarfile
import urllib.request
from pathlib import Path

REPOS = {'mihomo': 'MetaCubeX/mihomo', 'adguard': 'AdguardTeam/AdGuardHome', 'panel': 'MetaCubeX/metacubexd'}
MAX_DOWNLOAD = 180 * 1024 * 1024

def architecture(machine=None):
    if machine is None:
        receipt = Path('/opt/gateway/seed/architecture')
        machine = receipt.read_text().strip() if receipt.is_file() else platform.machine()
    machine = machine.lower()
    aliases = {'x86_64': 'amd64', 'x64': 'amd64', 'amd64': 'amd64',
               'aarch64': 'arm64', 'arm64': 'arm64', 'i386': '386',
               'i486': '386', 'i586': '386', 'i686': '386', 'x86': '386',
               '386': '386', 'armv7l': 'armv7', 'armv7': 'armv7',
               'armhf': 'armv7', 'arm/v7': 'armv7', 'armel': 'armv5',
               'armv5': 'armv5', 'armv5tel': 'armv5', 'arm/v5': 'armv5',
               'armv6': 'armv6', 'armv6l': 'armv6', 'arm/v6': 'armv6',
               'mips': 'mips', 'mipsle': 'mipsle', 'mipsel': 'mipsle', 'mips64': 'mips64',
               'mips64le': 'mips64le', 'mips64el': 'mips64le', 'riscv64': 'riscv64'}
    if machine not in aliases:
        raise ValueError('Unsupported CPU architecture: ' + machine)
    return aliases[machine]

def download(url, limit=MAX_DOWNLOAD):
    if not url.startswith('https://'):
        raise ValueError('下载必须使用 HTTPS')
    with tempfile.TemporaryFile() as stream:
        result = subprocess.run(['curl', '--fail', '--location', '--silent', '--show-error', '--retry', '2', '--connect-timeout', '15', '--max-time', '180', '--max-filesize', str(limit), '--proto', '=https', '--proto-redir', '=https', '-A', 'gateway-container/1.0', url], stdout=stream, stderr=subprocess.PIPE, timeout=560)
        if result.returncode:
            raise ValueError('官方文件下载失败，请检查网络后重试')
        stream.seek(0)
        data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError('下载文件超过限制')
    return data

def discover(component, arch=None, version=None):
    arch = architecture(arch)
    if component == 'tailscale':
        catalog = json.loads(download('https://pkgs.tailscale.com/stable/?mode=json', 1024 * 1024))
        name = catalog['Tarballs']['arm' if arch.startswith('armv') else arch]
        url = 'https://pkgs.tailscale.com/stable/' + name
        digest = download(url + '.sha256', 1024).decode().strip().split()[0]
        return {'component': component, 'version': name.split('_')[1], 'url': url, 'sha256': digest}
    repo = REPOS[component]
    endpoint = 'tags/' + version if version else 'latest'
    release = json.loads(download(f'https://api.github.com/repos/{repo}/releases/{endpoint}', 3 * 1024 * 1024))
    version = release['tag_name']
    mihomo_arch = arch + '-softfloat' if arch in ('mips', 'mipsle') else arch
    adguard_arch = arch + '_softfloat' if arch.startswith('mips') else arch
    name = {'mihomo': f'mihomo-linux-amd64-compatible-{version}.gz' if arch == 'amd64' else f'mihomo-linux-{mihomo_arch}-{version}.gz',
            'adguard': f'AdGuardHome_linux_{adguard_arch}.tar.gz', 'panel': 'compressed-dist.tgz'}[component]
    asset = next(a for a in release['assets'] if a['name'] == name)
    digest = asset.get('digest', '')
    if not digest.startswith('sha256:'):
        raise ValueError('官方发布未提供 SHA256，暂不升级')
    return {'component': component, 'version': version, 'url': asset['browser_download_url'], 'sha256': digest[7:]}

def install_asset(manifest, dest):
    data = download(manifest['url'])
    if hashlib.sha256(data).hexdigest() != manifest['sha256']:
        raise ValueError('SHA256 校验失败，原版本保持')
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=False)
    component = manifest['component']
    if component == 'mihomo':
        binary = gzip.decompress(data)
        if len(binary) > MAX_DOWNLOAD:
            raise ValueError('解压文件过大')
        (dest / 'mihomo').write_bytes(binary)
        (dest / 'mihomo').chmod(0o755)
    else:
        total = 0
        with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
            for member in archive:
                if not member.isfile():
                    continue
                path = Path(member.name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('下载包包含不安全路径')
                if component == 'panel':
                    parts = list(path.parts)
                    if parts and parts[0] in ('.', 'dist'):
                        parts = parts[1:]
                    relative = Path(*parts)
                else:
                    if path.name not in ({'AdGuardHome'} if component == 'adguard' else {'tailscale', 'tailscaled'}):
                        continue
                    relative = Path(path.name)
                total += member.size
                if total > 400 * 1024 * 1024:
                    raise ValueError('解压文件过大')
                target = dest / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(member) as stream:
                    target.write_bytes(stream.read())
                target.chmod(0o755 if component != 'panel' else 0o644)
    required = {'mihomo': ['mihomo'], 'adguard': ['AdGuardHome'], 'tailscale': ['tailscale', 'tailscaled'], 'panel': ['index.html']}[component]
    if not all((dest / p).is_file() for p in required):
        raise ValueError('发布包缺少必要文件')
    (dest / 'version.json').write_text(json.dumps(manifest, indent=2) + '\n')
