'use strict';

let liveSelector = {}, proxyModel, proxyTab = 'groups', pendingUpload = false, proxyGeneration = 0;
const entryTitles = {provider: '节点订阅', exit: '代理出口', binding: '网段绑定', group: '策略组', note: '出口备注'};

function showProxyMode(visual) {
  $('#proxy-fields').hidden = !visual;
  $('#config-editor').hidden = visual;
  $('#proxy-config-page').hidden = visual;
  for (const tab of $$('[data-proxy-tab]')) tab.setAttribute('aria-pressed', String(visual && tab.dataset.proxyTab === (proxyTab === 'group-domains' ? 'groups' : proxyTab)));
  $('#proxy-subscription').hidden = !visual || proxyTab !== 'providers';
  if (visual && proxyModel) renderProxyBrowser();
  $('#config-code').setAttribute('aria-pressed', String(!visual));
}

const proxyHistory = [];
let proxyWindow = null;
function navigateProxy(tab, group = '', restore = null) {
  if (!restore && proxyTab === tab && (!group || group === rulePolicy) && (tab === 'yaml') === !$('#config-editor').hidden) return;
  const wasCode = !$('#config-editor').hidden;
  if (!restore) proxyHistory.push({tab:wasCode ? 'yaml' : proxyTab, policy:rulePolicy, page:resultPage,
    search:$('#proxy-search').value, scroll:$('.proxy-canvas').scrollTop});
  resetProxyBrowser();
  proxyTab = tab;
  rulePolicy = restore?.policy ?? group;
  resultPage = restore?.page ?? 0;
  $('#proxy-search').value = restore?.search ?? '';
  if (tab === 'yaml') { showProxyMode(false); editor.focus?.(); }
  else if (wasCode) guard(openProxyVisual);
  else showProxyMode(true);
  $('.proxy-canvas').scrollTop = restore?.scroll ?? 0;
}
function backProxy() {
  if (busy) return;
  const previous = proxyHistory.pop();
  if (previous) navigateProxy(previous.tab, previous.policy, previous);
  else closeProxyWindow();
}

async function openProxyWindow(force = false, ranges = false) {
  const dialog = $('#proxy-window'), workspace = $('#proxy-workspace');
  if (dialog.open && !force) {
    focusGatewayWindow(proxyWindow);
    if (ranges) navigateProxy('bindings');
    return;
  }
  if (!dialog.open) {
    proxyHistory.length = 0;
    resetProxyBrowser();
    proxyTab = ranges ? 'bindings' : 'groups';
    proxyWindow = createGatewayWindow(dialog, 'Clash 配置编辑器', '/icons/clash.svg', closeProxyWindow);
  }
  const request = ++proxyGeneration;
  workspace.inert = true;
  const done = beginLoading(workspace);
  try {
    const [config, settings] = await Promise.all([api('/proxy/config'), api('/settings')]);
    if (request !== proxyGeneration) return;
    prefs = settings;
    pendingUpload = false;
    liveSelector = config.selector || {};
    revision = config.revision;
    savedConfig = config.content;
    editor.setValue(config.content);
    updateConfigState();
    await openProxyVisual(proxyTab !== 'yaml');
    if (request !== proxyGeneration) return;
    $('#subscription-url').value = prefs.subscription.url || '';
    $('#subscription-interval').value = prefs.subscription.interval_hours || 0;
    $('#subscription-status').textContent = prefs.subscription.error || '';
    $('#refresh-subscription').disabled = !prefs.subscription.url;
    workspace.inert = false;
  } catch (error) {
    if (request === proxyGeneration) { destroyProxyWindow(); toast(error.message, true); }
  } finally { done(); }
}

async function closeProxyWindow() {
  if (busy || !await discardChanges()) return;
  destroyProxyWindow();
}

function destroyProxyWindow() {
  ++proxyGeneration;
  ++domainRequest;
  savedConfig = null;
  $('#proxy-entry').close();
  if (proxyWindow) {
    const win = proxyWindow;
    proxyWindow = null;
    win.close(true);
  }
  $('#proxy-window').close();
}

async function openProxyVisual(visual = true) {
  const request = proxyGeneration, content = editor.getValue();
  try {
    const result = await post('/proxy/draft', {content, upload: pendingUpload});
    if (request !== proxyGeneration || content !== editor.getValue()) return;
    if (pendingUpload) { editor.setValue(result.content); pendingUpload = false; updateConfigState(); }
    proxyModel = result.model;
    showProxyMode(visual);
  } catch (error) {
    if (request !== proxyGeneration || content !== editor.getValue()) return;
    showProxyMode(false);
    toast(error.message, true);
  }
}

async function updateProxyDraft(edit) {
  const request = proxyGeneration, content = editor.getValue();
  const result = await post('/proxy/draft', {content, edit});
  if (request !== proxyGeneration || content !== editor.getValue()) return false;
  editor.setValue(result.content);
  proxyModel = result.model;
  if (!$('#proxy-fields').hidden) renderProxyBrowser();
  updateConfigState();
  return true;
}

function updateConfigState() {
  if (!$('#proxy-window').open || savedConfig === null) return;
  const dirty = configDirty();
  $('#config-filename').textContent = dirty ? 'config.yaml · 等待应用' : 'config.yaml · 当前正在使用';
  $('#config-code').textContent = dirty ? '配置 · 待应用' : '配置';
}

function proxyDialog(title, build) {
  const dialog = $('#proxy-entry'), form = $('#proxy-entry-form'), fields = $('#proxy-entry-fields');
  $('#proxy-entry-title').textContent = title;
  fields.replaceChildren();
  function field(name, caption, value, type = 'text', options = null) {
    const input = element(options ? 'select' : type === 'textarea' ? 'textarea' : 'input'), label = element('label', caption);
    input.name = name;
    input.id = 'proxy-entry-' + name;
    label.htmlFor = input.id;
    if (options) {
      for (const [key, text] of options) input.add(new Option(text, key));
    } else {
      if (type !== 'textarea') input.type = type;
      input.spellcheck = false;
      input.autocapitalize = 'none';
    }
    if (type === 'checkbox') {
      input.checked = Boolean(value);
      label.className = 'check';
      label.prepend(input);
    } else {
      input.value = value ?? '';
      label.append(input);
    }
    fields.append(label);
    return input;
  }
  const getEdit = build(field, fields);
  form.onsubmit = event => {
    event.preventDefault();
    const data = new FormData(form);
    guard(async () => {
      if (await updateProxyDraft(getEdit(data))) dialog.close();
    }, '#proxy-entry-fields');
  };
  dialog.showModal();
  fields.querySelector('input:not([readonly]), select, textarea')?.focus();
}

function openProxyEntry(kind, item) {
  proxyDialog((item ? '编辑' : '添加') + entryTitles[kind], (field, fields) => {
    if (kind === 'provider') {
      const name = field('name', '订阅名称', item?.name);
      name.readOnly = Boolean(item);
      name.required = true;
      field('url', '订阅地址（HTTP / HTTPS）', item?.url, 'url').required = true;
    } else if (kind === 'note') {
      field('note','出口备注',item['x-gateway-note'] || '');
    } else if (kind === 'exit') {
      field('name', '出口名称', item?.name).required = true;
      field('note', '出口备注', item?.['x-gateway-note'] || '');
      field('type', '协议', item?.type || 'http', 'text', [['http', 'HTTP'], ['socks5', 'SOCKS5']]);
      field('server', '服务器', item?.server).required = true;
      const port = field('port', '端口', item?.port, 'number');
      port.min = 1;
      port.max = 65535;
      port.required = true;
      field('username', '用户名', item?.username).autocomplete = 'off';
      field('password', '密码', item?.password, 'password').autocomplete = 'off';
      const dialers = new Set([proxyModel.targets.includes('🔗 PROXY-RELAY') && '🔗 PROXY-RELAY', item?.['dialer-proxy']].filter(Boolean));
      field('dialer-proxy', '前置代理', item ? item['dialer-proxy'] || '' : (dialers.has('🔗 PROXY-RELAY') ? '🔗 PROXY-RELAY' : ''), 'text', [['', '无'], ...[...dialers].map(n => [n, n])]);
      field('tls', '使用 TLS', item?.tls, 'checkbox');
    } else if (kind === 'group') {
      field('name','分组名称','').required = true;
      const routes = new Set([...proxyModel.deviceExits, ...proxyModel.groups.filter(g => ['🤖 PROXY','🔗 PROXY-RELAY'].includes(g.name)).map(g => g.name), 'DIRECT']);
      field('route','默认线路',routes.has('🤖 PROXY') ? '🤖 PROXY' : [...routes][0],
        'text',[...routes].map(n => [n,policyLabel(n)]));
    } else {
      const range = field('ip', '网段或单个 IP', item?.ip);
      range.placeholder = '192.168.1.240-249、192.168.1.0/24 或单个 IP';
      range.required = true;
      const targets = proxyModel.deviceExits;
      field('target', '固定出口', item?.target || '', 'text',
        [['', '选择出口'], ...targets.map(n => [n, n])]).required = true;
      field('note', '网段备注', item?.note || '');

    }
    return data => {
      const edit = Object.fromEntries(data);
      edit.kind = kind;
      if (kind === 'provider') edit.new = !item;
      if (kind === 'note') edit.name = item.name;
      if (kind === 'exit') {
        if (item) edit.original = item.name;
        edit.deviceExit = true;
      }
      if (kind === 'group') {
        edit.type = 'select';
        edit.proxies = [edit.route];
        edit.use = [];
      }
      if (kind === 'binding' && item) edit.id = item.id;
      return edit;
    };
  });
}

function setupProxyEditor() {
  for (const tab of $$('[data-proxy-tab]')) tab.onclick = () => navigateProxy(tab.dataset.proxyTab);
  $('#back-proxy').onclick = backProxy;
  $('#back-to-policy-groups').onclick = backProxy;
  $('#back-proxy-entry').onclick = () => $('#proxy-entry').close();
  setupProxyBrowser();
  $('#ai-default-exit').onchange = async event => {
    const target = event.target.value;
    const keyboardFocus = event.target.matches(':focus-visible');
    await guard(async () => {
      try { await updateProxyDraft({kind:'default-exit', target}); }
      finally { renderProxyBrowser(); }
    });
    if (keyboardFocus) $('#ai-default-exit input:checked')?.focus({preventScroll:true});
  };
  $('#config-code').onclick = () => navigateProxy('yaml');
  $('#proxy-entry-cancel').onclick = () => $('#proxy-entry').close();
  $('#proxy-window').oncancel = event => { event.preventDefault(); backProxy(); };
  $('#download-config').onclick = () => {
    const link = element('a'), blob = new Blob([editor.getValue()], {type: 'application/yaml;charset=utf-8'});
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = 'config.yaml';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
}
