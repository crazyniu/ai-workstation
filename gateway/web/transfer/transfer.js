'use strict';
const $ = id => document.getElementById(id);
const base = '/api/transfer/';
const chunkSize = 8 * 1024 * 1024;
const join = (parent, name) => parent ? parent + '/' + name : name;
const current = () => new URLSearchParams(location.search).get('path') || '';
const pathQuery = path => '?' + new URLSearchParams({path});
const endpoint = (kind, path) => base + kind + pathQuery(path);

function status(message) {
  $('status').textContent = message;
}

async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.error || '请求失败（HTTP ' + res.status + '）');
  }
  if (res.status === 202) return;
  return res.json();
}

function node(tag, text, className) {
  const el = document.createElement(tag);
  if (text) el.textContent = text;
  if (className) el.className = className;
  return el;
}

function link(text, href, className) {
  const a = node('a', text, className);
  a.href = href;
  return a;
}

function readableSize(bytes) {
  if (bytes < 1024) return bytes + ' B';
  const units = ['KiB', 'MiB', 'GiB', 'TiB'];
  let size = bytes / 1024, index = 0;
  while (size >= 1024 && index < units.length - 1) { size /= 1024; index++; }
  return Number(size.toFixed(1)) + ' ' + units[index];
}

function breadcrumbs(path) {
  const parts = path ? path.split('/') : [];
  $('crumbs').replaceChildren(parts.length ? link('全部文件', './') : node('span', '全部文件'));
  parts.forEach((part, index) => {
    const target = parts.slice(0, index + 1).join('/');
    $('crumbs').append(node('span', '/'), index === parts.length - 1 ? node('span', part) : link(part, pathQuery(target)));
  });
}

let busy = false;
async function run(action) {
  if (busy) return;
  busy = true;
  const area = document.querySelector('.transfer');
  area.setAttribute('aria-busy', 'true');
  area.inert = true;
  try {
    status('');
    await action();
  } catch (error) {
    status('');
    toast(error.message, true);
  } finally {
    area.inert = false;
    area.removeAttribute('aria-busy');
    busy = false;
  }
}

async function refresh() {
  const parent = current();
  breadcrumbs(parent);
  const {entries} = await request(endpoint('list', parent));
  $('entries').replaceChildren();
  $('empty').hidden = entries.length !== 0;
  $('columns').hidden = entries.length === 0;
  $('count').textContent = entries.length + ' 项';
  for (const item of entries) {
    const path = join(parent, item.name);
    const folder = item.type === 'folder';
    const href = folder ? pathQuery(path) : endpoint('file', path);
    const row = node('li', '', 'entry');
    const name = link('', href, 'name');
    const img = node('img');
    img.src = folder ? '/icons/folder.svg' : './document.svg';
    img.width = img.height = 32;
    img.alt = '';
    name.append(img, node('span', item.name));
    const actions = node('div', '', 'row-actions');
    row.append(name);
    if (!folder) {
      name.download = item.name;
      const download = link('下载', href, 'text-action');
      download.setAttribute('aria-label', '下载' + item.name);
      download.download = item.name;
      row.append(node('span', readableSize(item.size), 'size'));
      actions.append(download);
    }
    const remove = node('button', '删除', 'text-action destructive');
    remove.setAttribute('aria-label', '删除' + item.name);
    remove.onclick = () => {
      const message = folder ? '删除文件夹“' + item.name + '”及其中所有内容？' : '删除文件“' + item.name + '”？';
      if (confirm(message)) run(async () => {
        await request(endpoint(item.type, path), {method: 'DELETE'});
        toast('已删除“' + item.name + '”');
        await refresh();
      });
    };
    actions.append(remove);
    row.append(actions);
    $('entries').append(row);
  }
}

async function upload(file, path) {
  const url = endpoint('file', path);
  if (file.size <= chunkSize) {
    status('正在上传 ' + file.name);
    await request(url, {method: 'PUT', body: file});
    return;
  }
  const id = Array.from(crypto.getRandomValues(new Uint8Array(16)), n => n.toString(16).padStart(2, '0')).join('');
  for (let start = 0; start < file.size; start += chunkSize) {
    const end = Math.min(start + chunkSize, file.size);
    status('正在上传 ' + file.name + ' · ' + Math.floor(start / file.size * 100) + '%');
    await request(url, {method: 'PUT', headers: {
      'Upload-Id': id, 'Content-Range': 'bytes ' + start + '-' + (end - 1) + '/' + file.size
    }, body: file.slice(start, end)});
  }
}

$('upload').onclick = () => $('files').click();
$('files').onchange = () => {
  const files = Array.from($('files').files);
  $('files').value = '';
  if (files.length) run(async () => {
    for (const file of files) {
      try { await upload(file, join(current(), file.name)); }
      catch (error) { await refresh(); throw new Error(file.name + '：' + error.message); }
    }
    await refresh();
    status('已上传 ' + files.length + ' 个文件');
  });
};
$('refresh').onclick = () => run(refresh);
$('new-folder').onclick = () => {
  $('folder-form').reset();
  $('folder-dialog').showModal();
};
$('cancel-folder').onclick = () => $('folder-dialog').close();
$('folder-form').onsubmit = event => {
  event.preventDefault();
  const name = $('folder-name').value;
  if (name.includes('/') || name.includes('\\')) {
    $('folder-name').setCustomValidity('文件夹名称不能包含斜杠');
    $('folder-name').reportValidity();
    return;
  }
  $('folder-dialog').close();
  run(async () => {
    await request(endpoint('folder', join(current(), name)), {method: 'PUT'});
    await refresh();
  });
};
$('folder-name').oninput = () => $('folder-name').setCustomValidity('');
$('clear').onclick = () => {
  if (!confirm('清空整个共享区？所有文件和文件夹都将永久删除。')) return;
  run(async () => {
    await request(base + 'all', {method: 'DELETE'});
    history.replaceState(null, '', './');
    toast('已清空全部文件和文件夹');
    await refresh();
  });
};

const promptText = `请连接下面的局域网互传 MCP（Streamable HTTP，无需认证）。先调用 tools/list，再按我的要求管理文件和文件夹，或读写共享文档。
${location.origin}${base}mcp`;
async function copyText(text, label, field) {
  const message = '已复制' + label;
  if (navigator.clipboard) {
    try { await navigator.clipboard.writeText(text); toast(message); return; }
    catch { /* Continue with selection-based copying on plain HTTP. */ }
  }
  if (!field) {
    field = $('prompt');
    field.value = text;
    $('manual').showModal();
  }
  field.focus();
  field.select();
  field.oncopy = null;
  let copied = false;
  try { copied = document.execCommand('copy'); } catch { /* Keep the text selected. */ }
  if (copied) {
    if (field === $('prompt')) $('manual').close();
    toast(message);
  } else {
    toast('自动复制未成功，请复制已选文字', true);
    field.oncopy = () => toast('已复制所选文字');
  }
}
$('copy').onclick = () => copyText(promptText, ' AI 提示词');

const documentDialog = $('shared-document');
const documentText = $('document-text');
let documentRevision = '', savedText = '', protocol = '', requestId = 0;

async function rpc(method, params, version = protocol) {
  const headers = {'Content-Type': 'application/json', Accept: 'application/json, text/event-stream'};
  if (version) headers['MCP-Protocol-Version'] = version;
  const message = {jsonrpc: '2.0', method, params};
  if (method !== 'notifications/initialized') message.id = ++requestId;
  const reply = await request(base + 'mcp', {method: 'POST', headers, body: JSON.stringify(message)});
  if (reply?.error) throw new Error(reply.error.message);
  return reply?.result;
}

async function documentTool(name, args = {}) {
  if (!protocol) {
    const info = await rpc('initialize', {protocolVersion: '2025-11-25', capabilities: {},
      clientInfo: {name: 'gateway-transfer-web', version: '1.0'}});
    await rpc('notifications/initialized', {}, info.protocolVersion);
    protocol = info.protocolVersion;
  }
  const result = await rpc('tools/call', {name, arguments: args});
  const text = result.content[0].text;
  if (result.isError) throw new Error(text);
  return JSON.parse(text);
}

function updateDocumentActions() {
  $('copy-document').disabled = !documentText.value;
  $('save-document').disabled = documentText.value === savedText;
}
async function readDocument() {
  const doc = await documentTool('read_document');
  documentText.value = doc.text;
  savedText = documentText.value;
  documentRevision = doc.revision;
  updateDocumentActions();
}
function mayDiscardDocument() {
  return documentText.value === savedText || confirm('放弃未保存的修改？');
}
function editDocument(action) {
  return run(async () => {
    documentText.readOnly = true;
    try { await action(); }
    finally { documentText.readOnly = false; }
  });
}

$('open-document').onclick = () => run(async () => {
  await readDocument();
  documentDialog.showModal();
});
documentText.oninput = updateDocumentActions;
$('copy-document').onclick = () => copyText(documentText.value, '共享文本', documentText);
$('reload-document').onclick = () => {
  if (!busy && mayDiscardDocument()) editDocument(readDocument);
};
$('document-form').onsubmit = event => {
  event.preventDefault();
  editDocument(async () => {
    const text = documentText.value;
    const doc = await documentTool('save_document', {text, revision: documentRevision});
    savedText = text;
    documentRevision = doc.revision;
    updateDocumentActions();
    toast('共享文档已保存');
  });
};
$('close-document').onclick = () => {
  if (!busy && mayDiscardDocument()) documentDialog.close();
};
documentDialog.oncancel = event => {
  if (busy || !mayDiscardDocument()) event.preventDefault();
};
run(refresh);
