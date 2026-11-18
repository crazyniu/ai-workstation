'use strict';

const ruleLabels = {
  DOMAIN: '完整域名', 'DOMAIN-SUFFIX': '域名及其子域名', 'DOMAIN-KEYWORD': '域名关键词',
  'DOMAIN-WILDCARD': '域名通配符', 'DOMAIN-REGEX': '域名正则', 'IP-CIDR': 'IP / 网段',
  'IP-CIDR6': 'IPv6 / 网段', 'IP-SUFFIX': 'IP 后缀', GEOIP: 'IP 地区', GEOSITE: '域名分类',
  'RULE-SET': '规则集', 'SRC-IP-CIDR': '来源 IP / 网段', 'DST-PORT': '目标端口',
  'SRC-PORT': '来源端口', NETWORK: '网络协议', AND: '同时匹配', OR: '任一匹配',
  NOT: '反向匹配', 'SUB-RULE': '调用子规则', MATCH: '兜底策略', 'IP-ASN':'目标自治系统号',
  'SRC-GEOIP':'来源 IP 地区', 'SRC-IP-ASN':'来源自治系统号', 'SRC-IP-SUFFIX':'来源 IP 后缀',
  'IN-PORT':'入站端口', 'IN-TYPE':'入站类型', 'IN-USER':'入站用户', 'IN-NAME':'入站名称',
  'PROCESS-NAME':'进程名', 'PROCESS-NAME-WILDCARD':'进程名通配符', 'PROCESS-NAME-REGEX':'进程名正则',
  'PROCESS-PATH':'进程路径', 'PROCESS-PATH-WILDCARD':'进程路径通配符', 'PROCESS-PATH-REGEX':'进程路径正则',
  UID:'用户 ID', DSCP:'流量标记', 'REMATCH-NAME':'重匹配名称'
};
const configLabels = {
  'proxy-providers': '节点订阅', 'rule-providers': '规则集', 'proxy-groups': '代理组', proxies: '代理节点',
  rules: '主规则', 'sub-rules': '子规则', hosts: '自定义域名解析', sniffer: '流量嗅探', profile: '状态保存',
  mode: '运行模式', 'log-level': '日志级别', dns: 'DNS 解析', tun: 'TUN 路由'
};
const nestedLabels = {payload:'规则条目', name:'名称', type:'类型', behavior:'匹配方式', interval:'更新间隔（秒）',
  url:'地址', path:'文件路径', use:'使用的订阅', proxies:'组内节点', proxy:'下载出口', nameserver:'上游 DNS',
  'nameserver-policy':'按域名指定 DNS', 'fake-ip-filter':'Fake IP 过滤', 'direct-nameserver':'直连 DNS',
  'route-exclude-address':'排除的路由地址', 'skip-src-address':'跳过的来源地址', 'skip-dst-address':'跳过的目标地址'};
const fieldName = (key, depth) => (depth ? nestedLabels : configLabels)[key] || key;
const perPage = 20;
let optionPath = [], ruleScope = '', rulePolicy = '', resultPage = 0;

function resetProxyBrowser() {
  optionPath = [];
  ruleScope = '';
  rulePolicy = '';
  resultPage = 0;
  $('#proxy-search').value = '';
}

function splitProxyRule(text, scope) {
  if (scope.behavior === 'domain') return {type: 'DOMAIN', operand: text, flags: []};
  if (scope.behavior === 'ipcidr') return {type: text.includes(':') ? 'IP-CIDR6' : 'IP-CIDR', operand: text, flags: []};
  const tokens = text.split(',');
  const type = tokens.shift().trim().toUpperCase(), flags = [];
  const minimum = (scope.behavior ? 0 : 1) + (type === 'MATCH' ? 0 : 1);
  while (tokens.length > minimum && ['no-resolve','src','dst'].includes(tokens.at(-1).trim())) flags.unshift(tokens.pop().trim());
  const target = scope.behavior ? '' : (tokens.pop() || '').trim();
  return {type, operand: tokens.join(',').trim(), target, flags};
}

const logicalTypes = ['AND', 'OR', 'NOT'];

function conditionParts(type, body) {
  if (!body) return [''];
  const source = type === 'SUB-RULE' ? body : body.slice(1, -1);
  const parts = [];
  let start = 0, depth = 0, escaped = false, bracket = false;
  for (let i = 0; i <= source.length; i++) {
    const ch = source[i];
    if (i === source.length || ch === ',' && !depth) {
      const part = source.slice(start, i).trim();
      if (depth || !part.startsWith('(') || !part.endsWith(')')) return null;
      parts.push(part.slice(1, -1));
      start = i + 1;
    } else if (escaped) escaped = false;
    else if (ch === '\\') escaped = true;
    else if (ch === '[') bracket = true;
    else if (ch === ']') bracket = false;
    else if (!bracket && ch === '(') depth++;
    else if (!bracket && ch === ')') depth--;
  }
  return parts;
}

function conditionFields(type, parts) {
  const group = element('fieldset', undefined, 'proxy-conditions');
  group.append(element('legend', '匹配条件'));
  const list = element('div');
  group.append(list);
  const multiple = type === 'AND' || type === 'OR';
  const readers = new Map();
  function add(text) {
    const comma = text.indexOf(',');
    const initial = comma < 0 ? 'DOMAIN-SUFFIX' : text.slice(0, comma);
    const original = comma < 0 ? '' : text.slice(comma + 1);
    const row = element('div', undefined, 'proxy-condition');
    const select = element('select'), input = element('input');
    select.setAttribute('aria-label', '条件类型');
    input.setAttribute('aria-label', '匹配值');
    for (const name of new Set([...Object.keys(ruleLabels), initial])) {
      if (!['MATCH', 'SUB-RULE'].includes(name)) select.add(new Option(ruleLabels[name] || name, name));
    }
    select.value = initial;
    input.value = original;
    input.spellcheck = false;
    row.append(select, input);
    if (multiple) row.append(button('移除', () => { readers.delete(row); row.remove(); }, 'text-button'));
    let nested;
    function refresh() {
      nested?.group.remove();
      nested = null;
      if (logicalTypes.includes(select.value)) {
        const children = conditionParts(select.value, select.value === initial ? original : '');
        if (children) {
          nested = conditionFields(select.value, children);
          row.append(nested.group);
        }
      }
      input.hidden = Boolean(nested);
      input.required = !nested;
    }
    select.onchange = refresh;
    refresh();
    list.append(row);
    readers.set(row, () => '(' + select.value + ',' + (nested ? nested.read() : input.value.trim()) + ')');
  }
  for (const part of parts) add(part);
  if (multiple) group.append(button('添加条件', () => add(''), 'text-button'));
  return {group, read() {
    if (!readers.size) throw Error('请添加匹配条件');
    const text = [...readers.values()].map(read => read()).join(',');
    return type === 'SUB-RULE' ? text : '(' + text + ')';
  }};
}

const policyLabel = name => ({DIRECT:'直连', REJECT:'拒绝', 'REJECT-DROP':'静默丢弃'})[name] || name;

function proxyRuleScopes() {
  const opts = proxyModel.options, managedIndexes = new Set(), managedSubs = new Set();
  for (const binding of proxyModel.bindings) {
    if (!proxyModel.deviceExits.includes(binding.target) && !binding.sub?.startsWith('Gateway-Range-')) continue;
    for (let i = binding.id; i < binding.end; i++) managedIndexes.add(i);
    if (binding.sub) managedSubs.add(binding.sub);
  }
  const main = {name:'主规则', path:['rules'], list:opts.rules || [], skip:managedIndexes};
  const scopes = [main], visited = new Set(), providerTargets = new Map();
  for (const scope of scopes) {
    scope.list.forEach((text, index) => {
      if (scope.skip?.has(index)) return;
      const rule = splitProxyRule(text, scope);
      if (rule.type === 'SUB-RULE' && !visited.has(rule.target) && !managedSubs.has(rule.target)) {
        visited.add(rule.target);
        const list = opts['sub-rules']?.[rule.target];
        if (list) scopes.push({name:'子规则 · ' + rule.target, path:['sub-rules',rule.target], list});
      }
      if (rule.type === 'RULE-SET') {
        if (!providerTargets.has(rule.operand)) providerTargets.set(rule.operand, new Set());
        providerTargets.get(rule.operand).add(rule.target);
      }
    });
  }
  for (const [name, provider] of Object.entries(opts['rule-providers'] || {})) {
    if (provider.type === 'inline' || Array.isArray(provider.payload)) {
      scopes.push({name:'规则集 · ' + name, path:['rule-providers',name,'payload'], list:provider.payload || [],
        behavior:provider.behavior || 'classical', targets:[...(providerTargets.get(name) || [])]});
    }
  }
  return scopes;
}

function showGroupRules(name) {
  proxyTab = 'rules';
  resetProxyBrowser();
  rulePolicy = name;
  showProxyMode(true);
  $('.proxy-canvas').scrollTop = 0;
  $('#proxy-browser-title').focus({preventScroll:true});
}

function openRuleEntry(scopes, original, index) {
  proxyDialog(index == null ? '添加分流规则' : '编辑分流规则', (field, fields) => {
    const scopeInput = field('scope', '作用范围', JSON.stringify(original.path), 'text',
      scopes.map(s => [JSON.stringify(s.path), s.name]));
    scopeInput.disabled = index != null;
    const rule = index == null ? {type: 'DOMAIN-SUFFIX', operand: '', target: rulePolicy, flags: []}
      : splitProxyRule(original.list[index], original);
    const type = field('type', '匹配类型', '', 'text', []);
    const operand = field('operand', '匹配内容', rule.operand);
    const target = field('target', '执行策略', '', 'text', []);
    const position = field('position', '顺序（1 为最先匹配）', '', 'number');
    position.min = 1;
    position.required = true;
    const noResolve = field('no-resolve', '不触发 DNS 解析', rule.flags.includes('no-resolve'), 'checkbox');
    const src = field('src', '按来源匹配', rule.flags.includes('src'), 'checkbox');
    const selectedScope = () => scopes[scopeInput.selectedIndex];
    let conditions;
    function syncType() {
      const scope = selectedScope();
      const match = type.value === 'MATCH';
      conditions?.group.remove();
      conditions = null;
      if ([...logicalTypes, 'SUB-RULE'].includes(type.value)) {
        const parts = conditionParts(type.value, type.value === rule.type ? rule.operand : '');
        if (parts) {
          conditions = conditionFields(type.value, parts);
          operand.parentElement.after(conditions.group);
        }
      }
      operand.parentElement.hidden = match || Boolean(conditions);
      operand.required = !operand.parentElement.hidden;
      operand.placeholder = ['DOMAIN', 'DOMAIN-SUFFIX'].includes(type.value) ? 'example.com'
        : type.value === 'IP-CIDR' ? '192.0.2.1 或 192.0.2.0/24' : '';
      const useTarget = !scope.behavior;
      target.parentElement.hidden = !useTarget;
      target.required = useTarget;
      const choices = type.value === 'SUB-RULE' ? Object.keys(proxyModel.options['sub-rules'] || {})
        : ['DIRECT', 'REJECT', 'REJECT-DROP', 'PASS', 'GLOBAL', 'COMPATIBLE', ...proxyModel.targets];
      const value = choices.includes(target.value) ? target.value : type.value === rule.type ? rule.target : '';
      target.replaceChildren(new Option('选择策略', ''), ...[...new Set([...choices, value].filter(Boolean))].map(n => new Option(policyLabel(n), n)));
      target.value = value || '';
      const flagsAllowed = !['domain','ipcidr'].includes(scope.behavior) && !match;
      noResolve.parentElement.hidden = !flagsAllowed || !(/IP|GEOIP|RULE-SET/.test(type.value) || rule.flags.includes('no-resolve'));
      src.parentElement.hidden = !flagsAllowed || !(/IP|GEOIP|RULE-SET/.test(type.value) || rule.flags.includes('src'));
    }
    function syncScope() {
      const scope = selectedScope();
      const types = scope.behavior === 'domain' ? ['DOMAIN'] : scope.behavior === 'ipcidr' ? ['IP-CIDR']
        : [...new Set([...Object.keys(ruleLabels), ...scope.list.map(s => s.split(',')[0]), rule.type])]
          .filter(t => !scope.behavior || !['RULE-SET','SUB-RULE'].includes(t));
      type.replaceChildren(...types.map(v => new Option(ruleLabels[v] || v, v)));
      type.value = types.includes(rule.type) ? rule.type : types[0];
      type.parentElement.hidden = types.length === 1;
      position.max = scope.list.length + (index == null ? 1 : 0);
      const fallback = scope.list.findIndex(s => s.startsWith('MATCH,'));
      const firstGroupRule = rulePolicy && !scope.behavior ? scope.list.findIndex((text, i) =>
        !scope.skip?.has(i) && splitProxyRule(text,scope).target === rulePolicy) : -1;
      const insertAt = firstGroupRule >= 0 ? firstGroupRule : fallback >= 0 ? fallback : scope.list.length;
      position.value = (index ?? insertAt) + 1;
      syncType();
    }
    const advanced = element('details', undefined, 'rule-advanced');
    advanced.append(element('summary', '高级设置'), scopeInput.parentElement, position.parentElement,
                    noResolve.parentElement, src.parentElement);
    fields.append(advanced);
    scopeInput.onchange = syncScope;
    type.onchange = syncType;
    syncScope();
    return () => {
      const flags = rule.flags.filter(f => f !== 'no-resolve' && f !== 'src');
      if (noResolve.checked && !noResolve.parentElement.hidden) flags.push('no-resolve');
      if (src.checked && !src.parentElement.hidden) flags.push('src');
      return {kind: 'rule', path: selectedScope().path, index, type: type.value, operand: conditions ? conditions.read() : operand.value,
        target: target.value, flags, position: Number(position.value)};
    };
  });
}

function optionKind(value) {
  if (Array.isArray(value)) return 'list';
  if (value === null) return 'null';
  return typeof value;
}

function sensitiveOption(path) {
  return path.some(key => /password|secret|token|authorization|private-key|headers?|api-key/i.test(String(key)));
}

function optionText(path, value) {
  if (Array.isArray(value)) return value.length + ' 项';
  if (value && typeof value === 'object') return value.name || Object.keys(value).length + ' 个字段';
  if (sensitiveOption(path)) return '••••••';
  if (typeof value === 'string' && /^https?:\/\//i.test(value)) {
    try { return new URL(value).origin; } catch {}
  }
  if (typeof value === 'boolean') return value ? '开启' : '关闭';
  return String(value ?? '空值');
}

function openOptionEntry(parent, key, existing) {
  const list = Array.isArray(parent);
  const value = existing ? parent[key] : '';
  proxyDialog(existing ? '编辑配置项' : '添加配置项', (field, fields) => {
    const enums = {mode: ['rule','global','direct'], 'log-level': ['info','warning','error','debug','silent']};
    if (existing && !optionPath.length && Object.hasOwn(enums, key)) {
      const choices = [...new Set([...enums[key], value])];
      const selected = field('value', configLabels[key], value, 'text', choices.map(s => [s, s]));
      return () => ({kind: 'option', path: [key], action: 'set', value: selected.value});
    }
    const name = field('key', list ? '列表顺序' : '字段名', list ? Number(key) + 1 : key, list ? 'number' : 'text');
    name.required = true;
    if (list) { name.min = 1; name.max = parent.length + (existing ? 0 : 1); }
    else if (existing) name.readOnly = true;
    const type = field('type', '值类型', optionKind(value), 'text',
      [['string','文本'],['boolean','开关'],['number','数字'],['object','字段组'],['list','列表'],['null','空值']]);
    const input = field('value', '值', ['object','list','null'].includes(optionKind(value)) ? '' : value,
      sensitiveOption([...optionPath, key]) ? 'password' : 'textarea');
    const toggle = field('enabled', '启用', value === true, 'checkbox');
    function refresh() {
      input.parentElement.hidden = !['string','number'].includes(type.value);
      toggle.parentElement.hidden = type.value !== 'boolean';
    }
    type.onchange = refresh;
    if (!existing && !optionPath.length) {
      const keys = element('datalist');
      keys.id = 'proxy-option-keys';
      const sections = {proxies:'list', 'proxy-groups':'list', rules:'list', mode:'string', 'log-level':'string'};
      for (const [id, label] of Object.entries(configLabels)) {
        if (!Object.hasOwn(parent, id)) keys.append(new Option(label, id));
      }
      fields.append(keys);
      name.setAttribute('list', keys.id);
      name.onchange = () => {
        if (Object.hasOwn(configLabels, name.value)) { type.value = sections[name.value] || 'object'; refresh(); }
      };
    }
    refresh();
    return () => {
      const kind = type.value;
      let next = input.value;
      if (kind === 'boolean') next = toggle.checked;
      if (kind === 'number') {
        next = Number(input.value);
        if (!input.value.trim() || !Number.isFinite(next)) throw Error('请输入有效数字');
      }
      if (kind === 'null') next = null;
      if (kind === 'object') next = {};
      if (kind === 'list') next = [];
      const position = list ? Number(name.value) - 1 : undefined;
      const part = existing ? key : list ? position : name.value.trim();
      if (!list && !String(part).trim()) throw Error('请填写字段名');
      return {kind: 'option', path: [...optionPath, part], action: existing ? 'set' : 'add', value: next, position};
    };
  });
}

function renderProxyBrowser() {
  const collections = {exits: ['PROXY 出口池', 'exit'], providers: ['节点订阅', 'provider'],
                       groups: ['策略组', 'group'], bindings: ['网段出口', 'binding']};
  const collection = collections[proxyTab];
  const config = proxyModel.options;
  const pool = (config['proxy-groups'] || []).find(g => g.name === '🤖 PROXY');
  const defaults = $('#routing-defaults'), selector = $('#ai-default-exit');
  defaults.hidden = !['bindings','exits','groups'].includes(proxyTab);
  if (!defaults.hidden) {
    const dynamic = pool?.use?.length || pool?.['include-all'] || pool?.['include-all-providers'] || pool?.['include-all-proxies'];
    const members = [...new Set([...(pool?.proxies || []), ...(dynamic ? liveSelector.all || [] : [])])];
    const selected = pool?.['default-selected'] || liveSelector.now || members[0];
    defaults.hidden = members.length === 0;
    defaults.disabled = pool?.type !== 'select';
    selector.replaceChildren(...members.map(name => {
      const label = element('label'), input = element('input');
      input.type = 'radio';
      input.name = 'ai-default-exit';
      input.value = name;
      input.checked = name === selected;
      label.append(input, name);
      return label;
    }));
  }

  const advanced = proxyTab === 'options', isRules = proxyTab === 'rules';
  const search = $('#proxy-search').value.trim().toLowerCase();
  const results = $('#proxy-results'), add = $('#add-proxy-item'), select = $('#proxy-scope');
  const pathNav = $('#proxy-path');
  pathNav.hidden = !advanced;
  const mode = String(proxyModel.options.mode || 'rule').toLowerCase();
  $('#proxy-rule-mode').hidden = Boolean(collection) || advanced || mode === 'rule';
  if (!advanced && mode !== 'rule') {
    $('#proxy-rule-mode').textContent = (mode === 'direct' ? '直连模式' : '全局模式') + ' · 切换为规则模式';
  }
  $('#proxy-scope-label').hidden = !isRules;
  $('#rule-policy-label').hidden = !isRules;
  $('#proxy-browser-title').textContent = collection ? collection[0] : advanced ? '全部配置项' : rulePolicy ? policyLabel(rulePolicy) + ' · 分流规则' : '分流规则';
  const rows = [];
  function row(title, detail, actions) {
    if (!search || (title + ' ' + detail).toLowerCase().includes(search)) rows.push({title, detail, actions});
  }
  if (collection) {
    const [title, kind] = collection;
    add.textContent = {binding:'添加网段',exit:'添加出口',group:'添加分组',provider:'添加订阅'}[kind];
    add.onclick = () => {
      if (kind === 'binding' && !proxyModel.deviceExits.length) { toast('请先在 PROXY 出口池添加出口', true); return; }
      openProxyEntry(kind);
    };
    function advancedEntry(path) {
      proxyTab = 'options';
      resetProxyBrowser();
      optionPath = path;
      showProxyMode(true);
    }
    function entry(item, title, detail, path, editable = true) {
      row(title, detail, () => {
        const actions = [button('编辑', () => editable ? openProxyEntry(kind, item) : advancedEntry(path), 'text-button')];
        if (editable && path) actions.push(button('全部字段', () => advancedEntry(path), 'text-button'));
        if (kind === 'group') actions.unshift(button('编辑规则', () => showGroupRules(item.name), 'text-button'));
        if (kind === 'group' && !['🤖 PROXY','🔗 PROXY-RELAY'].includes(item.name)) {
          const enabled = !proxyModel.disabledGroups.includes(item.name);
          const toggle = button(enabled ? '已启用' : '已关闭', () => guard(() =>
            updateProxyDraft({kind:'toggle-group', name:item.name, enabled:!enabled})), 'group-switch');
          toggle.setAttribute('role','switch');
          toggle.setAttribute('aria-label',item.name);
          toggle.setAttribute('aria-checked',String(enabled));
          actions.unshift(toggle);
        }
        if (kind === 'binding') actions.push(button('解绑', () => guard(() =>
          updateProxyDraft({kind, id: item.id, remove: true})), 'text-button'));
        return actions;
      });
    }
    if (kind === 'exit') (config.proxies || []).forEach((item, i) =>
      proxyModel.deviceExits.includes(item.name) && entry(item, item.name, [item.type?.toUpperCase(), item.server, item.port].filter(Boolean).join(' · '),
            ['proxies', i], ['http', 'socks5'].includes(item.type)));
    if (kind === 'provider') for (const [name, item] of Object.entries(config['proxy-providers'] || {})) {
      let detail = item.type;
      try { detail = new URL(item.url).host; } catch {}
      entry({...item, name}, name, detail, ['proxy-providers', name], item.type === 'http');
    }
    if (kind === 'group') (config['proxy-groups'] || []).forEach((item, i) =>
      entry(item, item.name, [item.type, (item.proxies || []).length + ' 个成员', (item.use || []).length + ' 个订阅'].join(' · '),
            ['proxy-groups', i]));
    if (kind === 'binding') for (const item of proxyModel.bindings) entry(item, item.ip, [item.note, item.target].filter(Boolean).join(' · '));
  } else if (advanced) {
    let parent = proxyModel.options;
    const valid = [];
    for (const part of optionPath) {
      const child = parent[part];
      if (!child || typeof child !== 'object') break;
      valid.push(part);
      parent = child;
    }
    optionPath = valid;
    const navigate = path => { optionPath = path; $('#proxy-search').value = ''; resultPage = 0; renderProxyBrowser(); };
    pathNav.replaceChildren();
    const crumbs = ['全部配置', ...optionPath.map((k, depth) => typeof k === 'number' ? String(k + 1) : fieldName(k, depth))];
    crumbs.forEach((name, i) => {
      if (i) pathNav.append(element('span', '/'));
      pathNav.append(i === crumbs.length - 1 ? element('strong', name) : button(name, () => navigate(optionPath.slice(0, i)), 'text-button'));
    });
    add.textContent = '添加配置项';
    add.onclick = () => openOptionEntry(parent, Array.isArray(parent) ? parent.length : '', false);
    const entries = Array.isArray(parent) ? Array.from(parent.entries()) : Object.entries(parent);
    for (const [key, value] of entries) {
      const path = [...optionPath, key], container = value !== null && typeof value === 'object';
      const title = typeof key === 'number' ? (value?.name || '第 ' + (key + 1) + ' 项') : fieldName(key, optionPath.length);
      const detail = (title !== key && typeof key === 'string' ? key + ' · ' : '') + optionText(path, value);
      row(title, detail, () => {
        const buttons = [button(container ? '打开' : '编辑', () => container ? navigate(path) : openOptionEntry(parent, key, true), 'text-button')];
        if (path.length > 1 || !Object.hasOwn(proxyModel.fixed, key)) {
          buttons.push(button('移除', () => guard(() => updateProxyDraft({kind: 'option', action: 'remove', path})), 'text-button'));
        }
        if (Array.isArray(parent) && container) {
          for (const [delta, label] of [[-1,'上移'],[1,'下移']]) {
            if (key + delta >= 0 && key + delta < parent.length) buttons.push(button(label, () => guard(() =>
              updateProxyDraft({kind: 'option', action: 'move', path, position: key + delta})), 'text-button'));
          }
        }
        return buttons;
      });
    }
  } else {
    const scopes = proxyRuleScopes();
    const policySelect = $('#rule-policy-filter');
    const policies = new Set(['DIRECT','REJECT','REJECT-DROP',...proxyModel.targets]);
    for (const scope of scopes.filter(s => !s.behavior)) {
      scope.list.forEach((text, i) => {
        if (scope.skip?.has(i)) return;
        const rule = splitProxyRule(text, scope);
        if (rule.type !== 'SUB-RULE' && rule.target) policies.add(rule.target);
      });
    }
    policySelect.replaceChildren(new Option('全部策略',''), ...[...policies].map(n => new Option(policyLabel(n),n)));
    policySelect.value = rulePolicy;
    const allowed = scopes.filter(scope => !scope.behavior || !rulePolicy || scope.targets.includes(rulePolicy));
    if (!allowed.some(scope => JSON.stringify(scope.path) === ruleScope)) ruleScope = '';
    select.replaceChildren(new Option(rulePolicy ? '关联规则' : '主规则',''),
      ...allowed.slice(rulePolicy ? 0 : 1).map(scope => new Option(scope.name,JSON.stringify(scope.path))));
    select.value = ruleScope;
    const displayed = ruleScope ? allowed.filter(s => JSON.stringify(s.path) === ruleScope)
      : rulePolicy ? allowed.filter(s => !s.behavior) : [scopes[0]];
    add.textContent = '添加规则';
    add.onclick = () => openRuleEntry(allowed, displayed[0], null);
    for (const scope of displayed) {
      scope.list.forEach((text, index) => {
        if (scope.skip?.has(index)) return;
        const rule = splitProxyRule(text, scope);
        if (rulePolicy && !scope.behavior && (rule.type === 'SUB-RULE' || rule.target !== rulePolicy)) return;
        const type = ruleLabels[rule.type] || rule.type;
        const content = rule.type === 'MATCH' ? '其余所有流量' : rule.operand;
        const policy = scope.behavior ? (scope.targets.map(policyLabel).join(' / ') || '由引用规则决定')
          : rule.type === 'SUB-RULE' ? '子规则 · ' + rule.target : policyLabel(rule.target);
        if (search && ![content, type, rule.type, policy, rule.target, scope.name].join(' ').toLowerCase().includes(search)) return;
        rows.push({title:content, type, policy, order:index + 1, scope:scope.name, actions:() => {
          const actions = [button('编辑', () => openRuleEntry(allowed,scope,index), 'text-button')];
          if (rule.type === 'RULE-SET') {
            const provider = proxyModel.options['rule-providers']?.[rule.operand];
            if (provider) actions.push(button(Array.isArray(provider.payload) || provider.type === 'inline' ? '编辑条目' : '订阅来源', () => {
              if (Array.isArray(provider.payload) || provider.type === 'inline') {
                ruleScope = JSON.stringify(['rule-providers',rule.operand,'payload']);
              } else {
                proxyTab = 'options';
                resetProxyBrowser();
                optionPath = ['rule-providers',rule.operand];
              }
              resultPage = 0;
              $('#proxy-search').value = '';
              showProxyMode(true);
              $('.proxy-canvas').scrollTop = 0;
            }, 'text-button'));
          }
          actions.push(button('移除', () => guard(() => updateProxyDraft({kind:'rule',path:scope.path,index,remove:true})), 'text-button'));
          return actions;
        }});
      });
    }
  }
  const pages = Math.max(1, Math.ceil(rows.length / perPage));
  resultPage = Math.min(resultPage, pages - 1);
  $('#proxy-count').textContent = rows.length + ' 项';
  results.replaceChildren();
  const visible = rows.slice(resultPage * perPage, (resultPage + 1) * perPage);
  if (isRules && visible.length) {
    const table = element('table', undefined, 'routing-rule-table');
    const heading = table.createTHead().insertRow();
    for (const label of ['顺序','匹配类型','匹配内容','执行策略','操作']) heading.append(element('th',label));
    const body = table.createTBody();
    for (const item of visible) {
      const tr = body.insertRow();
      for (const value of [item.order,item.type,item.title,item.policy]) tr.insertCell().textContent = value;
      tr.cells[0].title = item.scope;
      tr.insertCell().append(...item.actions());
    }
    results.append(table);
  } else if (proxyTab === 'bindings' && visible.length) {
    const table = element('table', undefined, 'device-bindings'), heading = table.createTHead().insertRow();
    for (const name of ['来源网段','备注','固定出口','操作']) heading.append(element('th', name));
    const body = table.createTBody(), devices = new Map(proxyModel.bindings.map(b => [b.ip,b]));
    for (const row of visible) {
      const item = devices.get(row.title), tr = body.insertRow();
      for (const value of [item.ip, item.note || '—', item.target]) tr.insertCell().textContent = value;
      const actions = tr.insertCell();
      actions.append(...row.actions());
    }
    results.append(table);
  } else {
    for (const item of visible) proxyRow(results, item.title, item.detail, item.actions());
  }
  if (!rows.length) results.append(element('p', search ? '没有匹配项' : '暂无条目', 'muted'));
  $('#proxy-pager').hidden = pages === 1;
  $('#proxy-page').textContent = (resultPage + 1) + ' / ' + pages;
  for (const [id, disabled] of [['#proxy-prev', resultPage === 0], ['#proxy-next', resultPage === pages - 1]]) {
    $(id).disabled = disabled;
    $(id).dataset.stateDisabled = String(disabled);
  }
}

function setupProxyBrowser() {
  $('#proxy-rule-mode').onclick = () => guard(() => updateProxyDraft({kind:'option', path:['mode'], action:'set', value:'rule'}));
  $('#rule-policy-filter').onchange = e => { rulePolicy = e.target.value; ruleScope = ''; resultPage = 0; renderProxyBrowser(); };
  $('#proxy-scope').onchange = e => { ruleScope = e.target.value; resultPage = 0; renderProxyBrowser(); };
  $('#proxy-search').oninput = () => { resultPage = 0; renderProxyBrowser(); };
  for (const [id, step] of [['#proxy-prev', -1], ['#proxy-next', 1]]) {
    $(id).onclick = () => {
      resultPage += step;
      renderProxyBrowser();
      $('#proxy-browser-title').focus({preventScroll:true});
      $('#proxy-browser').scrollIntoView({block:'start'});
    };
  }
}
