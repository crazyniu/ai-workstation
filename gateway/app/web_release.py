"""Install the gateway management application from its official GitHub releases."""
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
import uuid

from releases import download
from state import DASH, read, save

REPO = 'crazyniu/ai-workstation'
TAG = re.compile(r'gateway-web-v(\d+)\.(\d+)\.(\d+)')
ASSET = 'gateway-web.tar.gz'
BASE = Path('/opt/gateway')
ACTIVE = Path(__file__).resolve().parents[1]
RUNDIR = Path('/run/gateway')
JOB = RUNDIR / 'web-update.json'
CACHE = DASH / 'web-release.json'
SUPERVISOR = ['supervisorctl', '-c', str(BASE / 'runtime/supervisord.conf')]


def installed(root=ACTIVE):
    return read(root / 'web/release.json', {}).get('tag', '')


def release(refresh=False):
    cached = read(CACHE, {})
    if not refresh and time.time() - cached.get('checked', 0) < 3600:
        return cached
    req = urllib.request.Request(f'https://api.github.com/repos/{REPO}/releases?per_page=100',
                                 headers={'User-Agent': 'ai-workstation-gateway', 'Accept': 'application/vnd.github+json'})
    with urllib.request.urlopen(req, timeout=12) as response:
        items = json.load(response)
    for item in items:
        tag = item['tag_name']
        if item['draft'] or item['prerelease'] or not TAG.fullmatch(tag):
            continue
        asset = next((a for a in item['assets'] if a['name'] == ASSET), None)
        if not asset:
            continue
        checksum = asset.get('digest') or ''
        if not re.fullmatch(r'sha256:[a-f0-9]{64}', checksum):
            raise ValueError('发布包缺少有效的 SHA-256')
        result = dict(tag=tag, digest=checksum[7:], notes=(item.get('body') or '')[:6000],
                      url=f'https://github.com/{REPO}/releases/tag/{tag}', checked=time.time())
        break
    else:
        result = dict(tag='', checked=time.time())
    save(CACHE, result)
    return result


def newer(tag, current):
    if not tag:
        return False
    match = TAG.fullmatch(current)
    return not match or tuple(map(int, TAG.fullmatch(tag).groups())) > tuple(map(int, match.groups()))


def info(refresh=False):
    current = installed()
    error = ''
    try:
        latest = release(refresh)
    except (ValueError, OSError, KeyError):
        latest = read(CACHE, {})
        error = '暂时无法读取 GitHub Release'
    tag = latest.get('tag', '')
    return dict(current=current, latest=tag, available=newer(tag, current), notes=latest.get('notes', ''),
                url=latest.get('url', ''), error=error)


def locked():
    return (RUNDIR / 'web-update.lock').open('a')


def running():
    if not (RUNDIR / 'web-update.lock').exists():
        return False
    with locked() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            return True
    return False


def begin(tag):
    if not isinstance(tag, str) or not TAG.fullmatch(tag):
        raise ValueError('请选择有效的网关 Web 版本')
    with locked() as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise ValueError('网关 Web 正在升级') from None
        job = dict(id=uuid.uuid4().hex, tag=tag, status='running')
        save(JOB, job)
        try:
            subprocess.Popen([sys.executable, __file__, tag, job['id']], pass_fds=(lock.fileno(),),
                             stdin=subprocess.DEVNULL, start_new_session=True, cwd='/')
        except OSError:
            save(JOB, dict(job, status='error', error='无法启动升级任务'))
            raise
        return job


def progress():
    job = read(JOB, {})
    if job.get('status') == 'running' and not running():
        return dict(job, status='error', error='升级任务已中断，请重新检查当前版本')
    return job


def unpack(data, stage, tag):
    total = 0
    with tarfile.open(fileobj=io.BytesIO(data), mode='r:gz') as archive:
        for file in archive:
            path = Path(file.name)
            if path.is_absolute() or '..' in path.parts or not path.parts or path.parts[0] not in ('app', 'web'):
                raise ValueError('升级包文件路径无效')
            if file.isdir():
                continue
            if not file.isfile():
                raise ValueError('升级包包含不支持的文件')
            total += file.size
            if total > 64 * 1024 * 1024:
                raise ValueError('升级包过大')
            dest = stage / path
            dest.parent.mkdir(parents=True, exist_ok=True)
            with dest.open('xb') as out, archive.extractfile(file) as src:
                shutil.copyfileobj(src, out)
            dest.chmod(0o644)
    if installed(stage) != tag or not all((stage/f).is_file() for f in ('web/index.html', 'app/server.py', 'app/web_release.py')):
        raise ValueError('升级包版本或内容无效')


def activate(target):
    next_link = BASE / '.web-next'
    next_link.unlink(missing_ok=True)
    next_link.symlink_to(target)
    os.replace(next_link, BASE / 'current')
    subprocess.run([*SUPERVISOR, 'restart', 'api'], check=True, timeout=45)


def install(tag):
    latest = release(refresh=True)
    if latest.get('tag') != tag or not newer(tag, installed()):
        raise ValueError('版本信息已变化，请重新检查更新')
    data = download(f'https://github.com/{REPO}/releases/download/{tag}/{ASSET}', 32 * 1024 * 1024)
    if hashlib.sha256(data).hexdigest() != latest['digest']:
        raise ValueError('升级包 SHA-256 校验失败')
    releases = BASE / 'web-releases'
    releases.mkdir(exist_ok=True)
    stage = Path(tempfile.mkdtemp(dir=releases))
    previous = os.readlink(BASE / 'current')
    try:
        unpack(data, stage, tag)
        stage.chmod(0o755)
        try:
            activate(stage)
            with urllib.request.urlopen('http://127.0.0.1:8787/api/web-version', timeout=5) as response:
                if json.load(response)['tag'] != tag:
                    raise ValueError('管理 API 版本不匹配')
        except Exception:
            activate(previous)
            raise ValueError('新版管理 API 未就绪，已切回上一版') from None
    finally:
        if (BASE / 'current').resolve() != stage:
            shutil.rmtree(stage)


if __name__ == '__main__':
    os.umask(0o022)
    target, ident = sys.argv[1:]
    try:
        install(target)
    except Exception as exc:
        save(JOB, dict(id=ident, tag=target, status='error', error=str(exc) if isinstance(exc, ValueError) else '网关 Web 升级失败'))
        sys.exit(1)
    save(JOB, dict(id=ident, tag=target, status='success'))
