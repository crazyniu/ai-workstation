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
  $('#gateway-version').textContent = '网关 Web ' + current + ' · ' + latest;
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

async function offerWebRelease(info) {
  const title = '网关 Web ' + releaseLabel(info.latest);
  if (!await askConfirm((info.notes || '有新的网关管理页面可用。') +
      '\n\n升级时管理页会短暂重连。现在升级？', title)) return;
  if (!await discardChanges()) return;
  await guard(async () => {
    const task = await post('/web-release/install', {tag: info.latest});
    await followWebRelease(task);
  });
}

document.querySelector('#web-release-install').onclick = () => {
  if (latestWebRelease?.available) offerWebRelease(latestWebRelease).catch(e => toast(e.message, true));
};
