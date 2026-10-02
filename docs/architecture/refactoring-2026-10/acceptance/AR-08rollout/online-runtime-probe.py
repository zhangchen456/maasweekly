import json,urllib.request,urllib.error,urllib.parse,concurrent.futures,subprocess,ssl,time
from pathlib import Path
DS='ds_0da7f0c0f2bcd5df62281a262539b65a1742e3fbd710a14724359b58675c1b13'
RID='rl_8ebc6b9e4e_0da7f0c0f2bc'
def call(base,path,client=None,body=None,ctx=None):
 h={'Cache-Control':'no-cache'}
 if client:h['X-Maas-Client-IP']=client
 if body is not None:h.update({'Content-Type':'application/json','Accept':'application/json, text/event-stream'})
 req=urllib.request.Request(base+path,headers=h,data=json.dumps(body).encode() if body is not None else None)
 try:
  with urllib.request.urlopen(req,timeout=25,context=ctx) as r:return r.status,json.loads(r.read()),dict(r.headers)
 except urllib.error.HTTPError as e:return e.code,json.loads(e.read()),dict(e.headers)
report={'releaseId':RID,'datasetVersion':DS}
base='http://127.0.0.1:8789'
code,data,h=call(base,'/api/v1/status');assert code==200 and data['datasetVersion']==DS
rate=[]
for _ in range(70):
 code,data,h=call(base,'/api/v1/prices?limit=1','203.0.113.211');rate.append(code)
 if code==429:break
assert code==429 and h.get('Retry-After') and data['status']==429
code,b,h=call(base,'/api/v1/prices?limit=1','203.0.113.212');assert code==200
body={'jsonrpc':'2.0','id':1,'method':'tools/call','params':{'name':'maas_get_prices','arguments':{'limit':1}}}
code,m,h=call(base,'/api/mcp','203.0.113.211',body);assert code==200 and m['result']['structuredContent']['datasetVersion']==DS
report['apiQuota']={'clientALimited':True,'attempts':len(rate),'clientBStatus':200,'mcpIndependentStatus':200,'scope':'controlled distinct proxy identities on trusted loopback'}
ctx=ssl._create_unverified_context() # only local127.0.0.1 TLS; CI/public verification independently validates origin TLS
code,data,h=call('https://127.0.0.1','/api/v1/prices?limit=1','203.0.113.211',ctx=ctx)
assert code==200 and data['datasetVersion']==DS
report['nginxOverwritesSpoofedClientHeader']=True
def one(_):return call('https://127.0.0.1','/api/v1/prices?limit=1',ctx=ctx)
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool: responses=list(pool.map(one,range(30)))
errors=[x for x in responses if x[0]==429];assert errors
for code,data,h in errors:
 assert data['status']==429 and data['code']=='rate_limited' and data['detail']=='Proxy request quota exceeded'
 assert h.get('Retry-After')=='2' and h.get('Access-Control-Allow-Origin')=='*' and 'application/problem+json' in h.get('Content-Type','')
report['nginxQuota']={'requests':30,'responses429':len(errors),'problemJson':True,'retryAfter':True,'cors':True,'scope':'bounded local source burst; no public visitor quota touched'}
report['status']=subprocess.check_output(['/usr/local/sbin/maasweekly-activate','status'],text=True)
assert 'current:  '+RID in report['status'] and 'previous: rl_6efd666e1f_0da7f0c0f2bc' in report['status']
report['units']=subprocess.check_output(['systemctl','show','maas-agent@blue','maas-agent@green','--property=Id,ActiveState,MemoryCurrent,MemoryPeak,MemoryMax'],text=True)
report['availableKiB']=int(next(x.split()[1] for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')))
raw=subprocess.check_output(['journalctl','-u','maas-agent@green','--since','2026-10-02 04:26:59 UTC','-o','cat','--no-pager'],text=True)
events=[]
for line in raw.splitlines():
 try:e=json.loads(line)
 except ValueError:continue
 if isinstance(e,dict) and str(e.get('kind','')).startswith('api.'):events.append(e)
report['diagnostics']={'events':len(events),'kinds':sorted({e['kind'] for e in events}),'lastMetric':next((e for e in reversed(events) if e['kind']=='api.metrics'),None),'unexpectedPrivateFields':any(set(e)&{'url','query','ip','body','cursor','secret'} for e in events)}
assert events and not report['diagnostics']['unexpectedPrivateFields']
f=Path('/srv/maasweekly/shared/state/release-diagnostics.jsonl')
report['releaseDiagnostic']=json.loads(f.read_text().splitlines()[-1]);assert report['releaseDiagnostic']['releaseId']==RID and report['releaseDiagnostic']['outcome']=='success'
report['diagnosticBytes']=f.stat().st_size
print(json.dumps(report,indent=2))
