#!/usr/bin/env python3
"""Root-controlled fixed data job; credentials only cross stdin, never argv or files."""
import fcntl,json,os,pwd,re,stat,subprocess,sys,time
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
    mounts=[(root/'tooling','/code','ro'),(writer,'/work','rw'),(writer/'data','/code/data','rw'),(root/'tooling/data/model-registry','/code/data/model-registry','ro'),(writer/'site-data','/code/site/src/data','rw'),(writer/'content','/code/site/src/content','rw'),(STORE/'blobs','/store/blobs','rw'),(public,'/public','rw'),(Path('/var/run/postgresql'),'/var/run/postgresql','ro')]
    args=['docker','run','--rm','-i','--init','--name','maas-data-writer','--user',f'{uid}:{gid}','--read-only','--tmpfs','/tmp:rw,size=256m','--shm-size','256m','--memory','1536m','--memory-swap','1536m','--cpus','1','--pids-limit','256','--cap-drop','ALL','--cap-add','SYS_CHROOT','--security-opt','no-new-privileges','--security-opt','seccomp='+str(root/'tooling/ops/data-writer/seccomp.json'),'-e','MAAS_DATA_DSN=dbname=maas_data user=maasdata host=/var/run/postgresql','-e','MAAS_CODE_COMMIT='+(root/'tooling/code-commit').read_text().strip()]
    for source,target,access in mounts:args+=['-v',f'{source}:{target}:{access}']
    args += [image,'python','/code/ops/data-writer/run.py']
    log=STORE/'reports'/('writer-'+str(time.time_ns())+'-'+mode+'.log')
    with log.open('wb') as output:
        try:result=subprocess.run(args,input=body,stdout=output,stderr=subprocess.STDOUT,timeout=2700)
        except BaseException:
            subprocess.run(['docker','stop','--time','20','maas-data-writer'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            raise
    if result.returncode:raise RuntimeError('data job failed; log='+str(log))
    print('data stage completed:',mode,flush=True)

def main():
    os.umask(0o077)
    if os.geteuid()!=0:raise ValueError('root required')
    body=sys.stdin.buffer.read(1048577)
    if len(body)>1048576:raise ValueError('request too large')
    incoming=json.loads(body);mode=incoming.get('mode')
    if mode not in ['prepare','validate','update','weekly','aggregate','import','rebuild']:raise ValueError('invalid mode')
    with (ROOT/'locks/release.lock').open('a+b') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        root=runtime();docker(root,mode,body)
        if mode=='prepare':return
        receipt=json.loads((STORE/'writer/candidate.json').read_text());candidate=receipt['candidate']
        if not re.fullmatch('/public/candidates/[a-f0-9]{32}',candidate):raise ValueError('invalid candidate path')
        host=SHARED/'public-data'/candidate.removeprefix('/public/')
        reader_gid=pwd.getpwnam('maasagent').pw_gid;writer_uid=pwd.getpwnam('maasdata').pw_uid
        fd=os.open(SHARED,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW)
        try:
            for part in ['public-data','candidates',host.name]:
                child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd);os.close(fd);fd=child
            for _,dirs,files,directory in os.fwalk('.',dir_fd=fd,follow_symlinks=False):
                if os.fstat(directory).st_uid!=writer_uid:raise ValueError('unexpected candidate owner')
                os.fchown(directory,writer_uid,reader_gid);os.fchmod(directory,0o2750)
                for name in dirs:
                    if stat.S_ISLNK(os.stat(name,dir_fd=directory,follow_symlinks=False).st_mode):raise ValueError('candidate directory link refused')
                for name in files:
                    file=os.open(name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=directory)
                    try:
                        info=os.fstat(file)
                        if not stat.S_ISREG(info.st_mode) or info.st_uid!=writer_uid or info.st_nlink!=1:raise ValueError('unexpected candidate file')
                        os.fchown(file,writer_uid,reader_gid);os.fchmod(file,0o640)
                    finally:os.close(file)
        finally:os.close(fd)
        env={**os.environ,'PGHOST':'/var/run/postgresql','PGDATABASE':'maas_data','PGUSER':'maasagent'}
        command(['runuser','-u','maasagent','--','node',str(root/'scripts/verify-runtime-site.mjs'),'--package-root',str(root),'--data-root',str(host)],env=env)
        if mode in ['validate','aggregate']:print('data committed and SSR validation passed; not published');return
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
