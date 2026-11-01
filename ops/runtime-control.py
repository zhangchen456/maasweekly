#!/usr/bin/env python3
"""Root-owned, reversible SSR slot switch. Shared data is never rolled back here."""
import argparse,fcntl,hashlib,json,os,re,subprocess,tempfile,time,sys
from pathlib import Path
from urllib.request import urlopen,Request
from urllib.error import HTTPError
sys.path.insert(0, str(Path(__file__).resolve().parent))
from runtime_safety import require_capacity, wait_runtime
import runtime_workers as workers
ROOT=Path('/srv/maasweekly')
SHARED=ROOT/'shared'
FILES=[SHARED/'nginx/site-root.inc',SHARED/'nginx/agent-upstream.inc',SHARED/'nginx/agent-routes.inc',Path('/etc/nginx/snippets/maasweekly-https.conf')]
def run(*args):subprocess.run(args,check=True,stdout=subprocess.DEVNULL)
def atomic(path,body):
    path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(dir=path.parent)
    with os.fdopen(fd,'wb') as f:f.write(body);f.flush();os.fsync(f.fileno())
    os.chmod(name,0o644);os.replace(name,path)

def retire_previous(previous, candidate):
    """Drain old requests only after the new route and recovery state are durable."""
    slot = previous.get('slot')
    if slot not in ('blue', 'green') or slot == candidate['slot']:
        return
    time.sleep(30)
    try:
        subprocess.run(['systemctl', 'stop', 'maas-agent@'+slot],
                       check=True, timeout=45, stdout=subprocess.DEVNULL)
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
        # A cleanup failure must not undo a healthy, committed deployment.
        print('warning: previous API slot could not be stopped: '+str(error), file=sys.stderr)
def fetch(port,route):
    try:
        with urlopen('http://127.0.0.1:'+str(port)+route,timeout=20) as r:return r.status,r.read()
    except HTTPError as e:return e.code,e.read()
def probe(port, code=None):
    published=json.loads((SHARED/'public-data/v1/publication.json').read_text())
    status,body=fetch(port,'/api/v1/status')
    if status!=200 or json.loads(body)['datasetVersion']!=published['datasetVersion']:raise ValueError('candidate dataset mismatch')
    # Existing rollback packages predate this capability. New packages must prove
    # their process code and loaded page input, not just their public dataset.
    if code:
        metadata=json.loads((ROOT/'runtime'/code/'metadata/runtime-manifest.json').read_text())
        if metadata.get('runtimeHealthVersion') == 1:
            wait_runtime(port,published,code,timeout=5)
    latest=json.loads(body)['status']['weekly']['latestId']
    if not isinstance(latest,str) or not re.fullmatch(r'\d{4}-\d{2}-\d{2}',latest):raise ValueError('latest weekly missing')
    for route in ['/','/en/','/models/','/pricing/','/feed.xml','/feed/weekly.xml','/sitemap.xml',f'/weekly/{latest}/',f'/en/weekly/{latest}/']:
        status,body=fetch(port,route)
        if status!=200 or b'data-private-weekly' in body:raise ValueError('candidate public page failed: '+route)
    if fetch(port,'/_internal/weekly-body/'+latest+'/')[0]!=404:raise ValueError('internal report exposed')
    if fetch(port,'/api/pro/weekly/'+latest)[0]!=401:raise ValueError('report entitlement boundary failed')
    return published['datasetVersion']
def stage(code):
    package=ROOT/'runtime'/code
    if not re.fullmatch('[a-f0-9]{10,40}',code) or package.is_symlink() or not (package/'site/dist/server/entry.mjs').is_file():raise ValueError('invalid runtime code')
    manifest_path=package/'metadata/runtime-manifest.json'
    if manifest_path.exists():
        components=json.loads(manifest_path.read_text()).get('components')
        if components and (components.get('workerProtocol')!=1 or components.get('controllerProtocol')!=2):raise ValueError('unsupported runtime component protocol')
    for parent in [package,package/'site',package/'site/dist']:parent.chmod(0o755)
    client=package/'site/dist/client'
    for item in [client,*client.rglob('*')]:
        if item.is_symlink():raise ValueError('public asset symlink refused')
        item.chmod(0o755 if item.is_dir() else 0o644)
    data=package/'data/public';data.mkdir(parents=True,exist_ok=True)
    link=data/'v1'
    if not link.exists():link.symlink_to(SHARED/'public-data/v1')
    active=(SHARED/'runtime.json')
    state=json.loads(active.read_text()) if active.exists() else {'slot':'green'}
    slot='blue' if state['slot']=='green' else 'green';port=8788 if slot=='blue' else 8789
    values={'PORT':port,'MAAS_RELEASE_DIR':package,'PUBLIC_DATA_ROOT':SHARED/'public-data/v1','MAAS_SITE_ENTRY':package/'site/dist/server/entry.mjs','PGHOST':'/var/run/postgresql','PGDATABASE':'maas_data','PGUSER':'maasagent','RELOAD_INTERVAL_MS':5000}
    atomic(SHARED/'slots'/f'{slot}.env',(''.join(f'{k}={v}\n' for k,v in values.items())).encode())
    run('systemctl','restart','maas-agent@'+slot)
    for _ in range(30):
        try:dataset=probe(port,code);break
        except Exception:time.sleep(1)
    else:raise ValueError('candidate did not become ready')
    result={'code':code,'slot':slot,'port':port,'datasetVersion':dataset}
    atomic(SHARED/'runtime-candidate.json',(json.dumps(result)+'\n').encode());return result

def activate(code):
    candidate=json.loads((SHARED/'runtime-candidate.json').read_text())
    if candidate['code']!=code:raise ValueError('stage this exact code first')
    probe(candidate['port'],code)
    backup=SHARED/'runtime-recovery'/str(time.time_ns());backup.mkdir(parents=True)
    old=[p.read_bytes() for p in FILES]
    for n,body in enumerate(old):(backup/str(n)).write_bytes(body)
    old_current=os.readlink(ROOT/'current')
    (backup/'current').write_text(old_current)
    for name in ['runtime.json','runtime-mode','runtime-previous.json']:
        path=SHARED/name
        if path.exists():(backup/name).write_bytes(path.read_bytes())
    slot=candidate['slot'];port=candidate['port'];package=ROOT/'runtime'/code
    routes=old[2].decode()
    for route in ['/feed.xml','/feed/weekly.xml']:
        # Replace only the existing balanced location block, including nested types {}.
        start=routes.index('location = '+route+' {');pos=routes.index('{',start);depth=1;end=pos+1
        while depth:
            depth += (routes[end]=='{')-(routes[end]=='}');end+=1
        routes=routes[:start]+f'location = {route} {{ proxy_pass http://agent_api; proxy_set_header Host $host; proxy_cache off; }}'+routes[end:]
    snippet=old[3].decode()
    snippet=snippet.replace('location = /_runtime/health { return 404; }\n','')
    start=snippet.index('location / {');end=snippet.index('\n}',start)+2
    snippet=snippet[:start]+'''location = /_runtime/health { return 404; }
location / {
    proxy_pass http://agent_api;
    proxy_http_version 1.1;
    proxy_set_header Host $host;
    proxy_set_header X-Maas-Client-IP $remote_addr;
    proxy_set_header X-Forwarded-For "";
    proxy_cache off;
    proxy_read_timeout 30s;
}
location ~ ^/(?:logos/|brand/|favicon[^/]*\\.(?:svg|png|ico)$|apple-touch-icon\\.png$|android-chrome[^/]*\\.png$|(?:analytics|language|time-display)\\.js$|site\\.webmanifest$|llms\\.txt$|openapi-v1\\.json$|changes\\.html$) {
    try_files $uri =404;
}
'''+snippet[end:]
    manage_workers=workers.managed(package) or workers.managed((ROOT/'current').resolve())
    atomic(SHARED/'runtime-switch-pending.json',(json.dumps({'backup':str(backup),'code':code,'workers':manage_workers})+'\n').encode())
    try:
        if manage_workers:workers.drain()
        atomic(FILES[0],f'root {package}/site/dist/client;\n'.encode())
        atomic(FILES[1],f'upstream agent_api {{ server 127.0.0.1:{port}; }}\n'.encode())
        atomic(FILES[2],routes.encode());atomic(FILES[3],snippet.encode())
        run('nginx','-t');run('systemctl','reload','nginx')
        # Test the real TLS virtual host through local nginx, avoiding DNS/edge ambiguity.
        for route in ['/','/en/','/api/v1/status','/feed.xml','/favicon.svg']:
            run('curl','--silent','--show-error','--fail','--max-time','20','--resolve','daily.maas.click:443:127.0.0.1','https://daily.maas.click'+route)
        previous=json.loads((SHARED/'runtime.json').read_text()) if (SHARED/'runtime.json').exists() else {'legacy':old_current,'slot':'green','recovery':str(backup)}
        atomic(SHARED/'runtime-previous.json',(json.dumps(previous)+'\n').encode())
        atomic(SHARED/'runtime.json',(json.dumps(candidate)+'\n').encode())
        atomic(SHARED/'runtime-mode',b'enabled\n')
        temp=ROOT/'.runtime-current';temp.unlink(missing_ok=True);temp.symlink_to(package);os.replace(temp,ROOT/'current')
        if manage_workers:
            candidate['workers']=workers.start_and_verify(ROOT,package)
            candidate['controllers']={name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in [('runtime',__file__),('workers',workers.__file__)]}
            atomic(SHARED/'runtime.json',(json.dumps(candidate)+'\n').encode())
        (SHARED/'runtime-switch-pending.json').unlink(missing_ok=True)
    except BaseException:
        recover_pending()
        raise
    retire_previous(previous, candidate)
    return {**candidate,'status':'active','recovery':str(backup)}

def rollback():
    previous=json.loads((SHARED/'runtime-previous.json').read_text())
    if 'code' in previous:
        stage(previous['code']);return activate(previous['code'])
    # A static rollback is only valid before independently published data changes.
    legacy=ROOT/previous['legacy']
    published=json.loads((SHARED/'public-data/v1/publication.json').read_text())
    old=json.loads((legacy/'data/public/v1/manifest.json').read_text())
    if published['datasetVersion']!=old['datasetVersion']:raise ValueError('legacy rollback cannot cover current data')
    backup=Path(previous['recovery'])
    for n,path in enumerate(FILES):atomic(path,(backup/str(n)).read_bytes())
    run('nginx','-t');run('systemctl','reload','nginx')
    tmp=ROOT/'.runtime-current';tmp.unlink(missing_ok=True);tmp.symlink_to(previous['legacy']);os.replace(tmp,ROOT/'current')
    for name in ['runtime.json','runtime-mode']:(SHARED/name).unlink(missing_ok=True)
    return {'status':'legacy_restored'}

def recover_pending():
    pending=SHARED/'runtime-switch-pending.json'
    if not pending.exists():return
    info=json.loads(pending.read_text());backup=Path(info['backup'])
    if not backup.resolve().is_relative_to((SHARED/'runtime-recovery').resolve()):raise ValueError('invalid recovery path')
    if info.get('workers'):workers.drain()
    for n,path in enumerate(FILES):atomic(path,(backup/str(n)).read_bytes())
    for name in ['runtime.json','runtime-mode','runtime-previous.json']:
        saved=backup/name
        if saved.exists():atomic(SHARED/name,saved.read_bytes())
        else:(SHARED/name).unlink(missing_ok=True)
    tmp=ROOT/'.runtime-current';tmp.unlink(missing_ok=True);tmp.symlink_to((backup/'current').read_text());os.replace(tmp,ROOT/'current')
    run('nginx','-t');run('systemctl','reload','nginx')
    if info.get('workers'):
        proofs=workers.start_and_verify(ROOT,(ROOT/'current').resolve())
        state=json.loads((SHARED/'runtime.json').read_text())
        state['workers']=proofs
        state['controllers']={name:hashlib.sha256(Path(path).read_bytes()).hexdigest() for name,path in [('runtime',__file__),('workers',workers.__file__)]}
        atomic(SHARED/'runtime.json',(json.dumps(state)+'\n').encode())
    pending.unlink()

def install_package(rid):
    if not re.fullmatch('rl_[a-f0-9]{10}_000000000000',rid):raise ValueError('invalid runtime upload ID')
    import importlib.util,pwd
    module=Path(__file__).with_name('runtime-package.py')
    spec=importlib.util.spec_from_file_location('runtime_package',module);package_module=importlib.util.module_from_spec(spec);spec.loader.exec_module(package_module)
    require_capacity(ROOT,'code',package_module.MAX_BYTES)
    package,manifest=package_module.install(ROOT/'incoming'/rid,ROOT/'runtime')
    if rid!='rl_'+manifest['codeCommit'][:10]+'_000000000000':raise ValueError('upload/code mismatch')
    active=SHARED/'runtime.json'
    if active.exists():
        current=json.loads(active.read_text())
        if current.get('code')==manifest['codeCommit']:
            probe(current['port'],current['code']);workers.start_and_verify(ROOT,package);return {**current,'status':'already_active'}
    requirements=package/'tooling/requirements.lock.txt'
    if requirements.read_bytes()!=(ROOT/'runtime/build-tools/writer/requirements.lock.txt').read_bytes():raise ValueError('writer dependency image must be rebuilt before this code release')
    (package/'tooling/site/src/data').mkdir(parents=True,exist_ok=True);(package/'tooling/site/src/content').mkdir(parents=True,exist_ok=True)
    executables={f['path'] for f in manifest['files'] if f.get('executable')}
    reader=pwd.getpwnam('maasagent').pw_gid;writer=pwd.getpwnam('maasdata').pw_gid
    for item in [package,*package.rglob('*')]:
        is_tooling=item==package/'tooling' or (package/'tooling') in item.parents
        os.chown(item,0,writer if is_tooling else reader,follow_symlinks=False)
        if not item.is_symlink():item.chmod(0o750 if item.is_dir() or str(item.relative_to(package)) in executables else 0o640)
    package.chmod(0o755)
    run('runuser','-u','maasdata','--','env','MAAS_SHADOW_DSN=dbname=maas_data','python3',str(package/'tooling/pipeline/scripts/shadow-data.py'),'migrate')
    env={**os.environ,'PGHOST':'/var/run/postgresql','PGDATABASE':'maas_data','PGUSER':'maasagent'}
    subprocess.run(['runuser','-u','maasagent','--','node',str(package/'scripts/verify-runtime-site.mjs'),'--package-root',str(package),'--data-root',str(SHARED/'public-data/v1')],env=env,check=True)
    stage(manifest['codeCommit']);return activate(manifest['codeCommit'])

def main():
    if os.geteuid()!=0:raise ValueError('root required')
    p=argparse.ArgumentParser();p.add_argument('action',choices=['stage','activate','rollback','status','install']);p.add_argument('code',nargs='?');a=p.parse_args()
    if a.action=='status':print((SHARED/'runtime.json').read_text());return
    with (ROOT/'locks/release.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        recover_pending()
        print(json.dumps(install_package(a.code) if a.action=='install' else stage(a.code) if a.action=='stage' else rollback() if a.action=='rollback' else activate(a.code)))
if __name__=='__main__':main()
