"""Stateless Streamable HTTP MCP endpoint for the gateway file share."""
import base64
import binascii
import io
import json
import os
import shutil
import uuid
from urllib.parse import urlencode

import lan_transfer as share
from state import read, save

VERSIONS = ('2025-11-25', '2025-06-18', '2025-03-26')
INLINE_LIMIT = 1024 * 1024
PATH = {'type': 'string', 'description': '相对于共享区的路径，例如 收件箱/报告.pdf'}
OFFSET = {'type': 'integer', 'minimum': 0, 'description': '起始字节位置，默认 0'}


def tool(name, description, properties, required=(), read_only=False, destructive=False):
    return {
        'name': name, 'description': description,
        'inputSchema': {'type': 'object', 'properties': properties, 'required': list(required),
                        'additionalProperties': False},
        'annotations': {'readOnlyHint': read_only, 'destructiveHint': destructive, 'openWorldHint': False},
    }


TOOLS = {item['name']: item for item in (
    tool('list_files', '列出一个共享目录。省略 path 表示根目录。', {'path': PATH}, read_only=True),
    tool('create_folder', '新建文件夹。父目录须已存在。', {'path': PATH}, ['path']),
    tool('upload_file', '上传文件。仅传 path 可取得本地文件的 HTTP PUT 上传地址和分块规则；也可直接传 Base64 内容。',
         {'path': PATH, 'data_base64': {'type': 'string', 'description': '本块的原始文件字节，Base64 编码，最多 1 MiB 原始数据。'},
          'offset': OFFSET, 'total': {'type': 'integer', 'minimum': 0, 'description': '分块上传时填入完整文件的字节数'},
          'upload_id': {'type': 'string', 'description': '续传时使用第一块返回的 upload_id'}}, ['path']),
    tool('download_file', '取得文件的 HTTP 下载地址和大小。需要内联内容时指定 length，按 offset 分块读取 Base64。',
         {'path': PATH, 'offset': OFFSET, 'length': {'type': 'integer', 'minimum': 1, 'maximum': INLINE_LIMIT}},
         ['path'], read_only=True),
    tool('delete_file', '删除指定文件。', {'path': PATH}, ['path'], destructive=True),
    tool('delete_folder', '递归删除指定文件夹及其内容。', {'path': PATH}, ['path'], destructive=True),
    tool('clear_all', '清空整个共享区的所有文件和文件夹。', {}, destructive=True),
    tool('read_document', '读取局域网共享纯文本文档及其 revision。', {}, read_only=True),
    tool('save_document', '保存局域网共享文档。先读取最新 revision，防止覆盖其他设备的修改。',
         {'text': {'type': 'string'}, 'revision': {'type': 'string'}}, ['text', 'revision'], destructive=True),
)}


class RpcError(Exception):
    def __init__(self, code, message):
        super().__init__(message)
        self.code = code


def arguments(name, args):
    if not isinstance(name, str) or name not in TOOLS:
        raise RpcError(-32602, '未知的工具')
    schema = TOOLS[name]['inputSchema']
    props = schema['properties']
    if not isinstance(args, dict) or not set(schema['required']) <= args.keys() <= props.keys():
        raise RpcError(-32602, '工具参数不符合 inputSchema')
    for key, value in args.items():
        field = props[key]
        if field['type'] == 'string' and not isinstance(value, str):
            raise RpcError(-32602, key + ' 必须是字符串')
        if field['type'] == 'integer' and (type(value) is not int or value < field['minimum']
                                          or ('maximum' in field and value > field['maximum'])):
            raise RpcError(-32602, key + ' 超出允许范围')
    return args


def upload(path, args, url):
    if 'data_base64' not in args:
        if args.keys() != {'path'}:
            raise ValueError('分块上传需要 data_base64')
        if path.exists():
            raise FileExistsError
        return {'method': 'PUT', 'url': url, 'body': '原始文件字节', 'maxRequestBytes': share.MAX_REQUEST,
                'chunks': '分块按顺序 PUT。每块带 Content-Range: bytes 起-止/总字节数 和相同的 Upload-Id（32 位小写十六进制）。'}
    try:
        data = base64.b64decode(args['data_base64'], validate=True)
    except (ValueError, binascii.Error):
        raise ValueError('data_base64 不是有效的 Base64') from None
    if len(data) > INLINE_LIMIT:
        raise ValueError('每块最多 1 MiB 原始数据，也可使用 HTTP 上传地址')
    offset = args.get('offset', 0)
    if offset and ('upload_id' not in args or 'total' not in args):
        raise ValueError('续传需要 upload_id 和 total')
    ident = args.get('upload_id') or uuid.uuid4().hex
    _, result = share.write_upload(path, io.BytesIO(data), len(data), offset, args.get('total', len(data)), ident)
    if 'received' in result:
        result['upload_id'] = ident
    return result


def file_tool(name, args, origin):
    with share.LOCK:
        if name in ('read_document', 'save_document'):
            path = share.ROOT / 'lan-transfer-document.json'
            document = read(path, {'text': '', 'revision': ''})
            if name == 'read_document':
                return document
            if args['text'] != document['text']:
                if args['revision'] != document['revision']:
                    raise ValueError('其他设备已更新共享文档。请先复制草稿，再刷新。')
                document = {'text': args['text'], 'revision': uuid.uuid4().hex}
                save(path, document)
            return {'revision': document['revision']}
        share.prepare_share()
        if name == 'clear_all':
            share.clear_share()
            return {'ok': True}
        relative = args.get('path', '')
        path = share.share_path(relative, allow_root=name == 'list_files')
        if name == 'list_files':
            return {'entries': share.listing(path)}
        if name == 'create_folder':
            path.mkdir(mode=0o700)
        elif name == 'delete_folder':
            shutil.rmtree(path)
        elif name == 'delete_file':
            path.unlink()
        else:
            url = origin + share.PREFIX + 'file?' + urlencode({'path': relative})
            if name == 'upload_file':
                return upload(path, args, url)
            with path.open('rb') as stream:
                size = os.fstat(stream.fileno()).st_size
                result = {'path': relative, 'size': size, 'url': url}
                if 'length' in args:
                    offset = args.get('offset', 0)
                    if offset > size:
                        raise ValueError('offset 超过文件末尾')
                    stream.seek(offset)
                    result['data_base64'] = base64.b64encode(stream.read(args['length'])).decode('ascii')
                    result['next_offset'] = stream.tell() if stream.tell() < size else None
                return result
        return {'ok': True, 'path': relative}


def call(params, origin):
    name = params.get('name')
    args = arguments(name, params.get('arguments', {}))
    try:
        result = file_tool(name, args, origin)
        return {'content': [{'type': 'text', 'text': json.dumps(result, ensure_ascii=False)}]}
    except FileNotFoundError:
        error = '文件或父目录不存在'
    except FileExistsError:
        error = '已存在同名项目'
    except (NotADirectoryError, IsADirectoryError):
        error = '文件或文件夹类型不符'
    except (share.RequestError, ValueError) as exc:
        error = str(exc)
    except OSError:
        error = '网关无法读写共享目录'
    return {'isError': True, 'content': [{'type': 'text', 'text': error}]}


def handle_mcp(handler):
    if handler.command != 'POST':
        handler.send_response(405)
        handler.send_header('Allow', 'POST')
        handler.send_header('Content-Length', '0')
        handler.end_headers()
        return
    ident = None
    status = 200
    try:
        if handler.headers.get_content_type() != 'application/json':
            status = 415
            raise RpcError(-32600, '请使用 application/json')
        version = handler.headers.get('MCP-Protocol-Version')
        if version is not None and version not in VERSIONS:
            status = 400
            raise RpcError(-32600, '不支持的 MCP 协议版本')
        try:
            message = handler.body(limit=2 * 1024 * 1024)
        except ValueError:
            status = 400
            raise RpcError(-32700, '无效的 JSON-RPC 消息') from None
        if message.get('jsonrpc') != '2.0':
            status = 400
            raise RpcError(-32600, '需要 JSON-RPC 2.0')
        method = message.get('method')
        if 'id' not in message and isinstance(method, str):
            handler.send_response(202)
            handler.send_header('Content-Length', '0')
            handler.end_headers()
            return
        if type(message.get('id')) not in (int, str) or not isinstance(method, str):
            status = 400
            raise RpcError(-32600, '请求需要 method 和 id')
        ident = message['id']
        params = message.get('params', {})
        if not isinstance(params, dict):
            raise RpcError(-32602, 'params 必须为对象')
        if method == 'initialize':
            requested = params.get('protocolVersion')
            result = {'protocolVersion': requested if requested in VERSIONS else VERSIONS[0],
                      'capabilities': {'tools': {}}, 'serverInfo': {'name': 'lan-transfer', 'version': '1.0.0'}}
        elif method == 'ping':
            result = {}
        elif method == 'tools/list':
            result = {'tools': list(TOOLS.values())}
        elif method == 'tools/call':
            result = call(params, 'http://' + handler.headers['Host'])
        else:
            raise RpcError(-32601, '未知的方法')
        reply = {'result': result}
    except RpcError as exc:
        reply = {'error': {'code': exc.code, 'message': str(exc)}}
    handler.reply(status, {'jsonrpc': '2.0', 'id': ident, **reply})
