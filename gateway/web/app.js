'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let initialized=false,cards=[],revision=null,editing=null,busy=false,status={},prefs={};
let desktopPrefs={workstation_url:'https://192.168.1.251:6080/',order:[]},draggingIcon=null;
let currentPage=null,navigation=0,savedConfig=null,settingsWindow=null;
let tailscaleRequest=null,tailscaleNavigation=0,settingsLoadingDone=null,wallpaperRead=0,wallpaperLoadingDone=null;
let faviconPreviewRequest=0,faviconPreviewTimer=null,faviconActive=0;
const faviconQueue=[],faviconPending=new Map(),faviconCache=new Map();
let appearance={fit:'cover',image:'',wallpaper:'coast',theme:'auto'},pendingAppearance=null;
let iconCatalog=['link','server','globe','folder','clash','adguard','tailscale'].map(id=>({id,name:({link:'链接',server:'服务器',globe:'网站',folder:'文件',clash:'Clash',adguard:'AdGuard Home',tailscale:'Tailscale'})[id],category:'常用',path:'/icons/'+id+'.svg'}));
let wallpaperCatalog=[{id:'coast',name:'海岸',path:'/assets/coast-wallpaper.webp'}];
const systemTheme=window.matchMedia('(prefers-color-scheme: dark)');
function applyTheme(theme='auto'){const chosen=['light','dark','auto'].includes(theme)?theme:'auto';document.documentElement.dataset.theme=chosen==='auto'?(systemTheme.matches?'dark':'light'):chosen;try{localStorage.setItem('gateway-theme',chosen);}catch{}}
try{appearance.theme=localStorage.getItem('gateway-theme')||'auto';applyTheme(appearance.theme);}catch{applyTheme('auto');}
systemTheme.addEventListener('change',()=>{if(appearance.theme==='auto')applyTheme('auto');});
async function loadCatalogs(){
  await Promise.allSettled([
    fetch('/icons/catalog.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(items=>{if(!Array.isArray(items))return;const valid=items.filter(item=>/^[a-z0-9-]+$/.test(item.id)&&typeof item.name==='string'&&item.path==='/icons/'+item.id+'.svg');if(valid.length)iconCatalog=valid;}),
    fetch('/assets/wallpapers/catalog.json').then(r=>{if(!r.ok)throw Error();return r.json();}).then(items=>{if(!Array.isArray(items))return;const valid=items.filter(item=>/^[a-z0-9-]+$/.test(item.id)&&typeof item.name==='string'&&/^\/assets\/[a-zA-Z0-9/_.-]+\.(webp|jpg|png)$/.test(item.path)&&!item.path.includes('..'));if(valid.length)wallpaperCatalog=valid;})
  ]);
}
function drawIconChoices(){
  const selected=$('#link-icon').value;$('#auto-icon').setAttribute('aria-pressed',String(selected==='auto'));
  const query=$('#icon-search').value.trim().toLocaleLowerCase(),list=$('#icon-choices');list.replaceChildren();
  const matches=iconCatalog.filter(item=>(item.name+' '+item.id+' '+(item.category||'')).toLocaleLowerCase().includes(query));
  for(const item of matches){const choice=button('',()=>{$('#link-icon').value=item.id;cancelFaviconPreview();drawIconChoices();list.querySelector('[aria-selected="true"]')?.focus();},'icon-choice');choice.dataset.icon=item.id;choice.setAttribute('role','option');choice.setAttribute('aria-label',item.name);choice.setAttribute('aria-selected',String(item.id===selected));choice.title=item.name;choice.tabIndex=item.id===selected?0:-1;choice.append(icon(item.id));list.append(choice);}
  if(!list.querySelector('[tabindex="0"]')&&list.firstChild)list.firstChild.tabIndex=0;
  $('#icon-empty').hidden=!!matches.length;
}
function faviconURL(value){
  try{const url=new URL(value.trim());if(!['http:','https:'].includes(url.protocol)||!url.hostname||url.username||url.password)return '';url.hash='';return '/api/favicon?url='+encodeURIComponent(url.href);}catch{return '';}
}
// Every favicon consumer shares the same queue; image elements render the fetched
// bytes locally so their requests cannot bypass the server's four-fetch limit.
function loadFavicon(source){
  if(!source)return Promise.resolve('');
  const cached=faviconCache.get(source);
  if(cached&&cached.expires>Date.now()){faviconCache.delete(source);faviconCache.set(source,cached);return Promise.resolve(cached.data);}
  faviconCache.delete(source);if(faviconPending.has(source))return faviconPending.get(source);
  let resolve;const pending=new Promise(done=>resolve=done);faviconPending.set(source,pending);faviconQueue.push({source,resolve});pumpFavicons();return pending;
}
function pumpFavicons(){
  while(faviconActive<3&&faviconQueue.length){
    const task=faviconQueue.shift();faviconActive++;
    fetchFavicon(task.source).catch(()=>'').then(data=>{
      faviconCache.set(task.source,{data,expires:Date.now()+(data?3600000:15000)});
      while(faviconCache.size>64)faviconCache.delete(faviconCache.keys().next().value);
      faviconPending.delete(task.source);task.resolve(data);
    }).finally(()=>{faviconActive--;pumpFavicons();});
  }
}
async function fetchFavicon(source){
  const controller=new AbortController(),timeout=setTimeout(()=>controller.abort(),12000);
  try{
    const response=await fetch(source,{credentials:'same-origin',signal:controller.signal});
    if(!response.ok)throw Error('Icon unavailable');
    const blob=await response.blob();
    if(!blob.size||blob.size>512*1024||!/^image\/(?:png|x-icon|vnd\.microsoft\.icon|jpeg|webp|gif)$/i.test(blob.type))throw Error('Invalid icon');
    return await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('Invalid icon'));reader.readAsDataURL(blob);});
  }finally{clearTimeout(timeout);}
}
function cancelFaviconPreview(){
  faviconPreviewRequest++;clearTimeout(faviconPreviewTimer);faviconPreviewTimer=null;
  $('#auto-icon').removeAttribute('aria-busy');
}
function previewFavicon(delay=450){
  cancelFaviconPreview();const preview=$('#auto-icon-preview');preview.src='/icons/link.svg';
  const source=faviconURL($('#link-url').value);if($('#link-icon').value!=='auto'||!source)return;
  const request=faviconPreviewRequest;$('#auto-icon').setAttribute('aria-busy','true');
  faviconPreviewTimer=setTimeout(()=>{
    faviconPreviewTimer=null;
    loadFavicon(source).then(data=>{
      if(request!==faviconPreviewRequest||!$('#link-dialog').open||$('#link-icon').value!=='auto')return;
      preview.src=data||'/icons/link.svg';$('#auto-icon').removeAttribute('aria-busy');
    });
  },delay);
}
function setupIconPicker(){
  $('#auto-icon-preview').onerror=function(){if(this.getAttribute('src')!=='/icons/link.svg')this.src='/icons/link.svg';};
  $('#auto-icon').onclick=()=>{$('#link-icon').value='auto';drawIconChoices();previewFavicon(0);};
  $('#link-url').addEventListener('input',()=>{if($('#link-icon').value==='auto')previewFavicon();});
  $('#link-dialog').addEventListener('close',cancelFaviconPreview);
  $('#icon-search').addEventListener('input',drawIconChoices);
  $('#icon-choices').addEventListener('keydown',e=>{const keys=['ArrowRight','ArrowLeft','ArrowUp','ArrowDown','Home','End'];if(!keys.includes(e.key))return;e.preventDefault();const items=[...$('#icon-choices').children],i=items.indexOf(document.activeElement);if(!items.length)return;const columns=Math.max(1,Math.round($('#icon-choices').clientWidth/items[0].offsetWidth));const delta={ArrowRight:1,ArrowLeft:-1,ArrowDown:columns,ArrowUp:-columns}[e.key];const n=e.key==='Home'?0:e.key==='End'?items.length-1:Math.max(0,Math.min(items.length-1,i+delta));items.forEach((item,index)=>item.tabIndex=index===n?0:-1);items[n].focus();});
}
function drawWallpapers(){const gallery=$('#wallpaper-gallery');gallery.replaceChildren();for(const item of wallpaperCatalog){const choice=button('',()=>{finishWallpaperRead();pendingAppearance.wallpaper=item.id;pendingAppearance.image='';wallpaperStyles($('#wallpaper-preview'),pendingAppearance);drawWallpapers();},'wallpaper-choice');choice.setAttribute('aria-pressed',String(!pendingAppearance.image&&pendingAppearance.wallpaper===item.id));const image=element('img');image.src=item.path;image.alt='';choice.append(image,element('span',item.name));gallery.append(choice);}}

const stateNames={Running:'已连接',NeedsLogin:'等待登录',NeedsMachineAuth:'等待设备批准',Stopped:'已断开',Starting:'正在连接',NoState:'尚未登录',Unavailable:'服务暂时不可用'};
const names={mihomo:'Mihomo',adguard:'AdGuard Home',tailscale:'Tailscale',panel:'Clash 面板'};
const editor=window.createYamlEditor?.($('#config-editor'),$('#config-content'),()=>{})||{getValue:()=>$('#config-content').value,setValue:v=>$('#config-content').value=v,setDisabled:v=>$('#config-content').disabled=v};
// The bundled editor exposes its token colors through generated stylesheet rules.
// Bind those five stable colors to theme variables without modifying the bundle.
function themeEditorTokens(){
  const tokens={'rgb(20, 92, 171)':'--syntax-key','rgb(138, 78, 18)':'--syntax-string','rgb(119, 80, 167)':'--syntax-number','rgb(107, 120, 137)':'--syntax-comment','rgb(82, 97, 116)':'--syntax-meta'};
  for(const sheet of document.styleSheets){try{for(const rule of sheet.cssRules){const token=tokens[rule.style?.color];if(token)rule.style.color='var('+token+')';}}catch{}}
}
themeEditorTokens();
// Each operation owns a lease, so an older request cannot dismiss a newer spinner.
const loadingRegions=new Map();
function beginLoading(region){
  if(!region)return ()=>{};
  let state=loadingRegions.get(region);
  if(!state){
    const overlay=element('div',undefined,'loading-overlay'),spinner=element('span',undefined,'loading-spinner');
    overlay.setAttribute('role','status');overlay.setAttribute('aria-label','正在加载');spinner.setAttribute('aria-hidden','true');overlay.append(spinner);
    state={tokens:new Set(),overlay,originalBusy:region.getAttribute('aria-busy')};
    state.position=()=>{overlay.style.top=(region.scrollTop+region.clientHeight/2)+'px';overlay.style.left=(region.scrollLeft+region.clientWidth/2)+'px';};
    region.classList.add('loading-region');region.setAttribute('aria-busy','true');region.append(overlay);loadingRegions.set(region,state);
    region.addEventListener('scroll',state.position,{passive:true});state.observer=new ResizeObserver(state.position);state.observer.observe(region);state.position();
  }
  const token=Symbol();state.tokens.add(token);
  return ()=>{
    if(!state.tokens.delete(token)||state.tokens.size)return;
    state.observer.disconnect();region.removeEventListener('scroll',state.position);state.overlay.remove();region.classList.remove('loading-region');
    if(state.originalBusy===null)region.removeAttribute('aria-busy');else region.setAttribute('aria-busy',state.originalBusy);
    loadingRegions.delete(region);
  };
}
function loadingRegion(target=null){
  if(target)return $(target);
  return $('#settings-dialog').open?$('#settings-content'):$('.desktop-workspace');
}
async function withLoading(region,work){const done=beginLoading(region);try{return await work();}finally{done();}}
function finishSettingsLoading(){settingsLoadingDone?.();settingsLoadingDone=null;}

async function api(path,options={}){
  let r;try{r=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});}catch{throw Error('无法连接网关，请检查网络后重试。');}
  let data;try{data=await r.json();}catch{throw Error('网关返回异常，请稍后重试。');}
  if(!r.ok){if(r.status===401&&!path.startsWith('/auth'))await authState();throw Error(data.error||'请求失败，请稍后重试。');}return data;
}
const post=(path,data={})=>api(path,{method:'POST',body:JSON.stringify(data)});
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function icon(name,url=''){const image=document.createElement('img');image.alt='';image.width=96;image.height=96;image.referrerPolicy='no-referrer';image.onerror=()=>{image.onerror=null;image.src='/icons/link.svg';};image.src='/icons/'+(name!=='auto'&&/^[a-z0-9-]+$/.test(name)?name:'link')+'.svg';if(name==='auto')loadFavicon(faviconURL(url)).then(data=>{if(data)image.src=data;});return image;}
function button(text,handler,className){const el=element('button',text,className);el.type='button';el.onclick=handler;return el;}
function configDirty(){return savedConfig!==null&&editor.getValue()!==savedConfig;}
async function discardChanges(){return !configDirty()||await askConfirm('配置文件尚未应用。离开后将丢弃这些修改，是否继续？');}
async function closeSettings(){if(!await discardChanges())return;destroySettings();}
function destroySettings(){finishSettingsLoading();if(settingsWindow){const w=settingsWindow;settingsWindow=null;w.close(true);}$('#settings-dialog').close();navigation++;currentPage=null;savedConfig=null;}
async function guard(work,target=null){
  if(busy)return;
  const done=beginLoading(loadingRegion(target));
  busy=true;const controls=$$('button,input,select,textarea').filter(el=>!el.disabled&&!el.closest('#auth-dialog, #confirm-dialog, #desktop-toast')&&!['close-settings','close-link'].includes(el.id));
  controls.forEach(el=>el.disabled=true);editor.setDisabled(true);
  try{await work();}catch(e){toast(e.message,true);}finally{busy=false;controls.filter(el=>el.isConnected).forEach(el=>el.disabled=el.dataset.stateDisabled==='true');editor.setDisabled(false);done();$('#refresh-subscription').disabled=!prefs.subscription?.url;}
}
function openLinkEditor(card=null){cancelFaviconPreview();editing=card?.id||null;$('#link-title').textContent=card?'编辑链接':'添加链接';$('#link-name').value=card?.name||'';$('#link-url').value=card?.url||'';$('#link-icon').value=card?(card.icon||'link'):'auto';$('#icon-search').value='';drawIconChoices();$('#link-newtab').checked=card?.open_in_new_tab??true;syncSelects();$('#link-dialog').showModal();previewFavicon(0);}
function desktopItems(){
  const builtins=[{name:'Clash',icon:'clash',url:'/ui/'},{name:'AdGuard Home',icon:'adguard',url:'/adguard/'},{name:'Tailscale',icon:'tailscale',page:'tailscale'},{name:'工作站',icon:'workstation',url:desktopPrefs.workstation_url},{name:'设置',icon:'settings',page:'overview'}].map(item=>({...item,id:'builtin:'+item.icon,fixed:true}));
  const items=[...builtins,...cards],lookup=new Map(items.map(item=>[item.id,item]));
  return [...new Set([...desktopPrefs.order,...lookup.keys()])].map(id=>lookup.get(id)).filter(Boolean);
}
function clearIconDrag(){draggingIcon=null;$$('.desktop-item').forEach(el=>el.classList.remove('dragging','drop-before','drop-after'));}
async function saveDesktopOrder(ids){await post('/cards/order',{ids});await loadCards();toast('桌面顺序已保存');}
function drawDesktop(){
  const desktop=$('#desktop');desktop.replaceChildren();
  for(const item of desktopItems()){
    const el=item.page?element('button'):element('a');el.className='desktop-item';el.dataset.id=item.id||item.icon;el._desktopItem=item;el.append(icon(item.icon||'link',item.url),element('span',item.name));
    if(item.page)el.onclick=()=>openSettings(item.page);else{el.href=item.url;if(item.open_in_new_tab||item.fixed){el.target='_blank';el.rel='noopener noreferrer';}}
    el.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation();showContext(e.clientX,e.clientY,item,el);});
    el.addEventListener('keydown',e=>{if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){e.preventDefault();const r=el.getBoundingClientRect();showContext(r.right,r.top,item,el);}});
    el.draggable=true;
    el.addEventListener('dragstart',e=>{if(busy){e.preventDefault();return;}draggingIcon=item.id;e.dataTransfer.setData('application/x-gateway-desktop',item.id);e.dataTransfer.effectAllowed='move';el.classList.add('dragging');});
    el.addEventListener('dragend',clearIconDrag);
    el.addEventListener('dragover',e=>{if(!draggingIcon||draggingIcon===item.id)return;e.preventDefault();e.dataTransfer.dropEffect='move';const after=e.clientY>el.getBoundingClientRect().top+el.offsetHeight/2;el.classList.toggle('drop-before',!after);el.classList.toggle('drop-after',after);});
    el.addEventListener('dragleave',()=>el.classList.remove('drop-before','drop-after'));
    el.addEventListener('drop',e=>{e.preventDefault();const from=draggingIcon,after=e.clientY>el.getBoundingClientRect().top+el.offsetHeight/2;clearIconDrag();if(!from||from===item.id)return;const ids=desktopItems().map(c=>c.id).filter(id=>id!==from);ids.splice(ids.indexOf(item.id)+(after?1:0),0,from);guard(()=>saveDesktopOrder(ids));});
    el.addEventListener('keydown',e=>{if(!e.altKey||!['ArrowUp','ArrowDown'].includes(e.key))return;e.preventDefault();const ids=desktopItems().map(c=>c.id),i=ids.indexOf(item.id),next=i+(e.key==='ArrowUp'?-1:1);if(next<0||next>=ids.length)return;[ids[i],ids[next]]=[ids[next],ids[i]];guard(async()=>{await saveDesktopOrder(ids);[...desktop.children].find(child=>child.dataset.id===item.id)?.focus();});});
    desktop.append(el);
  }drawLinks();
}
function drawLinks(){const list=$('#link-list');list.replaceChildren();if(!cards.length){list.append(element('p','还没有自定义链接。','muted'));return;}cards.forEach((card,index)=>{const row=element('div',undefined,'service-row'),details=element('div',undefined,'details'),tools=element('div',undefined,'tools');details.append(element('strong',card.name),element('span',card.url));tools.append(button('编辑',()=>openLinkEditor(card)),button('上移',()=>guard(async()=>{if(!index)return;const ids=cards.map(c=>c.id);[ids[index],ids[index-1]]=[ids[index-1],ids[index]];await post('/cards/order',{ids});await loadCards();})),button('下移',()=>guard(async()=>{if(index===cards.length-1)return;const ids=cards.map(c=>c.id);[ids[index],ids[index+1]]=[ids[index+1],ids[index]];await post('/cards/order',{ids});await loadCards();})),button('删除',()=>guard(async()=>{if(!await askConfirm('删除链接“'+card.name+'”？'))return;await api('/cards/'+card.id,{method:'DELETE'});await loadCards();}),'danger'));tools.children[1].disabled=index===0;tools.children[2].disabled=index===cards.length-1;row.append(icon(card.icon||'link',card.url),details,tools);list.append(row);});}
async function loadCards(){const data=await api('/cards');cards=data.cards;desktopPrefs=data.desktop;drawDesktop();}
async function loadStatus(){status=await api('/status');$('#home-domain').textContent='http://'+status.domain;}
function renderLoginSettings(auth){
  const required=auth.login_required!==false;
  $('#login-required').checked=required;
  $('#login-settings-status').textContent=required?'当前已开启密码登录。':'当前已关闭密码登录，打开网页即可进入网关。';
  $('#login-session').hidden=!required;
}
async function authState(){const a=await api('/auth');initialized=a.initialized;$('#auth-title').textContent=initialized?'登录网关':'欢迎使用 Gateway';$('#auth-copy').textContent=initialized?'使用管理员密码进入网关桌面，默认初始密码为 root。':'设置管理员密码，开始配置你的网关。';$('#auth-submit').textContent=initialized?'登录':'创建管理员';$('#confirm-field').hidden=initialized;$('#password').autocomplete=initialized?'current-password':'new-password';if(!a.authenticated){cards=[];desktopPrefs={workstation_url:"https://192.168.1.251:6080/",order:[]};drawDesktop();destroySettings();$('#link-dialog').close();navigation++;currentPage=null;savedConfig=null;$('#home-domain').textContent='';if(!$('#auth-dialog').open)$('#auth-dialog').showModal();return false;}$('#auth-dialog').close();await Promise.all([loadCards(),loadStatus(),loadAppearance()]);return true;}
async function openSettings(page='overview',{force=false}={}){
  if(!force&&$('#settings-dialog').open&&currentPage===page){showSettingsWindow();return;}
  if(!force&&!await discardChanges())return;
  finishSettingsLoading();const request=++navigation;currentPage=page;if(page!=='proxy')savedConfig=null;
  showSettingsWindow();$('#settings-dialog').classList.toggle('is-overview',page==='overview');settingsWindow?.window.classList.toggle('is-overview',page==='overview');$('#settings-content').scrollTop=0;const done=beginLoading($('#settings-content'));settingsLoadingDone=done;
  $$('[data-section]').forEach(el=>el.hidden=el.dataset.section!==page);
  $$('[data-page]').forEach(el=>{el.classList.toggle('active',el.dataset.page===page);el.setAttribute('aria-current',el.dataset.page===page?'page':'false');});
  try{
    const loaded=await api('/settings');if(request!==navigation)return;prefs=loaded;
    if(page==='proxy'){
      const c=await api('/proxy/config');if(request!==navigation)return;
      revision=c.revision;savedConfig=c.content;editor.setValue(c.content);if($('#config-filename'))$('#config-filename').textContent=status.configured?'config.yaml · 当前正在使用':'尚未导入配置文件';
      $('#subscription-url').value=prefs.subscription.url||'';$('#subscription-interval').value=prefs.subscription.interval_hours||0;syncSelects();
      $('#subscription-status').textContent=prefs.subscription.error||(prefs.subscription.last_updated?'上次更新：'+new Date(prefs.subscription.last_updated*1000).toLocaleString():'支持返回 Clash/Mihomo YAML 的配置订阅。');
      $('#refresh-subscription').disabled=busy||!prefs.subscription.url;
    }
    if(page==='dns'){$('#domain').value=prefs.domain;$('#domain-address').textContent='当前地址：'+status.address+' · http://'+prefs.domain;}
    if(page==='tailscale')await loadTailscale();
    if(page==='updates'){const task=await loadUpdates();if(task?.status==='running'){await job(task,{request});if(request===navigation)await loadUpdates();}}
    if(page==='desktop'){await loadCards();$('#workstation-url').value=desktopPrefs.workstation_url;}
    if(page==='account'){const auth=await api('/auth');if(request!==navigation)return;renderLoginSettings(auth);$('#login-settings-password').value='';}
  }catch(e){if(request===navigation){currentPage=null;toast(e.message,true);}}
  finally{done();if(settingsLoadingDone===done)settingsLoadingDone=null;}
}
function loadTailscale(){
  if(!tailscaleRequest||tailscaleNavigation!==navigation){
    tailscaleNavigation=navigation;const pending=renderTailscale().finally(()=>{if(tailscaleRequest===pending)tailscaleRequest=null;});tailscaleRequest=pending;
  }
  return tailscaleRequest;
}
async function renderTailscale(){
    const request=navigation;
    const t=await api('/tailscale');if(request!==navigation||currentPage!=='tailscale')return;
    const dl=$('#tailscale-status');dl.replaceChildren();
    const connection=t.state==='Running'&&!t.online?'正在重新连接':stateNames[t.state]||t.state;
    for(const [key,value] of [['状态',connection],['设备',t.name||'尚未登录'],['地址',(t.ips||[]).join(' · ')||'—'],['在线节点',String(t.peers)]])dl.append(element('dt',key),element('dd',value));
    $('#tailscale-subnets').textContent=(t.routes?.routes||'').split(',').filter(Boolean).join(' · ')||'未检测到局域网';
    $('#tailscale-approval').textContent=t.approval_note||'连接后自动配置内网访问，无需填写网段。';
    $('#tailscale-admin').hidden=!(t.state==='NeedsMachineAuth'||t.route_state==='pending');
    const link=$('#tailscale-login-link'),url=t.login_url;
    link.hidden=!(t.state==='NeedsLogin'&&url&&/^https:\/\/(login\.tailscale\.com|controlplane\.tailscale\.com)\//.test(url));
    if(!link.hidden)link.href=url;else link.removeAttribute('href');
    const action=$('#tailscale-action');
    action.hidden=!link.hidden||t.state==='NeedsMachineAuth';
    action.dataset.ts=t.state==='Running'?'disconnect':'connect';
    action.textContent=t.state==='Running'?'断开连接':t.state==='Starting'?'正在连接…':t.state==='Unavailable'?'重试连接':t.has_identity?'连接':'登录并连接';
    action.classList.toggle('primary',t.state!=='Running');
    action.dataset.stateDisabled=String(t.state==='Starting');action.disabled=busy||t.state==='Starting';
    const account=$('#tailscale-account');account.hidden=!t.has_identity||['NeedsLogin','NoState','Unavailable'].includes(t.state);if(account.hidden)account.open=false;
    const health=(t.health||[]).join('；');
    const refresh=$('#tailscale-refresh-status');refresh.classList.remove('error');refresh.textContent=health||'状态自动更新';
}
setInterval(()=>{
  if(currentPage!=='tailscale'||!$('#settings-dialog').open||document.hidden||busy)return;
  loadTailscale().catch(e=>{if(currentPage==='tailscale'){const refresh=$('#tailscale-refresh-status');refresh.textContent=e.message+' 状态更新会自动重试。';refresh.classList.add('error');}});
},4000);
async function loadUpdates(){const request=navigation,u=await api('/updates');if(request!==navigation||currentPage!=='updates')return;const list=$('#components');list.replaceChildren();for(const [component,manifest] of Object.entries(u.components)){const row=element('div',undefined,'service-row'),details=element('div',undefined,'details');const checked=u.checked[component];details.append(element('strong',names[component]),element('span','当前 '+(manifest.version||'未知')+(checked?.latest?' · 最新 '+checked.latest:checked?.error?' · '+checked.error:'')));const install=button(checked?.available?'升级':'重新安装',()=>guard(async()=>{if(!await askConfirm('升级 '+names[component]+'？对应服务将短暂中断。'))return;await job(await post('/updates/install',{component}));await loadUpdates();}));row.append(icon(component==='mihomo'||component==='panel'?'clash':component),details,install);list.append(row);}$('#upgrade-status').textContent=u.job?(u.job.status==='running'?'':u.job.status==='success'?'上次操作已完成':u.job.error||''):'';$('#refresh-job').hidden=u.job?.status!=='running';$('#refresh-job').onclick=()=>guard(async()=>{await job(u.job);await loadUpdates();});return u.job;}
async function job(initial,{request=null}={}){let task=initial;while(task.status==='running'){await new Promise(r=>setTimeout(r,1200));if(request!==null&&request!==navigation)return;task=await api('/jobs/'+task.id);}if(request!==null&&request!==navigation)return;if(task.status==='error')throw Error(task.error||'操作失败，请检查服务状态后重试。');toast('操作完成。');return task.result;}
$('#auth-dialog').addEventListener('cancel',e=>e.preventDefault());
$('#auth-form').onsubmit=async e=>{e.preventDefault();const password=$('#password').value;if(!initialized&&password!==$('#confirm-password').value){toast('两次密码不一致',true);return;}const done=beginLoading($('#auth-form'));$('#auth-submit').disabled=true;try{await post(initialized?'/auth/login':'/auth/setup',{password});$('#password').value='';$('#confirm-password').value='';await authState();}catch(e){toast(e.message,true);}finally{done();$('#auth-submit').disabled=false;}};
$('#open-settings').onclick=()=>openSettings();$('#close-settings').onclick=closeSettings;$$('[data-page]').forEach(b=>b.onclick=()=>openSettings(b.dataset.page));$('#add').onclick=()=>openLinkEditor();$('#add-from-settings').onclick=()=>openLinkEditor();$('#close-link').onclick=()=>$('#link-dialog').close();
$('#link-form').onsubmit=e=>{e.preventDefault();guard(async()=>{const value={name:$('#link-name').value,url:$('#link-url').value,icon:$('#link-icon').value,tag:'链接',open_in_new_tab:$('#link-newtab').checked};await api(editing?'/cards/'+editing:'/cards',{method:editing?'PATCH':'POST',body:JSON.stringify(value)});$('#link-dialog').close();await loadCards();toast(editing?'链接已更新。':'链接已添加。');},'#link-dialog .form-content');};
$('#workstation-form').onsubmit=e=>{e.preventDefault();guard(async()=>{await post('/settings/workstation',{url:$('#workstation-url').value.trim()});await loadCards();toast('工作站入口已保存。');});};
$('#upload-config').onclick=()=>$('#config-file').click();$('#config-file').onchange=async()=>{const file=$('#config-file').files[0];if(!file)return;try{if(file.size>2*1024*1024||!file.size||! /\.ya?ml$/i.test(file.name))throw Error('选择 2 MB 以内的 YAML 文件');editor.setValue(await file.text());if($('#config-filename'))$('#config-filename').textContent=file.name+' · 等待应用';toast('文件已载入，点击保存并应用后生效。');}catch(e){toast(e.message,true);}$('#config-file').value='';};
$('#save-config').onclick=()=>guard(async()=>{$('#save-config').disabled=true;try{const result=await post('/proxy/config',{filename:'config.yaml',content:editor.getValue(),revision});const saved=await api('/proxy/config');revision=saved.revision;savedConfig=saved.content;editor.setValue(saved.content);if($('#config-filename'))$('#config-filename').textContent='config.yaml · 当前正在使用';toast(result.message||'配置已应用。');await loadStatus();}finally{$('#save-config').disabled=false;}});
$('#subscription-form').onsubmit=e=>{e.preventDefault();guard(async()=>{if(!await discardChanges())return;await post('/subscription',{url:$('#subscription-url').value,interval_hours:Number($('#subscription-interval').value)});await openSettings('proxy',{force:true});await loadStatus();toast('订阅已导入。');});};$('#refresh-subscription').onclick=()=>guard(async()=>{if(!await discardChanges())return;await post('/subscription/refresh');await openSettings('proxy',{force:true});toast('订阅已刷新。');});
$('#domain-form').onsubmit=e=>{e.preventDefault();guard(async()=>{await post('/settings/domain',{domain:$('#domain').value});await loadStatus();await openSettings('dns',{force:true});toast('域名已保存。');});};
$$('[data-ts]').forEach(b=>b.onclick=()=>guard(async()=>{
  const action=b.dataset.ts;
  if(['disconnect','logout'].includes(action)&&!await askConfirm(action==='logout'?'退出 Tailscale 账号会中断远程访问，之后需要重新授权。是否继续？':'断开 Tailscale 会中断远程访问，登录身份会保留。是否继续？'))return;
  if(tailscaleRequest)await tailscaleRequest.catch(()=>{});
  const r=await post('/tailscale/action',{action});if(r.id)await job(r);await loadTailscale();
  toast(action==='logout'?'已退出 Tailscale 账号。':action==='disconnect'?'已断开连接。':'');
}));
$('#check-updates').onclick=()=>guard(async()=>{await job(await post('/updates/check'));await loadUpdates();});
$('#backup').onclick=()=>guard(async()=>{const r=await api('/backup');const a=element('a');a.href='data:application/gzip;base64,'+r.data;a.download=r.filename;document.body.append(a);a.click();a.remove();toast('备份已下载，请妥善保存。');});
$('#restore').onclick=()=>guard(async()=>{const file=$('#restore-file').files[0];if(!file||!$('#restore-confirm').checked)throw Error('请选择备份并确认替换配置');if(file.size>24*1024*1024)throw Error('备份超过 24 MB');const bytes=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));await job(await post('/restore',{data:btoa(text)}));savedConfig=null;await Promise.all([loadStatus(),loadCards(),loadAppearance()]);$('#restore-file').value='';$('#restore-confirm').checked=false;toast('备份已恢复。');});
$('#login-settings-form').onsubmit=e=>{e.preventDefault();guard(async()=>{await post('/auth/settings',{login_required:$('#login-required').checked,current_password:$('#login-settings-password').value});renderLoginSettings(await api('/auth'));$('#login-settings-password').value='';toast($('#login-required').checked?'密码登录已开启。':'密码登录已关闭，打开网页即可进入网关。');});};
$('#password-form').onsubmit=e=>{e.preventDefault();const password=$('#new-password').value;if(!$('#current-password').value){toast('请输入当前密码。',true);return;}if(!password){toast('请输入新密码。',true);return;}if(password!==$('#repeat-password').value){toast('两次新密码不一致，请重新输入。',true);return;}guard(async()=>{await post('/password',{current_password:$('#current-password').value,password});$('#password-form').reset();toast('密码已保存。');});};
$('#logout').onclick=()=>guard(async()=>{if(!await discardChanges())return;await post('/auth/logout');destroySettings();await authState();});
$('#settings-dialog').addEventListener('cancel',e=>{e.preventDefault();closeSettings();});
window.addEventListener('beforeunload',e=>{if(configDirty()){e.preventDefault();e.returnValue='';}});
function showSettingsWindow(){
  const shell=$('#settings-dialog');
  if(settingsWindow){if(settingsWindow.min)settingsWindow.restore();settingsWindow.show();settingsWindow.focus();return;}
  shell.show();
  const mobile=window.matchMedia('(max-width:700px)').matches;
  settingsWindow=new WinBox({title:'控制面板',icon:'/icons/settings.svg',mount:shell,class:['gateway-window','no-full',...(mobile?['no-resize','no-move']:[])],width:Math.min(1040,innerWidth-100),height:Math.min(700,innerHeight-130),minwidth:Math.min(640,innerWidth),minheight:400,x:'center',y:mobile?0:Math.max(60,(innerHeight-Math.min(700,innerHeight-130))/2),top:mobile?0:48,bottom:mobile?0:22,header:48,max:mobile,onclose(force){if(force)return false;closeSettings();return true;}});
  for(const [cls,label] of [['wb-close','关闭控制面板'],['wb-min','最小化控制面板'],['wb-max','最大化或还原控制面板']]){
    const control=settingsWindow.window.querySelector('.'+cls);control.setAttribute('role','button');control.setAttribute('aria-label',label);control.tabIndex=0;
    control.onkeydown=e=>{if(['Enter',' '].includes(e.key)){e.preventDefault();control.click();}};
  }
}
function askConfirm(copy,title='确认操作'){
  return new Promise(resolve=>{
    const dialog=$('#confirm-dialog');if(dialog.open){resolve(false);return;}$('#confirm-title').textContent=title;$('#confirm-copy').textContent=copy;
    const finish=value=>{dialog.close();dialog.oncancel=null;resolve(value);};
    $('#confirm-cancel').onclick=()=>finish(false);$('#confirm-accept').onclick=()=>finish(true);dialog.oncancel=e=>{e.preventDefault();finish(false);};
    dialog.showModal();$('#confirm-cancel').focus();
  });
}
let toastTimer=null,toastRemaining=0,toastStarted=0;
function dismissToast(){
  clearTimeout(toastTimer);toastTimer=null;
  const el=$('#desktop-toast');
  if(el.matches(':popover-open'))el.hidePopover();
  el.hidden=true;
}
function syncToastLayer(){
  const el=$('#desktop-toast');if(el.hidden)return;
  const parent=document.activeElement?.closest('dialog:modal')||$$('dialog:modal').at(-1)||document.body;
  if(el.parentElement!==parent){if(el.matches(':popover-open'))el.hidePopover();parent.append(el);}
  if(el.showPopover&&!el.matches(':popover-open'))el.showPopover();
}
function resumeToast(){
  clearTimeout(toastTimer);toastTimer=null;
  const el=$('#desktop-toast');
  if(el.hidden||el.matches(':hover')||el.contains(document.activeElement))return;
  toastStarted=performance.now();toastTimer=setTimeout(dismissToast,toastRemaining);
}
function pauseToast(){
  if(toastTimer===null)return;
  clearTimeout(toastTimer);toastTimer=null;
  toastRemaining=Math.max(0,toastRemaining-(performance.now()-toastStarted));
}
function toast(message,error=false){
  if(!message)return;
  const el=$('#desktop-toast'),text=$('#toast-message');
  el.classList.toggle('error',error);text.setAttribute('role',error?'alert':'status');text.setAttribute('aria-live',error?'assertive':'polite');
  el.hidden=false;syncToastLayer();text.textContent=message;
  toastRemaining=Math.max(error?8000:4200,Math.min(12000,message.length*160));resumeToast();
}
function setupToast(){
  const el=$('#desktop-toast');$('#toast-close').onclick=dismissToast;
  el.addEventListener('mouseenter',pauseToast);el.addEventListener('mouseleave',resumeToast);
  el.addEventListener('focusin',pauseToast);el.addEventListener('focusout',()=>queueMicrotask(resumeToast));
  el.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();dismissToast();}});
  new MutationObserver(records=>{if(records.some(record=>record.target instanceof HTMLDialogElement))syncToastLayer();}).observe(document.body,{subtree:true,attributes:true,attributeFilter:['open']});
}
async function deleteCard(card){if(!await askConfirm('删除链接“'+card.name+'”？此操作仅移除桌面入口。','删除桌面链接'))return;await api('/cards/'+card.id,{method:'DELETE'});await loadCards();toast('链接已删除');}
function hideContext(){const menu=$('#desktop-context-menu');if(menu)menu.hidden=true;}
function showContext(x,y,item=null,origin=null){
  if($('#auth-dialog').open)return;
  const menu=$('#desktop-context-menu');menu.replaceChildren();
  const add=(label,symbol,action,danger=false,url='')=>{const b=button('',()=>{hideContext();Promise.resolve(action()).catch(e=>toast(e.message,true));},danger?'danger':'');b.setAttribute('role','menuitem');b.append(icon(symbol,url),element('span',label));menu.append(b);};
  const line=()=>{const hr=element('div',undefined,'context-divider');hr.setAttribute('role','separator');menu.append(hr);};
  if(item){add('打开',item.icon||'link',()=>origin.click(),false,item.url);if(!item.fixed){line();add('编辑链接','link',()=>openLinkEditor(item));add('删除链接','trash',()=>guard(()=>deleteCard(item)));}else if(item.id==='builtin:workstation'){line();add('设置入口地址','settings',async()=>{await openSettings('desktop');$('#workstation-url').focus();});}}
  else{add('添加链接','add',()=>openLinkEditor());add('刷新桌面','refresh',()=>withLoading($('.desktop-workspace'),async()=>{await Promise.all([loadCards(),loadStatus()]);toast('桌面已刷新');}));add('按名称排列','sort',()=>guard(()=>saveDesktopOrder(desktopItems().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(c=>c.id))));line();add('个性化设置','appearance',()=>openPersonalization());add('控制面板','settings',()=>openSettings());}
  menu.hidden=false;menu.style.left=Math.max(8,Math.min(x,innerWidth-menu.offsetWidth-8))+'px';menu.style.top=Math.max(8,Math.min(y,innerHeight-menu.offsetHeight-8))+'px';menu.querySelector('button')?.focus();
  menu.onkeydown=e=>{const items=[...menu.querySelectorAll('button')],i=items.indexOf(document.activeElement);if(e.key==='Escape'){e.stopPropagation();hideContext();origin?.focus();}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?items.length-1:(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next].focus();}};
}
function setupSelects(){
  $$('select').forEach(select=>{
    const wrapper=element('div',undefined,'custom-select'),trigger=button('',()=>{if(select.disabled)return;const wasOpen=!list.hidden;$$('.select-options').forEach(el=>el.hidden=true);list.hidden=wasOpen;trigger.setAttribute('aria-expanded',String(!wasOpen));if(!wasOpen)list.querySelector('[aria-selected="true"]')?.focus();},'select-trigger'),list=element('div',undefined,'select-options');
    select.after(wrapper);wrapper.append(trigger,list);select.hidden=true;list.hidden=true;list.id=select.id+'-options';list.setAttribute('role','listbox');trigger.setAttribute('role','combobox');trigger.setAttribute('aria-controls',list.id);trigger.setAttribute('aria-expanded','false');trigger.setAttribute('aria-haspopup','listbox');trigger.setAttribute('aria-label',select.closest('label')?.firstChild?.textContent.trim()||'选择');
    const refresh=()=>{trigger.textContent=select.selectedOptions[0]?.textContent||'';trigger.disabled=select.disabled;for(const option of list.children)option.setAttribute('aria-selected',String(option.dataset.value===select.value));};
    for(const option of select.options){const choice=button(option.textContent,()=>{select.value=option.value;select.dispatchEvent(new Event('change',{bubbles:true}));list.hidden=true;trigger.setAttribute('aria-expanded','false');refresh();trigger.focus();});choice.dataset.value=option.value;choice.setAttribute('role','option');list.append(choice);}
    wrapper.addEventListener('keydown',e=>{if(e.key==='Escape'){list.hidden=true;trigger.setAttribute('aria-expanded','false');trigger.focus();e.stopPropagation();}if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();list.hidden=false;trigger.setAttribute('aria-expanded','true');const choices=[...list.children],i=choices.indexOf(document.activeElement),n=e.key==='Home'?0:e.key==='End'?choices.length-1:(i+(e.key==='ArrowDown'?1:-1)+choices.length)%choices.length;choices[n].focus();}});
    select._refresh=refresh;select.addEventListener('change',refresh);new MutationObserver(refresh).observe(select,{attributes:true,attributeFilter:['disabled']});refresh();
  });
}
function syncSelects(){$$('select').forEach(el=>el._refresh?.());}
function wallpaperSource(value){return value.image||wallpaperCatalog.find(item=>item.id===(value.wallpaper||'coast'))?.path||'/assets/coast-wallpaper.webp';}
function wallpaperStyles(el,value){el.style.backgroundImage='url("'+wallpaperSource(value)+'")';el.style.backgroundSize=value.fit==='stretch'?'100% 100%':['center','tile'].includes(value.fit)?'auto':value.fit;el.style.backgroundPosition='center';el.style.backgroundRepeat=value.fit==='tile'?'repeat':'no-repeat';}
function applyAppearance(value){appearance={fit:'cover',image:'',wallpaper:'coast',theme:'auto',...value};applyTheme(appearance.theme);document.body.style.setProperty('--wallpaper-image','url("'+wallpaperSource(appearance)+'")');document.body.style.backgroundSize=value.fit==='stretch'?'100% 100%':['center','tile'].includes(value.fit)?'auto':value.fit;document.body.style.backgroundPosition='center';document.body.style.backgroundRepeat=value.fit==='tile'?'repeat':'no-repeat';}
async function loadAppearance(){applyAppearance(await api('/appearance'));}
function finishWallpaperRead(){wallpaperRead++;wallpaperLoadingDone?.();wallpaperLoadingDone=null;$('#wallpaper-apply').disabled=busy;$('#wallpaper-file').value='';}
function openPersonalization(){finishWallpaperRead();$('#wallpaper-apply').disabled=busy;pendingAppearance={...appearance};wallpaperStyles($('#wallpaper-preview'),pendingAppearance);$$('[name=wallpaper-fit]').forEach(el=>el.checked=el.value===appearance.fit);$$('[name=appearance-theme]').forEach(el=>el.checked=el.value===appearance.theme);drawWallpapers();$('#personalization-dialog').showModal();}
function setupDesktop(){
  $$('form').forEach(form=>{
    form.noValidate=true;
    form.addEventListener('submit',e=>{
      const field=[...form.elements].find(control=>control.willValidate&&!control.validity.valid);
      if(!field)return;
      e.preventDefault();e.stopImmediatePropagation();field.focus();
      const label=field.getAttribute('aria-label')||field.labels?.[0]?.textContent.trim()||'此项';
      toast(field.validity.valueMissing?'请填写'+label+'。':field.validity.typeMismatch?'请输入有效的'+label+'。':field.validationMessage,true);
    },true);
  });
  setupSelects();setupIconPicker();
  document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!$('#desktop-context-menu').hidden){hideContext();return;}if(settingsWindow&&!document.querySelector('dialog:modal')){e.preventDefault();closeSettings();}});
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#desktop-context-menu'))hideContext();if(!e.target.closest('.custom-select')){$$('.select-options').forEach(el=>el.hidden=true);$$('.select-trigger').forEach(el=>el.setAttribute('aria-expanded','false'));}});
  document.addEventListener('contextmenu',e=>{if(e.target.closest('dialog,.winbox,.topbar,#desktop-context-menu'))return;e.preventDefault();showContext(e.clientX,e.clientY);});
  let hold=null,point=null;
  $('#desktop').addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;point=[e.clientX,e.clientY];const target=e.target.closest('.desktop-item');hold=setTimeout(()=>{const item=target?._desktopItem;showContext(e.clientX,e.clientY,item,target);hold=null;},600);});
  $('#desktop').addEventListener('pointermove',e=>{if(point&&Math.hypot(e.clientX-point[0],e.clientY-point[1])>10){clearTimeout(hold);hold=null;}});
  for(const type of ['pointerup','pointercancel'])$('#desktop').addEventListener(type,()=>{clearTimeout(hold);hold=null;point=null;});
  $('#desktop').addEventListener('click',e=>{if(!$('#desktop-context-menu').hidden){e.preventDefault();e.stopImmediatePropagation();}},true);
  $('#show-desktop').onclick=()=>{if(settingsWindow){if(settingsWindow.min)settingsWindow.restore();else settingsWindow.minimize();}};
  $('#open-personalization').onclick=openPersonalization;$$('[data-personalization]').forEach(el=>el.onclick=openPersonalization);
  $('#minimize-settings').onclick=()=>settingsWindow?.minimize();$('#maximize-settings').onclick=()=>{if(settingsWindow?.max)settingsWindow.restore();else settingsWindow?.maximize();};
  for(const id of ['close-personalization','wallpaper-cancel'])$('#'+id).onclick=()=>$('#personalization-dialog').close();
  $('#personalization-dialog').addEventListener('close',finishWallpaperRead);
  $('#wallpaper-preview').onclick=()=>$('#wallpaper-file').click();$('#wallpaper-upload').onclick=()=>$('#wallpaper-file').click();$$('[name=appearance-theme]').forEach(el=>el.onchange=()=>pendingAppearance.theme=el.value);
  $$('[name=wallpaper-fit]').forEach(el=>el.onchange=()=>{pendingAppearance.fit=el.value;wallpaperStyles($('#wallpaper-preview'),pendingAppearance);});
  $('#wallpaper-reset').onclick=()=>{finishWallpaperRead();pendingAppearance.image='';pendingAppearance.wallpaper='coast';wallpaperStyles($('#wallpaper-preview'),pendingAppearance);drawWallpapers();};
  $('#wallpaper-file').onchange=async()=>{
    const file=$('#wallpaper-file').files[0];if(!file)return;
    finishWallpaperRead();const request=wallpaperRead,draft=pendingAppearance,done=beginLoading(loadingRegion('#personalization-dialog .personalization-content'));wallpaperLoadingDone=done;
    const isCurrent=()=>request===wallpaperRead&&pendingAppearance===draft&&$('#personalization-dialog').open;
    $('#wallpaper-apply').disabled=true;
    try{
      if(file.size>3*1024*1024||!['image/png','image/jpeg','image/webp'].includes(file.type))throw Error('请选择 3 MB 以内的 PNG、JPEG 或 WebP 图片');
      const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(reader.result);reader.onerror=()=>reject(Error('图片读取失败'));reader.readAsDataURL(file);});
      await new Promise((resolve,reject)=>{const image=new Image();image.onload=resolve;image.onerror=()=>reject(Error('图片无法打开，请重新选择'));image.src=data;});
      if(!isCurrent())return;draft.image=data;wallpaperStyles($('#wallpaper-preview'),draft);drawWallpapers();
    }catch(e){if(isCurrent())toast(e.message,true);}
    finally{done();if(wallpaperLoadingDone===done)wallpaperLoadingDone=null;if(isCurrent()){$('#wallpaper-apply').disabled=busy;$('#wallpaper-file').value='';}}
  };
  $('#wallpaper-apply').onclick=()=>guard(async()=>{const saved=await post('/appearance',pendingAppearance);applyAppearance(saved);$('#personalization-dialog').close();toast('个性化设置已保存');},'#personalization-dialog .personalization-content');
  $('#restore-file').addEventListener('change',()=>$('#restore-filename').textContent=$('#restore-file').files[0]?.name||'尚未选择文件');
  window.addEventListener('resize',()=>{hideContext();if(!settingsWindow)return;const mobile=innerWidth<=700;if(mobile)settingsWindow.maximize();});
}

setupToast();setupDesktop();drawDesktop();withLoading($('.desktop-workspace'),async()=>{await loadCatalogs();await authState();}).catch(e=>{if(!$('#auth-dialog').open)$('#auth-dialog').showModal();toast(e.message,true);});
