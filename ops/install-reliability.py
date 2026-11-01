#!/usr/bin/env python3
"""Install audited root helpers from the active, hash-verified runtime. Does not touch backups."""
import fcntl,hashlib,json,os,shutil,subprocess,tempfile,time
from pathlib import Path
ROOT=Path('/srv/maasweekly')
MAPPING={
 'ops/runtime_workers.py':'/usr/local/lib/maasweekly/runtime_workers.py',
 'ops/runtime_safety.py':'/usr/local/lib/maasweekly/runtime_safety.py',
 'ops/pipeline_monitor.py':'/usr/local/lib/maasweekly/pipeline_monitor.py',
 'ops/runtime-control.py':'/usr/local/lib/maasweekly/runtime-control.py',
 'ops/data-writer/launch.py':'/usr/local/lib/maasweekly/data-update.py',
 'ops/maas-pipeline-monitor.service':'/etc/systemd/system/maas-pipeline-monitor.service',
 'ops/maas-pipeline-monitor.timer':'/etc/systemd/system/maas-pipeline-monitor.timer',
}
def main():
 if os.geteuid()!=0:raise ValueError('root required')
 with (ROOT/'locks/release.lock').open('a+b') as lock:
  fcntl.flock(lock,fcntl.LOCK_EX)
  state=json.loads((ROOT/'shared/runtime.json').read_text());package=ROOT/'runtime'/state['code']
  if (ROOT/'current').resolve()!=package or package.is_symlink():raise ValueError('active runtime mismatch')
  manifest=json.loads((package/'metadata/runtime-manifest.json').read_text())
  if manifest.get('runtimeHealthVersion')!=1:raise ValueError('deploy runtime health capability first')
  entries={x['path']:x for x in manifest['files']};bodies={}
  for source,target in MAPPING.items():
   file=package/'tooling'/source;body=file.read_bytes()
   if file.is_symlink() or hashlib.sha256(body).hexdigest()!=entries['tooling/'+source]['sha256']:raise ValueError('helper hash mismatch')
   bodies[target]=body
  backup=ROOT/'shared/reliability-install'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());backup.mkdir(parents=True,mode=0o700)
  audit=[]
  for target,body in bodies.items():
   target=Path(target)
   if target.is_symlink():raise ValueError('target symlink refused')
   saved=backup/target.name
   if target.exists():shutil.copy2(target,saved)
   audit.append({'target':str(target),'backup':str(saved) if saved.exists() else None,'sha256':hashlib.sha256(body).hexdigest()})
  (backup/'manifest.json').write_text(json.dumps(audit,indent=2)+'\n')
  try:
   for target,body in bodies.items():
    target=Path(target);fd,name=tempfile.mkstemp(dir=target.parent)
    with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    os.chmod(name,0o644);os.replace(name,target)
   subprocess.run(['systemctl','daemon-reload'],check=True)
  except BaseException:
   for item in audit:
    if item['backup']:shutil.copy2(item['backup'],item['target'])
    else:Path(item['target']).unlink(missing_ok=True)
   subprocess.run(['systemctl','daemon-reload'],check=True);raise
  print(json.dumps({'code':state['code'],'backup':str(backup),'installed':audit,'timerStarted':False}))
if __name__=='__main__':main()
