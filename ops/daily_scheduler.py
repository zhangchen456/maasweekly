"""Host trigger using encrypted credentials and the existing locked data publisher."""
import argparse,fcntl,json,os,subprocess,sys,tempfile,time
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
ROOT=Path('/srv/maasweekly');ZONE=ZoneInfo('Asia/Shanghai')
KEYS={'LLM_API_KEY','TRANSLATION_API_KEY','OPENROUTER_API_KEY'}
def local_day(milliseconds):return datetime.fromtimestamp(milliseconds/1000,ZONE).date().isoformat()
def decision(shared,now=None,*,enforce_window=True):
 now=now or datetime.now(ZONE);today=now.date().isoformat()
 pub=json.loads((shared/'public-data/v1/publication.json').read_text())
 daily_path=shared/'pipeline-monitor/daily.json'
 daily=json.loads(daily_path.read_text()) if daily_path.exists() else {}
 if pub.get('dataThrough')==today and daily.get('state')=='succeeded' and local_day(daily['startedAt'])==today:return 'already_published'
 # Never retry a deterministic failure or run over a surviving writer.
 if daily and (daily.get('state')=='running' or local_day(daily['startedAt'])==today):return 'already_attempted'
 if enforce_window and not (5<=now.hour<13):return 'outside_window'
 return 'start'
def atomic(path,body):
 fd,name=tempfile.mkstemp(dir=path.parent)
 try:
  with os.fdopen(fd,'wb') as out:out.write(body);out.flush();os.fsync(out.fileno())
  os.chmod(name,0o600);os.replace(name,path)
 finally:
  if os.path.exists(name):os.unlink(name)
def remember_credentials(shared,secrets):
 directory=shared/'scheduler'
 if not (directory/'enabled').is_file():return
 if directory.is_symlink() or directory.resolve()!=directory:raise ValueError('unsafe scheduler directory')
 if not isinstance(secrets,dict) or set(secrets)-KEYS or any(not isinstance(v,str) or len(v)>16384 or '\0' in v for v in secrets.values()):raise ValueError('invalid scheduler credentials')
 if not secrets.get('LLM_API_KEY') or not secrets.get('TRANSLATION_API_KEY'):raise ValueError('scheduled collection needs digest and translation credentials')
 encrypted=subprocess.run(['systemd-creds','encrypt','--name=maas-daily-input','--with-key=host','-','-'],input=json.dumps(secrets).encode(),capture_output=True,timeout=20)
 if encrypted.returncode:raise RuntimeError('scheduler credential encryption failed')
 atomic(directory/'credentials.enc',encrypted.stdout)
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');args=ap.parse_args()
 shared=ROOT/'shared';directory=shared/'scheduler'
 if not (directory/'enabled').is_file():print(json.dumps({'decision':'disabled'}));return
 outcome=decision(shared)
 if args.check:print(json.dumps({'decision':outcome,'credentialsReady':(directory/'credentials.enc').is_file()}));return
 with (directory/'trigger.lock').open('a+b') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print(json.dumps({'decision':'busy'}));return
  outcome=decision(shared)
  if outcome!='start':print(json.dumps({'decision':outcome}));return
  if not (directory/'credentials.enc').is_file():raise RuntimeError('scheduler credentials not provisioned')
  result=subprocess.run(['systemd-creds','decrypt','--name=maas-daily-input',str(directory/'credentials.enc'),'-'],capture_output=True,timeout=20)
  if result.returncode:raise RuntimeError('scheduler credential decryption failed')
  secrets=json.loads(result.stdout);assert secrets.get('LLM_API_KEY') and secrets.get('TRANSLATION_API_KEY')
  # Publisher rechecks under release.lock, closing the race with delayed GitHub runs.
  request={'mode':'update','secrets':secrets,'runContext':{'GITHUB_EVENT_NAME':'server_schedule'}}
  subprocess.run([sys.executable,'-B','/usr/local/lib/maasweekly/data-update.py'],input=json.dumps(request).encode(),check=True,timeout=5700)
if __name__=='__main__':main()
