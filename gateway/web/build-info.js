'use strict';

let latestWebRelease = null;
let releaseRequest = 0;
const releaseLabel = tag => tag ? tag.replace(/^gateway-web-/, '') : '开发版';

async function loadWebRelease(refresh = false, notify = false) {
  const request = ++releaseRequest;
  const info = refresh ? await post('/web-release/check') : await api('/web-release');
  if (request !== releaseRequest) return;
  latestWebRelease = info;
  const current = releaseLabel(info.current);
  const latest = info.latest ? '最新 ' + releaseLabel(info.latest) : info.error || '暂无正式发布';
  $('#gateway-version').textContent = 'Niu Gateway ' + current + ' · ' + latest;
  $('#web-release-detail').textContent = '当前 ' + current + ' · ' + latest + (info.latest && info.error ? '（上次检查）' : '');
  $('#web-release-install').hidden = !info.available || !!info.error;
  if (notify && info.available && !info.error && !busy && !configDirty() && !document.querySelector('dialog:modal')) {
    let seen;
    try { seen = sessionStorage.getItem('gateway-release-prompt'); sessionStorage.setItem('gateway-release-prompt', info.latest); } catch {}
    if (seen !== info.latest) await offerWebRelease(info);
  }
}

async function followWebRelease(initial) {
  const detail = $('#web-release-detail');
  detail.textContent = '正在升级到 ' + releaseLabel(initial.tag);
  for (let attempt = 0; attempt < 330; attempt++) {
    await new Promise(resolve => setTimeout(resolve, 2000));
    let task;
    try { task = await api('/web-release/job'); } catch { continue; }
    if (task.id !== initial.id) throw Error('升级任务已变化，请重新打开服务升级');
    if (task.status === 'error') { detail.textContent = task.error; throw Error(task.error); }
    if (task.status === 'success') { location.reload(); return; }
  }
  throw Error('升级仍在处理中，请在服务升级中查看进度');
}

// Release notes are GitHub Markdown. Build the nodes directly, so nothing in them runs as HTML.
const REPOSITORY = 'https://github.com/crazyniu/ai-workstation';
function markdownNode(tag, children) {
  const node = document.createElement(tag);
  node.append(...children);
  return node;
}
function markdownLink(href, children) {
  let url;
  try { url = new URL(href); } catch { url = null; }
  if (!url || !['http:', 'https:'].includes(url.protocol)) {
    // Only web links open; anything else keeps its text.
    const text = document.createDocumentFragment();
    text.append(...children);
    return text;
  }
  const link = markdownNode('a', children);
  link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
  return link;
}
function linkLabel(url) {
  // Like GitHub: a compare link shows its range and a pull request link its number.
  const own = url.startsWith(REPOSITORY + '/') ? url.slice(REPOSITORY.length + 1) : '';
  const compare = own.match(/^compare\/(.+)$/), pull = own.match(/^(?:pull|issues)\/(\d+)$/);
  return compare ? compare[1] : pull ? '#' + pull[1] : url;
}
function markdownInline(text) {
  const nodes = [], pattern = /`([^`]+)`|!?\[([^\]]+)\]\(\s*((?:[^\s()]|\([^\s()]*\))+)(?:\s+"[^"]*")?\s*\)|\*\*(.+?)\*\*|__(.+?)__|~~(.+?)~~|\*([^*\s](?:[^*]*[^*\s])?)\*|(https?:\/\/[^\s<>()（）]+)|(^|[\s(（，,])#(\d+)(?![\w-])/g;
  let last = 0, match;
  while ((match = pattern.exec(text))) {
    const [whole, code, label, href, strong, strong2, strike, em, bare, before, issue] = match;
    if (match.index > last) nodes.push(document.createTextNode(text.slice(last, match.index)));
    if (code !== undefined) nodes.push(markdownNode('code', [code]));
    else if (label !== undefined) nodes.push(markdownLink(href, markdownInline(label)));
    else if (strong !== undefined || strong2 !== undefined) nodes.push(markdownNode('strong', markdownInline(strong ?? strong2)));
    else if (strike !== undefined) nodes.push(markdownNode('del', markdownInline(strike)));
    else if (em !== undefined) nodes.push(markdownNode('em', markdownInline(em)));
    else if (bare !== undefined) {
      const url = bare.replace(/[.,;:!?'"。，；：！？、]+$/, '');
      nodes.push(markdownLink(url, [linkLabel(url)]));
      if (url.length < bare.length) nodes.push(document.createTextNode(bare.slice(url.length)));
    } else {
      if (before) nodes.push(document.createTextNode(before));
      nodes.push(markdownLink(REPOSITORY + '/issues/' + issue, ['#' + issue]));
    }
    last = match.index + whole.length;
  }
  if (last < text.length) nodes.push(document.createTextNode(text.slice(last)));
  return nodes;
}
function renderMarkdown(source) {
  const root = document.createDocumentFragment(), lines = String(source || '').replace(/\r\n?/g, '\n').split('\n');
  let paragraph = null, lists = [], match;
  const block = node => { paragraph = null; lists = []; root.append(node); };
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (/^\s*(```|~~~)/.test(line)) {
      const fence = line.trim().slice(0, 3), code = [];
      while (++i < lines.length && !lines[i].trim().startsWith(fence)) code.push(lines[i]);
      block(markdownNode('pre', [markdownNode('code', [code.join('\n')])]));
    } else if (!line.trim()) {
      paragraph = null;
    } else if ((match = line.match(/^\s{0,3}(#{1,6})\s+(.*?)(?:\s+#+)?\s*$/))) {
      block(markdownNode(match[1].length <= 2 ? 'h3' : 'h4', markdownInline(match[2])));
    } else if (/^\s{0,3}([-*_])(?:\s*\1){2,}\s*$/.test(line)) {
      block(document.createElement('hr'));
    } else if (/^\s{0,3}>/.test(line)) {
      const quote = [];
      for (; i < lines.length && (match = lines[i].match(/^\s{0,3}>\s?(.*)$/)); i++) quote.push(match[1]);
      i--;
      block(markdownNode('blockquote', [renderMarkdown(quote.join('\n'))]));
    } else if ((match = line.match(/^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/))) {
      paragraph = null;
      const indent = match[1].replace(/\t/g, '    ').length, ordered = /\d/.test(match[2]);
      while (lists.length > 1 && indent < lists.at(-1).indent) lists.pop();
      let top = lists.at(-1);
      const deeper = top && indent > top.indent && top.item;
      if (!top || deeper || top.list.tagName !== (ordered ? 'OL' : 'UL')) {
        // A deeper item nests; a numbered list after a bulleted one (or the reverse) starts beside it.
        const list = document.createElement(ordered ? 'ol' : 'ul'), parent = deeper ? top.item : top ? top.list.parentNode : root;
        if (ordered && parseInt(match[2], 10) !== 1) list.start = parseInt(match[2], 10);
        if (top && !deeper) lists.pop();
        parent.append(list);
        top = {indent, list, item: null};
        lists.push(top);
      }
      top.item = markdownNode('li', markdownInline(match[3]));
      top.list.append(top.item);
    } else if (lists.length && /^\s+\S/.test(line)) {
      lists.at(-1).item.append(document.createElement('br'), ...markdownInline(line.trim()));
    } else {
      lists = [];
      if (paragraph) paragraph.append(document.createElement('br'), ...markdownInline(line.trim()));
      else { paragraph = markdownNode('p', markdownInline(line.trim())); root.append(paragraph); }
    }
  }
  return root;
}

function askRelease(info) {
  return new Promise(resolve => {
    const dialog = $('#release-dialog');
    if (dialog.open) { resolve(false); return; }
    $('#release-title').textContent = 'Niu Gateway ' + releaseLabel(info.latest);
    $('#release-version').textContent = '当前版本 ' + releaseLabel(info.current);
    const notes = $('#release-notes');
    notes.replaceChildren(renderMarkdown(info.notes || '有新的 Niu Gateway 版本可用。'));
    const link = $('#release-link'), page = String(info.url || '');
    link.hidden = !page.startsWith(REPOSITORY + '/releases/');
    link.href = link.hidden ? REPOSITORY + '/releases' : page;
    const finish = value => { dialog.close(); dialog.oncancel = null; resolve(value); };
    $('#release-later').onclick = () => finish(false);
    $('#release-install').onclick = () => finish(true);
    dialog.oncancel = event => { event.preventDefault(); finish(false); };
    dialog.showModal();
    notes.scrollTop = 0;
    $('#release-later').focus();
  });
}

async function offerWebRelease(info) {
  if (!await askRelease(info)) return;
  if (!await discardChanges()) return;
  await guard(async () => {
    const task = await post('/web-release/install', {tag: info.latest});
    await followWebRelease(task);
  });
}

document.querySelector('#web-release-install').onclick = () => {
  if (latestWebRelease?.available) offerWebRelease(latestWebRelease).catch(e => toast(e.message, true));
};
