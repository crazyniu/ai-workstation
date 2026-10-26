import base64,hashlib,hmac,ipaddress,json,os,re,secrets,shutil,subprocess,tempfile,threading,time
from pathlib import Path
import yaml

ROOT=Path(os.environ.get('DATA_DIR','/data'))
DASH=ROOT/'dashboard'
CONFIG=ROOT/'mihomo/config.yaml'
LOCK=threading.RLock()

def read(path, default=None):
    try: return json.loads(Path(path).read_text())
    except FileNotFoundError: return default

def atomic(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,tmp=tempfile.mkstemp(dir=path.parent,prefix='.write-')
    try:
        with os.fdopen(fd,'wb') as f:
            f.write(data if isinstance(data,bytes) else data.encode());f.flush();os.fsync(f.fileno())
        os.chmod(tmp,0o600);os.replace(tmp,path)
    finally:
        if os.path.exists(tmp):os.unlink(tmp)

def save(path,data):atomic(path,json.dumps(data,ensure_ascii=False,indent=2)+'\n')
def settings():return read(DASH/'settings.json',{'domain':'home.arpa','subscription':{'url':'','interval_hours':0},'tailscale':{'routes':'','accept_routes':True,'auto_routes':True}})
def command(args,timeout=20,check=True):
    r=subprocess.run(args,capture_output=True,text=True,timeout=timeout)
    if check and r.returncode: raise ValueError('操作失败，请检查服务状态和配置')
    return r

def config():return yaml.safe_load(CONFIG.read_text())
def write_config(value):atomic(CONFIG,yaml.safe_dump(value,allow_unicode=True,sort_keys=False))
def password_hash(password,salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()
def password_valid(password,stored):
    return hmac.compare_digest(password_hash(password,stored.split(':')[0]),stored)

def validate_password(password):
    if not isinstance(password,str) or not 1<=len(password)<=256:raise ValueError('密码长度为 1–256 个字符')
    return password

def initialize_admin():
    # Compose supplies an initial password only; persistent credentials always win.
    with LOCK:
        if not (DASH/'admin.json').exists():
            password=validate_password(os.environ.get('GATEWAY_ADMIN_PASSWORD','root'))
            save(DASH/'admin.json',{'password':password_hash(password)})

def local_domain(domain):
    domain=domain.lower().rstrip('.')
    if len(domain)>253 or not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+',domain):
        raise ValueError('请输入有效域名')
    if domain.endswith(('.dev','.app','.page')):raise ValueError('此域名强制 HTTPS，请使用 home.arpa 或配置证书')
    return domain

def lan_ip():
    address=os.environ.get('GATEWAY_LAN_ADDRESS','')
    return str(ipaddress.ip_interface(address).ip) if address else os.environ.get('GATEWAY_PUBLIC_ADDRESS','127.0.0.1')

def lan_networks():
    """Use the configured LAN, never the container control bridge or VPN routes."""
    address=os.environ.get('GATEWAY_LAN_ADDRESS','')
    if address:
        candidates=[ipaddress.ip_interface(address)]
    else:
        iface=os.environ.get('GATEWAY_RUNTIME_INTERFACE') or os.environ.get('GATEWAY_LAN_INTERFACE')
        if not iface:
            routes=json.loads(command(['ip','-j','-4','route','show','default']).stdout)
            iface=next((r.get('dev') for r in routes if r.get('dev')),None)
        if not iface or iface.startswith(('lo','docker','br-','veth','tailscale','tun','Mihomo')):
            raise ValueError('未检测到局域网接口，请检查网关网络连接后重试')
        addresses=json.loads(command(['ip','-j','-4','addr','show','dev',iface]).stdout)
        candidates=[ipaddress.ip_interface(str(a['local'])+'/'+str(a['prefixlen']))
                    for link in addresses for a in link.get('addr_info',[])
                    if a.get('family')=='inet' and a.get('scope')=='global']
    networks=sorted({str(a.network) for a in candidates if a.version==4 and 0<a.network.prefixlen<32
                     and not (a.ip.is_loopback or a.ip.is_link_local or a.ip.is_multicast or a.ip.is_unspecified)
                     and not a.network.overlaps(ipaddress.ip_network('100.64.0.0/10'))})
    if not networks:raise ValueError('未检测到可发布的局域网子网，请检查网关网络连接后重试')
    return networks

def domain_config(value,old=None):
    c=config();domain=local_domain(value);hosts=c.setdefault('hosts',{})
    if old and old!=domain:hosts.pop(old,None)
    hosts[domain]=lan_ip()
    dns=c.setdefault('dns',{});dns['use-hosts']=True
    filters=dns.setdefault('fake-ip-filter',[])
    for name in (domain,'+.home.arpa'):
        if name not in filters:filters.append(name)
    write_config(c)
    path=ROOT/'adguard/AdGuardHome.yaml'
    if path.exists():
        a=yaml.safe_load(path.read_text());f=a.setdefault('filtering',{})
        rewrites=[r for r in f.get('rewrites',[]) if r.get('domain') not in (old,domain)]
        rewrites.append({'domain':domain,'answer':lan_ip()});f['rewrites']=rewrites
        atomic(path,yaml.safe_dump(a,sort_keys=False))

def seed_adguard_filter(seed,value):
    """Populate only the absent, enabled official default filter cache."""
    target=ROOT/'adguard/work/data/filters/1.txt'
    if target.exists():return False
    manifest=read(Path(seed)/'filters/manifest.json')
    if not manifest:return False
    if not any(f.get('id')==1 and f.get('enabled') and f.get('url')==manifest['update_url'] for f in value.get('filters',[])):
        return False
    content=(Path(seed)/'filters/adguard-dns.txt').read_bytes()
    if hashlib.sha256(content).hexdigest()!=manifest['sha256']:
        raise ValueError('内置广告过滤规则校验失败')
    atomic(target,content)
    return True

def initialize():
    for p in ('dashboard','mihomo','adguard/work','tailscale','components/current','components/versions','backups'):(ROOT/p).mkdir(parents=True,exist_ok=True)
    seed=Path(os.environ.get('SEED_DIR','/opt/gateway/seed'))
    for component in ('mihomo','adguard','tailscale','panel'):
        link=ROOT/'components/current'/component
        if not link.exists():
            source=seed/component
            target=ROOT/'components/versions'/component/'bundled'
            target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists():shutil.copytree(source,target)
            link.symlink_to(target)
    if not CONFIG.exists():
        write_config({'mixed-port':7890,'socks-port':7891,'allow-lan':True,'bind-address':os.environ.get('GATEWAY_BIND_ADDRESS','*'),'mode':'rule','log-level':'info','ipv6':False,
          'external-controller':'127.0.0.1:9090','secret':secrets.token_urlsafe(32),'external-ui':str(ROOT/'components/current/panel'),
          'dns':{'enable':True,'listen':os.environ.get('GATEWAY_CORE_DNS_LISTEN','0.0.0.0:53'),'enhanced-mode':'fake-ip','fake-ip-range':'198.18.0.1/16','nameserver':[os.environ.get('GATEWAY_LAN_ROUTER','1.1.1.1')],'proxy-server-nameserver':[os.environ.get('GATEWAY_LAN_ROUTER','1.1.1.1')]},
          'tun':{'enable':os.environ.get('GATEWAY_MODE','true')=='true','device':'Mihomo','stack':'gvisor','auto-route':True,'strict-route':True,'auto-detect-interface':True,'dns-hijack':['any:53','tcp://any:53'],'route-exclude-address':['192.168.0.0/16','10.0.0.0/8','172.16.0.0/12']},'proxies':[],'proxy-groups':[],'rules':['MATCH,DIRECT']})
    c=config();c['external-controller']='127.0.0.1:9090';c['external-ui']=str(ROOT/'components/current/panel');c.setdefault('secret',secrets.token_urlsafe(32));write_config(c)
    if not (ROOT/'adguard/AdGuardHome.yaml').exists():
        atomic(ROOT/'adguard/AdGuardHome.yaml',yaml.safe_dump({'http':{'address':'127.0.0.1:3000'},'users':[],'language':'zh-cn',
          'dns':{'bind_hosts':[os.environ.get('GATEWAY_BIND_ADDRESS','0.0.0.0')],'port':int(os.environ.get('GATEWAY_DNS_PORT','5353')),'upstream_dns':[os.environ.get('GATEWAY_CORE_DNS_UPSTREAM','127.0.0.1:53')],'fallback_dns':[],'bootstrap_dns':['1.1.1.1'],'ratelimit':100,'cache_size':4194304,'use_private_ptr_resolvers':False},
          'filtering':{'protection_enabled':True,'filtering_enabled':True,'filters_update_interval':24},
          'filters':[{'enabled':True,'url':'https://adguardteam.github.io/AdGuardSDNSFilter/Filters/filter.txt','name':'AdGuard DNS filter','id':1}],
          'querylog':{'enabled':True,'file_enabled':True,'interval':'168h'},'statistics':{'enabled':True,'interval':'24h'},'dhcp':{'enabled':False},'schema_version':34},sort_keys=False))
    # Preserve filtering and upstreams on migration; expose the UI only through authenticated Nginx.
    p=ROOT/'adguard/AdGuardHome.yaml';a=yaml.safe_load(p.read_text());a['http']['address']='127.0.0.1:3000';a['users']=[];a['dns']['bind_hosts']=[os.environ.get('GATEWAY_BIND_ADDRESS','0.0.0.0')];atomic(p,yaml.safe_dump(a,sort_keys=False))
    seed_adguard_filter(seed,a)
    if not (DASH/'settings.json').exists():save(DASH/'settings.json',settings())
    initialize_admin()
    if not (DASH/'session-key').exists():atomic(DASH/'session-key',secrets.token_hex(32))
    domain_config(settings()['domain'])
    Path('/run/gateway').mkdir(parents=True,exist_ok=True)
    atomic('/run/gateway/proxy-auth.conf','proxy_set_header Authorization "Bearer '+config()['secret'].replace('"','').replace('\n','')+'";\n')

if __name__=='__main__':initialize()
