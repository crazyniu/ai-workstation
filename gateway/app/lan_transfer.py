"""Anonymous file exchange on the gateway's LAN."""
import errno
import hashlib
import ipaddress
import os
import re
import shutil
import threading
import time
import uuid
from urllib.parse import parse_qs, quote, urlsplit

from state import ROOT, lan_ip, lan_networks, settings

PREFIX = '/api/transfer/'
SHARE = ROOT / 'lan-transfer'
PART = '.lan-upload-'
LOCK = threading.Lock()
MAX_REQUEST = 32 * 1024 * 1024
DISK_RESERVE = 256 * 1024 * 1024


class RequestError(Exception):
    def __init__(self, status, message):
        super().__init__(message)
        self.status = status


def is_local(handler):
    peer = ipaddress.ip_address(handler.headers.get('X-Real-IP', handler.client_address[0]))
    host = urlsplit('//' + handler.headers.get('Host', '')).hostname
    if host not in {lan_ip(), settings()['domain'], 'localhost', '127.0.0.1', '::1'}:
        return False
    return peer.is_loopback or any(peer in ipaddress.ip_network(net) for net in lan_networks())


def share_path(value, allow_root=False):
    path = SHARE
    names = value.split('/') if value else []
    if not names and not allow_root:
        raise RequestError(400, '请指定文件或文件夹')
    for name in names:
        if (name in ('', '.', '..') or name.startswith(PART) or '\\' in name
                or any(ord(c) < 32 or ord(c) == 127 for c in name)):
            raise RequestError(400, '文件路径无效')
        path = path / name
        if path.is_symlink():
            raise RequestError(400, '不支持符号链接')
    return path


def listing(path):
    entries = []
    for item in path.iterdir():
        if item.name.startswith(PART):
            if item.is_file() and item.stat().st_mtime < time.time() - 86400:
                item.unlink()
            continue
        if item.is_symlink() or not (item.is_file() or item.is_dir()):
            continue
        folder = item.is_dir()
        entries.append(dict(name=item.name, type='folder' if folder else 'file',
                            size=None if folder else item.stat().st_size))
    return sorted(entries, key=lambda e: (e['type'] != 'folder', e['name'].casefold()))


def upload(handler, path):
    if path.exists():
        raise FileExistsError
    length = int(handler.headers.get('Content-Length', '-1'))
    if length < 0:
        raise RequestError(411, '上传需要 Content-Length')
    if length > MAX_REQUEST:
        raise RequestError(413, '单次请求上限为 32 MiB，请分块上传')
    offset, total = 0, length
    ident = uuid.uuid4().hex
    interval = handler.headers.get('Content-Range')
    if interval is not None:
        match = re.fullmatch(r'bytes (\d+)-(\d+)/(\d+)', interval)
        ident = handler.headers.get('Upload-Id', '')
        if not match or not re.fullmatch(r'[0-9a-f]{32}', ident):
            raise RequestError(400, '分块需要有效的 Content-Range 和 Upload-Id')
        offset, end, total = map(int, match.groups())
        if not offset <= end < total or end - offset + 1 != length:
            raise RequestError(400, '分块范围与长度不符')
    if shutil.disk_usage(SHARE).free < length + DISK_RESERVE:
        raise RequestError(507, '网关磁盘可用空间不足')
    # Bind the partial file to its destination and intended size.
    key = hashlib.sha256(f'{path.name}:{total}:{ident}'.encode()).hexdigest()
    part = path.with_name(PART + key)
    if offset and (not part.exists() or part.stat().st_size != offset):
        raise RequestError(409, '分块位置不符，请重新上传')
    try:
        with part.open('ab' if offset else 'wb') as stream:
            remaining = length
            while remaining:
                chunk = handler.rfile.read(min(remaining, 1024 * 1024))
                if not chunk:
                    raise RequestError(400, '上传中断，请重试')
                stream.write(chunk)
                remaining -= len(chunk)
        received = offset + length
        if received == total:
            part.rename(path)
            return 201, {'path': str(path.relative_to(SHARE)), 'size': total}
        return 200, {'received': received}
    except (OSError, RequestError):
        if offset and part.exists():
            os.truncate(part, offset)
        else:
            part.unlink(missing_ok=True)
        raise


def download(handler, stream, name):
    with stream:
        handler.send_response(200)
        handler.send_header('Content-Type', 'application/octet-stream')
        handler.send_header('Content-Disposition', "attachment; filename*=UTF-8''" + quote(name, safe=''))
        handler.send_header('Content-Length', str(os.fstat(stream.fileno()).st_size))
        handler.send_header('Cache-Control', 'no-store')
        handler.send_header('X-Content-Type-Options', 'nosniff')
        handler.send_header('Content-Security-Policy', "sandbox; default-src 'none'")
        handler.end_headers()
        shutil.copyfileobj(stream, handler.wfile, length=1024 * 1024)


def handle(handler):
    route = urlsplit(handler.path)
    operation = route.path.removeprefix(PREFIX)
    method = handler.command
    try:
        if not is_local(handler) or not handler.same_origin():
            raise RequestError(403, '请通过网关的局域网地址访问')
        query = parse_qs(route.query, keep_blank_values=True, errors='strict')
        paths = query.get('path', [''])
        if len(paths) != 1:
            raise RequestError(400, '请指定一个路径')
        with LOCK:
            if SHARE.is_symlink():
                raise RequestError(409, '共享目录不能是符号链接')
            SHARE.mkdir(mode=0o700, exist_ok=True)
            if (method, operation) == ('DELETE', 'all'):
                if query:
                    raise RequestError(400, '清空全部无需路径')
                for item in SHARE.iterdir():
                    if item.is_dir() and not item.is_symlink():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
                return handler.reply(200, {'ok': True})
            path = share_path(paths[0], allow_root=(method, operation) == ('GET', 'list'))
            if (method, operation) == ('GET', 'list'):
                return handler.reply(200, {'entries': listing(path)})
            if (method, operation) == ('PUT', 'folder'):
                path.mkdir(mode=0o700)
                return handler.reply(201, {'ok': True})
            if (method, operation) == ('DELETE', 'folder'):
                shutil.rmtree(path)
                return handler.reply(200, {'ok': True})
            if (method, operation) == ('DELETE', 'file'):
                path.unlink()
                return handler.reply(200, {'ok': True})
            if (method, operation) == ('PUT', 'file'):
                return handler.reply(*upload(handler, path))
            if (method, operation) != ('GET', 'file'):
                raise RequestError(404, '接口不存在')
            stream = path.open('rb')
        download(handler, stream, path.name)
    except (BrokenPipeError, ConnectionResetError):
        pass
    except RequestError as exc:
        handler.reply(exc.status, {'error': str(exc)})
    except FileNotFoundError:
        handler.reply(404, {'error': '文件或文件夹不存在'})
    except FileExistsError:
        handler.reply(409, {'error': '已存在同名项目'})
    except (NotADirectoryError, IsADirectoryError):
        handler.reply(400, {'error': '文件或文件夹类型不符'})
    except ValueError:
        handler.reply(400, {'error': '请求参数无效'})
    except OSError as exc:
        if exc.errno == errno.ENOSPC:
            handler.reply(507, {'error': '网关磁盘已满'})
        elif exc.errno == errno.ENAMETOOLONG:
            handler.reply(400, {'error': '文件路径过长'})
        else:
            handler.reply(500, {'error': '网关无法读写共享目录'})
