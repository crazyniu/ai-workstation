'use strict';

let proxyModel, proxyTab = 'connections', pendingUpload = false;
const entryTitles = {provider: '节点订阅', exit: '代理出口', binding: '来源 IP 绑定'};

function showProxyMode(visual) {
  $('#proxy-fields').hidden = !visual;
  $('#config-editor').hidden = visual;
  for (const tab of $$('[data-proxy-tab]')) tab.setAttribute('aria-pressed', String(visual && tab.dataset.proxyTab === proxyTab));
  const connections = proxyTab === 'connections';
  for (const pane of $$('[data-proxy-pane]')) pane.hidden = !connections;
  $('#proxy-subscription').hidden = !visual || !connections;
  $('#proxy-browser').hidden = connections;
  if (visual && !connections) renderProxyBrowser();
  $('#config-code').setAttribute('aria-pressed', String(!visual));
}

function proxyRow(list, title, detail, actions) {
  const row = element('div', undefined, 'proxy-row');
  const info = element('div');
  info.append(element('strong', title), element('span', detail));
  const tools = element('div', undefined, 'proxy-row-actions');
  tools.append(...actions);
  row.append(info, tools);
  list.append(row);
}

function drawProxyModel(model) {
  proxyModel = model;
  const providers = $('#proxy-providers'), exits = $('#proxy-exits'), bindings = $('#proxy-bindings');
  for (const list of [providers, exits, bindings]) list.replaceChildren();
  const edit = (kind, item) => button('编辑', () => openProxyEntry(kind, item), 'text-button');
  for (const item of model.providers) {
    let host = '';
    try { host = new URL(item.url).host; } catch {}
    proxyRow(providers, item.name, host, [edit('provider', item)]);
  }
  for (const item of model.exits) {
    const protocol = item.type === 'http' && item.tls ? 'HTTPS' : item.type.toUpperCase();
    proxyRow(exits, item.name, protocol + ' · ' + item.server + ' · ' + item.port, [edit('exit', item)]);
  }
  for (const item of model.bindings) {
    const remove = button('解绑', () => guard(() => updateProxyDraft({kind: 'binding', id: item.id, remove: true})), 'text-button');
    proxyRow(bindings, item.ip, item.target, [edit('binding', item), remove]);
  }
  if (!model.providers.length) providers.append(element('p', '暂无 HTTP 订阅', 'muted'));
  if (!model.exits.length) exits.append(element('p', '暂无 HTTP 或 SOCKS5 出口', 'muted'));
  if (!model.bindings.length) bindings.append(element('p', '暂无来源 IP 绑定', 'muted'));
}

async function openProxyVisual(visual = true) {
  const request = navigation, content = editor.getValue();
  try {
    const result = await post('/proxy/draft', {content, upload: pendingUpload});
    if (request !== navigation || content !== editor.getValue()) return;
    if (pendingUpload) { editor.setValue(result.content); pendingUpload = false; }
    drawProxyModel(result.model);
    showProxyMode(visual);
  } catch (error) {
    if (request !== navigation || content !== editor.getValue()) return;
    showProxyMode(false);
    toast(error.message, true);
  }
}

async function updateProxyDraft(edit) {
  const request = navigation, content = editor.getValue();
  const result = await post('/proxy/draft', {content, edit});
  if (request !== navigation || content !== editor.getValue()) return false;
  editor.setValue(result.content);
  drawProxyModel(result.model);
  if (proxyTab !== 'connections') renderProxyBrowser();
  updateConfigState();
  return true;
}

function updateConfigState() {
  if (currentPage !== 'proxy' || savedConfig === null) return;
  $('#config-filename').textContent = configDirty() ? 'config.yaml · 等待应用' : 'config.yaml · 当前正在使用';
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
    } else if (kind === 'exit') {
      field('name', '出口名称', item?.name).required = true;
      field('type', '协议', item?.type || 'http', 'text', [['http', 'HTTP'], ['socks5', 'SOCKS5']]);
      field('server', '服务器', item?.server).required = true;
      const port = field('port', '端口', item?.port, 'number');
      port.min = 1;
      port.max = 65535;
      port.required = true;
      field('username', '用户名', item?.username).autocomplete = 'off';
      field('password', '密码', item?.password, 'password').autocomplete = 'off';
      const dialers = new Set([...proxyModel.targets, item?.['dialer-proxy']].filter(name => name && name !== item?.name));
      field('dialer-proxy', '前置代理', item?.['dialer-proxy'] || '', 'text', [['', '无'], ...[...dialers].map(n => [n, n])]);
      field('tls', '使用 TLS', item?.tls, 'checkbox');
      if (proxyModel.groups.length) {
        const choices = element('details', undefined, 'proxy-groups');
        choices.append(element('summary', '所属代理组'));
        for (const group of proxyModel.groups) {
          const label = element('label', undefined, 'check'), input = element('input');
          input.type = 'checkbox';
          input.name = 'groups';
          input.value = group.name;
          input.checked = group.members.includes(item?.name);
          label.append(input, group.name);
          choices.append(label);
        }
        fields.append(choices);
      }
    } else {
      field('ip', '来源 IP', item?.ip).required = true;
      const targets = new Set([...proxyModel.exits.map(n => n.name), ...proxyModel.targets, 'DIRECT', 'REJECT', item?.target].filter(Boolean));
      field('target', '出口', item?.target || '', 'text', [['', '选择出口'], ...[...targets].map(n => [n, n])]).required = true;
    }
    return data => {
      const edit = Object.fromEntries(data);
      edit.kind = kind;
      if (kind === 'provider') edit.new = !item;
      if (kind === 'exit') {
        if (item) edit.original = item.name;
        edit.groups = data.getAll('groups');
      }
      if (kind === 'binding' && item) edit.id = item.id;
      return edit;
    };
  });
}

function setupProxyEditor() {
  for (const tab of $$('[data-proxy-tab]')) tab.onclick = () => {
    if (proxyTab !== tab.dataset.proxyTab) resetProxyBrowser();
    proxyTab = tab.dataset.proxyTab;
    if ($('#proxy-fields').hidden) guard(openProxyVisual);
    else showProxyMode(true);
  };
  setupProxyBrowser();
  $('#config-code').onclick = () => { showProxyMode(false); editor.focus?.(); };
  $('#proxy-entry-cancel').onclick = () => $('#proxy-entry').close();
  $('#add-provider').onclick = () => openProxyEntry('provider');
  $('#add-exit').onclick = () => openProxyEntry('exit');
  $('#add-binding').onclick = () => openProxyEntry('binding');
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
