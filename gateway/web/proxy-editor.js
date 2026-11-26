'use strict';
// Visual editor for the gateway's Clash profile. It sends the same draft edits
// as the previous editor; every change stays a draft in the YAML editor until
// 应用 sends it through the server's importer.

const AI_POOL = '🤖 PROXY', RELAY = '🔗 PROXY-RELAY';
const hiddenGroups = new Set(['GLOBAL', 'AUTO', '订阅下载', 'PROXY-RELAY', 'PROXY']);
const domainTypes = {'DOMAIN-SUFFIX':'域名及子域名', DOMAIN:'完整域名', 'DOMAIN-KEYWORD':'包含关键词', 'DOMAIN-WILDCARD':'通配域名'};
const ruleLabels = {...domainTypes, 'IP-CIDR':'IPv4 网段', 'IP-CIDR6':'IPv6 网段', GEOIP:'IP 地区', GEOSITE:'域名分类',
  'RULE-SET':'规则集', MATCH:'兜底规则'};
const groupTints = ['blue', 'purple', 'pink', 'red', 'orange', 'yellow', 'green', 'teal'];

let liveSelector = {}, proxyModel = null, proxyTab = 'bindings', proxyGroup = '', pendingUpload = false;
let proxyGeneration = 0, proxyWindow = null, resultPage = 0, domainRequest = 0, searchTimer = null;
let ruleFilter = '', listSearch = '', listSize = 20;
try { listSize = [10, 20, 50, 100].includes(Number(localStorage.getItem('gateway-page-size'))) ? Number(localStorage.getItem('gateway-page-size')) : 20; } catch {}

const policyLabel = name => ({DIRECT:'直连', REJECT:'拦截', 'REJECT-DROP':'静默丢弃', [AI_POOL]:'AI', [RELAY]:'中转节点'})[name] || name;
const visibleGroup = name => !hiddenGroups.has(name.replace(/^[^\p{L}\p{N}]+/u, '').trim().toUpperCase());
const tintFor = name => groupTints[[...name].reduce((sum, c) => sum + c.codePointAt(0), 0) % groupTints.length];

function setStateDisabled(control, disabled) {
  control.dataset.stateDisabled = String(disabled);
  if (!busy) control.disabled = disabled;
}

// ---------- Window lifecycle ----------

async function openProxyWindow(force = false, ranges = false) {
  const dialog = $('#proxy-window'), workspace = $('#proxy-workspace');
  if (dialog.open && !force) {
    focusGatewayWindow(proxyWindow);
    if (ranges) navigateProxy('bindings');
    return;
  }
  if (!dialog.open) {
    proxyTab = 'bindings';
    proxyGroup = '';
    resultPage = 0;
    $('.proxy-layout').dataset.view = 'page';
    proxyWindow = createGatewayWindow(dialog, '代理配置', '/icons/clash.svg', closeProxyWindow,
      {toolbar:$('#proxy-toolbar'), app:'proxy', onCompact:syncProxyBack});
  }
  const request = ++proxyGeneration;
  workspace.inert = true;
  const done = beginLoading(workspace);
  try {
    const config = await api('/proxy/config');
    if (request !== proxyGeneration) return;
    pendingUpload = false;
    liveSelector = config.selector || {};
    revision = config.revision;
    savedConfig = config.content;
    editor.setValue(config.content);
    await openProxyVisual();
    if (request !== proxyGeneration) return;
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
  proxyModel = null;
  $('#proxy-entry').close();
  if (proxyWindow) {
    const win = proxyWindow;
    proxyWindow = null;
    releaseGatewayWindow(win);
  }
  $('#proxy-window').close();
}

function compactProxy() { return Boolean(proxyWindow?.window.classList.contains('is-compact')); }
function syncProxyBack() {
  const layout = $('.proxy-layout');
  if (!compactProxy()) layout.dataset.view = 'page';
  $('#proxy-back').hidden = !(proxyTab === 'group' || (compactProxy() && layout.dataset.view === 'page'));
}

function navigateProxy(tab, group = '') {
  const layout = $('.proxy-layout'), fromYaml = proxyTab === 'yaml' && tab !== 'yaml';
  if (tab !== proxyTab || group !== proxyGroup) {
    proxyTab = tab;
    proxyGroup = group;
    resultPage = 0;
    ruleFilter = '';
    listSearch = '';
  }
  layout.dataset.view = 'page';
  $('.proxy-canvas').scrollTop = 0;
  if (fromYaml) guard(openProxyVisual);
  else renderProxy();
  (tab === 'yaml' ? $('#config-title') : $('#proxy-page-title'))?.focus({preventScroll:true});
}

function backProxy() {
  if (busy) return;
  if (proxyTab === 'group') { navigateProxy('groups'); return; }
  const layout = $('.proxy-layout');
  if (compactProxy() && layout.dataset.view === 'page') {
    layout.dataset.view = 'menu';
    syncProxyBack();
    layout.querySelector('[data-proxy-tab].active')?.focus({preventScroll:true});
    return;
  }
  closeProxyWindow();
}

// ---------- Draft state ----------

async function openProxyVisual() {
  const request = proxyGeneration, content = editor.getValue();
  try {
    const result = await post('/proxy/draft', {content, upload: pendingUpload});
    if (request !== proxyGeneration || content !== editor.getValue()) return;
    if (result.content !== undefined) { editor.setValue(result.content); pendingUpload = false; }
    proxyModel = result.model;
    updateConfigState();
    renderProxy();
  } catch (error) {
    if (request !== proxyGeneration || content !== editor.getValue()) return;
    proxyTab = 'yaml';
    renderProxy();
    toast(error.message, true);
  }
}

async function updateProxyDraft(edits) {
  const request = proxyGeneration, content = editor.getValue();
  let result = {content};
  for (const edit of [].concat(edits)) result = await post('/proxy/draft', {content:result.content, edit});
  if (request !== proxyGeneration || content !== editor.getValue()) return false;
  editor.setValue(result.content);
  proxyModel = result.model;
  updateConfigState();
  renderProxy();
  return true;
}

function updateConfigState() {
  if (!$('#proxy-window').open || savedConfig === null) return;
  const dirty = configDirty() || pendingUpload;
  $('#proxy-change-state').textContent = dirty ? '有未应用的更改' : '';
  $('#config-filename').textContent = dirty ? 'config.yaml · 有未应用的更改' : 'config.yaml · 正在使用';
  setStateDisabled($('#save-config'), !dirty);
  setStateDisabled($('#discard-config'), !dirty);
  $('#config-code').classList.toggle('is-dirty', dirty);
}

async function applyProxyConfig() {
  const request = proxyGeneration;
  const draft = await post('/proxy/draft', {content: editor.getValue(), upload: pendingUpload});
  if (request !== proxyGeneration) return;
  if (draft.content !== undefined) editor.setValue(draft.content);
  pendingUpload = false;
  const result = await post('/proxy/config', {filename:'config.yaml', content:editor.getValue(), revision, edit_network:true});
  const saved = await api('/proxy/config');
  if (request !== proxyGeneration) return;
  revision = saved.revision;
  savedConfig = saved.content;
  liveSelector = saved.selector || {};
  editor.setValue(saved.content);
  await openProxyVisual();
  toast(result.message || '配置已应用。');
  await loadStatus();
}

async function discardProxyChanges() {
  if (!await askConfirm('放弃所有尚未应用的更改，恢复为网关正在使用的配置？', '放弃更改', {accept:'放弃', danger:true})) return;
  pendingUpload = false;
  editor.setValue(savedConfig);
  await openProxyVisual();
  toast('已恢复为正在使用的配置。');
}

// ---------- Building blocks ----------

function selectInput(options, value = '') {
  const select = element('select');
  const add = (parent, [key, label]) => parent.append(new Option(label, key));
  for (const item of options) {
    if (item.options) {
      const group = element('optgroup');
      group.label = item.label;
      item.options.forEach(option => add(group, option));
      select.append(group);
    } else add(select, item);
  }
  if (value && ![...select.options].some(option => option.value === value)) add(select, [value, policyLabel(value)]);
  select.value = value;
  return select;
}

function labeledButton(symbol, text, handler, className = '') {
  const control = button('', handler, className);
  control.append(glyph(symbol), element('span', text));
  return control;
}

function routeChip(name) {
  const chip = element('span', undefined, 'route-chip');
  chip.dataset.kind = name === 'DIRECT' ? 'direct' : name === 'REJECT' ? 'reject' : proxyModel.deviceExits.includes(name) ? 'exit' : 'policy';
  chip.append(glyph('arrow-right'), element('span', policyLabel(name) || '未设置'));
  chip.title = '出口：' + (policyLabel(name) || '未设置');
  return chip;
}

function statusPill(label, tone) {
  const pill = element('span', label, 'status-pill');
  pill.dataset.tone = tone;
  return pill;
}

function listRow({symbol = '', tint = 'gray', title, subtitle = '', mono = false, lead = null, trailing = [], actions = [], open = null, label = ''}) {
  const row = element('div', undefined, 'list-row');
  if (lead) row.append(lead);
  else if (symbol) {
    const mark = element('span', undefined, 'row-symbol');
    mark.dataset.tint = tint;
    mark.append(glyph(symbol));
    row.append(mark);
  }
  const copy = element('div', undefined, 'row-copy');
  copy.append(element('strong', title, mono ? 'mono' : undefined));
  if (subtitle) copy.append(element('span', subtitle));
  row.append(copy, ...trailing.filter(Boolean));
  if (actions.length) {
    const tools = element('div', undefined, 'row-actions');
    tools.append(...actions);
    row.append(tools);
  }
  if (open) {
    const link = button('', open, 'row-open');
    link.setAttribute('aria-label', label || '打开 ' + title);
    link.append(glyph('chevron-right'));
    row.append(link);
    row.classList.add('is-link');
    row.addEventListener('click', event => {
      if (!event.target.closest('button, a, input, select, label, textarea')) link.click();
    });
  }
  return row;
}

function emptyState(title, detail) {
  const empty = element('div', undefined, 'empty-state');
  empty.append(element('strong', title), element('span', detail));
  return empty;
}

function listCard(rows, empty) {
  const card = element('div', undefined, 'card list-card');
  card.append(...(rows.length ? rows : [empty]));
  return card;
}

function callout(text, tone = '', action = null) {
  const box = element('div', undefined, 'callout' + (tone ? ' ' + tone : ''));
  box.append(element('span', text));
  if (action) box.append(button(action[0], action[1], 'text-button'));
  return box;
}

function pane(title, intro, actions = []) {
  const page = $('#proxy-page');
  page.replaceChildren();
  const header = element('header', undefined, 'pane-header'), copy = element('div'), heading = element('h2', title);
  heading.id = 'proxy-page-title';
  heading.tabIndex = -1;
  copy.append(heading);
  if (intro) copy.append(element('p', intro));
  header.append(copy);
  if (actions.length) {
    const box = element('div', undefined, 'pane-actions');
    box.append(...actions);
    header.append(box);
  }
  page.append(header);
  return page;
}

function groupTitle(text) { return element('h3', text, 'group-title'); }

function pager(total, redraw) {
  const pages = Math.max(1, Math.ceil(total / listSize));
  resultPage = Math.min(resultPage, pages - 1);
  if (total <= 10) return null;
  const bar = element('div', undefined, 'pager');
  const size = selectInput([10, 20, 50, 100].map(n => [String(n), n + ' 条/页']), String(listSize));
  size.setAttribute('aria-label', '每页显示数量');
  size.onchange = () => {
    listSize = Number(size.value);
    try { localStorage.setItem('gateway-page-size', size.value); } catch {}
    resultPage = 0;
    redraw();
  };
  const turn = step => () => { resultPage += step; redraw(); $('.proxy-canvas').scrollTop = 0; };
  const prev = iconButton('chevron-left', '上一页', turn(-1)), next = iconButton('chevron-right', '下一页', turn(1));
  setStateDisabled(prev, resultPage === 0);
  setStateDisabled(next, resultPage >= pages - 1);
  bar.append(size, element('span', undefined, 'toolbar-spacer'), prev, element('span', (resultPage + 1) + ' / ' + pages, 'pager-label'), next);
  return bar;
}

function pagedList(container, rows, empty, redraw) {
  const start = resultPage * listSize;
  const bar = pager(rows.length, redraw);
  container.append(listCard(rows.slice(resultPage * listSize, resultPage * listSize + listSize), empty));
  if (bar) container.append(bar);
  return start;
}

function searchField(placeholder, onSearch) {
  const label = element('label', undefined, 'search-field');
  const input = element('input');
  input.type = 'search';
  input.placeholder = placeholder;
  input.autocomplete = 'off';
  input.spellcheck = false;
  input.value = listSearch;
  input.setAttribute('aria-label', placeholder);
  input.oninput = () => {
    listSearch = input.value;
    resultPage = 0;
    clearTimeout(searchTimer);
    ++domainRequest;
    searchTimer = setTimeout(onSearch, 160);
  };
  label.append(glyph('search'), input);
  return label;
}

// ---------- Routing choices ----------

function aiMembers() { return proxyModel.groups.find(g => g.name === AI_POOL)?.members || []; }
function aiExit() {
  const pool = (proxyModel.options['proxy-groups'] || []).find(g => g.name === AI_POOL) || {}, members = aiMembers();
  return pool['default-selected'] || (members.includes(liveSelector.now) ? liveSelector.now : members[0] || '');
}
function groupExit(group) { return group.name === AI_POOL ? aiExit() : group.exit; }
function siteGroups() {
  const groups = proxyModel.groups.filter(g => visibleGroup(g.name));
  const ai = proxyModel.groups.find(g => g.name === AI_POOL);
  return ai ? [ai, ...groups] : groups;
}

function routeOptions(self = '') {
  if (self === AI_POOL) return aiMembers().map(name => [name, policyLabel(name)]);
  const has = name => proxyModel.targets.includes(name);
  return [
    {label:'常用', options:[['DIRECT', '直连'], ...(has(RELAY) ? [[RELAY, '中转节点']] : []), ...(has(AI_POOL) && self !== AI_POOL ? [[AI_POOL, 'AI 分组的出口']] : [])]},
    {label:'出口', options:proxyModel.deviceExits.map(name => [name, name])},
    {label:'分组', options:proxyModel.groups.map(g => g.name).filter(name => ![self, AI_POOL, RELAY].includes(name)).map(name => [name, name])},
    {label:'其他', options:[['REJECT', '拦截']]},
  ].filter(group => group.options.length);
}

function groupRoutes() {
  const groups = proxyModel.groups.map(g => g.name);
  return [...proxyModel.deviceExits, ...[AI_POOL, RELAY].filter(name => groups.includes(name)), 'DIRECT'];
}
function groupRouteOptions(current = '') {
  const groups = proxyModel.groups.map(g => g.name), common = [...[AI_POOL, RELAY].filter(name => groups.includes(name)), 'DIRECT'];
  const label = name => name === AI_POOL ? 'AI 分组的出口' : policyLabel(name);
  const options = [{label:'常用', options:common.map(name => [name, label(name)])},
    {label:'出口', options:proxyModel.deviceExits.map(name => [name, name])}];
  if (current && !groupRoutes().includes(current)) options.push({label:'当前', options:[[current, label(current)]]});
  return options.filter(group => group.options.length);
}

function routeHint(name) {
  if (name === 'DIRECT') return '不经过代理，直接访问';
  if (name === 'REJECT') return '阻止访问';
  if (name === RELAY) return '使用中转订阅里的节点';
  if (name === AI_POOL) return '跟随 AI 分组的出口';
  if (proxyModel.deviceExits.includes(name)) return '从该出口访问';
  return name ? '跟随分组「' + name + '」的出口' : '尚未设置';
}

// ---------- Pages ----------

function renderProxy() {
  if (!proxyModel) return;
  ++domainRequest;
  const yaml = proxyTab === 'yaml', active = proxyTab === 'group' ? 'groups' : proxyTab;
  $('#proxy-page').hidden = yaml;
  $('#proxy-config-page').hidden = !yaml;
  $('#config-editor').hidden = !yaml;
  for (const tab of $$('[data-proxy-tab]')) {
    const on = tab.dataset.proxyTab === active;
    tab.classList.toggle('active', on);
    if (on) tab.setAttribute('aria-current', 'page');
    else tab.removeAttribute('aria-current');
  }
  syncProxyBack();
  ({bindings:drawBindings, groups:drawGroups, group:drawGroup, exits:drawExits, providers:drawProviders, rules:drawRules})[proxyTab]?.();
}

function setupNotice(page) {
  if (!proxyModel.deviceExits.length) page.append(callout('还没有出口。先添加一个 HTTP 或 SOCKS5 出口，再为设备或分组选择它。', 'warn', ['添加出口', () => navigateProxy('exits')]));
  else if (!proxyModel.relayReady) page.append(callout('还没有中转订阅，经中转的出口暂时无法连通。', 'warn', ['添加中转订阅', () => navigateProxy('providers')]));
}

function drawBindings() {
  const page = pane('设备出口', '为单个 IP 或 IP 段指定出口。这些设备访问互联网的全部流量都从所选出口发出；访问局域网不受影响。',
    [labeledButton('plus', '添加设备', () => editBinding(), 'primary')]);
  setupNotice(page);
  const rows = proxyModel.bindings.map(b => listRow({symbol:'devices', tint:'blue', title:b.ip, mono:true, subtitle:b.note || '未备注',
    trailing:[routeChip(b.target)],
    actions:[iconButton('edit', '编辑 ' + b.ip, () => editBinding(b)),
      iconButton('trash', '删除 ' + b.ip, () => guard(() => updateProxyDraft({kind:'binding', id:b.id, remove:true})), 'danger')]}));
  pagedList(page, rows, emptyState('还没有指定出口的设备', '添加 IP 或 IP 段后，这些设备会从所选出口访问互联网。'), renderProxy);
  const other = element('p', undefined, 'pane-note');
  other.append('其他设备按「分组」访问网站，未匹配任何分组的流量使用「其他网站」的设置。 ', button('查看分组', () => navigateProxy('groups'), 'text-button'));
  page.append(other);
}

function drawGroups() {
  const page = pane('分组', '把网站按用途分组（例如 Google、YouTube），为每个分组选择出口。未在「设备出口」中列出的设备按分组访问网站。',
    [labeledButton('plus', '添加分组', () => editGroup(), 'primary')]);
  setupNotice(page);
  const rows = siteGroups().map(g => {
    const ai = g.name === AI_POOL, enabled = !proxyModel.disabledGroups.includes(g.name);
    const counts = [g.domains && g.domains + ' 个域名', g.ruleSets && g.ruleSets + ' 个规则集', g.otherRules && g.otherRules + ' 条其他规则']
      .filter(Boolean).join(' · ') || '还没有域名';
    return listRow({symbol:ai ? 'sparkles' : 'globe', tint:ai ? 'indigo' : tintFor(g.name), title:ai ? 'AI' : g.name,
      subtitle:(enabled ? '' : '已关闭 · ') + counts, trailing:[routeChip(groupExit(g)), ai ? null : groupSwitch(g, enabled)],
      open:() => navigateProxy('group', g.name), label:'查看分组 ' + (ai ? 'AI' : g.name)});
  });
  page.append(listCard(rows, emptyState('还没有分组', '添加分组后，为它填写域名并选择出口。')));
  page.append(groupTitle('其他网站'), listCard([fallbackRow()]));
}

function fallbackRow() {
  const rules = proxyModel.options.rules || [], index = rules.findIndex(rule => readRule(rule).type === 'MATCH');
  const current = index < 0 ? '' : readRule(rules[index]).target;
  const select = selectInput(routeOptions(), current);
  select.setAttribute('aria-label', '其他网站的出口');
  if (!current) select.prepend(new Option('未设置', '', true, true));
  select.onchange = () => guard(async () => {
    try {
      await updateProxyDraft({kind:'rule', path:['rules'], index:index < 0 ? null : index, type:'MATCH', operand:'', target:select.value,
        flags:[], position:index < 0 ? rules.length + 1 : index + 1});
    } finally { renderProxy(); }
  });
  return listRow({symbol:'globe', tint:'gray', title:'未匹配任何分组的流量', subtitle:routeHint(current), trailing:[select]});
}

function groupSwitch(group, enabled) {
  const label = element('label', undefined, 'switch'), input = element('input'), track = element('span', undefined, 'switch-track');
  input.type = 'checkbox';
  input.setAttribute('role', 'switch');
  input.checked = enabled;
  input.setAttribute('aria-label', '启用分组 ' + group.name);
  track.setAttribute('aria-hidden', 'true');
  input.onchange = () => {
    const next = input.checked;
    input.checked = enabled;
    guard(() => updateProxyDraft({kind:'toggle-group', name:group.name, enabled:next}));
  };
  label.append(input, track);
  return label;
}

function drawGroup() {
  const group = proxyModel.groups.find(g => g.name === proxyGroup);
  if (!group) { proxyTab = 'groups'; drawGroups(); return; }
  const ai = group.name === AI_POOL, enabled = !proxyModel.disabledGroups.includes(group.name), route = groupExit(group);
  const actions = ai ? [] : [labeledButton('edit', '重命名', () => renameGroup(group)), labeledButton('trash', '删除分组', () => deleteGroup(group), 'danger')];
  const page = pane(ai ? 'AI' : group.name, ai ? 'OpenAI、Claude 等 AI 服务的域名使用这里选择的出口。' : '访问下列域名时，使用这个分组的出口。', actions);
  const select = selectInput(ai ? routeOptions(AI_POOL) : groupRouteOptions(route), route);
  select.setAttribute('aria-label', '分组出口');
  setStateDisabled(select, group.type !== 'select');
  select.onchange = () => guard(async () => {
    try {
      await updateProxyDraft(ai ? {kind:'default-exit', target:select.value} : {kind:'group', original:group.name, name:group.name,
        type:group.type, proxies:[select.value, ...group.members.filter(member => member !== select.value)], use:group.use});
    } finally { renderProxy(); }
  });
  const rows = [listRow({symbol:'arrow-right', tint:'green', title:'出口', subtitle:group.type === 'select' ? routeHint(route) : '自动选择的分组由 Clash 测速决定出口', trailing:[select]})];
  if (!ai) rows.push(listRow({symbol:'layers', tint:'gray', title:'启用分组', subtitle:'关闭后，这些域名改用「其他网站」的设置', trailing:[groupSwitch(group, enabled)]}));
  page.append(listCard(rows));
  if (!ai && group.type === 'select') page.append(element('p', '这里设置的是分组的默认出口。如果在 Clash 面板里为这个分组手动选过节点，以手动选择为准。', 'pane-note'));
  const tools = element('div', undefined, 'list-toolbar');
  tools.append(searchField('搜索域名', drawDomains), labeledButton('plus', '添加域名', () => addDomains(group.name)));
  const results = element('div');
  results.id = 'group-domains';
  page.append(groupTitle('域名'), tools, results);
  drawDomains();
}

async function drawDomains() {
  const request = ++domainRequest, model = proxyModel, group = proxyGroup, results = $('#group-domains');
  if (!results) return;
  results.setAttribute('aria-busy', 'true');
  try {
    const data = await post('/proxy/draft', {content:editor.getValue(), domainPage:{group, search:listSearch.trim().toLowerCase(), page:resultPage, limit:listSize}});
    if (request !== domainRequest || model !== proxyModel || proxyTab !== 'group' || group !== proxyGroup) return;
    const pages = Math.max(1, Math.ceil(data.total / listSize));
    if (resultPage > pages - 1) { resultPage = pages - 1; drawDomains(); return; }
    const rows = data.rows.map(item => listRow({title:item.domain, mono:true,
      subtitle:domainTypes[item.type] + (item.provider ? ' · 来自规则集 ' + item.provider : ''),
      actions:[iconButton('edit', '编辑 ' + item.domain, () => editMatch(item, group)),
        iconButton('trash', (item.provider ? '排除 ' : '移除 ') + item.domain, () => removeMatch(item, group), 'danger')]}));
    results.replaceChildren(listCard(rows, emptyState(listSearch ? '没有匹配的域名' : '还没有域名', listSearch ? '换个关键词试试。' : '添加域名后，访问这些网站会使用这个分组的出口。')));
    const bar = pager(data.total, drawDomains);
    if (bar) results.append(bar);
    if (data.missing.length) results.append(callout('以下规则集尚未下载，应用配置后才能列出其中的域名：' + data.missing.join('、')));
  } catch (error) {
    if (request === domainRequest) results.replaceChildren(callout(error.message, 'error'));
  } finally {
    if (request === domainRequest) results.removeAttribute('aria-busy');
  }
}

function drawExits() {
  const page = pane('出口', '出口是固定 IP 的 HTTP 或 SOCKS5 代理（例如住宅 IP）。新出口默认经由中转节点连接。',
    [labeledButton('plus', '添加出口', () => editExit(), 'primary')]);
  page.append(routeDiagram());
  if (!proxyModel.relayReady) page.append(callout('还没有中转订阅，经中转的出口暂时无法连通。', 'warn', ['添加中转订阅', () => navigateProxy('providers')]));
  const nodes = new Map((proxyModel.options.proxies || []).map(node => [node.name, node]));
  const rows = proxyModel.deviceExits.map(name => nodes.get(name)).filter(Boolean).map(node => {
    const editable = ['http', 'socks5'].includes(node.type), dialer = node['dialer-proxy'] || '';
    const devices = proxyModel.bindings.filter(b => b.target === node.name).length;
    const detail = [node.type?.toUpperCase(), node.server && node.server + ':' + node.port, node['x-gateway-note']].filter(Boolean).join(' · ');
    return listRow({symbol:'server', tint:'green', title:node.name, subtitle:detail,
      trailing:[devices ? element('span', devices + ' 台设备', 'row-meta') : null, dialer ? statusPill(dialer === RELAY ? '经中转' : '经 ' + policyLabel(dialer), 'ok') : statusPill('未经中转', 'warn')],
      actions:[iconButton('edit', '编辑 ' + node.name, () => editable ? editExit(node) : editExitNote(node)),
        editable ? iconButton('trash', '删除 ' + node.name, () => deleteExit(node), 'danger') : null].filter(Boolean)});
  });
  page.append(listCard(rows, emptyState('还没有出口', '添加住宅 IP 等固定出口后，就可以把它指定给设备或分组。')));
  if (rows.some(row => row.querySelector('[data-tone=warn]'))) page.append(element('p', '「未经中转」的出口由网关直接连接。需要经过中转时，编辑出口并在「前置代理」中选择中转节点。', 'pane-note'));
}

function routeDiagram() {
  const chain = element('div', undefined, 'route-diagram');
  chain.setAttribute('aria-label', '连接路径：设备，中转节点，出口，互联网');
  [['devices', '设备', 'blue'], ['relay', '中转节点', 'orange'], ['server', '出口', 'green'], ['globe', '互联网', 'gray']].forEach(([symbol, text, tint], index) => {
    if (index) chain.append(glyph('arrow-right'));
    const step = element('span', undefined, 'route-step'), mark = element('span', undefined, 'row-symbol');
    mark.dataset.tint = tint;
    mark.append(glyph(symbol));
    step.append(mark, element('span', text));
    chain.append(step);
  });
  return chain;
}

function drawProviders() {
  const page = pane('中转订阅', '中转节点来自机场订阅，设置了前置代理的出口经由这些节点连接。需要切换具体的中转节点时，在 Clash 面板中选择「🔗 PROXY-RELAY」。',
    [labeledButton('window', 'Clash 面板', () => openFrameApp('panel')), labeledButton('plus', '添加订阅', () => editProvider(), 'primary')]);
  const rows = Object.entries(proxyModel.options['proxy-providers'] || {}).map(([name, provider]) => {
    let source = provider.type;
    try { source = new URL(provider.url).host; } catch {}
    return listRow({symbol:'relay', tint:'orange', title:name, subtitle:source,
      actions:[provider.type === 'http' ? iconButton('edit', '编辑 ' + name, () => editProvider({...provider, name})) : null,
        iconButton('trash', '删除 ' + name, () => guard(async () => {
          if (!await askConfirm('删除中转订阅「' + name + '」？出口将无法使用这个订阅里的节点。', '删除中转订阅', {accept:'删除', danger:true})) return;
          await updateProxyDraft({kind:'provider', name, remove:true});
        }), 'danger')].filter(Boolean)});
  });
  page.append(listCard(rows, emptyState('还没有中转订阅', '添加机场订阅地址后，出口就能经由订阅中的节点连接。')));
}

function readRule(text) {
  const parts = text.split(','), type = parts.shift().trim(), flags = [];
  while (parts.length > (type === 'MATCH' ? 1 : 2) && ['no-resolve', 'dst', 'src'].includes(parts.at(-1).trim())) flags.unshift(parts.pop().trim());
  return {type, target:parts.pop()?.trim(), domain:parts.join(',').trim(), flags};
}

function ruleEntries() {
  const bound = new Set();
  for (const b of proxyModel.bindings) for (let i = b.id; i < b.end; i++) bound.add(i);
  return (proxyModel.options.rules || []).map((text, index) => ({...readRule(text), index, path:['rules']}))
    .filter(rule => !bound.has(rule.index) && Object.hasOwn(ruleLabels, rule.type));
}

function drawRules() {
  const page = pane('全部规则', '规则从上到下依次匹配，命中第一条即停止。设备出口的规则由「设备出口」管理，不在此列出。',
    [labeledButton('plus', '添加规则', () => editMatch(null), 'primary')]);
  const entries = ruleEntries();
  const targets = [...new Set(entries.map(rule => rule.target).filter(Boolean))];
  const filter = selectInput([['', '全部出口'], ...targets.map(name => [name, policyLabel(name)])], ruleFilter);
  filter.setAttribute('aria-label', '按出口筛选');
  filter.onchange = () => { ruleFilter = filter.value; resultPage = 0; renderProxy(); };
  const tools = element('div', undefined, 'list-toolbar');
  tools.append(searchField('搜索规则', renderProxy), filter);
  page.append(tools);
  const query = listSearch.trim().toLowerCase();
  const shown = entries.filter(rule => (!ruleFilter || rule.target === ruleFilter) && (!query || (rule.domain + ' ' + rule.type).toLowerCase().includes(query)));
  const rows = shown.map(rule => {
    const position = entries.indexOf(rule), prev = entries[position - 1], next = entries[position + 1];
    const up = iconButton('up', '上移第 ' + (rule.index + 1) + ' 条', () => moveRule(rule, prev)), down = iconButton('down', '下移第 ' + (rule.index + 1) + ' 条', () => moveRule(rule, next));
    setStateDisabled(up, !prev || rule.type === 'MATCH');
    setStateDisabled(down, !next || rule.type === 'MATCH' || next.type === 'MATCH');
    const order = element('span', String(rule.index + 1), 'rule-order');
    return listRow({lead:order, title:rule.type === 'MATCH' ? '其余所有流量' : rule.domain, mono:rule.type !== 'MATCH',
      subtitle:ruleLabels[rule.type] + (rule.flags.length ? ' · ' + rule.flags.join(' ') : ''), trailing:[routeChip(rule.target)],
      actions:[up, down, iconButton('edit', '编辑第 ' + (rule.index + 1) + ' 条规则', () => editMatch(rule)),
        iconButton('trash', '删除第 ' + (rule.index + 1) + ' 条规则', () => removeMatch(rule), 'danger')]});
  });
  pagedList(page, rows, emptyState(query || ruleFilter ? '没有匹配的规则' : '还没有规则', query || ruleFilter ? '换个条件试试。' : '添加规则以决定流量的出口。'), renderProxy);
}

function moveRule(rule, neighbor) {
  if (!neighbor) return;
  // The same request as changing 匹配顺序 in the rule dialog.
  return guard(() => updateProxyDraft({kind:'rule', path:rule.path, index:rule.index, type:rule.type, operand:rule.domain,
    target:rule.target, flags:rule.flags, position:neighbor.index + 1, originalType:rule.type, originalDomain:rule.domain}));
}

// ---------- Dialogs ----------

function proxyDialog({title, intro = '', submit = '完成', build, done = null}) {
  const dialog = $('#proxy-entry'), form = $('#proxy-entry-form'), fields = $('#proxy-entry-fields');
  $('#proxy-entry-title').textContent = title;
  $('#proxy-entry-submit').textContent = submit;
  $('#proxy-entry-intro').textContent = intro;
  $('#proxy-entry-intro').hidden = !intro;
  fields.replaceChildren();
  function field(name, caption, value, {type = 'text', options = null, placeholder = '', hint = '', required = false, wide = false, rows = 5} = {}) {
    const wrap = element('label', undefined, type === 'checkbox' ? 'check' : 'field');
    let input;
    if (options) input = selectInput(options, value ?? '');
    else if (type === 'textarea') { input = element('textarea'); input.rows = rows; }
    else { input = element('input'); input.type = type; }
    input.name = name;
    input.id = 'proxy-entry-' + name;
    input.required = required;
    input.setAttribute('aria-label', caption);
    if (!options) { input.spellcheck = false; input.autocapitalize = 'none'; input.autocomplete = 'off'; }
    if (placeholder) input.placeholder = placeholder;
    if (type === 'checkbox') { input.checked = Boolean(value); wrap.append(input, element('span', caption)); }
    else {
      if (!options) input.value = value ?? '';
      wrap.append(element('span', caption), input);
      if (hint) wrap.append(element('small', hint, 'field-hint'));
    }
    if (wide || type === 'textarea') wrap.classList.add('wide');
    fields.append(wrap);
    return input;
  }
  const note = (text, tone = '') => { const item = element('p', text, 'field-note wide' + (tone ? ' ' + tone : '')); fields.append(item); return item; };
  const getEdit = build(field, note);
  form.onsubmit = event => {
    event.preventDefault();
    const data = Object.fromEntries(new FormData(form));
    guard(async () => {
      const edit = getEdit(data);
      if (edit && await updateProxyDraft(edit)) { dialog.close(); done?.([].concat(edit)[0]); }
    }, '#proxy-entry-fields');
  };
  dialog.showModal();
  fields.querySelector('input:not([readonly]), select, textarea')?.focus();
}

function editBinding(item = null) {
  if (!proxyModel.deviceExits.length) { toast('请先在「出口」中添加出口。', true); return; }
  proxyDialog({title:item ? '编辑设备出口' : '添加设备', submit:item ? '保存' : '添加',
    intro:'这些设备访问互联网的全部流量都从所选出口发出。',
    build:field => {
      field('ip', 'IP 或 IP 段', item?.ip, {required:true, wide:true, placeholder:'192.168.1.20', hint:'支持单个 IP、起止范围（192.168.1.20-29）和网段（192.168.1.0/24）。'});
      field('target', '出口', item?.target || proxyModel.deviceExits[0], {required:true, options:proxyModel.deviceExits.map(name => [name, name])});
      field('note', '备注', item?.note, {placeholder:'例如：书房电脑'});
      return data => ({kind:'binding', ip:data.ip, target:data.target, note:data.note, ...(item ? {id:item.id} : {})});
    }});
}

function editExit(item = null) {
  proxyDialog({title:item ? '编辑出口' : '添加出口', submit:item ? '保存' : '添加',
    intro:'填写出口代理的连接信息。',
    build:field => {
      field('name', '名称', item?.name, {required:true, placeholder:'例如：美国住宅 01'});
      field('note', '备注', item?.['x-gateway-note'] || '', {placeholder:'可选'});
      field('type', '协议', item?.type || 'http', {options:[['http', 'HTTP'], ['socks5', 'SOCKS5']]});
      const port = field('port', '端口', item?.port, {type:'number', required:true, placeholder:'8080'});
      port.min = 1;
      port.max = 65535;
      field('server', '服务器', item?.server, {required:true, wide:true, placeholder:'IP 地址或域名'});
      field('username', '用户名', item?.username, {placeholder:'可选'});
      field('password', '密码', item?.password, {type:'password', placeholder:'可选'});
      const dialers = new Set([proxyModel.targets.includes(RELAY) && RELAY, item?.['dialer-proxy']].filter(Boolean));
      field('dialer-proxy', '前置代理', item ? item['dialer-proxy'] || '' : (dialers.has(RELAY) ? RELAY : ''),
        {options:[['', '无（直接连接）'], ...[...dialers].map(name => [name, policyLabel(name)])], hint:'选择中转节点时：设备 → 中转节点 → 该出口 → 互联网。'});
      field('tls', '使用 TLS 加密连接出口', item?.tls, {type:'checkbox'});
      return data => ({kind:'exit', ...data, tls:data.tls === 'on', deviceExit:true, ...(item ? {original:item.name} : {})});
    }});
}

function editExitNote(item) {
  proxyDialog({title:'编辑备注', submit:'保存', build:field => {
    field('note', '出口备注', item['x-gateway-note'] || '', {wide:true});
    return data => ({kind:'note', name:item.name, note:data.note});
  }});
}

function deleteExit(item) {
  return guard(async () => {
    const devices = proxyModel.bindings.filter(b => b.target === item.name).length;
    if (devices) { toast('「' + item.name + '」仍被 ' + devices + ' 台设备使用。请先在「设备出口」中为它们改用其他出口。', true); return; }
    if (!await askConfirm('删除出口「' + item.name + '」？', '删除出口', {accept:'删除', danger:true})) return;
    await updateProxyDraft({kind:'exit', original:item.name, remove:true});
  });
}

function editProvider(item = null) {
  proxyDialog({title:item ? '编辑中转订阅' : '添加中转订阅', submit:item ? '保存' : '添加',
    intro:'填写机场提供的 Clash / Mihomo 订阅地址。订阅中的节点会作为中转节点。',
    build:field => {
      const name = field('name', '名称', item?.name, {required:true, placeholder:'例如：机场 A'});
      name.readOnly = Boolean(item);
      field('url', '订阅地址', item?.url, {type:'url', required:true, wide:true, placeholder:'https://'});
      return data => ({kind:'provider', name:data.name, url:data.url, new:!item});
    }});
}

function domainFields(field) {
  field('domains', '域名', '', {type:'textarea', rows:5, placeholder:'google.com\nyoutube.com', hint:'每行一个，也可以用空格或逗号分隔；可以直接粘贴网址。'});
  field('match', '匹配方式', 'DOMAIN-SUFFIX', {options:Object.entries(domainTypes), hint:'「域名及子域名」会同时匹配 www.google.com 等子域名。'});
}

function editGroup() {
  proxyDialog({title:'添加分组', submit:'添加', intro:'例如「Google」或「YouTube」。添加后可以随时修改域名和出口。',
    build:field => {
      field('name', '分组名称', '', {required:true, placeholder:'例如：YouTube'});
      const routes = groupRoutes();
      field('route', '出口', routes.includes(AI_POOL) ? AI_POOL : routes[0], {options:groupRouteOptions()});
      domainFields(field);
      return data => {
        const name = data.name.trim();
        return [{kind:'group', name, route:data.route, type:'select', proxies:[data.route], use:[]},
          ...(data.domains.trim() ? [{kind:'domains', group:name, domains:data.domains, type:data.match}] : [])];
      };
    },
    done:edit => { navigateProxy('group', edit.name); toast('分组已添加，应用后生效。'); }});
}

function renameGroup(group) {
  proxyDialog({title:'重命名分组', submit:'保存', build:field => {
    field('name', '分组名称', group.name, {required:true, wide:true});
    return data => ({kind:'group', original:group.name, name:data.name.trim(), type:group.type, proxies:group.members, use:group.use});
  }, done:edit => navigateProxy('group', edit.name)});
}

function deleteGroup(group) {
  return guard(async () => {
    const total = group.domains + group.ruleSets + group.otherRules;
    if (!await askConfirm('删除分组「' + group.name + '」' + (total ? '，同时移除它的 ' + total + ' 条规则' : '') + '？', '删除分组', {accept:'删除', danger:true})) return;
    if (await updateProxyDraft({kind:'group', original:group.name, remove:true})) navigateProxy('groups');
  });
}

function addDomains(group) {
  proxyDialog({title:'添加域名', submit:'添加', build:field => {
    domainFields(field);
    return data => ({kind:'domains', group, domains:data.domains, type:data.match});
  }});
}

function insertPosition(target) {
  const rules = proxyModel.options.rules || [];
  const last = rules.findLastIndex(text => readRule(text).target === target);
  if (last >= 0) return last + 2;
  const fallback = rules.findIndex(text => text.startsWith('MATCH,'));
  return fallback < 0 ? rules.length + 1 : fallback + 1;
}

function editMatch(item, group = '') {
  const existing = Boolean(item), entry = item || {type:'DOMAIN-SUFFIX', domain:'', target:group || ruleFilter};
  proxyDialog({title:(existing ? '编辑' : '添加') + (group ? '域名' : '规则'), submit:existing ? '保存' : '添加', build:(field, note) => {
    const type = field('type', '匹配方式', entry.type, {options:Object.entries(group ? domainTypes : ruleLabels)});
    const value = field('domain', group ? '域名' : '匹配内容', entry.domain, {wide:true});
    let policy, position, noResolve;
    if (!group) {
      policy = field('target', '出口', entry.target || '', {required:true, options:[['', '选择出口'], ...routeOptions()]});
      position = field('position', '匹配顺序', existing ? entry.index + 1 : insertPosition(entry.target), {type:'number', hint:'数字越小越先匹配。'});
      position.min = 1;
      position.max = (proxyModel.options.rules || []).length + (existing ? 0 : 1);
      noResolve = field('no-resolve', '匹配时不解析域名（no-resolve）', entry.flags?.includes('no-resolve'), {type:'checkbox'});
    } else if (entry.provider) note('这个域名来自规则集「' + entry.provider + '」。修改后会在规则集之外单独添加，并在本分组中排除原条目。');
    function sync() {
      value.parentElement.hidden = type.value === 'MATCH';
      value.required = !value.parentElement.hidden;
      value.placeholder = type.value.startsWith('DOMAIN') ? 'example.com' : type.value.startsWith('IP-CIDR') ? '192.0.2.0/24' : '';
      if (noResolve) noResolve.parentElement.hidden = !['IP-CIDR', 'IP-CIDR6', 'GEOIP', 'RULE-SET'].includes(type.value);
    }
    type.onchange = sync;
    sync();
    return () => {
      const target = group || policy.value, flags = (entry.flags || []).filter(flag => flag !== 'no-resolve');
      if (noResolve?.checked && !noResolve.parentElement.hidden) flags.push('no-resolve');
      return {kind:entry.provider ? 'subscription-domain' : 'rule', path:entry.path || ['rules'], index:entry.index ?? null,
        type:type.value, operand:value.value, target, flags,
        position:position ? Number(position.value) : existing ? entry.index + 1 : insertPosition(target),
        provider:entry.provider, originalType:entry.type, originalDomain:entry.domain};
    };
  }});
}

function removeMatch(entry, group = '') {
  return guard(() => updateProxyDraft({kind:entry.provider ? 'subscription-domain' : 'rule',
    path:entry.path, index:entry.index, remove:true, provider:entry.provider, target:group,
    originalType:entry.type, originalDomain:entry.domain}));
}

// ---------- Setup ----------

function setupProxyEditor() {
  for (const tab of $$('[data-proxy-tab]')) tab.onclick = () => navigateProxy(tab.dataset.proxyTab);
  $('#proxy-back').onclick = backProxy;
  $('#back-proxy-entry').onclick = () => $('#proxy-entry').close();
  $('#proxy-entry-cancel').onclick = () => $('#proxy-entry').close();
  $('#proxy-window').oncancel = event => { event.preventDefault(); backProxy(); };
  $('#save-config').onclick = () => guard(applyProxyConfig, '#proxy-workspace');
  $('#discard-config').onclick = () => guard(discardProxyChanges, '#proxy-workspace');
  $('#config-content').addEventListener('input', updateConfigState);
  $('#upload-config').onclick = () => $('#config-file').click();
  $('#config-file').onchange = async () => {
    const input = $('#config-file'), file = input.files[0];
    if (!file) return;
    await guard(async () => {
      if (!file.size || file.size > 2 * 1024 * 1024 || !/\.ya?ml$/i.test(file.name)) throw Error('请选择 2 MB 以内的 YAML 文件。');
      if (!await discardChanges()) return;
      const request = proxyGeneration, draft = await file.text();
      if (request !== proxyGeneration || !$('#proxy-window').open) return;
      editor.setValue(draft);
      pendingUpload = true;
      await openProxyVisual();
      $('#config-filename').textContent = file.name + ' · 有未应用的更改';
    });
    input.value = '';
  };
  $('#download-config').onclick = () => {
    const link = element('a'), url = URL.createObjectURL(new Blob([editor.getValue()], {type:'application/yaml;charset=utf-8'}));
    link.href = url;
    link.download = 'config.yaml';
    document.body.append(link);
    link.click();
    link.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  };
}
