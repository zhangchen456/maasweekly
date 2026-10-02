#!/usr/bin/env python3
"""Read-only bounded candidate HTTP probe; never persist cursor or secret values."""
import concurrent.futures,json,time,urllib.request,urllib.error,urllib.parse,subprocess,sys,os,signal,base64,hmac,hashlib,shlex
from pathlib import Path
base,rid,expected,unit,root=sys.argv[1:]
report={'releaseId':rid,'expectedDatasetVersion':expected,'scope':'Non-public loopback transient service; existing production pointer unchanged'}
def call(path,client='203.0.113.90',body=None):
 headers={'X-Maas-Client-IP':client}
 if body is not None:headers.update({'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
 req=urllib.request.Request(base+path,data=json.dumps(body).encode() if body is not None else None,headers=headers)
 start=time.perf_counter()
 try:
  with urllib.request.urlopen(req,timeout=20) as r:status=r.status;raw=r.read();hdr=dict(r.headers)
 except urllib.error.HTTPError as e:status=e.code;raw=e.read();hdr=dict(e.headers)
 return status,json.loads(raw),hdr,(time.perf_counter()-start)*1000
for _ in range(100):
 try:
  status,data,_,_=call('/api/v1/status')
  if status==200:break
 except (OSError,ValueError):pass
 time.sleep(.1)
else:raise RuntimeError('candidate not ready')
assert data['datasetVersion']==expected
report['rest']={}
for route in ('status','changes?limit=1','prices?limit=1','models'):
 status,data,_,_=call('/api/v1/'+route);assert status==200 and data['datasetVersion']==expected
 report['rest'][route]=status
status,first,_,_=call('/api/v1/prices?limit=1');cursor=first['page']['nextCursor'];assert cursor
# First real existing cursor from the prior production process is passed in a 0600 local file.
prior=Path(root).parent/(rid+'.prior-cursor.json')
if prior.exists():
 saved=json.loads(prior.read_text());status,data,_,_=call('/api/v1/prices?'+urllib.parse.urlencode({'cursor':saved['cursor']}))
 assert status==200 and data['datasetVersion']==saved['datasetVersion'];report['priorProductionCursorContinues']=True
# Historical version probe is explicitly internally signed, not an old user cursor.
manifest=json.loads((Path(root)/'data/public/v1/manifest.json').read_text())
old=next(x['datasetVersion'] for x in manifest['retainedVersions'] if x['datasetVersion']!=expected)
secret=None
for line in Path('/srv/maasweekly/shared/agent.env').read_text().splitlines():
 if line.startswith('CURSOR_SECRET='):secret=shlex.split(line.split('=',1)[1])[0]
assert secret
payload=json.loads(base64.urlsafe_b64decode(cursor+'='*(-len(cursor)%4)));payload.pop('mac',None);payload['ds']=old
canonical=lambda value:json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False)
payload['mac']=base64.urlsafe_b64encode(hmac.new(secret.encode(),canonical(payload).encode(),hashlib.sha256).digest()).decode().rstrip('=')
synthetic=base64.urlsafe_b64encode(canonical(payload).encode()).decode().rstrip('=')
status,data,_,elapsed=call('/api/v1/prices?'+urllib.parse.urlencode({'cursor':synthetic}))
assert status==200 and data['datasetVersion']==old
report['historicalCursor']={'version':old,'status':status,'elapsedMs':elapsed,'scope':'internally signed contract fixture'}
# Force verification while holding a historical dataset; request stays on the current version.
pid=int(subprocess.check_output(['systemctl','show',unit,'--property=MainPID','--value'],text=True).strip());assert pid>0
os.kill(pid,signal.SIGHUP)
latencies=[]
def workload(worker):
 values=[]
 for n in range(6):
  status,data,_,elapsed=call('/api/v1/'+('prices?q=nonmatchingcapacityquery&limit=100' if n%2 else 'changes?limit=100'),f'203.0.113.{20+worker}')
  assert status==200 and data['datasetVersion']==expected;values.append(elapsed)
 return values
with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
 for values in pool.map(workload,range(10)):latencies.extend(values)
assert sorted(latencies)[int(len(latencies)*.95)-1]<=200, 'candidate P95 exceeds local comparison threshold'
report['traffic']={'concurrency':10,'requests':len(latencies),'p95Ms':sorted(latencies)[int(len(latencies)*.95)-1],'maxMs':max(latencies),'allSuccessful':True}
time.sleep(2)
status,data,_,_=call('/api/v1/prices?'+urllib.parse.urlencode({'cursor':cursor}));assert status==200 and data['datasetVersion']==expected;report['cursorAfterReload']=True
rate=[]
for _ in range(90):
 status,data,hdr,_=call('/api/v1/prices?limit=1','203.0.113.201');rate.append(status)
 if status==429:break
assert rate[-1]==429 and 'Retry-After' in hdr
status,data,_,_=call('/api/v1/prices?limit=1','203.0.113.202');assert status==200
report['limiter']={'clientALimited':True,'clientBStatus':status,'attempts':len(rate)}
status,data,_,_=call('/api/mcp','203.0.113.201',{'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'maas_get_prices','arguments':{'limit':1}}})
assert status==200 and not data['result'].get('isError') and data['result']['structuredContent']['datasetVersion']==expected
report['mcp']={'status':status,'independentOfRestQuota':True,'datasetVersion':expected}
fields=subprocess.check_output(['systemctl','show',unit,'--property=ActiveState,MemoryCurrent,MemoryPeak,MemoryMax'],text=True).splitlines()
report['service']=dict(x.split('=',1) for x in fields)
assert report['service']['ActiveState']=='active'
report['publicPointer']=subprocess.check_output(['readlink','/srv/maasweekly/current'],text=True).strip()
report['availableKiB']=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
print(json.dumps(report,indent=2))
