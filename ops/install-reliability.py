#!/usr/bin/env python3
"""Install audited root helpers from the active, hash-verified runtime. Does not touch backups."""
import argparse,fcntl,hashlib,json,os,pwd,re,shutil,subprocess,sys,tempfile,time
from pathlib import Path
ROOT=Path('/srv/maasweekly')
MAPPING={
 'ops/backup_retention.py':'/usr/local/lib/maasweekly/backup_retention.py',
 'ops/daily_scheduler.py':'/usr/local/lib/maasweekly/daily_scheduler.py',
 'ops/cache_retention.py':'/usr/local/lib/maasweekly/cache_retention.py',
 'ops/delivery_checks.py':'/usr/local/lib/maasweekly/delivery_checks.py',
 'ops/reliability_observation.py':'/usr/local/lib/maasweekly/reliability_observation.py',
 'ops/maas-daily-scheduler.service':'/etc/systemd/system/maas-daily-scheduler.service',
 'ops/maas-daily-scheduler.timer':'/etc/systemd/system/maas-daily-scheduler.timer',
 'ops/maas-data-cache-cleanup.service':'/etc/systemd/system/maas-data-cache-cleanup.service',
 'ops/maas-data-cache-cleanup.timer':'/etc/systemd/system/maas-data-cache-cleanup.timer',

 'ops/weekly-editorial.py':'/usr/local/lib/maasweekly/weekly-editorial.py',
 'ops/server/maasweekly-activate':'/usr/local/sbin/maasweekly-activate',
 'ops/server/maasweekly-deploy-shell':'/usr/local/bin/maasweekly-deploy-shell',
 'ops/runtime_workers.py':'/usr/local/lib/maasweekly/runtime_workers.py',
 'ops/maas-editorial-worker.service':'/etc/systemd/system/maas-editorial-worker.service',
 'ops/maas-diagnostic-worker.service':'/etc/systemd/system/maas-diagnostic-worker.service',
 'ops/runtime_safety.py':'/usr/local/lib/maasweekly/runtime_safety.py',
 'ops/pipeline_monitor.py':'/usr/local/lib/maasweekly/pipeline_monitor.py',
 'ops/runtime-control.py':'/usr/local/lib/maasweekly/runtime-control.py',
 'ops/data-writer/launch.py':'/usr/local/lib/maasweekly/data-update.py',
 'ops/maas-pipeline-monitor.service':'/etc/systemd/system/maas-pipeline-monitor.service',
 'ops/maas-pipeline-monitor.timer':'/etc/systemd/system/maas-pipeline-monitor.timer',
 'ops/daily_data_alert.py':'/usr/local/lib/maasweekly/daily_data_alert.py',
 'ops/operations_checks.py':'/usr/local/lib/maasweekly/operations_checks.py',
 'ops/daily_inspection.py':'/usr/local/lib/maasweekly/daily_inspection.py',
 'ops/maas-daily-inspection.service':'/etc/systemd/system/maas-daily-inspection.service',
 'ops/maas-daily-inspection.timer':'/etc/systemd/system/maas-daily-inspection.timer',
 'ops/maas-account-health.service':'/etc/systemd/system/maas-account-health.service',
 'pipeline/config/source_registry.json':'/usr/local/lib/maasweekly/inspection-sources.json',
 'ops/maas-daily-data-alert.service':'/etc/systemd/system/maas-daily-data-alert.service',
 'ops/maas-daily-data-alert.timer':'/etc/systemd/system/maas-daily-data-alert.timer',
}
def prepare_worker_state(root):
 directory=root/'shared/state/worker-runtime'
 if directory.is_symlink():raise ValueError('worker state symlink refused')
 directory.mkdir(mode=0o750,exist_ok=True)
 account=pwd.getpwnam('maasagent');os.chown(directory,account.pw_uid,account.pw_gid);directory.chmod(0o750)

def prepare_alert_state(root):
 directory=root/'shared/state/data-alerts'
 if directory.is_symlink():raise ValueError('alert state symlink refused')
 directory.mkdir(mode=0o700,exist_ok=True)
 account=pwd.getpwnam('maasagent');os.chown(directory,account.pw_uid,account.pw_gid);directory.chmod(0o700)
 # Bootstrap only from a real full-update receipt; do not invent a new observation time.
 current=root/'shared/pipeline-monitor/current.json';daily=current.with_name('daily.json')
 if daily.is_symlink():raise ValueError('daily state symlink refused')
 if not daily.exists() and current.exists():
  if current.is_symlink():raise ValueError('pipeline state symlink refused')
  value=json.loads(current.read_text())
  if value.get('mode')=='update':
   shutil.copy2(current,daily);os.chown(daily,0,account.pw_gid);daily.chmod(0o640)

def alert_environment(root,recipient):
 if not re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',recipient) or any(c in recipient for c in '\r\n\0'):raise ValueError('invalid alert recipient')
 source=root/'shared/agent.env'
 if source.is_symlink():raise ValueError('mail configuration symlink refused')
 values={}
 for line in source.read_text().splitlines():
  if '=' in line and not line.startswith('#'):
   k,v=line.split('=',1)
   if k in ['RESEND_API_KEY','MAAS_MAIL_FROM']:values[k]=v.strip().strip('"').strip("'")
 if not all(values.get(k) for k in ['RESEND_API_KEY','MAAS_MAIL_FROM']):raise ValueError('server mail configuration required')
 values['MAAS_DATA_ALERT_TO']=recipient
 def quote(v):
  if any(c in v for c in '\r\n\0'):raise ValueError('invalid mail configuration')
  return '"'+v.replace('\\','\\\\').replace('"','\\"')+'"'
 return ('\n'.join(k+'='+quote(v) for k,v in values.items())+'\n').encode()

def main(argv=()):
 parser=argparse.ArgumentParser();parser.add_argument('--data-alert-to');parser.add_argument('--enable-daily-scheduler',action='store_true');args=parser.parse_args(argv)
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
  if args.data_alert_to:bodies[str(ROOT/'shared/data-alert.env')]=alert_environment(ROOT,args.data_alert_to)
  backup=ROOT/'shared/reliability-install'/time.strftime('%Y%m%dT%H%M%SZ',time.gmtime());backup.mkdir(parents=True,mode=0o700)
  audit=[]
  for target,body in bodies.items():
   target=Path(target)
   if target.is_symlink():raise ValueError('target symlink refused')
   saved=backup/target.name
   if target.exists():shutil.copy2(target,saved)
   audit.append({'target':str(target),'backup':str(saved) if saved.exists() else None,'sha256':hashlib.sha256(body).hexdigest()})
  (backup/'manifest.json').write_text(json.dumps(audit,indent=2)+'\n')
  if 'ops/daily_scheduler.py' in MAPPING:
   gid=pwd.getpwnam('maasagent').pw_gid
   for name in ['scheduler','cache-retention','backup-retention']:
    directory=ROOT/'shared'/name
    if directory.is_symlink():raise ValueError('unsafe operations directory')
    directory.mkdir(mode=0o750,exist_ok=True);os.chown(directory,0,gid);directory.chmod(0o750)
   if args.enable_daily_scheduler:
    enabled=ROOT/'shared/scheduler/enabled'
    if enabled.is_symlink():raise ValueError('unsafe scheduler enable marker')
    enabled.write_text('Independent daily collection enabled by operator.\n');enabled.chmod(0o644)
  if 'ops/runtime_workers.py' in MAPPING:prepare_worker_state(ROOT)
  if 'ops/daily_data_alert.py' in MAPPING:prepare_alert_state(ROOT)
  try:
   for target,body in bodies.items():
    target=Path(target);fd,name=tempfile.mkstemp(dir=target.parent)
    with os.fdopen(fd,'wb') as stream:stream.write(body);stream.flush();os.fsync(stream.fileno())
    mode=0o600 if target==ROOT/'shared/data-alert.env' else {'/usr/local/sbin/maasweekly-activate':0o750,'/usr/local/bin/maasweekly-deploy-shell':0o755}.get(str(target),0o644)
    os.chmod(name,mode);os.replace(name,target)
   subprocess.run(['systemctl','daemon-reload'],check=True)
  except BaseException:
   for item in audit:
    if item['backup']:shutil.copy2(item['backup'],item['target'])
    else:Path(item['target']).unlink(missing_ok=True)
   subprocess.run(['systemctl','daemon-reload'],check=True);raise
  public_audit=[{**item,'sha256':'redacted'} if item['target']==str(ROOT/'shared/data-alert.env') else item for item in audit]
  print(json.dumps({'code':state['code'],'backup':str(backup),'installed':public_audit,'timerStarted':False,'dataAlertsConfigured':bool(args.data_alert_to)}))
if __name__=='__main__':main(sys.argv[1:])
