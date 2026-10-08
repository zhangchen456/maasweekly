import json,uuid,time
from pathlib import Path
from playwright.sync_api import sync_playwright
out=Path('/Users/zhangchen/Work/maasweekly/docs/operations/admin-release-2026-10-08');base='https://daily.maas.click';rows=json.loads(Path('/private/tmp/maas-admin-synthetic-20261008.json').read_text());report={'environment':'production synthetic accounts; no mail/model/payment','checks':[],'errors':[]}
with sync_playwright() as p:
 b=p.chromium.launch(headless=True);ordinary=b.new_context();admin=b.new_context(viewport={'width':1440,'height':1000});anon=b.new_context()
 for ctx,role in [(ordinary,'ordinary'),(admin,'admin')]:ctx.add_cookies([{'name':'__Host-maas_session','value':next(r['session'] for r in rows if r['role']==role),'url':base,'secure':True,'httpOnly':True,'sameSite':'Lax'}])
 def check(name,condition):
  assert condition,name;report['checks'].append(name)
 routes=['me','overview','users','feedback','weekly','analytics','monitor/sources','monitor/runs','delivery','health','problems','payments/orders']
 for route in routes:
  r=anon.request.get(base+'/api/admin/'+route);check('anonymous '+route,r.status==401 and 'no-store' in r.headers.get('cache-control',''))
  time.sleep(.2)
 for ctx,label in [(ordinary,'Plus'),(admin,'admin')]:
  for route in routes:
   r=ctx.request.get(base+'/api/admin/'+route);check(label+' '+route,r.status==(403 if label=='Plus' else 200));time.sleep(.2)
 check('cross-origin rejected',admin.request.post(base+'/api/admin/problems',headers={'Origin':'https://invalid.example','Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())},data={}).status==403)
 check('standard body limit',admin.request.post(base+'/api/admin/problems',headers={'Origin':base,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())},data={'reason':'x'*17000}).status==413)
 check('revision body limit',admin.request.post(base+'/api/admin/weekly/test/revisions',headers={'Origin':base,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())},data={'reason':'x'*1100000}).status==413)
 user=next(r['userId'] for r in rows if r['role']=='ordinary');url=base+'/api/admin/users/'+user+'/entitlement';body={'operation':'revoke','expectedVersion':0,'reason':'synthetic acceptance revoke'};headers={'Origin':base,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())}
 first=admin.request.post(url,headers=headers,data=body);check('synthetic entitlement write',first.status==200);second=admin.request.post(url,headers=headers,data=body);check('idempotent replay',second.status==200 and first.json()==second.json());check('same key conflict',admin.request.post(url,headers=headers,data={**body,'reason':'different reason'}).status==409);check('stale version conflict',admin.request.post(url,headers={**headers,'Idempotency-Key':str(uuid.uuid4())},data=body).status==409);check('Free denied after revoke',ordinary.request.get(base+'/api/admin/me').status==403)
 def post(path,body):
  return admin.request.post(base+'/api/admin/'+path,headers={'Origin':base,'Content-Type':'application/json','Idempotency-Key':str(uuid.uuid4())},data={**body,'reason':'synthetic production acceptance'})
 task_ids={}
 (out/'synthetic-task-ids.json').write_text('{}')
 r=post('problems',{'title':'acceptance-admin-20261008 synthetic diagnosis','description':'Synthetic production worker check; no real feedback or private materials'});check('create synthetic problem',r.status==200);pid=r.json()['id'];task_ids['problemId']=pid; (out/'synthetic-task-ids.json').write_text(json.dumps(task_ids))
 version=admin.request.get(base+'/api/admin/problems/'+pid).json()['problem']['version']
 r=post('problems/'+pid+'/diagnose',{'expectedVersion':version,'material':{'description':'Synthetic worker input, no user data','redactionConfirmed':True},'budget':0});check('enqueue mock diagnostic',r.status==200)
 rid=r.json()['runId'];done=None
 for _ in range(30):
  detail=admin.request.get(base+'/api/admin/problems/'+pid).json();done=next((r for r in detail['runs'] if r['id']==rid),None)
  if done and done['state']=='succeeded':break
  time.sleep(1)
 check('production diagnostic worker completed mock',done is not None and done['state']=='succeeded')
 check('diagnosis advisory only',done['result']['advisoryOnly'] is True)
 r=post('weekly',{'periodEnd':'1900-01-01','selection':'acceptance-admin-20261008 synthetic zero-evidence worker','budget':0});check('create isolated historical issue',r.status==200 and r.json()['created'] is True);iid=r.json()['id'];task_ids['issueId']=iid; (out/'synthetic-task-ids.json').write_text(json.dumps(task_ids))
 detail=admin.request.get(base+'/api/admin/weekly/'+iid).json();r=post('weekly/'+iid+'/prepare',{'expectedVersion':detail['issue']['version'],'coverage':'failed','coverageNote':'Synthetic empty period, no publication permitted'});check('freeze synthetic zero evidence',r.status==200)
 detail=admin.request.get(base+'/api/admin/weekly/'+iid).json();r=post('weekly/'+iid+'/runs',{'expectedVersion':detail['issue']['version'],'stage':'prepare'});check('enqueue production editorial worker',r.status in [200,202]);rid=r.json()['runId'];done=None
 for _ in range(30):
  done=admin.request.get(base+'/api/admin/runs/'+rid).json()
  if done['state']=='succeeded':break
  time.sleep(1)
 check('production editorial worker completed deterministic stage',done['state']=='succeeded');detail=admin.request.get(base+'/api/admin/weekly/'+iid).json();check('no synthetic publication',detail['publications']==[])
 (out/'synthetic-task-ids.json').write_text(json.dumps(task_ids))
 (out/'http-online.json').write_text(json.dumps(report,ensure_ascii=False,indent=2))
 page=admin.new_page();page.on('pageerror',lambda e:report['errors'].append(str(e)));page.route('**/*',lambda route:route.continue_() if route.request.url.startswith(base+'/') else route.abort())
 for route in ['','weekly/','sources/','tasks/','delivery/','health/','problems/','analytics/']:
  page.goto(base+'/admin/'+route);page.wait_for_function("document.querySelector('#admin-status').textContent.includes('后台权限已确认')");check('browser '+route,page.locator('#admin-private').is_visible());time.sleep(.5)
 page.goto(base+'/admin/');page.wait_for_function("document.querySelector('#admin-status').textContent.includes('后台权限已确认')");page.screenshot(path=str(out/'admin-overview-online.png'),full_page=True);page.set_viewport_size({'width':390,'height':844});check('mobile no overflow',page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'));page.screenshot(path=str(out/'admin-mobile-online.png'),full_page=True)
 check('payment checkout disabled',ordinary.request.post(base+'/api/pro/billing/checkout',headers={'Origin':base,'Content-Type':'application/json'},data={}).status in [404,409,503]);check('no page errors',not report['errors']);b.close()
(out/'browser-online.json').write_text(json.dumps(report,ensure_ascii=False,indent=2));print(json.dumps({'checks':len(report['checks']),'errors':report['errors']}))
