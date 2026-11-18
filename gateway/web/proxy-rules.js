'use strict';

const domainTypes = {DOMAIN:'完整域名', 'DOMAIN-SUFFIX':'域名及子域名', 'DOMAIN-KEYWORD':'域名关键词', 'DOMAIN-WILDCARD':'通配域名'};
const ruleLabels = {...domainTypes, 'IP-CIDR':'IPv4 网段', 'IP-CIDR6':'IPv6 网段', GEOIP:'IP 地区', GEOSITE:'域名分类',
  'RULE-SET':'规则集', MATCH:'兜底规则'};
const hiddenPolicyGroups = new Set(['GLOBAL', 'AUTO', '订阅下载', 'PROXY-RELAY', 'PROXY']);
const sectionNames = {bindings:'固定出口', exits:'代理池', groups:'策略分组', providers:'节点订阅', rules:'分流规则'};
const policyLabel = name => ({DIRECT:'直连',REJECT:'拒绝','REJECT-DROP':'静默丢弃'})[name] || name;
let resultPage = 0, rulePolicy = '', domainRequest = 0, searchTimer;
const pageSize = () => Number($('#proxy-page-size').value);

function resetProxyBrowser() {
  ++domainRequest;
  clearTimeout(searchTimer);
  resultPage = 0;
  rulePolicy = '';
  $('#proxy-search').value = '';
}

function readRule(text) {
  const parts = text.split(','), type = parts.shift().trim(), flags = [];
  while (parts.length > (type === 'MATCH' ? 1 : 2) && ['no-resolve','dst','src'].includes(parts.at(-1).trim())) flags.unshift(parts.pop().trim());
  return {type, target:parts.pop()?.trim(), domain:parts.join(',').trim(), flags};
}

function insertPosition(target) {
  const rules = proxyModel.options.rules || [];
  const first = target && rules.findIndex(text => readRule(text).target === target);
  if (Number.isInteger(first) && first >= 0) return first + 1;
  const fallback = rules.findIndex(text => text.startsWith('MATCH,'));
  return fallback < 0 ? rules.length + 1 : fallback + 1;
}

function editMatch(item, group = '') {
  const existing = Boolean(item), entry = item || {type:'DOMAIN-SUFFIX',domain:'',target:group || rulePolicy};
  const labels = group ? domainTypes : ruleLabels;
  proxyDialog((existing ? '编辑' : '添加') + (group ? '域名' : '分流规则'), (field,fields) => {
    const type = field('type','匹配规则',entry.type,'text',Object.entries(labels).map(([key,label]) => [key,label]));
    const value = field('domain',group ? '域名' : '匹配内容',entry.domain);
    let policy, position, noResolve;
    if (!group) {
      const targets = [...new Set(['DIRECT','REJECT',...proxyModel.groups.map(g=>g.name),...proxyModel.deviceExits,entry.target].filter(Boolean))];
      policy = field('target','执行策略',entry.target || '', 'text',[['','选择策略'],...targets.map(n => [n,policyLabel(n)])]);
      policy.required = true;
      const options = element('details',undefined,'rule-advanced');
      options.append(element('summary','顺序与 DNS'));
      position = field('position','匹配顺序',existing ? entry.index + 1 : insertPosition(entry.target),'number');
      position.min = 1;
      position.max = (proxyModel.options.rules || []).length + (existing ? 0 : 1);
      noResolve = field('no-resolve','不触发 DNS 解析',entry.flags?.includes('no-resolve'),'checkbox');
      options.append(position.parentElement,noResolve.parentElement);
      fields.append(options);
    }
    function showFields() {
      value.parentElement.hidden = type.value === 'MATCH';
      value.required = !value.parentElement.hidden;
      value.placeholder = type.value.startsWith('DOMAIN') ? 'example.com' : type.value.startsWith('IP-CIDR') ? '192.0.2.0/24' : '';
      if (noResolve) noResolve.parentElement.hidden = !['IP-CIDR','IP-CIDR6','GEOIP','RULE-SET'].includes(type.value);
    }
    type.onchange = showFields;
    showFields();
    return () => {
      const target = group || policy.value;
      const flags = (entry.flags || []).filter(f => f !== 'no-resolve');
      if (noResolve?.checked && !noResolve.parentElement.hidden) flags.push('no-resolve');
      return {kind:entry.provider ? 'subscription-domain' : 'rule', path:entry.path || ['rules'], index:entry.index ?? null,
        type:type.value, operand:value.value, target, flags,
        position:position ? Number(position.value) : existing ? entry.index + 1 : insertPosition(target),
        provider:entry.provider, originalType:entry.type, originalDomain:entry.domain};
    };
  });
}

function removeMatch(entry, group = '') {
  return guard(() => updateProxyDraft({kind:entry.provider ? 'subscription-domain' : 'rule',
    path:entry.path, index:entry.index, remove:true, provider:entry.provider, target:group,
    originalType:entry.type, originalDomain:entry.domain}));
}

function tableRows(headers, rows) {
  const table = element('table',undefined,'editor-table');
  const head = table.createTHead().insertRow();
  for (const title of headers) {
    const th = element('th',title);
    th.scope = 'col';
    head.append(th);
  }
  const body = table.createTBody();
  for (const row of rows) {
    const tr = body.insertRow();
    row.cells.forEach((column,i) => {
      const cell = tr.insertCell();
      if (row.checkbox && i === 1) cell.append(row.checkbox());
      else cell.textContent = column;
    });
    tr.insertCell().append(...row.actions());
  }
  return table;
}

function drawPager(count) {
  const pages = Math.max(1,Math.ceil(count / pageSize()));
  resultPage = Math.min(resultPage,pages - 1);
  $('#proxy-count').textContent = count + ' 项';
  $('#proxy-page').textContent = (resultPage + 1) + ' / ' + pages;
  for (const [id, disabled] of [['#proxy-prev',resultPage === 0],['#proxy-next',resultPage >= pages - 1]]) {
    $(id).disabled = disabled;
    $(id).dataset.stateDisabled = String(disabled);
  }
}

function showList(headers, rows, empty) {
  $('#proxy-results').replaceChildren(rows.length ? tableRows(headers,rows) : element('p',empty,'muted'));
}

async function drawDomains(group, search) {
  const request = ++domainRequest, model = proxyModel;
  $('#proxy-results').setAttribute('aria-busy','true');
  $('#proxy-results').replaceChildren(element('p','正在读取域名…','muted'));
  try {
    const data = await post('/proxy/draft',{content:editor.getValue(),domainPage:{group,search,page:resultPage,limit:pageSize()}});
    if (request !== domainRequest || model !== proxyModel || proxyTab !== 'group-domains') return;
    const requested = resultPage;
    drawPager(data.total);
    if (requested !== resultPage) { drawDomains(group,search); return; }
    const rows = data.rows.map(item => ({cells:[item.domain,domainTypes[item.type]],actions:() => [
      button('编辑',()=>editMatch(item,group),'text-button'),
      button(item.provider ? '排除' : '移除',()=>removeMatch(item,group),'text-button')
    ]}));
    showList(['域名','匹配规则','操作'],rows,search ? '没有匹配的域名' : '暂无域名');
    if (data.missing.length) $('#proxy-results').append(element('p','未能读取规则集：' + data.missing.join('、'),'muted'));
  } catch (error) {
    if (request === domainRequest) { drawPager(0); $('#proxy-results').replaceChildren(element('p',error.message,'muted')); }
  } finally {
    if (request === domainRequest) $('#proxy-results').removeAttribute('aria-busy');
  }
}

function drawDefaults(config) {
  const defaults = $('#routing-defaults');
  defaults.hidden = proxyTab !== 'bindings';
  if (defaults.hidden) return;
  const pool = (config['proxy-groups'] || []).find(g => g.name === '🤖 PROXY');
  const dynamic = pool?.use?.length || pool?.['include-all'] || pool?.['include-all-providers'] || pool?.['include-all-proxies'];
  const members = [...new Set([...(pool?.proxies || []), ...(dynamic ? liveSelector.all || [] : [])])];
  const selected = pool?.['default-selected'] || liveSelector.now || members[0];
  defaults.hidden = members.length === 0;
  defaults.disabled = pool?.type !== 'select';
  $('#ai-default-exit').replaceChildren(...members.map(name => {
    const label = element('label'), input = element('input');
    input.type = 'radio';
    input.name = 'ai-default-exit';
    input.value = name;
    input.checked = name === selected;
    label.append(input,name);
    return label;
  }));
}

function renderProxyBrowser() {
  ++domainRequest;
  const config = proxyModel.options, groups = config['proxy-groups'] || [];
  const isRules = proxyTab === 'rules', domains = proxyTab === 'group-domains';
  $('#back-to-policy-groups').hidden = !domains;
  $('#proxy-pager').hidden = proxyTab === 'providers';
  $('#proxy-results').removeAttribute('aria-busy');
  $('#proxy-search-label').hidden = !domains;
  $('#proxy-filters').hidden = !domains && !isRules;
  $('#rule-policy-label').hidden = !isRules;
  $('#proxy-browser-title').textContent = domains ? (rulePolicy === '🤖 PROXY' ? '🤖 AI' : rulePolicy) + ' · 域名规则' : sectionNames[proxyTab];
  drawDefaults(config);
  const add = $('#add-proxy-item');
  if (domains) {
    add.textContent = '添加域名';
    add.onclick = () => editMatch(null,rulePolicy);
    drawDomains(rulePolicy,$('#proxy-search').value.trim().toLowerCase());
    return;
  }
  let headers, rows, empty;
  if (proxyTab === 'bindings') {
    headers = ['来源网段','备注','固定出口','操作'];
    empty = '暂无网段绑定';
    add.textContent = '添加网段';
    add.onclick = () => proxyModel.deviceExits.length ? openProxyEntry('binding') : toast('请先在代理池添加出口',true);
    rows = proxyModel.bindings.map(b => ({cells:[b.ip,b.note || '—',b.target],actions:() => [
      button('编辑',()=>openProxyEntry('binding',b),'text-button'),
      button('解绑',()=>guard(()=>updateProxyDraft({kind:'binding',id:b.id,remove:true})),'text-button')]}));
  } else if (proxyTab === 'exits') {
    headers = ['出口名称','服务器','备注','操作'];
    empty = '暂无代理出口';
    add.textContent = '添加出口';
    add.onclick = () => openProxyEntry('exit');
    rows = (config.proxies || []).filter(n => proxyModel.deviceExits.includes(n.name)).map(n => ({
      cells:[n.name,[n.type?.toUpperCase(),n.server,n.port].filter(Boolean).join(' · '),n['x-gateway-note'] || '—'],
      actions:() => [button('编辑',()=>openProxyEntry(['http','socks5'].includes(n.type) ? 'exit' : 'note',n),'text-button')]}));
  } else if (proxyTab === 'groups') {
    headers = ['策略分组','状态','操作'];
    empty = '暂无策略分组';
    add.textContent = '添加分组';
    add.onclick = () => openProxyEntry('group');
    rows = groups.filter(g => !hiddenPolicyGroups.has(g.name.replace(/^[^\p{L}\p{N}]+/u,'').trim().toUpperCase())).map(g => {
      const enabled = !proxyModel.disabledGroups.includes(g.name);
      return {
        cells:[g.name, enabled ? '已启用' : '已关闭'],
        checkbox:() => {
          const box = element('input');
          box.type = 'checkbox';
          box.checked = enabled;
          box.setAttribute('aria-label', '启用 ' + g.name);
          box.onchange = () => {
            const next = box.checked;
            box.checked = enabled;
            guard(() => updateProxyDraft({kind:'toggle-group',name:g.name,enabled:next}));
          };
          return box;
        },
        actions:() => [button('编辑域名',()=>navigateProxy('group-domains',g.name),'text-button')]
      };
    });
    if (groups.some(g => g.name === '🤖 PROXY')) {
      rows.unshift({cells:['🤖 AI','AI 默认出口'], actions:() => [
        button('编辑域名',()=>navigateProxy('group-domains','🤖 PROXY'),'text-button')
      ]});
    }
  } else if (proxyTab === 'providers') {
    headers = ['订阅名称','来源','操作'];
    empty = '暂无节点订阅';
    add.textContent = '添加订阅';
    add.onclick = () => openProxyEntry('provider');
    rows = Object.entries(config['proxy-providers'] || {}).map(([name,p]) => {
      let source = p.type;
      try { source = new URL(p.url).host; } catch {}
      return {cells:[name,source],actions:() => p.type === 'http' ? [button('编辑',()=>openProxyEntry('provider',{...p,name}),'text-button')] : []};
    });
  } else {
    headers = ['顺序','匹配类型','匹配内容','执行策略','操作'];
    empty = '暂无常用分流规则';
    add.textContent = '添加规则';
    add.onclick = () => editMatch(null);
    const targets = [...new Set(['DIRECT','REJECT',...groups.map(g=>g.name),...proxyModel.deviceExits])];
    $('#rule-policy-filter').replaceChildren(new Option('全部策略',''),...targets.map(n=>new Option(policyLabel(n),n)));
    $('#rule-policy-filter').value = rulePolicy;
    const bound = new Set();
    for (const b of proxyModel.bindings) for (let i=b.id;i<b.end;i++) bound.add(i);
    rows = [];
    (config.rules || []).forEach((text,index) => {
      const r = readRule(text);
      if (bound.has(index) || !Object.hasOwn(ruleLabels,r.type) || (rulePolicy && r.target !== rulePolicy)) return;
      const item = {...r,index,path:['rules']};
      rows.push({cells:[index+1,ruleLabels[r.type],r.type==='MATCH' ? '其余所有流量' : r.domain,policyLabel(r.target)],
        actions:() => [button('编辑',()=>editMatch(item),'text-button'),button('移除',()=>removeMatch(item),'text-button')]});
    });
  }
  if (proxyTab === 'providers') {
    $('#proxy-count').textContent = rows.length + ' 项';
  } else {
    drawPager(rows.length);
    rows = rows.slice(resultPage * pageSize(),(resultPage + 1) * pageSize());
  }
  showList(headers,rows,empty);
}

function setupProxyBrowser() {
  const size = $('#proxy-page-size');
  try {
    const saved = localStorage.getItem('gateway-page-size');
    if ([...size.options].some(o => o.value === saved)) size.value = saved;
  } catch {}
  size.onchange = () => {
    try { localStorage.setItem('gateway-page-size',size.value); } catch {}
    resultPage = 0;
    renderProxyBrowser();
  };
  $('#rule-policy-filter').onchange = e => { rulePolicy = e.target.value; resultPage = 0; renderProxyBrowser(); };
  $('#proxy-search').oninput = () => {
    resultPage = 0;
    clearTimeout(searchTimer);
    ++domainRequest;
    searchTimer = setTimeout(renderProxyBrowser,160);
  };
  for (const [id, step] of [['#proxy-prev',-1],['#proxy-next',1]]) {
    $(id).onclick = () => { resultPage += step; renderProxyBrowser(); $('.proxy-canvas').scrollTop = 0; };
  }
}
