"""Only reclaim old candidate copies verified against immutable canonical releases."""
import argparse,fcntl,hashlib,json,os,pwd,re,shutil,stat,time
from pathlib import Path
from pipeline_monitor import write_json
from runtime_safety import measure_capacity
ROOT=Path('/srv/maasweekly')
def digest(p):
 if p.is_symlink() or not stat.S_ISREG(p.lstat().st_mode):raise ValueError('non-regular file')
 with p.open('rb') as f:
  h=hashlib.sha256()
  while block:=f.read(1024*1024):h.update(block)
 return h.hexdigest()
def fingerprint(p):return {str(x.relative_to(p)):(x.lstat().st_ino,x.lstat().st_size,x.lstat().st_mtime_ns,x.lstat().st_mode) for x in [p,*p.rglob('*')]}
def plan(root,now=None):
 now=now or time.time();shared=root/'shared';base=shared/'public-data/candidates';canonical=shared/'public-data/v1'
 for p in [root,shared,base,canonical]:
  if p.resolve()!=p or not p.is_dir():raise ValueError('unsafe cache root')
 pub=json.loads((canonical/'publication.json').read_text());receipt=json.loads((shared/'data-store/writer/candidate.json').read_text())
 if not re.fullmatch('/public/candidates/[a-f0-9]{32}',receipt['candidate']):raise ValueError('invalid writer receipt')
 protected={pub['datasetVersion'],*[x['datasetVersion'] for x in pub.get('retainedVersions',[])]}
 candidates=sorted([x for x in base.iterdir() if x.is_dir() and not x.is_symlink() and re.fullmatch('[a-f0-9]{32}',x.name)],key=lambda p:p.stat().st_mtime,reverse=True)
 keep={x.name for x in candidates[:3]}|{Path(receipt['candidate']).name};rows=[];skipped=[]
 for p in candidates:
  if p.name in keep or now-p.stat().st_mtime<86400:continue
  try:
   before=fingerprint(p);m=json.loads((p/'publication.json').read_text());ds=m['datasetVersion']
   if ds in protected:continue
   if not re.fullmatch('ds_[a-f0-9]{64}',ds):raise ValueError('invalid dataset')
   expected={'publication.json','manifest.json','releases/'+ds+'/manifest.json'};total=0
   if not 1<=len(m['files'])<=20:raise ValueError('invalid inventory')
   for e in m['files']:
    name=e['path']
    if not re.fullmatch('releases/'+ds+r'/[a-z-]+\.json',name):raise ValueError('unsafe file')
    expected.add(name);src=p/name;dst=canonical/name
    if src.resolve()!=src or dst.resolve()!=dst:raise ValueError('symlink')
    if src.stat().st_size!=e['bytes'] or dst.stat().st_size!=e['bytes'] or digest(src)!=e['sha256'] or digest(dst)!=e['sha256']:raise ValueError('not an exact canonical copy')
    total+=e['bytes']
   if any(x.is_symlink() for x in p.rglob('*')) or {str(x.relative_to(p)) for x in p.rglob('*') if x.is_file()}!=expected:raise ValueError('unexpected tree')
   if fingerprint(p)!=before:raise ValueError('candidate changed')
   rows.append({'name':p.name,'bytes':total,'metadata':{n:json.loads((p/n).read_text()) for n in expected if n.endswith('manifest.json') or n=='publication.json'},'fingerprint':before})
  except (OSError,ValueError,KeyError,TypeError):skipped.append(p.name)
 return {'checkedAt':now,'protectedVersions':sorted(protected),'keep':sorted(keep),'skipped':skipped,'copies':rows}
def apply(root,plan):
 if not shutil.rmtree.avoids_symlink_attacks:raise ValueError('safe deletion unavailable')
 base=root/'shared/public-data/candidates'
 # Refuse any change across verification before mutating any candidate.
 for r in plan['copies']:
  if fingerprint(base/r['name'])!=r['fingerprint']:raise ValueError('candidate changed after verification')
 for r in plan['copies']:shutil.rmtree(base/r['name'])
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--apply',action='store_true');args=ap.parse_args()
 with (ROOT/'locks/release.lock').open('a+b') as lock:
  try:fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
  except BlockingIOError:print(json.dumps({'status':'deferred'}));return
  value=plan(ROOT);summary={k:v for k,v in value.items() if k!='copies'};summary.update(count=len(value['copies']),bytes=sum(r['bytes'] for r in value['copies']),mode='apply' if args.apply else 'plan')
  if args.apply:
   directory=ROOT/'shared/cache-retention';gid=pwd.getpwnam('maasagent').pw_gid
   audit=directory/('audit-'+str(time.time_ns())+'.json');write_json(audit,value,gid)
   apply(ROOT,value);summary['status']='completed';write_json(directory/'current.json',summary,gid)
   capacity=measure_capacity(ROOT,'update');capacity['checkedAt']=time.time();write_json(directory/'capacity.json',capacity,gid)
  print(json.dumps(summary))
if __name__=='__main__':main()
