'use strict';
const $ = id => document.getElementById(id);
const base = '/api/transfer/';
const chunkSize = 8 * 1024 * 1024;
const join = (parent, name) => parent ? parent + '/' + name : name;
const current = () => new URLSearchParams(location.search).get('path') || '';
const pathQuery = path => '?' + new URLSearchParams({path});
const endpoint = (kind, path) => base + kind + pathQuery(path);

function status(message, error = false) {
  $('status').textContent = message;
  $('status').classList.toggle('error', error);
}

async function request(url, options) {
  const res = await fetch(url, options);
  if (!res.ok) {
    const error = await res.json().catch(() => ({}));
    throw new Error(error.error || '请求失败（HTTP ' + res.status + '）');
  }
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
    status(error.message, true);
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
  for (const item of entries) {
    const path = join(parent, item.name);
    const folder = item.type === 'folder';
    const href = folder ? pathQuery(path) : endpoint('file', path);
    const row = node('li', '', 'entry');
    const name = link('', href, 'name');
    const img = node('img');
    img.src = folder ? '/icons/folder.svg' : '/icons/files.svg';
    img.width = img.height = 26;
    img.alt = '';
    name.append(img, node('span', item.name));
    row.append(name);
    if (!folder) {
      name.download = item.name;
      const download = link('下载', href, 'action');
      download.download = item.name;
      row.append(node('span', readableSize(item.size), 'size'), download);
    }
    const remove = node('button', '删除');
    remove.setAttribute('aria-label', '删除' + item.name);
    remove.onclick = () => {
      const message = folder ? '删除文件夹“' + item.name + '”及其中所有内容？' : '删除文件“' + item.name + '”？';
      if (confirm(message)) run(async () => {
        await request(endpoint(item.type, path), {method: 'DELETE'});
        await refresh();
      });
    };
    row.append(remove);
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
    await refresh();
    status('已清空全部文件和文件夹');
  });
};

let promptText = '';
const promptReady = fetch('./ai.txt').then(async res => {
  if (!res.ok) throw new Error('无法读取 AI 提示词');
  promptText = (await res.text()).replaceAll('http://192.168.1.250', location.origin);
}).catch(() => {});
$('copy').onclick = async () => {
  if (!promptText) await promptReady;
  if (!promptText) { status('无法读取 AI 提示词，请刷新页面', true); return; }
  if (navigator.clipboard) {
    try { await navigator.clipboard.writeText(promptText); status('已复制 AI 提示词'); return; }
    catch { /* Plain HTTP and browser permissions may require manual selection. */ }
  }
  $('prompt').value = promptText;
  $('manual').showModal();
  $('prompt').focus();
  $('prompt').select();
  if (document.execCommand('copy')) {
    $('manual').close();
    status('已复制 AI 提示词');
  }
};
run(refresh);
