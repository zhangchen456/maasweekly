#!/usr/bin/env python3
"""Root-controlled fixed data job; credentials only cross stdin, never argv or files."""
import fcntl,json,os,pwd,re,subprocess,sys,time
from pathlib import Path
ROOT=Path('/srv/maasweekly');SHARED=ROOT/'shared';STORE=SHARED/'data-store'
def command(args,**kwargs):return subprocess.run(args,check=True,**kwargs)
def runtime():
    value=json.loads((SHARED/'runtime.json').read_text());code=value['code']
    if not re.fullmatch('[a-f0-9]{10,40}',code):raise ValueError('invalid runtime')
    return ROOT/'runtime'/code

def docker(root,mode,body):
    writer=STORE/'writer';public=SHARED/'public-data';uid=pwd.getpwnam('maasdata').pw_uid;gid=pwd.getpwnam('maasdata').pw_gid
    image=(SHARED/'data-writer-image').read_text().strip()
    if not re.fullmatch('sha256:[a-f0-9]{64}',image):raise ValueError('pin the local writer image digest')
    mounts=[(root/'tooling','/code','ro'),(root,'/app','ro'),(writer,'/work','rw'),(writer/'data','/code/data','rw'),(root/'tooling/data/model-registry','/code/data/model-registry','ro'),(writer/'site-data','/code/site/src/data','rw'),(writer/'content','/code/site/src/content','rw'),(STORE/'blobs','/store/blobs','rw'),(STORE/'reports','/store/reports','rw'),(public,'/public','rw'),(Path('/var/run/postgresql'),'/var/run/postgresql','ro')]
    args=['docker','run','--rm','-i','--init','--name','maas-data-writer','--user',f'{uid}:{gid}','--read-only','--tmpfs','/tmp:rw,size=256m','--shm-size','256m','--memory','1536m','--memory-swap','1536m','--cpus','1','--pids-limit','256','--cap-drop','ALL','--cap-add','SYS_CHROOT','--security-opt','no-new-privileges','--security-opt','seccomp='+str(root/'tooling/ops/data-writer/seccomp.json'),'-e','MAAS_DATA_DSN=dbname=maas_data user=maasdata host=/var/run/postgresql','-e','MAAS_CODE_COMMIT='+(root/'tooling/code-commit').read_text().strip()]
    for source,target,access in mounts:args+=['-v',f'{source}:{target}:{access}']
    args += [image,'python','/code/ops/data-writer/run.py']
    log=STORE/'reports'/('writer-'+str(time.time_ns())+'-'+mode+'.log')
    with log.open('wb') as output:
        result=subprocess.run(args,input=body,stdout=output,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError('data job failed; log='+str(log))
    print('data stage completed:',mode,flush=True)

def main():
    if os.geteuid()!=0:raise ValueError('root required')
    body=sys.stdin.buffer.read(65537)
    if len(body)>65536:raise ValueError('request too large')
    incoming=json.loads(body);mode=incoming.get('mode')
    if mode not in ['prepare','validate','update']:raise ValueError('invalid mode')
    with (ROOT/'locks/release.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        root=runtime();docker(root,mode,body)
        if mode=='prepare':return
        receipt=json.loads((STORE/'writer/candidate.json').read_text());candidate=receipt['candidate']
        if not re.fullmatch('/public/candidates/[a-f0-9]{32}',candidate):raise ValueError('invalid candidate path')
        host=SHARED/'public-data'/candidate.removeprefix('/public/')
        reader_gid=pwd.getpwnam('maasagent').pw_gid
        for path in [host,*host.rglob('*')]:
            if path.is_symlink():raise ValueError('candidate symlink refused')
            os.chown(path,pwd.getpwnam('maasdata').pw_uid,reader_gid);path.chmod(0o2750 if path.is_dir() else 0o640)
        env={**os.environ,'PGHOST':'/var/run/postgresql','PGDATABASE':'maas_data','PGUSER':'maasagent'}
        command(['runuser','-u','maasagent','--','node',str(root/'scripts/verify-runtime-site.mjs'),'--package-root',str(root),'--data-root',str(host)],env=env)
        if mode=='validate':print('full data candidate and SSR validation passed; not published');return
        command(['runuser','-u','maasdata','--','bash',str(root/'tooling/ops/backup-data-store.sh')])
        docker(root,'publish',b'{"mode":"publish"}')
        expected=json.loads((host/'manifest.json').read_text())['datasetVersion']
        from urllib.request import urlopen
        for attempt in range(12):
            with urlopen('http://127.0.0.1:'+str(json.loads((SHARED/'runtime.json').read_text())['port'])+'/api/v1/status',timeout=15) as response:status=json.load(response)
            if status['datasetVersion']==expected:break
            time.sleep(2)
        else:raise ValueError('runtime has not accepted the published data')
        print(json.dumps({'status':'published','datasetVersion':expected,'codeDeployment':False,'gitCommit':False}),flush=True)
if __name__=='__main__':
    try:main()
    except Exception as error:
        print('data update failed: '+type(error).__name__+': '+str(error),file=sys.stderr);sys.exit(2)
