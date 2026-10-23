#!/usr/bin/env python3
import base64,hashlib,hmac,http.client,http.cookies,io,ipaddress,json,os,re,secrets,shutil,socket,subprocess,tarfile,tempfile,threading,time,urllib.parse,urllib.request,uuid
from http.server import ThreadingHTTPServer
from pathlib import Path
import yaml
import legacy
from state import ROOT,DASH,CONFIG,LOCK,read,save,atomic,settings,command,config,write_config,password_hash,password_valid,validate_password,domain_config,local_domain,lan_ip,lan_networks
import updates
import favicon
legacy.CONFIG_LOCK=LOCK
MAX_BODY=36*1024*1024
JOBS={}
FAILURES={}
JOB_LOCK=threading.Lock()

def ts(args,timeout=15):
    return command([str(ROOT/'components/current/tailscale/tailscale'),'--socket=/run/tailscale/tailscaled.sock']+args,timeout=timeout,check=False)

def tailscale_local_api(path,payload):
    # Use the same private Unix socket as the CLI; never expose identity preferences in argv.
    connection=http.client.HTTPConnection('local-tailscaled.sock',timeout=8)
    connection.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
    try:
        connection.sock.settimeout(8);connection.sock.connect('/run/tailscale/tailscaled.sock')
        connection.request('POST','/localapi/v0/'+path,json.dumps(payload),{'Content-Type':'application/json'})
        response=connection.getresponse();response.read()
        if response.status not in (200,204):raise ValueError('Tailscale 连接请求失败，请检查服务后重试')
    finally:connection.close()

def tailscale_raw_status():
    try:
        value=json.loads(ts(['status','--json']).stdout)
        return value if isinstance(value,dict) else {}
    except (ValueError,OSError,subprocess.SubprocessError):return {}

def tailscale_status():
    s=tailscale_raw_status();me=s.get('Self') or {};error=''
    try:networks=lan_networks()
    except (ValueError,OSError,subprocess.SubprocessError):networks=[];error='未检测到局域网子网，请检查网关网络连接'
    applied=settings().get('tailscale',{})
    configured=bool(networks) and applied.get('auto_routes') is True and applied.get('accept_routes') is True and applied.get('routes')==','.join(networks)
    primary=me.get('PrimaryRoutes') or []
    if error:route_state='error';note=error
    elif s.get('BackendState')!='Running':route_state='waiting';note='连接后自动配置内网访问，无需填写网段。'
    elif not me.get('Online'):route_state='waiting';note='正在重新连接 Tailscale，恢复后自动配置内网访问。'
    elif not configured:route_state='configuring';note='正在自动配置内网访问…'
    elif set(networks)<=set(primary):route_state='active';note='子网路由已生效，可从已授权的 Tailscale 设备访问内网。'
    else:route_state='pending';note='子网已自动发布，正在等待 Tailscale 路由批准或启用。'
    if not error and s.get('BackendState')=='Running':error=read(DASH/'tailscale-error.json',{}).get('error','')
    if error:route_state='error';note=error
    return {'state':s.get('BackendState','Unavailable'),'ips':s.get('TailscaleIPs',[]),'online':me.get('Online',False),
            'name':me.get('HostName',''),'login_url':s.get('AuthURL',''),'has_identity':bool(s.get('HaveNodeKey') or s.get('TailscaleIPs')),
            'routes':{'routes':','.join(networks),'accept_routes':True,'auto_routes':True},'route_state':route_state,
            'peers':sum(bool(p.get('Online')) for p in (s.get('Peer') or {}).values()),
            'primary_routes':primary,'approval_note':note,'health':s.get('Health') or []}

def configure_tailscale_routes():
    # Serialize with upgrades/restore; always verify against daemon preferences after a restart.
    with LOCK:
        routes=','.join(lan_networks())
        result=ts(['debug','prefs'])
        try:current=json.loads(result.stdout);current=current if isinstance(current,dict) else {}
        except ValueError:current={}
        advertised=set(current.get('AdvertiseRoutes') or [])-{'0.0.0.0/0','::/0'}
        if (result.returncode or advertised!=set(routes.split(','))
                or current.get('RouteAll') is not True or current.get('CorpDNS') is not False or current.get('NoSNAT') is not False):
            result=ts(['set','--accept-dns=false','--accept-routes=true','--snat-subnet-routes=true','--advertise-routes='+routes])
            if result.returncode:raise ValueError('自动配置内网访问失败，系统会重试；请检查 Tailscale 服务')
        prefs={'routes':routes,'accept_routes':True,'auto_routes':True}
        value=settings()
        if value.get('tailscale')!=prefs:value['tailscale']=prefs;save(DASH/'settings.json',value)
        (DASH/'tailscale-error.json').unlink(missing_ok=True)
    return prefs

def connect_tailscale():
    before=tailscale_raw_status()
    if not before.get('BackendState'):
        updates.control('start','tailscale')
        updates.wait_health('tailscale')
        before=tailscale_raw_status()
    configure_tailscale_routes()
    # Start with the current full profile, avoiding CLI up's accidental-setting-revert rules.
    current=ts(['debug','prefs'])
    try:prefs=json.loads(current.stdout)
    except ValueError:prefs=None
    if current.returncode or not isinstance(prefs,dict):raise ValueError('无法读取 Tailscale 配置，请检查服务后重试')
    prefs.update(WantRunning=True,LoggedOut=False)
    prefs['ControlURL']=prefs.get('ControlURL') or 'https://controlplane.tailscale.com'
    tailscale_local_api('start',{'UpdatePrefs':prefs})
    if before.get('BackendState') in ('NeedsLogin','NoState') or not (before.get('HaveNodeKey') or before.get('TailscaleIPs')):
        tailscale_local_api('login-interactive',{})
    deadline=time.monotonic()+8
    while True:
        status=tailscale_status()
        if status['login_url'] or status['state'] in ('Running','NeedsMachineAuth'):return status
        if time.monotonic()>=deadline:raise ValueError('无法连接 Tailscale，请检查网络或服务后重试')
        time.sleep(.3)

def maintain_tailscale_routes():
    with LOCK:
        if any(j['status']=='running' for j in JOBS.values()):return
        if tailscale_raw_status().get('BackendState')!='Running':return
        try:configure_tailscale_routes()
        except Exception as exc:
            message=str(exc) if isinstance(exc,ValueError) else '自动配置内网访问失败，系统会重试'
            save(DASH/'tailscale-error.json',{'error':message})

def tailscale_scheduler():
    while True:
        try:maintain_tailscale_routes()
        except Exception:pass  # Daemon starting/unavailable; retry independently of subscription refresh.
        time.sleep(30)

def submit(kind,work):
    with JOB_LOCK:
        if any(j['status']=='running' for j in JOBS.values()):raise ValueError('有任务正在执行，请等待完成')
        ident=uuid.uuid4().hex;JOBS[ident]={'id':ident,'kind':kind,'status':'running','started':time.time()}
    def run():
        try: result=work();JOBS[ident].update(status='success',result=result)
        except Exception as exc:JOBS[ident].update(status='error',error=str(exc) if isinstance(exc,ValueError) else '操作失败，原配置已保留；请检查连接或服务日志')
        JOBS[ident]['finished']=time.time();save(DASH/'last-job.json',JOBS[ident])
    threading.Thread(target=run,daemon=True).start()
    return JOBS[ident].copy()

def fetch_subscription(url):
    parsed=urllib.parse.urlparse(url)
    if parsed.scheme not in ('http','https') or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('请输入有效的 HTTP(S) 配置订阅链接')
    request=urllib.request.Request(url,headers={'User-Agent':'clash.meta'})
    with urllib.request.urlopen(request,timeout=30) as r:data=r.read(2*1024*1024+1)
    if len(data)>2*1024*1024:raise ValueError('订阅超过 2 MB')
    content=data.decode('utf-8-sig');value=yaml.safe_load(content)
    if not isinstance(value,dict) or not any(k in value for k in ('proxies','proxy-providers','proxy-groups')):
        raise ValueError('订阅必须返回 Clash/Mihomo YAML 配置')
    return content


def validate_appearance(value):
    if not isinstance(value,dict):raise ValueError('个性化设置必须为对象')
    fit=value.get('fit','cover');image=value.get('image','')
    theme=value.get('theme','auto');wallpaper=value.get('wallpaper','coast')
    if theme not in ('light','dark','auto'):raise ValueError('请选择有效的显示模式')
    if wallpaper not in ('coast','mountain','dusk','forest'):raise ValueError('请选择内置壁纸')
    if fit not in ('cover','contain','stretch','center','tile'):raise ValueError('请选择有效的壁纸显示方式')
    if not isinstance(image,str) or len(image)>4*1024*1024:raise ValueError('壁纸需要小于 3 MB')
    if image:
        match=re.fullmatch(r'data:image/(png|jpeg|webp);base64,([A-Za-z0-9+/=]+)',image)
        if not match:raise ValueError('请选择 PNG、JPEG 或 WebP 图片')
        try:raw=base64.b64decode(match[2],validate=True)
        except ValueError:raise ValueError('图片数据无效')
        signatures={'png':raw.startswith(b'\x89PNG\r\n\x1a\n'),'jpeg':raw.startswith(b'\xff\xd8\xff'),'webp':raw.startswith(b'RIFF') and raw[8:12]==b'WEBP'}
        if not signatures[match[1]]:raise ValueError('图片格式与内容不一致')
    return {'fit':fit,'image':image,'theme':theme,'wallpaper':wallpaper}

def valid_card_icon(icon):
    if icon=='auto':return True
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,63}',icon):return False
    web=Path('/opt/gateway/web')
    if not web.is_dir():web=Path(__file__).resolve().parents[1]/'web'
    catalog=read(web/'icons/catalog.json',[])
    if isinstance(catalog,dict):catalog=catalog.get('icons',[])
    allowed={'link','clash','adguard','tailscale','server','folder','globe'}
    if isinstance(catalog,list):allowed.update(item.get('id') for item in catalog if isinstance(item,dict))
    return icon in allowed and (web/'icons'/f'{icon}.svg').is_file()

class Handler(legacy.Handler):
    def reply(self,status,payload):
        body=json.dumps(payload,ensure_ascii=False).encode();self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Cache-Control','no-store');self.send_header('Content-Length',str(len(body)))
        self.end_headers();self.wfile.write(body)
    def body(self,limit=MAX_BODY):
        try:size=int(self.headers.get('Content-Length','0'))
        except ValueError:raise ValueError('无效请求')
        if not 0<=size<=limit:raise ValueError('请求超过限制')
        try:value=json.loads(self.rfile.read(size) or '{}')
        except (ValueError,UnicodeError):raise ValueError('无效 JSON')
        if not isinstance(value,dict):raise ValueError('请求必须为对象')
        return value
    def session(self):
        try:
            cookie=http.cookies.SimpleCookie(self.headers.get('Cookie',''));token=cookie['gateway_session'].value
            expires,signature=token.split('.')
            with LOCK:
                key=(DASH/'session-key').read_text().encode()
                return int(expires)>time.time() and hmac.compare_digest(signature,hmac.new(key,expires.encode(),hashlib.sha256).hexdigest())
        except (KeyError,ValueError,FileNotFoundError):return False
    def login_reply(self):
        expires=str(int(time.time()+43200));signature=hmac.new((DASH/'session-key').read_text().encode(),expires.encode(),hashlib.sha256).hexdigest()
        self.send_response(200);self.send_header('Set-Cookie',f'gateway_session={expires}.{signature}; Path=/; HttpOnly; SameSite=Strict; Max-Age=43200');self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}')
    def same_origin(self):
        origin=self.headers.get('Origin')
        return not origin or urllib.parse.urlparse(origin).netloc==self.headers.get('Host')
    def authorized(self):
        if not self.session():self.reply(401,{'error':'请先登录'});return False
        return True
    def do_GET(self):
        try:self.get()
        except Exception as exc:self.reply(400,{'error':str(exc) if isinstance(exc,ValueError) else '暂时无法读取，请检查服务状态'})
    def get(self):
        path=urllib.parse.urlparse(self.path).path
        if path=='/api/auth':self.reply(200,{'initialized':(DASH/'admin.json').exists(),'authenticated':self.session()});return
        if path=='/api/auth/check':
            self.send_response(204 if self.session() else 401);self.end_headers();return
        if not self.authorized():return
        if path=='/api/favicon':
            query=urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query)
            try:result=favicon.get_icon(query.get('url',[''])[0])
            except (ValueError,OSError,http.client.HTTPException):result=None
            if not result:self.reply(404,{'error':'网站图标暂不可用'});return
            body,mime=result
            self.send_response(200);self.send_header('Content-Type',mime)
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','private, max-age=3600')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Content-Security-Policy',"default-src 'none'; sandbox")
            self.end_headers();self.wfile.write(body);return
        if path=='/api/appearance':self.reply(200,validate_appearance(read(DASH/'appearance.json',{})));return
        if path=='/api/cards':self.reply(200,{'cards':legacy.read_cards()});return
        if path=='/api/proxy/config':
            content=CONFIG.read_bytes();self.reply(200,{'filename':'config.yaml','content':content.decode(),'revision':legacy.revision(content)});return
        if path=='/api/status':
            r=command(updates.SUPERVISOR+['status'],check=False)
            self.reply(200,{'services':r.stdout,'configured':read(DASH/'proxy-state.json',{}).get('configured',False),'domain':settings()['domain'],'address':lan_ip()});return
        if path=='/api/settings':self.reply(200,settings());return
        if path=='/api/tailscale':self.reply(200,tailscale_status());return
        if path=='/api/updates':self.reply(200,{'components':updates.manifests(),'checked':read(DASH/'releases.json',{}),'job':next((j for j in JOBS.values() if j['status']=='running'),read(DASH/'last-job.json'))});return
        if path.startswith('/api/jobs/'):
            job=JOBS.get(path.split('/')[-1]) or read(DASH/'last-job.json',{})
            if job.get('id')!=path.split('/')[-1]:self.reply(404,{'error':'任务不存在'});return
            self.reply(200,job);return
        if path=='/api/backup':
            stream=io.BytesIO()
            with tarfile.open(fileobj=stream,mode='w:gz') as archive:
                for name in backup_paths():
                    p=ROOT/name
                    if p.is_file():archive.add(p,arcname=name,recursive=False)
            self.reply(200,{'filename':'gateway-backup-'+time.strftime('%Y%m%d')+'.tgz','data':base64.b64encode(stream.getvalue()).decode()});return
        self.reply(404,{'error':'接口不存在'})
    def do_POST(self):
        try:self.post()
        except Exception as exc:self.reply(400,{'error':str(exc) if isinstance(exc,ValueError) else '操作失败，请检查输入及服务状态'})
    def post(self):
        path=urllib.parse.urlparse(self.path).path
        if not self.same_origin():self.reply(403,{'error':'请从本网关页面操作'});return
        if path in ('/api/auth/setup','/api/auth/login'):
            data=self.body(8192);password=validate_password(data.get('password',''));address=self.headers.get('X-Real-IP',self.client_address[0])
            attempts=FAILURES.get(address,[]);attempts=[t for t in attempts if t>time.time()-300]
            if len(attempts)>=10:self.reply(429,{'error':'尝试过多，请五分钟后重试'});return
            with LOCK:
                admin=read(DASH/'admin.json')
                if path.endswith('setup'):
                    if admin:raise ValueError('管理员已设置，请登录')
                    save(DASH/'admin.json',{'password':password_hash(password)})
                elif not admin or not password_valid(password,admin['password']):
                    FAILURES[address]=attempts+[time.time()];self.reply(401,{'error':'密码错误'});return
                FAILURES.pop(address,None)
                self.login_reply()
            return
        if not self.authorized():return
        if path=='/api/auth/logout':
            self.send_response(200);self.send_header('Set-Cookie','gateway_session=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0');self.end_headers();self.wfile.write(b'{}');return
        if path=='/api/proxy/config':
            super().import_config();return
        data=self.body()
        if path=='/api/password':
            password=validate_password(data.get('password',''))
            current=data.get('current_password','')
            if not isinstance(current,str):raise ValueError('请输入当前密码')
            with LOCK:
                # Re-check under the same lock as rotation to serialize concurrent requests.
                if not self.authorized():return
                admin=read(DASH/'admin.json')
                if not admin or not password_valid(current,admin['password']):
                    self.reply(400,{'error':'当前密码错误'});return
                save(DASH/'admin.json',{'password':password_hash(password)})
                atomic(DASH/'session-key',secrets.token_hex(32))
                self.login_reply()
            return
        if path=='/api/appearance':
            value=validate_appearance(data)
            with LOCK:save(DASH/'appearance.json',value)
            self.reply(200,value);return
        if path=='/api/cards':
            card=self.validate_card(data);card['id']=uuid.uuid4().hex
            with LOCK:
                cards=legacy.read_cards();cards.append(card);legacy.write_cards(cards)
            self.reply(201,{'ok':True});return
        if path=='/api/cards/order':
            ids=data.get('ids',[])
            with LOCK:
                cards=legacy.read_cards()
                if not isinstance(ids,list) or len(ids)!=len(cards) or set(ids)!={c['id'] for c in cards}:raise ValueError('排序列表已变化，请刷新')
                lookup={c['id']:c for c in cards};legacy.write_cards([lookup[i] for i in ids])
            self.reply(200,{'ok':True});return
        if path=='/api/subscription':
            url=str(data.get('url','')).strip();hours=int(data.get('interval_hours',0))
            if hours not in (0,1,6,12,24):raise ValueError('请选择有效更新间隔')
            content=fetch_subscription(url)
            # Use the exact existing transactional importer, including cache refresh and rollback.
            result=self.apply_content(content)
            with LOCK:
                s=settings();s['subscription']={'url':url,'interval_hours':hours,'last_updated':time.time()};save(DASH/'settings.json',s)
            self.reply(200,result);return
        if path=='/api/subscription/refresh':
            s=settings()['subscription'];content=fetch_subscription(s.get('url',''));result=self.apply_content(content)
            with LOCK:value=settings();value['subscription']['last_updated']=time.time();value['subscription'].pop('error',None);save(DASH/'settings.json',value)
            self.reply(200,result);return
        if path=='/api/settings/domain':
            update_domain(str(data.get('domain','')))
            self.reply(200,{'ok':True});return
        if path=='/api/tailscale/action':
            action=data.get('action')
            if action in ('login','connect','start'):
                self.reply(202,submit('tailscale-connect',connect_tailscale));return
            if action in ('disconnect','stop'):
                def disconnect():
                    if ts(['down']).returncode:raise ValueError('断开失败，请检查 Tailscale 服务后重试')
                    return {'ok':True}
                self.reply(202,submit('tailscale-disconnect',disconnect));return
            if action=='restart':
                def restart():
                    updates.control('restart','tailscale');updates.wait_health('tailscale')
                    if tailscale_raw_status().get('BackendState')=='Running':configure_tailscale_routes()
                    return tailscale_status()
                self.reply(202,submit('tailscale-restart',restart));return
            if action=='logout':
                def logout():
                    if ts(['logout']).returncode:raise ValueError('Tailscale 退出失败')
                    return {'ok':True}
                self.reply(202,submit('tailscale-logout',logout));return
            raise ValueError('无效操作')
        if path=='/api/tailscale/settings':
            configure_tailscale_routes()
            self.reply(200,{'ok':True,'note':'内网子网已自动配置'});return
        if path=='/api/updates/check':self.reply(202,submit('check-updates',updates.check));return
        if path=='/api/updates/install':
            component=data.get('component')
            if component not in updates.COMPONENTS:raise ValueError('无效服务')
            self.reply(202,submit('upgrade-'+component,lambda:updates.upgrade(component)));return
        if path=='/api/restore':
            payload=base64.b64decode(data.get('data',''),validate=True)
            self.reply(202,submit('restore',lambda:restore(payload)));return
        self.reply(404,{'error':'接口不存在'})
    def apply_content(self,content):
        payload={'content':content,'filename':'subscription.yaml','revision':legacy.revision(CONFIG.read_bytes())}
        original_body,original_reply=self.body,self.reply
        captured={}
        self.body=lambda *args:payload
        self.reply=lambda code,value:captured.update(code=code,value=value)
        try:self.import_config()
        finally:self.body,self.reply=original_body,original_reply
        if captured.get('code')!=200:raise ValueError(captured.get('value',{}).get('error','订阅应用失败'))
        save(DASH/'proxy-state.json',{'configured':True})
        return captured['value']
    def apply_config(self):
        # Legacy importer writes one HTTP response; record success only after it reports 200.
        self.config_status=None
        original=self.send_response
        def capture(code,*args,**kwargs):self.config_status=code;return original(code,*args,**kwargs)
        self.send_response=capture
        try:super().apply_config()
        finally:self.send_response=original
        if self.config_status==200:save(DASH/'proxy-state.json',{'configured':True})
    def validate_card(self,data):
        card=super().validate_card(dict(data,tag=data.get('tag') or '链接'))
        icon=str(data.get('icon','link'))
        if not valid_card_icon(icon):raise ValueError('请选择图标')
        card['icon']=icon;return card
    def do_PATCH(self):
        if not self.same_origin():self.reply(403,{'error':'请从本网关页面操作'});return
        if not self.authorized():return
        try:
            ident=self.path.split('/')[-1];card=self.validate_card(self.body())
            with LOCK:
                cards=legacy.read_cards();index=next((i for i,c in enumerate(cards) if c['id']==ident),None)
                if index is None:raise ValueError('链接不存在')
                cards[index]=dict(card,id=ident);legacy.write_cards(cards)
            self.reply(200,{'ok':True})
        except Exception as exc:self.reply(400,{'error':str(exc) if isinstance(exc,ValueError) else '更新失败'})
    def do_DELETE(self):
        if not self.same_origin():self.reply(403,{'error':'请从本网关页面操作'});return
        if not self.authorized():return
        with LOCK:super().do_DELETE()

def backup_paths():
    return ['mihomo/config.yaml','adguard/AdGuardHome.yaml','tailscale/tailscaled.state']+['dashboard/'+n for n in ('cards.json','settings.json','proxy-state.json','appearance.json')]

def update_domain(value):
    domain=local_domain(value)
    with LOCK:
        s=settings();stopped=False;snapshot={};changed=False
        paths=(CONFIG,ROOT/'adguard/AdGuardHome.yaml',DASH/'settings.json')
        try:
            # AdGuard saves its configuration on shutdown; stop before editing YAML.
            updates.control('stop','adguard');stopped=True
            snapshot={p:p.read_bytes() for p in paths}
            changed=True
            domain_config(domain,s['domain'])
            s['domain']=domain;save(DASH/'settings.json',s)
            legacy.controller_request('/configs?force=true',method='PUT',body={'path':str(CONFIG)})
            updates.control('start','adguard');updates.wait_health('adguard')
        except Exception as exc:
            try:
                if stopped:
                    command(updates.SUPERVISOR+['stop','adguard'],check=False)
                    if changed:
                        for p,body in snapshot.items():atomic(p,body)
                        legacy.controller_request('/configs?force=true',method='PUT',body={'path':str(CONFIG)})
                    updates.control('start','adguard');updates.wait_health('adguard')
            except Exception as rollback_exc:raise ValueError('域名更新失败，自动恢复未通过检查；请检查服务日志') from rollback_exc
            raise ValueError('域名更新失败，已恢复原设置') from exc

def restore(payload):
    if len(payload)>24*1024*1024:raise ValueError('备份过大')
    allowed=set(backup_paths());files={};total=0
    with tarfile.open(fileobj=io.BytesIO(payload),mode='r:gz') as archive:
        for m in archive:
            total+=m.size
            if m.name not in allowed or not m.isfile() or m.name in files or total>32*1024*1024:raise ValueError('无效或不安全的备份')
            files[m.name]=archive.extractfile(m).read()
    if 'mihomo/config.yaml' not in files or 'dashboard/settings.json' not in files:raise ValueError('备份缺少必要配置')
    c=yaml.safe_load(files['mihomo/config.yaml']);s=json.loads(files['dashboard/settings.json'])
    if not isinstance(c,dict) or not isinstance(s,dict):raise ValueError('备份配置无效')
    local_domain(s.get('domain',''))
    legacy.validate_providers(c)
    subscription=s.get('subscription');prefs=s.get('tailscale')
    if not isinstance(subscription,dict) or subscription.get('interval_hours',0) not in (0,1,6,12,24) or not isinstance(subscription.get('url',''),str):raise ValueError('备份订阅设置无效')
    if not isinstance(prefs,dict) or type(prefs.get('accept_routes'))!=bool or not isinstance(prefs.get('routes'),str):raise ValueError('备份路由设置无效')
    for route in prefs['routes'].split(','):
        if route.strip() and ipaddress.ip_network(route.strip(),strict=False).prefixlen==0:raise ValueError('备份包含默认路由，请在设置页配置子网路由')
    for key in ('last_attempt','last_updated'):
        if key in subscription and (type(subscription[key]) not in (int,float) or subscription[key]<0):raise ValueError('备份订阅时间无效')
    if 'dashboard/appearance.json' in files:validate_appearance(json.loads(files['dashboard/appearance.json']))
    if 'dashboard/cards.json' in files:
        cards=json.loads(files['dashboard/cards.json']);ids=set();validator=Handler.__new__(Handler)
        if not isinstance(cards,list) or len(cards)>1000:raise ValueError('备份桌面无效')
        for card in cards:
            if not isinstance(card,dict) or not isinstance(card.get('id'),str) or not card['id'] or card['id'] in ids:raise ValueError('备份桌面链接无效')
            validator.validate_card(card);ids.add(card['id'])
    if 'adguard/AdGuardHome.yaml' in files:
        agh=yaml.safe_load(files['adguard/AdGuardHome.yaml'])
        if not isinstance(agh,dict) or not isinstance(agh.get('dns'),dict):raise ValueError('备份 DNS 配置无效')
        # This installation authenticates the native UI at Nginx, never a LAN listener.
        agh.setdefault('http',{})['address']='127.0.0.1:3000';agh['users']=[];agh['dns']['bind_hosts']=['0.0.0.0']
        files['adguard/AdGuardHome.yaml']=yaml.safe_dump(agh,sort_keys=False).encode()
    with LOCK:
        backup=ROOT/'backups'/('restore-'+uuid.uuid4().hex);backup.mkdir(parents=True)
        previous_domain=settings()['domain']
        stopped=[];snapshot_complete=False;changed=False
        # domain_config also edits AdGuard even when it was omitted by the archive.
        affected=set(files)|{'mihomo/config.yaml','adguard/AdGuardHome.yaml'}
        state_dirs=('mihomo','adguard','tailscale');existing_dirs=set();existed=set()
        try:
            for service in ('mihomo','adguard','tailscale'):updates.control('stop',service);stopped.append(service)
            # Validation and startup can rewrite provider/geodata caches and service
            # databases. Roll back complete stopped state, not only uploaded YAML.
            for name in state_dirs:
                source=ROOT/name
                if source.exists():shutil.copytree(source,backup/name);existing_dirs.add(name)
            for name in affected:
                if name.split('/')[0] in state_dirs:continue
                dest=ROOT/name
                if dest.exists():
                    existed.add(name)
                    out=backup/name;out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(dest,out)
            snapshot_complete=True
            # Preserve this installation's controller identity and addresses when importing another deployment.
            current=config()
            for key in legacy.GATEWAY_KEYS:
                if key in current:c[key]=current[key]
                else:c.pop(key,None)
            files['mihomo/config.yaml']=yaml.safe_dump(c,sort_keys=False).encode()
            changed=True
            for name,body in files.items():atomic(ROOT/name,body)
            domain_config(s['domain'],previous_domain)
            command(['/opt/gateway/runtime/service','mihomo-test'],timeout=40)
            for service in stopped:updates.control('start',service)
            for service in stopped:updates.wait_health(service)
        except Exception as exc:
            try:
                for service in stopped:command(updates.SUPERVISOR+['stop',service],check=False)
                if snapshot_complete and changed:
                    for name in state_dirs:
                        target=ROOT/name
                        if target.exists():shutil.rmtree(target)
                        if name in existing_dirs:shutil.copytree(backup/name,target)
                    for name in affected:
                        if name.split('/')[0] in state_dirs:continue
                        if name in existed:atomic(ROOT/name,(backup/name).read_bytes())
                        else:(ROOT/name).unlink(missing_ok=True)
                for service in stopped:updates.control('start',service)
                for service in stopped:updates.wait_health(service)
            except Exception as rollback_exc:
                raise ValueError('恢复失败，自动回退未通过检查；请保留数据并检查备份 '+backup.name) from rollback_exc
            raise ValueError('恢复失败，已回退原配置') from exc
    return {'ok':True,'backup':backup.name}

def scheduler():
    # Same validated importer is invoked over loopback using an internal session cookie.
    while True:
        time.sleep(30)
        s=settings()['subscription'];interval=s.get('interval_hours',0)
        if not interval or time.time()-s.get('last_attempt',s.get('last_updated',0))<interval*3600:continue
        if not (DASH/'admin.json').exists():continue
        try:
            with LOCK:
                value=settings();value['subscription']['last_attempt']=time.time();save(DASH/'settings.json',value)
            expires=str(int(time.time()+60));signature=hmac.new((DASH/'session-key').read_text().encode(),expires.encode(),hashlib.sha256).hexdigest()
            req=urllib.request.Request('http://127.0.0.1:8787/api/subscription/refresh',data=b'{}',headers={'Cookie':f'gateway_session={expires}.{signature}','Content-Type':'application/json'})
            with urllib.request.urlopen(req,timeout=180) as r:
                if r.status!=200:raise ValueError('更新失败')
            with LOCK:value=settings();value['subscription']['last_updated']=time.time();value['subscription'].pop('error',None);save(DASH/'settings.json',value)
        except Exception:
            with LOCK:value=settings();value['subscription']['error']='定时刷新失败，原配置保留';save(DASH/'settings.json',value)

if __name__=='__main__':
    threading.Thread(target=scheduler,daemon=True).start()
    threading.Thread(target=tailscale_scheduler,daemon=True).start()
    ThreadingHTTPServer(('127.0.0.1',8787),Handler).serve_forever()
