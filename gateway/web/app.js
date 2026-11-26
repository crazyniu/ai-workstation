'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let initialized=false,cards=[],revision=null,editing=null,busy=false,status={};
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
const componentIcons={mihomo:'clash',adguard:'adguard',tailscale:'tailscale',panel:'globe'};
const editor=window.createYamlEditor?.($('#config-editor'),$('#config-content'),updateConfigState)||{getValue:()=>$('#config-content').value,setValue:v=>$('#config-content').value=v,setDisabled:v=>$('#config-content').disabled=v};
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
  if(proxyWindow?.focused)return $('#proxy-workspace');
  return $('#settings-dialog').open?$('#settings-content'):$('.desktop-workspace');
}
async function withLoading(region,work){const done=beginLoading(region);try{return await work();}finally{done();}}
function finishSettingsLoading(){settingsLoadingDone?.();settingsLoadingDone=null;}

async function api(path,options={}){
  let r;try{r=await fetch('/api'+path,{...options,headers:{'Content-Type':'application/json',...options.headers}});}catch{throw Error('无法连接网关，请检查网络后重试。');}
  let data;try{data=await r.json();}catch{throw Error('网关返回异常，请稍后重试。');}
  if(!r.ok){if(r.status===401&&!path.startsWith('/auth'))await readAccess();throw Error(data.error||'请求失败，请稍后重试。');}return data;
}
const post=(path,data={})=>api(path,{method:'POST',body:JSON.stringify(data)});
function element(tag,text,className){const el=document.createElement(tag);if(text!==undefined)el.textContent=text;if(className)el.className=className;return el;}
function icon(name,url=''){const image=document.createElement('img');image.alt='';image.width=96;image.height=96;image.referrerPolicy='no-referrer';image.onerror=()=>{image.onerror=null;image.src='/icons/link.svg';};image.src='/icons/'+(name!=='auto'&&/^[a-z0-9-]+$/.test(name)?name:'link')+'.svg';if(name==='auto')loadFavicon(faviconURL(url)).then(data=>{if(data)image.src=data;});return image;}
function button(text,handler,className){const el=element('button',text,className);el.type='button';el.onclick=handler;return el;}
function glyph(name){const ns='http://www.w3.org/2000/svg',svg=document.createElementNS(ns,'svg'),use=document.createElementNS(ns,'use');svg.setAttribute('class','glyph');svg.setAttribute('aria-hidden','true');use.setAttribute('href','#i-'+name);svg.append(use);return svg;}
function iconButton(name,label,handler,className=''){const el=button('',handler,('icon-button '+className).trim());el.setAttribute('aria-label',label);el.title=label;el.append(glyph(name));return el;}
function setTone(el,label,tone='idle'){el.textContent=label;el.dataset.tone=tone;}
function configDirty(){return savedConfig!==null&&editor.getValue()!==savedConfig;}
async function discardChanges(){return !configDirty()||await askConfirm('配置文件尚未应用。离开后将丢弃这些修改，是否继续？','放弃更改',{accept:'放弃',danger:true});}
function closeSettings(){destroySettings();}
function destroySettings(){finishSettingsLoading();if(settingsWindow){const w=settingsWindow;settingsWindow=null;releaseGatewayWindow(w);}$('#settings-dialog').close();navigation++;currentPage=null;}
async function guard(work,target=null){
  if(busy)return;
  const done=beginLoading(loadingRegion(target));
  busy=true;const controls=$$('button,input,select,textarea').filter(el=>!el.disabled&&!el.closest('#auth-dialog, #confirm-dialog, #desktop-toast')&&el.id!=='close-link');
  controls.forEach(el=>el.disabled=true);editor.setDisabled(true);
  try{await work();}catch(e){toast(e.message,true);}finally{busy=false;
    // Controls that track their own state may have changed it during the work.
    new Set([...controls.filter(el=>el.isConnected),...$$('[data-state-disabled]')]).forEach(el=>el.disabled=el.dataset.stateDisabled==='true');editor.setDisabled(false);done();}
}
function openLinkEditor(card=null){cancelFaviconPreview();editing=card?.id||null;$('#link-title').textContent=card?'编辑链接':'添加链接';$('#link-name').value=card?.name||'';$('#link-url').value=card?.url||'';$('#link-icon').value=card?(card.icon||'link'):'auto';$('#icon-search').value='';drawIconChoices();$('#link-newtab').checked=card?.open_in_new_tab??true;$('#link-dialog').showModal();previewFavicon(0);}
// System apps live in the Dock; the desktop holds the administrator's own links.
// On a phone the home screen also lists the apps that do not fit in the Dock.
const systemApps=[
  {id:'settings',name:'控制面板',icon:'settings',open:()=>openSettings()},
  {id:'proxy',name:'代理配置',icon:'clash',open:()=>openProxyWindow()},
  {id:'transfer',name:'局域网互传',icon:'files',open:()=>openFrameApp('transfer')},
  {id:'workstation',name:'工作站',icon:'workstation',url:()=>desktopPrefs.workstation_url},
  {id:'panel',name:'Clash 面板',icon:'speedtest',open:()=>openFrameApp('panel')},
  {id:'adguard',name:'AdGuard Home',icon:'adguard',open:()=>openFrameApp('adguard')},
];
const phoneDock=['settings','proxy','transfer','workstation'];
const phone=window.matchMedia('(max-width:700px)');
function desktopItems(){
  const lookup=new Map(cards.map(card=>[card.id,card]));
  return [...new Set([...desktopPrefs.order.filter(id=>lookup.has(id)),...lookup.keys()])].map(id=>lookup.get(id));
}
function appLauncher(app,className){
  const el=app.url?element('a'):element('button');el.className=className;el.dataset.app=app.id;el.append(icon(app.icon),element('span',app.name));
  if(app.url){el.href=app.url();el.target='_blank';el.rel='noopener noreferrer';}else{el.type='button';el.onclick=app.open;}
  el.setAttribute('aria-label',app.name);
  el.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation();showContext(e.clientX,e.clientY,{...app,system:true},el);});
  return el;
}
function drawDock(){
  const dock=$('#dock');dock.replaceChildren();
  for(const app of systemApps){const item=appLauncher(app,'dock-item');item.dataset.label=app.name;if(!phoneDock.includes(app.id))item.classList.add('desktop-only');dock.append(item);}
  markRunningApps();
}
function markRunningApps(){
  const running=new Set([settingsWindow&&'settings',proxyWindow&&'proxy',...frameWindows.keys()].filter(Boolean));
  for(const item of $$('.dock-item'))item.classList.toggle('running',running.has(item.dataset.app));
}
function clearIconDrag(){draggingIcon=null;$$('.desktop-item').forEach(el=>el.classList.remove('dragging','drop-before','drop-after'));}
async function saveDesktopOrder(ids){await post('/cards/order',{ids});await loadCards();toast('桌面顺序已保存');}
function drawDesktop(){
  const desktop=$('#desktop');desktop.replaceChildren();
  // Phones show every app on the home screen; desktops keep system apps in the Dock.
  for(const app of systemApps.filter(app=>!phoneDock.includes(app.id))){const el=appLauncher(app,'desktop-item phone-only');desktop.append(el);}
  for(const item of desktopItems()){
    const el=element('a');el.className='desktop-item';el.title=item.name;el.dataset.id=item.id;el._desktopItem=item;el.append(icon(item.icon||'link',item.url),element('span',item.name));
    el.href=item.url;if(item.open_in_new_tab){el.target='_blank';el.rel='noopener noreferrer';}
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
  }
  if(!cards.length&&initialized&&$('#auth-dialog').open===false){
    const hint=button('',()=>openLinkEditor(),'desktop-item desktop-add');hint.append(element('span','+','desktop-add-mark'),element('span','添加链接'));desktop.append(hint);
  }
  drawDock();drawLinks();
}
function moveLink(index,delta){
  return guard(async()=>{
    const ids=cards.map(c=>c.id),next=index+delta;if(next<0||next>=ids.length)return;
    [ids[index],ids[next]]=[ids[next],ids[index]];await post('/cards/order',{ids});await loadCards();
    const row=$('#link-list').children[next],same=row?.querySelector(delta<0?'[data-move=up]':'[data-move=down]');
    (same&&same.dataset.stateDisabled!=='true'?same:row?.querySelector('[data-move]:not([data-state-disabled=true])'))?.focus();
  });
}
function drawLinks(){
  const list=$('#link-list');list.replaceChildren();
  if(!cards.length){const empty=element('div',undefined,'empty-state');empty.append(element('strong','还没有自定义链接'),element('span','添加 NAS、路由器或常用服务后，它们会显示在桌面上。'));list.append(empty);return;}
  cards.forEach((card,index)=>{
    const row=element('div',undefined,'setting-row'),details=element('div',undefined,'setting-copy'),tools=element('div',undefined,'row-actions'),image=icon(card.icon||'link',card.url);
    image.className='row-icon';details.append(element('strong',card.name),element('span',card.url));
    const up=iconButton('up','上移 '+card.name,()=>moveLink(index,-1)),down=iconButton('down','下移 '+card.name,()=>moveLink(index,1));
    up.dataset.move='up';down.dataset.move='down';
    for(const [control,off] of [[up,index===0],[down,index===cards.length-1]]){control.disabled=off;control.dataset.stateDisabled=String(off);}
    tools.append(iconButton('edit','编辑 '+card.name,()=>openLinkEditor(card)),up,down,iconButton('trash','删除 '+card.name,()=>guard(()=>deleteCard(card)),'danger'));
    row.append(image,details,tools);list.append(row);
  });
}
async function loadCards(){const data=await api('/cards');cards=data.cards;desktopPrefs=data.desktop;drawDesktop();}
async function loadStatus(){status=await api('/status');}
let loginRequiredSaved=true;
function renderLoginSettings(auth){
  loginRequiredSaved=auth.login_required!==false;
  $('#login-required').checked=loginRequiredSaved;
  updateLoginHint();
  $('#login-session').hidden=!loginRequiredSaved;
}
// The password confirmation only appears once the switch differs from the saved state.
function updateLoginHint(){
  const required=$('#login-required').checked,changed=required!==loginRequiredSaved,hint=$('#login-settings-status');
  $('#login-confirm').hidden=!changed;if(!changed)$('#login-settings-password').value='';
  hint.className='callout '+(required?'':'warn');
  hint.textContent=required?'开启后，打开网关桌面需要输入管理员密码。':'关闭后，能访问网关网页的设备都可以直接管理网关。';
}
$('#login-required').addEventListener('change',updateLoginHint);
async function readAccess() {
  const access = await api('/auth');
  initialized = access.initialized;
  if (access.authenticated) {
    $('#auth-dialog').close();
    return true;
  }
  $('#auth-title').textContent = initialized ? '登录网关' : '创建管理员';
  $('#auth-copy').textContent = initialized ? '默认初始密码为 root。' : '';
  $('#auth-submit').textContent = initialized ? '登录' : '创建管理员';
  $('#confirm-field').hidden = initialized;
  $('#password').autocomplete = initialized ? 'current-password' : 'new-password';
  cards = [];
  desktopPrefs = {workstation_url:'https://192.168.1.251:6080/', order:[]};
  drawDesktop();
  destroyProxyWindow();
  destroySettings();
  closeAllWindows();
  $('#menubar-tailscale').hidden = true;
  $('#menubar-updates').hidden = true;
  $('#link-dialog').close();
  hideSystemMenu();
  if (!$('#auth-dialog').open) $('#auth-dialog').showModal();
  return false;
}
async function authState() {
  if (!await readAccess()) return false;
  await Promise.all([loadCards(), loadStatus(), loadAppearance()]);
  const release = loadWebRelease(false, true).catch(e => toast(e.message, true));
  refreshMenubarStatus();
  api('/updates').then(async u => { await Promise.race([release, new Promise(r => setTimeout(r, 4000))]); setUpdateBadge(countUpdates(u, latestWebRelease)); }).catch(() => {});
  return true;
}
async function openSettings(page='overview',{force=false}={}){
  if(page==='proxy'||page==='ranges')return openProxyWindow(force, page==='ranges');
  if(!force&&$('#settings-dialog').open&&currentPage===page){showSettingsWindow();return;}
  const previousPage=currentPage;
  finishSettingsLoading();const request=++navigation;currentPage=page;
  showSettingsWindow();$('#settings-dialog').classList.toggle('is-overview',page==='overview');settingsWindow?.window.classList.toggle('is-overview',page==='overview');$('#settings-content').scrollTop=0;const done=beginLoading($('#settings-content'));settingsLoadingDone=done;
  $$('[data-section]').forEach(el=>el.hidden=el.dataset.section!==page);
  $$('#settings-nav [data-page]').forEach(el=>{const on=el.dataset.page===page;el.classList.toggle('active',on);if(on)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  if(!force){
    const section=$('#settings-content > section:not([hidden])');
    const returnButton=page==='overview'&&previousPage?section.querySelector('[data-page="'+previousPage+'"]'):null;
    if(returnButton)returnButton.focus({preventScroll:true});
    else {const title=section.querySelector('h2');title.tabIndex=-1;title.focus({preventScroll:true});}
  }
  try{
    const prefs=await api('/settings');if(request!==navigation)return;
    // Status cards fill in on their own; a slow Tailscale query must not hold the page spinner.
    if(page==='overview')loadOverview(request).catch(e=>{if(request===navigation)toast(e.message,true);});
    if(page==='dns'){$('#domain').value=prefs.domain;$('#domain-address').textContent='当前地址：'+status.address+' · http://'+prefs.domain;}
    if(page==='tailscale')await loadTailscale();
    if(page==='updates'){loadWebRelease().catch(e=>toast(e.message,true));const webJob=await api('/web-release/job');if(webJob.status==='running'){await followWebRelease(webJob);return;}const task=await loadUpdates();if(task?.status==='running'){await job(task,{request});if(request===navigation)await loadUpdates();}}
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
const stateTones={Starting:'busy',NeedsLogin:'warn',NeedsMachineAuth:'warn',NoState:'idle',Stopped:'idle',Unavailable:'error'};
const routeStates={active:['已生效','ok'],pending:['等待批准','warn'],configuring:['正在配置','busy'],waiting:['等待连接','idle'],error:['异常','error']};
function tailscaleSummary(t){
  if(t.state==='Running')return t.online?{label:'已连接',tone:'ok'}:{label:'正在重新连接',tone:'busy'};
  return {label:stateNames[t.state]||t.state||'未知',tone:stateTones[t.state]||'idle'};
}
function markTailscale(t){const summary=tailscaleSummary(t),dot=$('#nav-tailscale-dot'),item=$('#menubar-tailscale');dot.hidden=false;dot.dataset.tone=summary.tone;dot.title='Tailscale：'+summary.label;item.hidden=false;item.dataset.tone=summary.tone;item.title='Tailscale：'+summary.label;$('#menubar-tailscale-label').textContent='Tailscale：'+summary.label;return summary;}
function serviceSummary(text=''){
  const rows=text.split('\n').map(line=>line.trim().split(/\s+/)).filter(row=>row[0]&&row[1]),stopped=rows.filter(row=>row[1]!=='RUNNING');
  if(!rows.length)return {label:'状态未知',tone:'idle'};
  return stopped.length?{label:stopped.length+' 个服务异常',tone:'warn',detail:stopped.map(row=>row[0]).join('、')}:{label:'运行正常',tone:'ok'};
}
async function loadOverview(request){
  const [current,ts,updateState,release]=await Promise.allSettled([loadStatus(),api('/tailscale'),api('/updates'),api('/web-release')]);
  if(request!==navigation)return;
  const domain=$('#overview-domain'),services=current.status==='fulfilled'?serviceSummary(status.services):{label:'读取失败',tone:'error'};
  $('#overview-address').textContent=status.address||'—';
  domain.textContent=status.domain?'http://'+status.domain:'—';domain.href=status.domain?'http://'+status.domain+'/':'/';
  setTone($('#overview-services'),services.label,services.tone);$('#overview-services').title=services.detail||'';
  if(ts.status==='fulfilled'){
    const t=ts.value,summary=markTailscale(t),ips=t.ips||[];
    setTone($('#overview-ts-state'),summary.label,summary.tone);
    $('#overview-ts-ip').textContent=ips.find(ip=>!ip.includes(':'))||ips[0]||'未分配地址';
    $('#overview-ts-detail').textContent=t.state==='Running'?(t.name||'本机')+' · '+t.peers+' 台设备在线':'打开 Tailscale 设置以连接';
  }else{setTone($('#overview-ts-state'),'读取失败','error');$('#overview-ts-ip').textContent='—';$('#overview-ts-detail').textContent=ts.reason.message;}
  const info=release.status==='fulfilled'?release.value:null,u=updateState.status==='fulfilled'?updateState.value:null,count=countUpdates(u,info);
  setUpdateBadge(count);
  $('#overview-web-version').textContent=info?'Web '+releaseLabel(info.current):'—';
  const detail=$('#overview-update-detail'),state=$('#overview-update-state');
  if(!u&&!info){setTone(state,'读取失败','error');detail.textContent=(updateState.reason||release.reason).message;}
  else if(count){setTone(state,count+' 项更新','busy');detail.textContent='前往服务升级查看并安装';}
  else if(info?.latest||Object.keys(u?.checked||{}).length){setTone(state,'已是最新','ok');detail.textContent='网关 Web 与核心组件均为最新版本';}
  else{setTone(state,'未检查','idle');detail.textContent='尚未检查更新';}
}
async function renderTailscale(){
    const request=navigation;
    const t=await api('/tailscale');if(request!==navigation||currentPage!=='tailscale')return;
    const summary=markTailscale(t),dl=$('#tailscale-status');
    setTone($('#tailscale-state'),summary.label,summary.tone);
    $('#tailscale-device').textContent=t.name||(t.has_identity?'Tailscale':'尚未登录 Tailscale');
    dl.replaceChildren();
    for(const [key,value,mono] of [['Tailscale 地址',(t.ips||[]).join('\n')||'—',true],['在线设备',t.state==='Running'?t.peers+' 台':'—'],['登录身份',t.has_identity?'已保存在网关':'未登录']]){
      const group=element('div'),dd=element('dd',value);if(mono)dd.className='mono';group.append(element('dt',key),dd);dl.append(group);
    }
    $('#tailscale-subnets').textContent=(t.routes?.routes||'').split(',').filter(Boolean).join('\n')||'未检测到局域网';
    const [routeLabel,routeTone]=routeStates[t.route_state]||['—','idle'];setTone($('#tailscale-route-state'),routeLabel,routeTone);
    const approval=$('#tailscale-approval');approval.textContent=t.approval_note||'';approval.className='callout'+({error:' error',pending:' warn',active:' ok'}[t.route_state]||'');
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
    $('#tailscale-account').hidden=!t.has_identity||['NeedsLogin','NoState','Unavailable'].includes(t.state);
    const refresh=$('#tailscale-refresh-status');refresh.className='callout warn';refresh.textContent=(t.health||[]).join('；');
}
setInterval(()=>{
  if(currentPage!=='tailscale'||!$('#settings-dialog').open||document.hidden||busy)return;
  loadTailscale().catch(e=>{if(currentPage==='tailscale'){const refresh=$('#tailscale-refresh-status');refresh.textContent=e.message+' 状态更新会自动重试。';refresh.className='callout error';}});
},4000);
async function loadUpdates(){
  const request=navigation,u=await api('/updates');
  if(request!==navigation||currentPage!=='updates')return;
  const list=$('#components');list.replaceChildren();
  for(const [component,manifest] of Object.entries(u.components)){
    const checked=u.checked[component],current=manifest.version;
    if(!current || current==='unknown')continue;
    const available=!checked?.error&&checked?.available&&checked.latest!==current;
    const row=element('div',undefined,'setting-row'),details=element('div',undefined,'setting-copy');
    const updateText=checked?.error?'检查失败：'+checked.error:available?'可升级到 '+checked.latest:checked?.latest?'已是最新版':'尚未检查更新';
    details.append(element('strong',names[component]||component),element('span',current+' · '+updateText,'setting-meta'+(checked?.error?' is-error':available?' is-update':'')));
    row.append(icon(componentIcons[component]||component),details);
    if(available)row.append(button('升级',()=>guard(async()=>{
      if(!await askConfirm((names[component]||component)+' 将升级到 '+checked.latest+'，期间服务会短暂中断。是否继续？','升级 '+(names[component]||component)))return;
      await job(await post('/updates/install',{component}));await loadUpdates();
    }),'primary'));
    list.append(row);
  }
  const errors=Object.entries(u.checked).filter(([,value])=>value.error).map(([component,value])=>(names[component]||component)+'：'+value.error);
  $('#upgrade-status').textContent=errors.length?'检查失败 · '+errors.join('；'):u.job?(u.job.status==='running'?'升级任务进行中…':u.job.status==='success'?'上次操作已完成。':u.job.error||''):'';
  $('#refresh-job').hidden=u.job?.status!=='running';
  $('#refresh-job').onclick=()=>guard(async()=>{await job(u.job);await loadUpdates();});
  setUpdateBadge(countUpdates(u,latestWebRelease));
  return u.job;
}
function countUpdates(u,release){
  let count=release?.available&&!release.error?1:0;
  for(const [component,manifest] of Object.entries(u?.components||{})){const checked=u.checked?.[component];if(manifest.version&&manifest.version!=='unknown'&&checked?.available&&!checked.error&&checked.latest!==manifest.version)count++;}
  return count;
}
function setUpdateBadge(count){const badge=$('#nav-update-badge'),item=$('#menubar-updates');badge.hidden=!count;badge.textContent=count?String(count):'';badge.title=count?count+' 项更新可用':'';item.hidden=!count;$('#menubar-updates-count').textContent=count?count+' 项更新':'';item.title=count?count+' 项更新可用':'';}
async function job(initial,{request=null}={}){let task=initial;while(task.status==='running'){await new Promise(r=>setTimeout(r,1200));if(request!==null&&request!==navigation)return;task=await api('/jobs/'+task.id);}if(request!==null&&request!==navigation)return;if(task.status==='error')throw Error(task.error||'操作失败，请检查服务状态后重试。');toast('操作完成。');return task.result;}
$('#auth-dialog').addEventListener('cancel',e=>e.preventDefault());
$('#auth-form').onsubmit=async e=>{e.preventDefault();const password=$('#password').value;if(!initialized&&password!==$('#confirm-password').value){toast('两次密码不一致',true);return;}const done=beginLoading($('#auth-form'));$('#auth-submit').disabled=true;try{await post(initialized?'/auth/login':'/auth/setup',{password});$('#password').value='';$('#confirm-password').value='';await authState();}catch(e){toast(e.message,true);}finally{done();$('#auth-submit').disabled=false;}};
$$('[data-page]').forEach(b=>b.onclick=()=>openSettings(b.dataset.page));$$('[data-app]').forEach(b=>b.onclick=()=>openFrameApp(b.dataset.app));$('#add-from-settings').onclick=()=>openLinkEditor();$('#close-link').onclick=()=>$('#link-dialog').close();
$('#link-form').onsubmit=e=>{e.preventDefault();guard(async()=>{const value={name:$('#link-name').value,url:$('#link-url').value,icon:$('#link-icon').value,tag:'链接',open_in_new_tab:$('#link-newtab').checked};await api(editing?'/cards/'+editing:'/cards',{method:editing?'PATCH':'POST',body:JSON.stringify(value)});$('#link-dialog').close();await loadCards();toast(editing?'链接已更新。':'链接已添加。');},'#link-dialog .form-content');};
$('#workstation-form').onsubmit=e=>{e.preventDefault();guard(async()=>{await post('/settings/workstation',{url:$('#workstation-url').value.trim()});await loadCards();toast('工作站入口已保存。');});};
setupProxyEditor();
$('#domain-form').onsubmit=e=>{e.preventDefault();guard(async()=>{await post('/settings/domain',{domain:$('#domain').value});await loadStatus();await openSettings('dns',{force:true});toast('域名已保存。');});};
$$('[data-ts]').forEach(b=>b.onclick=()=>guard(async()=>{
  const action=b.dataset.ts;
  if(['disconnect','logout'].includes(action)&&!await askConfirm(action==='logout'?'退出 Tailscale 账号会中断远程访问，之后需要重新授权。是否继续？':'断开 Tailscale 会中断远程访问，登录身份会保留。是否继续？',action==='logout'?'退出 Tailscale':'断开 Tailscale',{accept:action==='logout'?'退出':'断开',danger:true}))return;
  if(tailscaleRequest)await tailscaleRequest.catch(()=>{});
  const r=await post('/tailscale/action',{action});if(r.id)await job(r);await loadTailscale();
  toast(action==='logout'?'已退出 Tailscale 账号。':action==='disconnect'?'已断开连接。':'');
}));
$('#check-updates').onclick=()=>guard(async()=>{await Promise.all([loadWebRelease(true),job(await post('/updates/check'))]);await loadUpdates();});
$('#backup').onclick=()=>guard(async()=>{const r=await api('/backup');const a=element('a');a.href='data:application/gzip;base64,'+r.data;a.download=r.filename;document.body.append(a);a.click();a.remove();toast('备份已下载，请妥善保存。');});
$('#restore').onclick=()=>guard(async()=>{const file=$('#restore-file').files[0];if(!file||!$('#restore-confirm').checked)throw Error('请选择备份并确认替换配置');if(file.size>24*1024*1024)throw Error('备份超过 24 MB');if(!await discardChanges())return;const bytes=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<bytes.length;i+=32768)text+=String.fromCharCode(...bytes.subarray(i,i+32768));await job(await post('/restore',{data:btoa(text)}));if(proxyWindow)await openProxyWindow(true);await Promise.all([loadStatus(),loadCards(),loadAppearance()]);$('#restore-file').value='';$('#restore-confirm').checked=false;$('#restore-filename').textContent='未选择文件';syncRestore();toast('备份已恢复。');});
// Restoring stays unavailable until a file is chosen and the replacement is acknowledged.
function syncRestore(){const ready=Boolean($('#restore-file').files[0])&&$('#restore-confirm').checked,control=$('#restore');control.dataset.stateDisabled=String(!ready);if(!busy)control.disabled=!ready;}
function filterSettings(){
  const query=$('#settings-search').value.trim().toLocaleLowerCase();let found=false,group=null,groupVisible=false;
  const closeGroup=()=>{if(group)group.hidden=!groupVisible;};
  for(const item of $('#settings-nav').children){
    if(item.classList.contains('nav-search')||item.id==='settings-search-empty')continue;
    if(item.classList.contains('nav-group')){closeGroup();group=item;groupVisible=false;continue;}
    const match=!query||(item.textContent+' '+(item.dataset.keywords||'')).toLocaleLowerCase().includes(query);
    item.hidden=!match;if(match){found=true;groupVisible=true;}
  }
  closeGroup();$('#settings-search-empty').hidden=found;
}
$('#settings-search').addEventListener('input',filterSettings);
$('#settings-search').addEventListener('keydown',e=>{
  if(e.key==='Enter'){e.preventDefault();$('#settings-nav').querySelector(':scope > :is(button, a):not([hidden])')?.click();}
  else if(e.key==='Escape'&&e.target.value){e.preventDefault();e.stopPropagation();e.target.value='';filterSettings();}
});
$('#link-cancel').onclick=()=>$('#link-dialog').close();
$('#login-settings-form').onsubmit=e=>{e.preventDefault();guard(async()=>{await post('/auth/settings',{login_required:$('#login-required').checked,current_password:$('#login-settings-password').value});renderLoginSettings(await api('/auth'));$('#login-settings-password').value='';toast($('#login-required').checked?'密码登录已开启。':'密码登录已关闭，打开网页即可进入网关。');});};
$('#password-form').onsubmit=e=>{e.preventDefault();const password=$('#new-password').value;if(!$('#current-password').value){toast('请输入当前密码。',true);return;}if(!password){toast('请输入新密码。',true);return;}if(password!==$('#repeat-password').value){toast('两次新密码不一致，请重新输入。',true);return;}guard(async()=>{await post('/password',{current_password:$('#current-password').value,password});$('#password-form').reset();toast('密码已保存。');});};
$('#logout').onclick=()=>guard(async()=>{if(!await discardChanges())return;await post('/auth/logout');destroyProxyWindow();destroySettings();closeAllWindows();await authState();});
$('#settings-dialog').addEventListener('cancel',e=>{e.preventDefault();closeSettings();});
window.addEventListener('beforeunload',e=>{if(configDirty()){e.preventDefault();e.returnValue='';}});
// Windows follow the desktop's menu bar and Dock: they stay between the two,
// minimize into the Dock and report the focused app to the menu bar.
function windowBounds(){const mobile=phone.matches;return {top:mobile?0:34,bottom:mobile?0:Math.min(96,innerHeight*.12)};}
function createGatewayWindow(shell, title, iconPath, close, {toolbar=null, app='', onCompact=null, width=1120, height=780}={}) {
  if(shell.tagName==='DIALOG')shell.show();
  const mobile=phone.matches,bounds=windowBounds();
  const w=Math.min(width,innerWidth-48),h=Math.min(height,innerHeight-bounds.top-bounds.bottom-24);
  const win = new WinBox({title, icon:iconPath, mount:shell, class:['gateway-window','no-full'],
    width:w, height:h, minwidth:Math.min(420,innerWidth), minheight:Math.min(320,innerHeight), x:'center',
    y:mobile ? 0 : Math.max(bounds.top+8,bounds.top+(innerHeight-bounds.top-bounds.bottom-h)/2), top:bounds.top, bottom:bounds.bottom,
    header:52, max:mobile,
    onclose(force) { if (force) return false; close(); return true; },
    onfocus(){ lastGatewayWindow=this; $('#menubar-app').textContent=title; },
    onblur(){ if(!document.querySelector('.winbox.focus'))$('#menubar-app').textContent='Gateway'; },
    onminimize(){ $('#menubar-app').textContent='Gateway'; }});
  win.app=app;
  for (const [cls, action] of [['wb-close','关闭'],['wb-min','最小化'],['wb-max','缩放']]) {
    const control = win.window.querySelector('.'+cls);
    control.setAttribute('role','button');
    control.setAttribute('aria-label',action+' '+title);
    control.title=action;
    control.tabIndex = 0;
    control.onkeydown = event => { if (['Enter',' '].includes(event.key)) { event.preventDefault(); control.click(); } };
  }
  if(toolbar){win.toolbar={element:toolbar,home:toolbar.parentNode};win.window.querySelector('.wb-header').append(toolbar);}
  const sync=()=>{const compact=win.body&&win.body.clientWidth<=720;if(win.window.classList.contains('is-compact')!==compact){win.window.classList.toggle('is-compact',compact);onCompact?.(compact);}};
  win.resizeObserver=new ResizeObserver(sync);win.resizeObserver.observe(win.body);sync();
  markRunningApps();
  return win;
}
// A sheet or alert takes focus from its window; give it back when the sheet closes.
let lastGatewayWindow=null;
document.addEventListener('close',event=>{
  const win=lastGatewayWindow;
  if(event.target.tagName!=='DIALOG'||event.target.closest('.winbox')||!win||win.min||!win.window.isConnected)return;
  if(!document.querySelector('.winbox.focus'))win.focus();
},true);
function releaseGatewayWindow(win){
  win.resizeObserver?.disconnect();
  if(win.toolbar)win.toolbar.home.prepend(win.toolbar.element);
  win.close(true);
  if(!document.querySelector('.winbox.focus'))$('#menubar-app').textContent='Gateway';
  markRunningApps();
}
function focusGatewayWindow(win) {
  if (win.min) win.restore();
  win.show();
  win.focus();
}
function showSettingsWindow() {
  if (settingsWindow) focusGatewayWindow(settingsWindow);
  else settingsWindow = createGatewayWindow($('#settings-dialog'),'控制面板','/icons/settings.svg',closeSettings,
    {toolbar:$('#settings-toolbar'),app:'settings',width:1080,onCompact:syncSettingsBack});
  syncSettingsBack();
}
function syncSettingsBack(){$('#settings-back').hidden=!(settingsWindow?.window.classList.contains('is-compact')&&currentPage&&currentPage!=='overview');}

// Pages served by this gateway open in a window instead of a new browser tab.
const frameApps={
  transfer:{title:'局域网互传',icon:'/icons/files.svg',url:'/transfer/?embed=1',page:'/transfer/',width:980},
  panel:{title:'Clash 面板',icon:'/icons/speedtest.svg',url:'/ui/#/proxies',page:'/ui/#/proxies',width:1180},
  adguard:{title:'AdGuard Home',icon:'/icons/adguard.svg',url:'/adguard/',page:'/adguard/',width:1180},
};
const frameWindows=new Map();
function openFrameApp(key){
  const app=frameApps[key];if(!app)return;
  const open=frameWindows.get(key);
  if(open){focusGatewayWindow(open);return;}
  const shell=element('div',undefined,'frame-shell'),frame=element('iframe'),bar=element('div',undefined,'window-toolbar');
  frame.src=app.url;frame.title=app.title;frame.setAttribute('allow','clipboard-read; clipboard-write');
  const reload=iconButton('refresh','重新载入',()=>{try{frame.contentWindow.location.reload();}catch{frame.src=app.url;}},'toolbar-button');
  const tab=element('a',undefined,'button-link toolbar-button icon-button');tab.href=app.page;tab.target='_blank';tab.rel='noopener';tab.title='在新标签页中打开';tab.setAttribute('aria-label','在新标签页中打开 '+app.title);tab.append(glyph('external'));
  bar.append(element('span',undefined,'toolbar-spacer'),reload,tab);shell.append(frame,bar);document.body.append(shell);
  const win=createGatewayWindow(shell,app.title,app.icon,()=>closeFrameApp(key),{toolbar:bar,app:key,width:app.width});
  frameWindows.set(key,win);markRunningApps();
}
function closeFrameApp(key){
  const win=frameWindows.get(key);if(!win)return;
  frameWindows.delete(key);
  const shell=win.body?.firstChild;
  releaseGatewayWindow(win);shell?.remove();
}
function closeAllWindows(){for(const key of [...frameWindows.keys()])closeFrameApp(key);}

// Menu bar: the system menu, the focused app, status items and the clock.
function systemMenuItems(){
  return [
    ['关于这台网关','info',()=>openSettings('overview')],null,
    ['控制面板…','gear',()=>openSettings()],
    ['代理配置…','relay',()=>openProxyWindow()],
    ['局域网互传','window',()=>openFrameApp('transfer')],
    ['添加桌面链接…','plus',()=>openLinkEditor()],
    ['个性化…','image',()=>openPersonalization()],null,
    ['退出登录','logout',()=>$('#logout').click()],
  ];
}
function hideSystemMenu(){const menu=$('#system-menu');if(!menu||menu.hidden)return;menu.hidden=true;$('#system-menu-button').setAttribute('aria-expanded','false');}
function showSystemMenu(){
  const menu=$('#system-menu'),anchor=$('#system-menu-button');menu.replaceChildren();
  const head=element('div',undefined,'menu-heading');head.append(element('strong','Gateway'),element('span',status.domain?'http://'+status.domain:''));menu.append(head);
  for(const item of systemMenuItems()){
    if(!item){const line=element('div',undefined,'context-divider');line.setAttribute('role','separator');menu.append(line);continue;}
    const [label,symbol,action]=item,entry=button('',()=>{hideSystemMenu();Promise.resolve(action()).catch(e=>toast(e.message,true));});
    entry.setAttribute('role','menuitem');entry.append(glyph(symbol),element('span',label));menu.append(entry);
  }
  const rect=anchor.getBoundingClientRect();menu.hidden=false;menu.style.left=Math.max(6,Math.min(rect.left,innerWidth-menu.offsetWidth-6))+'px';menu.style.top=(rect.bottom+4)+'px';
  anchor.setAttribute('aria-expanded','true');menu.querySelector('button')?.focus();
}
function tickClock(){
  const now=new Date(),clock=$('#menubar-clock');
  const time=now.toLocaleTimeString('zh-CN',{hour:'2-digit',minute:'2-digit',hour12:false});
  clock.textContent=phone.matches?time:now.toLocaleDateString('zh-CN',{month:'long',day:'numeric',weekday:'short'})+' '+time;
  clock.dateTime=now.toISOString();
}
async function refreshMenubarStatus(){
  if(!$('#auth-dialog').open)await api('/tailscale').then(markTailscale).catch(()=>{});
}
function setupMenubar(){
  $('#system-menu-button').onclick=e=>{e.stopPropagation();if($('#system-menu').hidden)showSystemMenu();else hideSystemMenu();};
  $('#system-menu').addEventListener('keydown',e=>{const items=[...$('#system-menu').querySelectorAll('button')],i=items.indexOf(document.activeElement);if(e.key==='Escape'){e.stopPropagation();hideSystemMenu();$('#system-menu-button').focus();}else if(['ArrowDown','ArrowUp'].includes(e.key)){e.preventDefault();items[(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length].focus();}});
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#system-menu, #system-menu-button'))hideSystemMenu();});
  tickClock();setInterval(tickClock,15000);phone.addEventListener('change',()=>{tickClock();drawDock();});
  setInterval(()=>{if(!document.hidden)refreshMenubarStatus();},60000);
}
function askConfirm(copy,title='确认操作',{accept='确定',danger=false}={}){
  return new Promise(resolve=>{
    const dialog=$('#confirm-dialog');if(dialog.open){resolve(false);return;}$('#confirm-title').textContent=title;$('#confirm-copy').textContent=copy;
    const ok=$('#confirm-accept');ok.textContent=accept;ok.className=danger?'danger solid':'primary';dialog.classList.toggle('is-destructive',danger);
    const finish=value=>{dialog.close();dialog.oncancel=null;resolve(value);};
    $('#confirm-cancel').onclick=()=>finish(false);$('#confirm-accept').onclick=()=>finish(true);dialog.oncancel=e=>{e.preventDefault();finish(false);};
    dialog.showModal();$('#confirm-cancel').focus();
  });
}
async function deleteCard(card){if(!await askConfirm('删除链接“'+card.name+'”？此操作仅移除桌面入口。','删除桌面链接',{accept:'删除',danger:true}))return;await api('/cards/'+card.id,{method:'DELETE'});await loadCards();toast('链接已删除');}
function hideContext(){const menu=$('#desktop-context-menu');if(menu)menu.hidden=true;}
function showContext(x,y,item=null,origin=null){
  if($('#auth-dialog').open)return;
  const menu=$('#desktop-context-menu');menu.replaceChildren();
  const add=(label,symbol,action,danger=false,image=null)=>{const b=button('',()=>{hideContext();Promise.resolve(action()).catch(e=>toast(e.message,true));},danger?'danger':'');b.setAttribute('role','menuitem');b.append(image||glyph(symbol),element('span',label));menu.append(b);};
  const line=()=>{const hr=element('div',undefined,'context-divider');hr.setAttribute('role','separator');menu.append(hr);};
  if(item?.system){add('打开','',()=>origin.click(),false,icon(item.icon));if(item.id==='workstation'){line();add('设置入口地址…','gear',async()=>{await openSettings('desktop');$('#workstation-url').focus();});}}
  else if(item){add('打开','',()=>origin.click(),false,icon(item.icon||'link',item.url));line();add('编辑链接…','edit',()=>openLinkEditor(item));add('删除链接','trash',()=>guard(()=>deleteCard(item)),true);}
  else{add('添加链接…','plus',()=>openLinkEditor());add('刷新桌面','refresh',()=>withLoading($('.desktop-workspace'),async()=>{await Promise.all([loadCards(),loadStatus()]);toast('桌面已刷新');}));add('按名称排列','list',()=>guard(()=>saveDesktopOrder(desktopItems().sort((a,b)=>a.name.localeCompare(b.name,'zh-CN')).map(c=>c.id))));line();add('个性化…','image',()=>openPersonalization());add('控制面板…','gear',()=>openSettings());}
  menu.hidden=false;menu.style.left=Math.max(8,Math.min(x,innerWidth-menu.offsetWidth-8))+'px';menu.style.top=Math.max(8,Math.min(y,innerHeight-menu.offsetHeight-8))+'px';menu.querySelector('button')?.focus();
  menu.onkeydown=e=>{const items=[...menu.querySelectorAll('button')],i=items.indexOf(document.activeElement);if(e.key==='Escape'){e.stopPropagation();hideContext();origin?.focus();}else if(['ArrowDown','ArrowUp','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?items.length-1:(i+(e.key==='ArrowDown'?1:-1)+items.length)%items.length;items[next].focus();}};
}
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
  setupIconPicker();
  document.addEventListener('keydown',e=>{if(e.key!=='Escape')return;if(!$('#desktop-context-menu').hidden){hideContext();return;}if(!document.querySelector('dialog:modal')){if(proxyWindow?.focused){e.preventDefault();backProxy();}else if(settingsWindow?.focused){e.preventDefault();closeSettings();}}});
  document.addEventListener('pointerdown',e=>{if(!e.target.closest('#desktop-context-menu'))hideContext();});
  document.addEventListener('contextmenu',e=>{if(e.target.closest('dialog,.winbox,.menubar,.dock,.frame-shell,#desktop-context-menu,#system-menu'))return;e.preventDefault();showContext(e.clientX,e.clientY);});
  let hold=null,point=null;
  $('#desktop').addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;point=[e.clientX,e.clientY];const target=e.target.closest('.desktop-item');hold=setTimeout(()=>{const item=target?._desktopItem;showContext(e.clientX,e.clientY,item,target);hold=null;},600);});
  $('#desktop').addEventListener('pointermove',e=>{if(point&&Math.hypot(e.clientX-point[0],e.clientY-point[1])>10){clearTimeout(hold);hold=null;}});
  for(const type of ['pointerup','pointercancel'])$('#desktop').addEventListener(type,()=>{clearTimeout(hold);hold=null;point=null;});
  $('#desktop').addEventListener('click',e=>{if(!$('#desktop-context-menu').hidden){e.preventDefault();e.stopImmediatePropagation();}},true);
  $$('[data-personalization]').forEach(el=>el.onclick=openPersonalization);
  setupMenubar();
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
  $('#restore-file').addEventListener('change',()=>{$('#restore-filename').textContent=$('#restore-file').files[0]?.name||'未选择文件';syncRestore();});
  $('#restore-confirm').addEventListener('change',syncRestore);syncRestore();
  window.addEventListener('resize',hideContext);
}

setupDesktop();drawDesktop();withLoading($('.desktop-workspace'),async()=>{await loadCatalogs();await authState();}).catch(e=>toast(e.message,true));
