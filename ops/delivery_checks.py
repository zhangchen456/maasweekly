"""Read-only actual runtime delivery check; only aggregate results leave the process."""
import json,os,subprocess,time
from pathlib import Path
from datetime import date,datetime
from zoneinfo import ZoneInfo
def check(shared):
 root=shared.parent;package=(root/'current').resolve();publication=shared/'public-data/v1/publication.json'
 try:
  before=publication.read_bytes();pub=json.loads(before)
  env={'PATH':os.environ.get('PATH','/usr/bin:/bin'),'PGHOST':'/var/run/postgresql','PGDATABASE':'maas_data','PGUSER':'maasagent'}
  run=subprocess.run(['node',str(package/'scripts/verify-runtime-site.mjs'),'--package-root',str(package),'--data-root',str(publication.parent)],env=env,capture_output=True,text=True,timeout=240)
  if run.returncode:raise ValueError('delivery gate failed')
  result=json.loads(run.stdout.strip().splitlines()[-1]);latest=pub['coverage']['weekly']['latestId']
  if publication.read_bytes()!=before or result['datasetVersion']!=pub['datasetVersion']:raise ValueError('publication changed during check')
  age=(datetime.now(ZoneInfo('Asia/Shanghai')).date()-date.fromisoformat(latest)).days
  return {'status':'passed' if 0<=age<=10 else 'failed','checkedAt':time.time(),'datasetVersion':pub['datasetVersion'],'latestWeekly':latest,'weeklyAgeDays':age,'pages':result['pages']}
 except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError):return {'status':'failed','checkedAt':time.time(),'reason':'runtime_delivery_unverified'}
