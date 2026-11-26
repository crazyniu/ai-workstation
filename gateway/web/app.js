'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)];
let initialized=false,cards=[],revision=null,editing=null,busy=false,status={};
const DEFAULT_DOCK=['builtin:settings','builtin:proxy','builtin:files','builtin:workstation','builtin:terminal','builtin:clash','builtin:adguard'];
let desktopPrefs={workstation_url:'https://192.168.1.251:6080/',order:[],dock:[...DEFAULT_DOCK],positions:{}};
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
function openLinkEditor(card=null){cancelFaviconPreview();editing=card?.id||null;$('#link-title').textContent=card?'编辑链接':'添加链接';$('#link-name').value=card?.name||'';$('#link-url').value=card?.url||'';$('#link-icon').value=card?(card.icon||'link'):'auto';$('#icon-search').value='';drawIconChoices();$('#link-newtab').checked=card?.open_in_new_tab??false;$('#link-dialog').showModal();previewFavicon(0);}
// Gateway apps and the administrator's links share one layout: each sits in the
// Dock or at a cell of the desktop grid. A cell is [column from the right edge, row].
const systemApps=[
  {id:'builtin:settings',key:'settings',name:'控制面板',image:'settings',open:()=>openSettings()},
  {id:'builtin:proxy',key:'proxy',name:'代理配置',image:'proxy',open:()=>openProxyWindow()},
  {id:'builtin:files',key:'transfer',name:'局域网互传',image:'transfer',open:()=>openFrameApp('transfer')},
  {id:'builtin:workstation',key:'workstation',name:'工作站',image:'workstation',open:()=>openFrameApp('workstation')},
  {id:'builtin:terminal',key:'terminal',name:'终端',image:'terminal',open:()=>openTerminal().catch(e=>toast(e.message,true))},
  {id:'builtin:clash',key:'panel',name:'Clash 面板',image:'panel',open:()=>openFrameApp('panel')},
  {id:'builtin:adguard',key:'adguard',name:'AdGuard Home',image:'adguard',open:()=>openFrameApp('adguard')},
].map(app=>({...app,system:true}));
const appImage=name=>'/icons/apps/'+name+'.webp';
const CELL={width:104,height:112},GRID_LIMIT=100,PHONE_DOCK=4;
const phone=window.matchMedia('(max-width:700px)');
let layout={cells:new Map(),columns:1,rows:1},iconDrag=null,suppressClick=false,layoutSaving=Promise.resolve();
const cellKey=cell=>cell[0]+','+cell[1];
function itemById(id){return systemApps.find(app=>app.id===id)||cards.find(card=>card.id===id);}
function dockItems(){return desktopPrefs.dock.map(itemById).filter(Boolean);}
// Everything outside the Dock, in the administrator's list order.
function desktopItems(){
  const docked=new Set(desktopPrefs.dock),rank=new Map(desktopPrefs.order.map((id,i)=>[id,i]));
  return [...systemApps,...cards].filter(item=>!docked.has(item.id)).sort((a,b)=>(rank.get(a.id)??1e9)-(rank.get(b.id)??1e9));
}
function itemIcon(item){
  let image;
  if(item.system){image=document.createElement('img');image.alt='';image.width=96;image.height=96;image.src=appImage(item.image);}
  else image=icon(item.icon||'link',item.url);
  image.draggable=false;return image;
}
function launcher(item,className){
  const el=element(item.system?'button':'a');el.className=className;el.dataset.id=item.id;el.dataset.app=item.system?item.key:'link:'+item.id;el._desktopItem=item;
  el.append(itemIcon(item),element('span',item.name));el.setAttribute('aria-label',item.name);
  if(item.system){el.type='button';el.onclick=()=>item.open();}
  else{
    el.href=item.url;el.draggable=false;
    if(item.open_in_new_tab){el.target='_blank';el.rel='noopener noreferrer';}
    // Links open in a window like the gateway's own apps; modified clicks keep the browser's behavior.
    else el.onclick=e=>{if(e.button||e.metaKey||e.ctrlKey||e.shiftKey||e.altKey)return;e.preventDefault();openLinkWindow(item,el.querySelector('img')?.src);};
  }
  el.addEventListener('contextmenu',e=>{e.preventDefault();e.stopPropagation();showContext(e.clientX,e.clientY,item,el);});
  el.addEventListener('keydown',e=>{
    if(e.key==='ContextMenu'||(e.shiftKey&&e.key==='F10')){e.preventDefault();const r=el.getBoundingClientRect();showContext(r.right,r.top,item,el);}
    else if(e.altKey&&['ArrowUp','ArrowDown','ArrowLeft','ArrowRight'].includes(e.key)){e.preventDefault();nudgeIcon(item,e.key);}
  });
  el.addEventListener('pointerdown',e=>armIconDrag(e,item,el));
  return el;
}
function drawDock(){
  const dock=$('#dock');dock.replaceChildren();
  dockItems().forEach((item,index)=>{const el=launcher(item,'dock-item');if(index>=PHONE_DOCK)el.classList.add('desktop-only');dock.append(el);});
  dock.classList.toggle('empty',!dock.children.length);
  markRunningApps();
}
function markRunningApps(){
  const running=new Set([settingsWindow&&'settings',proxyWindow&&'proxy',...frameWindows.keys()].filter(Boolean));
  for(const item of $$('.dock-item'))item.classList.toggle('running',running.has(item.dataset.app));
}
function drawDesktop(){
  const desktop=$('#desktop');desktop.replaceChildren();
  // A phone's Dock holds four apps; the home screen lists the rest first.
  for(const item of dockItems().slice(PHONE_DOCK))desktop.append(launcher(item,'desktop-item phone-only'));
  for(const item of desktopItems())desktop.append(launcher(item,'desktop-item placed'));
  if(!cards.length&&initialized&&$('#auth-dialog').open===false){
    const hint=button('',()=>openLinkEditor(),'desktop-item desktop-add placed');hint.append(element('span','+','desktop-add-mark'),element('span','添加链接'));desktop.append(hint);
  }
  placeIcons();drawDock();drawLinks();
}
// Saved cells that fit the screen keep their place. Other icons take the free cell
// nearest their saved one, or the next one down the columns from the right, like macOS.
function placeIcons(){
  const desktop=$('#desktop'),placed=[...desktop.querySelectorAll('.desktop-item.placed')];
  if(phone.matches){placed.forEach(el=>el.style.left=el.style.top='');layout={cells:new Map(),columns:1,rows:1};return;}
  const columns=Math.max(1,Math.floor(desktop.clientWidth/CELL.width)),rows=Math.max(1,Math.floor(desktop.clientHeight/CELL.height));
  const taken=new Set(),cells=new Map(),fits=cell=>cell&&cell[0]<columns&&cell[1]<rows;
  for(const el of placed){const cell=desktopPrefs.positions[el.dataset.id];if(fits(cell)&&!taken.has(cellKey(cell))){cells.set(el,cell);taken.add(cellKey(cell));}}
  for(const el of placed){
    if(cells.has(el))continue;const saved=desktopPrefs.positions[el.dataset.id];
    const cell=freeCell(taken,columns,rows,saved&&[Math.min(saved[0],columns-1),Math.min(saved[1],rows-1)]);cells.set(el,cell);taken.add(cellKey(cell));
  }
  layout={cells:new Map([...cells].filter(([el])=>el.dataset.id).map(([el,cell])=>[el.dataset.id,cell])),columns,rows};
  for(const [el,cell] of cells){const [x,y]=cellOrigin(cell);el.style.left=x+'px';el.style.top=y+'px';}
}
function cellOrigin([column,row]){return [$('#desktop').clientWidth-(column+1)*CELL.width+(CELL.width-96)/2,row*CELL.height];}
function freeCell(taken,columns,rows,near=null){
  if(near){
    let best=null,distance=Infinity;
    for(let c=0;c<columns;c++)for(let r=0;r<rows;r++){const d=(c-near[0])**2+(r-near[1])**2;if(d<distance&&!taken.has(cellKey([c,r]))){distance=d;best=[c,r];}}
    if(best)return best;
  }
  // A full screen continues below it; the desktop scrolls.
  for(let page=0;;page+=rows)for(let c=0;c<columns;c++)for(let r=page;r<page+rows;r++)if(!taken.has(cellKey([c,r])))return [c,r];
}
// Where every desktop icon is now; saving these keeps the others still when one moves.
function currentPositions(except=null){
  return Object.fromEntries([...layout.cells].filter(([id,cell])=>id!==except&&cell[0]<GRID_LIMIT&&cell[1]<GRID_LIMIT));
}
function saveLayout(dock,positions,message=''){
  desktopPrefs={...desktopPrefs,dock,positions};drawDesktop();
  layoutSaving=layoutSaving.then(async()=>{
    try{const saved=await post('/desktop/layout',{dock,positions});desktopPrefs={...desktopPrefs,dock:saved.dock,positions:saved.positions};if(message)toast(message);}
    catch(e){toast(e.message,true);await loadCards().catch(()=>{});}
  });
  return layoutSaving;
}
function focusLauncher(id,dock=false){requestAnimationFrame(()=>$$(dock?'.dock-item':'.desktop-item.placed').find(el=>el.dataset.id===id)?.focus());}
function moveToDock(item,index=null){
  const dock=desktopPrefs.dock.filter(id=>id!==item.id);
  // A phone shows only the first four Dock items, so a new one joins those.
  dock.splice(index??(phone.matches?Math.min(dock.length,PHONE_DOCK-1):dock.length),0,item.id);
  return saveLayout(dock,currentPositions(item.id),'已放入程序坞');
}
function moveToDesktop(item,cell=null){
  const positions=currentPositions(item.id);
  positions[item.id]=cell||freeCell(new Set(Object.values(positions).map(cellKey)),layout.columns,layout.rows);
  return saveLayout(desktopPrefs.dock.filter(id=>id!==item.id),positions,cell?'':'已移到桌面');
}
function arrangeIcons(items){
  const positions={},rows=layout.rows;
  items.forEach((item,i)=>{const cell=[Math.floor(i/rows),i%rows];if(cell[0]<GRID_LIMIT)positions[item.id]=cell;});
  return saveLayout(desktopPrefs.dock,positions);
}
function nudgeIcon(item,key){
  if(desktopPrefs.dock.includes(item.id)){
    const dock=desktopPrefs.dock.filter(id=>id!==item.id),from=desktopPrefs.dock.indexOf(item.id),to=from+(key==='ArrowLeft'||key==='ArrowUp'?-1:1);
    if(to<0||to>dock.length)return;dock.splice(to,0,item.id);saveLayout(dock,currentPositions()).then(()=>focusLauncher(item.id,true));return;
  }
  const cell=layout.cells.get(item.id);if(!cell||phone.matches)return;
  const [dc,dr]={ArrowLeft:[1,0],ArrowRight:[-1,0],ArrowUp:[0,-1],ArrowDown:[0,1]}[key],positions=currentPositions(item.id),taken=new Set(Object.values(positions).map(cellKey));
  let [c,r]=cell;do{c+=dc;r+=dr;}while(c>=0&&r>=0&&c<layout.columns&&r<layout.rows&&taken.has(cellKey([c,r])));
  if(c<0||r<0||c>=layout.columns||r>=layout.rows)return;
  positions[item.id]=[c,r];saveLayout(desktopPrefs.dock,positions).then(()=>focusLauncher(item.id));
}

// Dragging: icons move freely between desktop cells, into the Dock and out of it.
function armIconDrag(e,item,el){
  if(e.button!==0||e.pointerType==='touch'||phone.matches||busy||iconDrag)return;
  iconDrag={item,el,fromDock:el.classList.contains('dock-item'),x:e.clientX,y:e.clientY,pointer:e.pointerId,active:false,target:null};
}
function startIconDrag(e){
  const drag=iconDrag,image=drag.el.querySelector('img'),rect=image.getBoundingClientRect();
  drag.active=true;drag.offset=[e.clientX-rect.left,e.clientY-rect.top];drag.size=[rect.width,rect.height];hideContext();
  drag.ghost=image.cloneNode();drag.ghost.className='icon-ghost';drag.ghost.style.width=rect.width+'px';drag.ghost.style.height=rect.height+'px';document.body.append(drag.ghost);
  drag.el.classList.add('drag-source');document.body.classList.add('icon-dragging');
  try{drag.el.setPointerCapture(drag.pointer);}catch{}
}
function dragOverDock(x,y){
  const dock=$('#dock').getBoundingClientRect(),margin=28;
  return y>=dock.top-margin&&x>=dock.left-margin&&x<=dock.right+margin;
}
function moveIconDrag(e){
  const drag=iconDrag,[ox,oy]=drag.offset,[w,h]=drag.size;
  drag.ghost.style.transform='translate('+(e.clientX-ox)+'px,'+(e.clientY-oy)+'px)';
  if(dragOverDock(e.clientX,e.clientY)){
    const items=[...$('#dock').children].filter(el=>el.classList.contains('dock-item')&&el!==drag.el);
    const index=items.filter(el=>{const r=el.getBoundingClientRect();return r.left+r.width/2<e.clientX;}).length;
    drag.target={dock:index};showDockGap(items[index]||null);hideDropCell();return;
  }
  hideDockGap();
  const desktop=$('#desktop'),box=desktop.getBoundingClientRect(),left=box.left+desktop.clientLeft,top=box.top+desktop.clientTop;
  const cx=e.clientX-ox+w/2,cy=e.clientY-oy+h/2;
  const column=Math.min(layout.columns-1,Math.max(0,Math.floor((left+desktop.clientWidth-cx)/CELL.width)));
  const row=Math.max(0,Math.min(layout.rows-1,Math.floor((cy-top+desktop.scrollTop)/CELL.height)));
  const taken=new Set(Object.values(currentPositions(drag.item.id)).map(cellKey));
  const cell=freeCell(taken,layout.columns,layout.rows,[column,row]);
  drag.target={cell};showDropCell(cell);
}
function showDockGap(before){
  let gap=$('#dock .dock-gap');if(!gap){gap=element('span',undefined,'dock-gap');gap.setAttribute('aria-hidden','true');}
  if(gap.nextSibling!==before||!gap.isConnected)$('#dock').insertBefore(gap,before);
  $('#dock').classList.add('drop-target');
}
function hideDockGap(){$('#dock .dock-gap')?.remove();$('#dock').classList.remove('drop-target');}
function showDropCell(cell){
  let mark=$('#desktop .drop-cell');if(!mark){mark=element('span',undefined,'drop-cell');mark.setAttribute('aria-hidden','true');$('#desktop').append(mark);}
  const [x,y]=cellOrigin(cell);mark.style.left=x+'px';mark.style.top=y+'px';
}
function hideDropCell(){$('#desktop .drop-cell')?.remove();}
function endIconDrag(commit){
  const drag=iconDrag;iconDrag=null;if(!drag?.active)return;
  drag.ghost.remove();drag.el.classList.remove('drag-source');document.body.classList.remove('icon-dragging');hideDockGap();hideDropCell();
  // The release also clicks the icon; that click must not open it.
  suppressClick=true;setTimeout(()=>suppressClick=false,0);
  if(!commit||!drag.target)return;
  if('dock' in drag.target)moveToDock(drag.item,drag.target.dock);
  else moveToDesktop(drag.item,drag.target.cell);
}
document.addEventListener('pointermove',e=>{
  if(!iconDrag||e.pointerId!==iconDrag.pointer)return;
  if(!iconDrag.active){if(Math.hypot(e.clientX-iconDrag.x,e.clientY-iconDrag.y)<6)return;startIconDrag(e);}
  moveIconDrag(e);
});
document.addEventListener('pointerup',e=>{if(iconDrag&&e.pointerId===iconDrag.pointer)endIconDrag(true);});
document.addEventListener('pointercancel',e=>{if(iconDrag&&e.pointerId===iconDrag.pointer)endIconDrag(false);});
document.addEventListener('keydown',e=>{if(e.key==='Escape'&&iconDrag?.active){e.preventDefault();e.stopImmediatePropagation();endIconDrag(false);}},true);
document.addEventListener('click',e=>{if(suppressClick){e.preventDefault();e.stopImmediatePropagation();suppressClick=false;}},true);
document.addEventListener('dragstart',e=>{if(e.target.closest?.('.desktop-item,.dock-item'))e.preventDefault();});
// The desktop's size follows the window, the phone layout and the menu bar.
let placing=0;new ResizeObserver(()=>{cancelAnimationFrame(placing);placing=requestAnimationFrame(placeIcons);}).observe($('#desktop'));
async function saveDesktopOrder(ids){await post('/cards/order',{ids});await loadCards();toast('桌面顺序已保存');}
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
  hint.textContent=required?'开启后，打开 Niu Gateway 需要输入管理员密码。':'关闭后，能访问网关网页的设备都可以直接管理网关。';
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
  desktopPrefs = {workstation_url:'https://192.168.1.251:6080/', order:[], dock:[...DEFAULT_DOCK], positions:{}};
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
  else if(info?.latest||Object.keys(u?.checked||{}).length){setTone(state,'已是最新','ok');detail.textContent='Niu Gateway 与核心组件均为最新版本';}
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
    renderDevices(t);
}
// Tailscale devices, and how this gateway currently reaches each one.
const osNames={linux:'Linux',windows:'Windows',macOS:'macOS',iOS:'iOS',android:'Android',freebsd:'FreeBSD',openbsd:'OpenBSD',tvOS:'tvOS',illumos:'illumos'};
const derpNames={tok:'东京',hkg:'香港',sin:'新加坡',syd:'悉尼',blr:'班加罗尔',lax:'洛杉矶',sfo:'旧金山',sea:'西雅图',den:'丹佛',dfw:'达拉斯',ord:'芝加哥',mia:'迈阿密',nyc:'纽约',tor:'多伦多',hnl:'檀香山',sao:'圣保罗',jnb:'约翰内斯堡',fra:'法兰克福',par:'巴黎',ams:'阿姆斯特丹',lhr:'伦敦',mad:'马德里',waw:'华沙'};
function formatBytes(value){const units=['B','KB','MB','GB','TB'];let n=Number(value)||0,i=0;while(n>=1024&&i<units.length-1){n/=1024;i++;}return (i&&n<10?n.toFixed(1):Math.round(n))+' '+units[i];}
function lastSeen(value){
  const time=Date.parse(value);if(!value||Number.isNaN(time))return '离线';
  const minutes=Math.max(0,Math.round((Date.now()-time)/60000));
  return '离线 · '+(minutes<1?'刚刚':minutes<60?minutes+' 分钟前':minutes<1440?Math.round(minutes/60)+' 小时前':Math.round(minutes/1440)+' 天前')+'在线';
}
function devicePath(path){
  if(path.kind==='direct')return ['直连 · '+path.address,'ok'];
  if(path.kind==='peer-relay')return ['中转 · '+path.address,'ok'];
  if(path.kind==='derp')return ['DERP 中继 · '+(derpNames[path.region]||path.name||path.region),'warn'];
  return ['空闲','idle'];
}
function renderDevices(t){
  const card=$('#tailscale-devices-card'),list=$('#tailscale-devices'),devices=t.devices||[];
  card.hidden=t.state!=='Running'||!devices.length;if(card.hidden)return;
  const peers=devices.filter(d=>d.path.kind!=='self');
  $('#tailscale-devices-summary').textContent=peers.length?peers.length+' 台其他设备，'+peers.filter(d=>d.online).length+' 台在线。“DERP 中继”表示流量经中继服务器转发，后面是中继所在地或自建中继的名称。':'这个 Tailscale 网络中还没有其他设备。';
  list.replaceChildren(...devices.map(d=>{
    const self=d.path.kind==='self',row=element('div',undefined,'list-row device-row'),symbol=element('span',undefined,'row-symbol');
    symbol.style.setProperty('--tint',self?'var(--accent)':d.online?'#34a853':'#8e8e93');symbol.append(glyph(self?'gateway':d.os==='linux'?'server':'devices'));
    const copy=element('div',undefined,'row-copy'),name=element('strong',d.name);
    if(self)name.append(element('span','本机','device-badge'));
    const ip=(d.ips||[]).find(a=>!a.includes(':'))||d.ips?.[0]||'';
    copy.append(name,element('span',[ip,osNames[d.os]||d.os,d.owner].filter(Boolean).join(' · ')));
    if(d.routes?.length)copy.append(element('span','子网 '+d.routes.join('、')));
    row.append(symbol,copy);
    if(!self){
      const meta=element('div',undefined,'device-meta');
      if(d.online){const [label,tone]=devicePath(d.path),pill=element('span',undefined,'status-pill');setTone(pill,label,tone);meta.append(pill);if(d.rx||d.tx)meta.append(element('span','↓ '+formatBytes(d.rx)+'  ↑ '+formatBytes(d.tx),'row-meta'));}
      else meta.append(element('span',lastSeen(d.last_seen),'row-meta'));
      row.append(meta);
    }
    return row;
  }));
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
    onblur(){ if(!document.querySelector('.winbox.focus'))$('#menubar-app').textContent='Niu Gateway'; },
    onminimize(){ $('#menubar-app').textContent='Niu Gateway'; }});
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
  if(!document.querySelector('.winbox.focus'))$('#menubar-app').textContent='Niu Gateway';
  markRunningApps();
}
function focusGatewayWindow(win) {
  if (win.min) win.restore();
  win.show();
  win.focus();
}
function showSettingsWindow() {
  if (settingsWindow) focusGatewayWindow(settingsWindow);
  else settingsWindow = createGatewayWindow($('#settings-dialog'),'控制面板',appImage('settings'),closeSettings,
    {toolbar:$('#settings-toolbar'),app:'settings',width:1080,onCompact:syncSettingsBack});
  syncSettingsBack();
}
function syncSettingsBack(){$('#settings-back').hidden=!(settingsWindow?.window.classList.contains('is-compact')&&currentPage&&currentPage!=='overview');}

// Gateway pages, the workstation and the administrator's links open in a window
// instead of a new browser tab. Each window can still move to a tab.
const frameApps={
  transfer:{title:'局域网互传',icon:appImage('transfer'),url:'/transfer/?embed=1',page:'/transfer/',width:980},
  panel:{title:'Clash 面板',icon:appImage('panel'),url:'/ui/#/proxies',page:'/ui/#/proxies',width:1180},
  adguard:{title:'AdGuard Home',icon:appImage('adguard'),url:'/adguard/',page:'/adguard/',width:1180},
  workstation:{title:'工作站',icon:appImage('workstation'),url:()=>desktopPrefs.workstation_url,width:1280,height:860,external:true},
  terminal:{title:'终端',icon:appImage('terminal'),url:'/terminal/',width:920,height:580},
};
// The terminal is a root shell on the gateway, served by ttyd in the gateway image.
const terminalNotes={
  login:['终端需要密码登录','终端可以直接以 root 身份操作网关，只在开启“登录需要密码”后提供。','前往账户设置'],
  image:['终端暂不可用','当前网关镜像还没有终端组件。Niu Gateway 可以在线更新，终端需要更新网关镜像后才能使用。','知道了'],
  native:['终端暂不可用','原生安装的网关不内置终端，请使用这台主机自身的 SSH 或终端。','知道了'],
};
async function openTerminal(){
  if(frameWindows.has('terminal')){focusGatewayWindow(frameWindows.get('terminal'));return;}
  const state=await api('/terminal');
  if(state.available){openFrameApp('terminal');return;}
  const [title,copy,accept]=terminalNotes[state.reason]||terminalNotes.image;
  if(await askConfirm(copy,title,{accept})&&state.reason==='login')openSettings('account');
}
const frameWindows=new Map();
function openLinkWindow(card,iconSource=''){
  openFrameApp('link:'+card.id,{title:card.name,icon:iconSource||'/icons/link.svg',url:card.url,width:1180,external:true});
}
function openFrameApp(key,app=frameApps[key]){
  if(!app)return;
  const open=frameWindows.get(key);
  if(open){focusGatewayWindow(open);return;}
  const url=typeof app.url==='function'?app.url():app.url,page=app.page||url;
  const shell=element('div',undefined,'frame-shell'),frame=element('iframe'),bar=element('div',undefined,'window-toolbar');
  frame.title=app.title;frame.setAttribute('allow','clipboard-read; clipboard-write; fullscreen');
  if(app.external)frame.referrerPolicy='no-referrer';
  const load=()=>{frame.src=url;if(app.external)checkFrame(url,shell);};
  const reload=iconButton('refresh','重新载入',()=>{if(app.external){load();return;}try{frame.contentWindow.location.reload();}catch{frame.src=url;}},'toolbar-button');
  const tab=element('a',undefined,'button-link toolbar-button icon-button');tab.href=page;tab.target='_blank';tab.rel=app.external?'noopener noreferrer':'noopener';tab.title='在新标签页中打开';tab.setAttribute('aria-label','在新标签页中打开 '+app.title);tab.append(glyph('external'));
  bar.append(element('span',undefined,'toolbar-spacer'),reload,tab);shell.append(frame,bar);
  if(app.external)shell.append(frameNotice(key,app,page,load));
  document.body.append(shell);load();
  const win=createGatewayWindow(shell,app.title,app.icon,()=>closeFrameApp(key),{toolbar:bar,app:key,width:app.width,height:app.height});
  frameWindows.set(key,win);markRunningApps();
}
// Another host may be offline, use a certificate this browser has not trusted yet, or
// forbid other pages from showing it. A page cannot read a cross-origin frame, so ask the
// host directly, and let the gateway read the headers that decide whether it may be framed.
const frameProblems={
  unreachable:'地址暂时无法访问，或这个网站使用了浏览器尚未信任的证书。请先在新标签页中打开它（自签名证书需要先选择继续访问），再回到这里重试。',
  refused:'这个网站不允许其他页面把它显示在窗口里（网站的 X-Frame-Options 或 CSP 设置），窗口中只会是空白。请在新标签页中打开它。',
  mixed:'当前网关页面通过 HTTPS 打开，浏览器不允许在其中显示 HTTP 网站。请在新标签页中打开它。',
};
function frameNotice(key,app,page,retry){
  const notice=element('div',undefined,'frame-notice'),box=element('div',undefined,'frame-notice-box'),actions=element('div',undefined,'window-actions');
  const image=element('img');image.src=app.icon;image.alt='';image.width=64;image.height=64;
  const tab=element('a','在新标签页中打开','button-link');tab.href=page;tab.target='_blank';tab.rel='noopener noreferrer';
  const copy=element('p'),again=button('重试',retry,'primary');actions.append(tab,again);
  // A link that can never show in a window can switch to a new tab for good.
  const card=key.startsWith('link:')?cards.find(c=>'link:'+c.id===key):null;
  const always=card&&button('以后都在新标签页打开',()=>{
    window.open(page,'_blank','noopener,noreferrer');closeFrameApp(key);
    guard(async()=>{await api('/cards/'+card.id,{method:'PATCH',body:JSON.stringify({name:card.name,url:card.url,icon:card.icon,tag:card.tag||'链接',open_in_new_tab:true})});await loadCards();toast('“'+card.name+'”以后会在新标签页中打开。');});
  });
  if(always)actions.prepend(always);
  notice.show=kind=>{
    copy.textContent=frameProblems[kind];const final=kind!=='unreachable';
    again.hidden=final;tab.classList.toggle('primary',final);if(always)always.hidden=!final;notice.hidden=false;
  };
  box.append(image,element('strong','无法在窗口中打开“'+app.title+'”'),copy,actions);
  notice.append(box);notice.hidden=true;return notice;
}
async function checkFrame(url,shell){
  const notice=shell.querySelector('.frame-notice'),request=(shell.frameCheck||0)+1;shell.frameCheck=request;notice.hidden=true;
  const show=kind=>{if(shell.frameCheck===request&&shell.isConnected)notice.show(kind);};
  let target;try{target=new URL(url,location.href);}catch{show('unreachable');return;}
  if(location.protocol==='https:'&&target.protocol==='http:'){show('mixed');return;}
  const framing=api('/frame-check?url='+encodeURIComponent(target.href)+'&origin='+encodeURIComponent(location.origin)).catch(()=>null);
  try{await fetch(target.href,{mode:'no-cors',cache:'no-store',credentials:'omit',referrerPolicy:'no-referrer',signal:AbortSignal.timeout?.(10000)});}
  catch{show('unreachable');return;}
  if((await framing)?.framable===false)show('refused');
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
    ['关于 Niu Gateway','info',()=>openAbout()],null,
    ['控制面板…','gear',()=>openSettings()],
    ['代理配置…','relay',()=>openProxyWindow()],
    ['局域网互传','window',()=>openFrameApp('transfer')],
    ['添加桌面链接…','plus',()=>openLinkEditor()],
    ['个性化…','image',()=>openPersonalization()],null,
    ['退出登录','logout',()=>$('#logout').click()],
  ];
}
// About this gateway: version, address and the project's source.
async function openAbout(){
  const dialog=$('#about-dialog');if(dialog.open)return;
  $('#about-address').textContent=[status.domain&&'http://'+status.domain,status.address].filter(Boolean).join(' · ')||location.host;
  $('#about-version').textContent='读取中…';dialog.showModal();$('#about-close').focus();
  try{const info=await api('/web-release');$('#about-version').textContent=releaseLabel(info.current)+(info.available?'，可更新到 '+releaseLabel(info.latest):'');}
  catch{$('#about-version').textContent=releaseLabel(latestWebRelease?.current||'');}
}
$('#about-close').onclick=()=>$('#about-dialog').close();
$('#about-updates').onclick=()=>{$('#about-dialog').close();openSettings('updates');};
$('#desktop-reset').onclick=()=>guard(async()=>{
  if(!await askConfirm('网关应用回到程序坞，桌面上的链接重新排列。链接本身不会改变。','恢复默认布局',{accept:'恢复'}))return;
  await saveLayout([...DEFAULT_DOCK],{},'已恢复默认布局');
});
function hideSystemMenu(){const menu=$('#system-menu');if(!menu||menu.hidden)return;menu.hidden=true;$('#system-menu-button').setAttribute('aria-expanded','false');}
function showSystemMenu(){
  const menu=$('#system-menu'),anchor=$('#system-menu-button');menu.replaceChildren();
  const head=element('div',undefined,'menu-heading');head.append(element('strong','Niu Gateway'),element('span',status.domain?'http://'+status.domain:''));menu.append(head);
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
async function deleteCard(card){if(!await askConfirm('删除链接“'+card.name+'”？此操作仅移除桌面入口。','删除桌面链接',{accept:'删除',danger:true}))return;await api('/cards/'+card.id,{method:'DELETE'});closeFrameApp('link:'+card.id);await loadCards();toast('链接已删除');}
function hideContext(){const menu=$('#desktop-context-menu');if(menu)menu.hidden=true;}
function showContext(x,y,item=null,origin=null){
  if($('#auth-dialog').open)return;
  const menu=$('#desktop-context-menu');menu.replaceChildren();
  const add=(label,symbol,action,danger=false,image=null)=>{const b=button('',()=>{hideContext();Promise.resolve(action()).catch(e=>toast(e.message,true));},danger?'danger':'');b.setAttribute('role','menuitem');b.append(image||glyph(symbol),element('span',label));menu.append(b);};
  const line=()=>{const hr=element('div',undefined,'context-divider');hr.setAttribute('role','separator');menu.append(hr);};
  if(item){
    const docked=desktopPrefs.dock.includes(item.id),image=origin?.querySelector('img')?.src;
    add('打开','',()=>origin.click(),false,itemIcon(item));
    if(item.key==='workstation')add('在新标签页中打开','external',()=>window.open(desktopPrefs.workstation_url,'_blank','noopener'));
    else if(!item.system)add(item.open_in_new_tab?'在窗口中打开':'在新标签页中打开',item.open_in_new_tab?'window':'external',()=>item.open_in_new_tab?openLinkWindow(item,image):window.open(item.url,'_blank','noopener,noreferrer'));
    line();add(docked?'移到桌面':'放入程序坞',docked?'desktop':'dock',()=>docked?moveToDesktop(item):moveToDock(item));
    if(item.key==='workstation')add('设置入口地址…','gear',async()=>{await openSettings('desktop');$('#workstation-url').focus();});
    if(!item.system){add('编辑链接…','edit',()=>openLinkEditor(item));add('删除链接','trash',()=>guard(()=>deleteCard(item)),true);}
  }
  else{
    add('添加链接…','plus',()=>openLinkEditor());add('刷新桌面','refresh',()=>withLoading($('.desktop-workspace'),async()=>{await Promise.all([loadCards(),loadStatus()]);toast('桌面已刷新');}));
    const byName=(a,b)=>a.name.localeCompare(b.name,'zh-CN');
    if(phone.matches)add('按名称排列','list',()=>guard(()=>saveDesktopOrder([...cards].sort(byName).map(c=>c.id))));
    else{
      add('整理图标','grid',()=>arrangeIcons([...layout.cells].sort((a,b)=>a[1][0]-b[1][0]||a[1][1]-b[1][1]).map(([id])=>itemById(id)).filter(Boolean)));
      add('按名称排列','list',()=>arrangeIcons(desktopItems().sort(byName)));
    }
    line();add('个性化…','image',()=>openPersonalization());add('控制面板…','gear',()=>openSettings());
  }
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
  for(const area of [$('#desktop'),$('#dock')]){
    area.addEventListener('pointerdown',e=>{if(e.pointerType!=='touch')return;point=[e.clientX,e.clientY];const target=e.target.closest('.desktop-item,.dock-item');if(area.id==='dock'&&!target)return;hold=setTimeout(()=>{showContext(e.clientX,e.clientY,target?._desktopItem,target);hold=null;},600);});
    area.addEventListener('pointermove',e=>{if(point&&Math.hypot(e.clientX-point[0],e.clientY-point[1])>10){clearTimeout(hold);hold=null;}});
    for(const type of ['pointerup','pointercancel'])area.addEventListener(type,()=>{clearTimeout(hold);hold=null;point=null;});
    area.addEventListener('click',e=>{if(!$('#desktop-context-menu').hidden){e.preventDefault();e.stopImmediatePropagation();}},true);
  }
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
