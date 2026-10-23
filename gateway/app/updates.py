import json,os,shutil,tempfile,time,uuid
from pathlib import Path
from state import ROOT,LOCK,atomic,save,read,command
from releases import discover,install_asset

COMPONENTS=('mihomo','adguard','tailscale','panel')
SUPERVISOR=['supervisorctl','-c','/opt/gateway/runtime/supervisord.conf']

def control(action,service):return command(SUPERVISOR+[action,service],timeout=45)
def manifests():
    return {c:read(ROOT/'components/current'/c/'version.json',{}) for c in COMPONENTS}
def check():
    result={}
    for c in COMPONENTS:
        current=manifests()[c]
        try:
            latest=discover(c)
            result[c]={'current':current.get('version','unknown'),'latest':latest['version'],'available':current.get('version')!=latest['version'],'manifest':latest}
        except Exception:
            result[c]={'current':current.get('version','unknown'),'error':'无法获取官方发布信息，请稍后重试'}
    save(ROOT/'dashboard/releases.json',result)
    return result

def health(component):
    # Process presence alone is insufficient: probe each service's actual control surface.
    import urllib.request
    if component in ('mihomo','panel'):
        from state import config
        req=urllib.request.Request('http://127.0.0.1:9090/'+('version' if component=='mihomo' else 'ui/'),headers={'Authorization':'Bearer '+config()['secret']})
        with urllib.request.urlopen(req,timeout=5) as r:
            if r.status!=200:raise ValueError('Clash 检查失败')
    elif component=='adguard':
        with urllib.request.urlopen('http://127.0.0.1:3000/control/status',timeout=5) as r:
            if not json.load(r).get('running'):raise ValueError('DNS 服务未运行')
        from state import settings,lan_ip
        result=command(['dig','@127.0.0.1','-p','5353',settings()['domain'],'+short','+time=3','+tries=1'],timeout=5)
        if lan_ip() not in result.stdout.splitlines():raise ValueError('本地域名解析检查失败')
    else:
        r=command([str(ROOT/'components/current/tailscale/tailscale'),'--socket=/run/tailscale/tailscaled.sock','status','--json'],check=False)
        status=json.loads(r.stdout)
        if not status.get('BackendState'):raise ValueError('Tailscale 状态不可用')

def switch(link,target):
    temp=link.with_name(link.name+'.next')
    temp.unlink(missing_ok=True);temp.symlink_to(target);os.replace(temp,link)

def wait_health(component,tailscale_before=None):
    for attempt in range(15):
        try:
            health(component)
            if tailscale_before is not None:verify_tailscale_identity(tailscale_before)
            return
        except Exception:
            if attempt==14:raise
            time.sleep(1)

def tailscale_identity():
    result=command([str(ROOT/'components/current/tailscale/tailscale'),'--socket=/run/tailscale/tailscaled.sock','status','--json'],check=False)
    try:return json.loads(result.stdout)
    except ValueError:return {}

def verify_tailscale_identity(before):
    if before.get('BackendState')!='Running':return
    after=tailscale_identity()
    prior=before.get('Self') or {};current=after.get('Self') or {}
    if (after.get('BackendState')!='Running' or set(before.get('TailscaleIPs',[]))!=set(after.get('TailscaleIPs',[]))
            or (prior.get('ID') and prior['ID']!=current.get('ID'))):
        raise ValueError('Tailscale 身份或地址检查失败')

def upgrade(component,manifest=None):
    if component not in COMPONENTS:raise ValueError('不支持此服务')
    with LOCK:
        manifest=manifest or discover(component)
        link=ROOT/'components/current'/component
        previous=link.resolve()
        target=ROOT/'components/versions'/component/(manifest['version'].replace('/','_')+'-'+uuid.uuid4().hex[:8])
        # Nothing running is changed until download and verification finish.
        install_asset(manifest,target)
        stamp=time.strftime('%Y%m%dT%H%M%SZ')+'-'+uuid.uuid4().hex[:6]
        backup=ROOT/'backups'/('upgrade-'+component+'-'+stamp)
        backup.mkdir(parents=True)
        service='mihomo' if component=='panel' else component
        configpaths=[ROOT/service]
        stopped=False
        snapshot_complete=False
        switched=False
        tailscale_before=tailscale_identity() if component=='tailscale' else {}
        try:
            if component=='mihomo':
                with tempfile.TemporaryDirectory() as scratch:
                    shutil.copytree(ROOT/'mihomo',Path(scratch)/'mihomo')
                    command([str(target/'mihomo'),'-t','-d',str(Path(scratch)/'mihomo'),'-f',str(ROOT/'mihomo/config.yaml')],timeout=40)
            if component=='adguard':
                with tempfile.TemporaryDirectory() as scratch:
                    shutil.copytree(ROOT/'adguard',Path(scratch)/'adguard')
                    command([str(target/'AdGuardHome'),'--check-config','-c',str(Path(scratch)/'adguard/AdGuardHome.yaml'),'-w',str(Path(scratch)/'adguard/work')],timeout=40)
            # Stop before copying state databases, then snapshot the complete affected state.
            control('stop',service);stopped=True
            for p in configpaths:
                if p.exists():shutil.copytree(p,backup/p.name,symlinks=False)
            snapshot_complete=True
            switch(link,target)
            switched=True
            control('start',service)
            if component=='tailscale':wait_health(component,tailscale_before)
            else:wait_health(component)
            save(backup/'upgrade.json',{'component':component,'previous':str(previous),'current':str(target),'success':True})
        except Exception as exc:
            if stopped:
                try:
                    command(SUPERVISOR+['stop',service],check=False)
                    if switched:switch(link,previous)
                    # An interrupted snapshot has never changed live state; do not
                    # replace a complete directory with a partial backup.
                    if snapshot_complete and switched:
                        for p in configpaths:
                            if p.exists():shutil.rmtree(p)
                            if (backup/p.name).exists():shutil.copytree(backup/p.name,p)
                    control('start',service)
                    if component=='tailscale':wait_health(component,tailscale_before)
                    else:wait_health(component)
                except Exception as rollback_exc:
                    raise ValueError('升级失败，自动恢复未通过检查；请保留数据并检查服务日志与备份 '+backup.name) from rollback_exc
            raise ValueError('升级失败，已恢复原版本和配置') from exc
        return {'component':component,'version':manifest['version'],'backup':backup.name}
