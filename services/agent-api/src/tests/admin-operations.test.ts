import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import http from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {AccountStore,AccountError} from '../account-store.js';
import {AdminStore,type AdminCommand} from '../admin-store.js';
import {AdminUsers} from '../admin-users.js';
import {AdminFeedback} from '../admin-feedback.js';
import {FeedbackStore} from '../feedback-store.js';
import {ProStore} from '../pro-store.js';
import {createAdminHandler} from '../admin-http.js';
import type {DatasetHolder} from '../dataset.js';
const secret='admin-operations-isolated-secret-32-characters';
const login=(a:AccountStore,email:string)=>a.verify(email,a.issueCode(email));
function fixture(){let time=1780000000000;const a=new AccountStore(':memory:',()=>time++,secret),admin=new AdminStore(a),users=new AdminUsers(admin),feedback=new AdminFeedback(admin);const u=login(a,'user@example.test');return {a,admin,users,feedback,u};}
function command(targetId:string,input:Record<string,unknown>,version:()=>number,action='users.entitlement',expected=version()):AdminCommand{return {actor:{type:'cli',id:'test-operator'},action,targetType:action.startsWith('users')?'user':'feedback',targetId,reason:'isolated regression',requestId:randomUUID(),idempotencyKey:randomUUID(),input,expectedVersion:expected,currentVersion:version};}
function userWrite(f:ReturnType<typeof fixture>,input:Record<string,unknown>,op='entitlement'){return f.users.write(command(f.u.user.id,input,()=>f.users.version(f.u.user.id),'users.'+op),op);}
function feedbackWrite(f:ReturnType<typeof fixture>,id:string,input:Record<string,unknown>,op='update'){return f.feedback.write(command(id,input,()=>f.feedback.version(id),'feedback.'+op),op);}
function submit(f:ReturnType<typeof fixture>){return f.feedback.feedback.submit(f.u.user.id,{title:'Real isolated feedback',description:'A reproducible issue requiring verification and publication.',page:'/account/'}).id;}
test('effective entitlement matrix uses original evaluator and filters before pagination',()=>{
 const f=fixture();try{const id=f.u.user.id,p=f.users.pro;assert.deepEqual(f.users.detail(id).effectiveEntitlement,p.entitlement(id));p.activateBeta(id);assert.equal(userWrite(f,{operation:'grant',starts:'2026-01-01T00:00:00Z',ends:'2027-01-01T00:00:00Z'}).source,'beta');
 assert.equal(userWrite(f,{operation:'revoke'}).status,'revoked');assert.ok(f.a.db.prepare('SELECT * FROM pro_beta_access WHERE userId=?').get(id));assert.equal(userWrite(f,{operation:'grant',starts:'2026-01-01T00:00:00Z',ends:'2027-01-01T00:00:00Z'}).source,'beta');
 process.env.PRO_BETA_ENABLED='false';assert.equal(f.users.detail(id).effectiveEntitlement.source,'manual');assert.deepEqual(f.users.detail(id).effectiveEntitlement,p.entitlement(id));userWrite(f,{operation:'grant',starts:'2020-01-01T00:00:00Z',ends:'2021-01-01T00:00:00Z'});assert.equal(p.entitlement(id).status,'expired');
 f.a.transaction(()=>{for(let i=0;i<3000;i++){const n='bulk-'+String(i).padStart(5,'0');f.a.db.prepare('INSERT INTO users SELECT ?,?,organizationId,\'free\',0,0,? FROM users LIMIT 1').run(n,n+'@example.test',n);if(i%2===0)f.a.db.prepare('INSERT INTO pro_entitlements VALUES(?,?,?,0)').run(n,0,1900000000000);}});
 let cursor:string|null=null;const seen=new Set<string>();do{const params=new URLSearchParams({entitlementStatus:'active',source:'manual',limit:'100'});if(cursor)params.set('cursor',cursor);const page=f.users.list(params);assert.ok(page.items.length<=100);for(const row of page.items){assert.equal(row.effectiveEntitlement.status,'active');assert.ok(!seen.has(row.id));seen.add(row.id);}cursor=page.nextCursor;}while(cursor);assert.equal(seen.size,1500);
 const page=f.users.list(new URLSearchParams({limit:'1'}));assert.throws(()=>f.users.list(new URLSearchParams({q:'different',cursor:page.nextCursor!})));assert.throws(()=>f.users.list(new URLSearchParams('q=a&q=b')));
 }finally{delete process.env.PRO_BETA_ENABLED;f.a.close();}
});
test('no-manual revoke creates marker, cancels pending mail; admin transaction rolls back all side effects',()=>{
 const f=fixture();try{const id=f.u.user.id;f.users.pro.activateBeta(id);f.a.db.prepare("INSERT INTO pro_reports VALUES('r',?,'period','{}','[]','normal',0)").run(id);f.a.db.prepare("INSERT INTO pro_mail VALUES('m',?,'r',0,'pending',0,NULL)").run(id);
 const cmd=command(id,{operation:'revoke'},()=>f.users.version(id));f.a.db.exec("CREATE TRIGGER audit_failure BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'injected'); END");assert.throws(()=>f.users.write(cmd,'entitlement'));assert.equal(f.users.pro.entitlement(id).status,'active');assert.equal(f.a.db.prepare('SELECT status FROM pro_mail').get()!.status,'pending');assert.equal(f.users.version(id),0);assert.equal(f.a.db.prepare('SELECT count(*) AS n FROM pro_entitlements').get()!.n,0);f.a.db.exec('DROP TRIGGER audit_failure');
 const first=f.users.write(cmd,'entitlement');assert.equal(first.status,'revoked');assert.deepEqual(f.users.write(cmd,'entitlement'),first);assert.equal(f.users.version(id),1);assert.equal(f.a.db.prepare('SELECT status FROM pro_mail').get()!.status,'cancelled');assert.equal(f.a.db.prepare('SELECT count(*) AS n FROM admin_audit').get()!.n,1);assert.throws(()=>f.users.write({...cmd,idempotencyKey:'different'},'entitlement'),(e:unknown)=>e instanceof AccountError&&e.status===409);
 const dto=JSON.stringify(f.users.detail(id));assert.ok(!/hash|encrypted|unsubscribeToken/.test(dto));userWrite(f,{},'revoke-sessions');assert.ok(!f.a.user(f.u.session));
 }finally{f.a.close();}
});
test('feedback gates code release + online verification, keeps notes private, reopens with audit, rejects cycles',()=>{
 const f=fixture();try{const id=submit(f),other=submit(f);feedbackWrite(f,id,{body:'PRIVATE INTERNAL BODY'},'notes');assert.ok(!JSON.stringify(f.feedback.feedback.list(f.u.user.id)).includes('PRIVATE INTERNAL BODY'));assert.ok(!JSON.stringify(f.feedback.feedback.detail(id)).includes('PRIVATE INTERNAL BODY'));
 assert.throws(()=>feedbackWrite(f,id,{stage:'resolved',resolutionType:'code',publicReply:'Fixed'}));assert.throws(()=>feedbackWrite(f,id,{kind:'code',artifactRef:'commit:abc',result:'passed',note:'checked'},'verify'));
 assert.throws(()=>feedbackWrite(f,id,{kind:'code',artifactRef:'javascript:alert(1)',releaseRef:'rl-test',environment:'online',result:'passed',note:'checked'},'verify'));
 feedbackWrite(f,id,{kind:'code',artifactRef:'https://example.test/commit/abc',releaseRef:'rl-test',environment:'online',result:'passed',note:'Verified deployed behavior'},'verify');feedbackWrite(f,id,{stage:'resolved',resolutionType:'code',publicReply:'公开修复说明'});assert.equal(f.feedback.feedback.list(f.u.user.id).find(r=>r.id===id)!.reply,'公开修复说明');assert.equal(f.feedback.ops(id).stage,'resolved');
 feedbackWrite(f,id,{stage:'investigating'});assert.throws(()=>feedbackWrite(f,id,{stage:'resolved'}));feedbackWrite(f,id,{kind:'other',artifactRef:'duplicate case',result:'passed',note:'Same behavior checked'},'verify');feedbackWrite(f,id,{stage:'resolved',resolutionType:'other',relatedFeedbackId:other});assert.throws(()=>feedbackWrite(f,other,{resolutionType:'other',relatedFeedbackId:id}));assert.throws(()=>feedbackWrite(f,other,{resolutionType:'other',relatedFeedbackId:other}));
 const history=f.admin.audit(new URLSearchParams({targetType:'feedback',targetId:id}));assert.ok(history.items.some((r:any)=>r.before?.stage==='resolved'&&r.after?.stage==='investigating'));assert.ok(!JSON.stringify(history).includes('PRIVATE INTERNAL BODY'));
 const version=f.feedback.version(other);f.a.db.exec("CREATE TRIGGER audit_failure BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'injected'); END");assert.throws(()=>feedbackWrite(f,other,{body:'rolled back'},'notes'));assert.equal(f.feedback.version(other),version);assert.equal(f.feedback.detail(other).notes.items.length,0);
 }finally{f.a.close();}
});
test('migration retains legacy resolved without fictional verification, retries failure and preserves old data',()=>{
 const a=new AccountStore(':memory:',Date.now,secret),u=login(a,'legacy@example.test'),fs=new FeedbackStore(a);const id=fs.submit(u.user.id,{title:'Legacy issue title',description:'Previously resolved feedback with original public explanation.'}).id;fs.update(id,'resolved','old reply');const snapshot=fs.detail(id);const s=new AdminStore(a);
 try{a.db.exec('CREATE TABLE feedback_notes(id TEXT)');assert.throws(()=>new AdminFeedback(s));assert.equal(a.db.prepare("SELECT 1 FROM sqlite_master WHERE name='admin_user_versions'").get(),undefined);assert.equal(a.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=2').get(),undefined);a.db.exec('DROP TABLE feedback_notes');const f=new AdminFeedback(s);new AdminFeedback(s);assert.deepEqual(fs.detail(id),snapshot);assert.equal(f.ops(id).resolutionType,'legacy');assert.equal(f.detail(id).verifications.items.length,0);}finally{a.close();}
});
test('two connections and CLI actor share versions rather than silently overwrite',()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'t02-connections-')),file=path.join(dir,'accounts.sqlite'),a=new AccountStore(file,Date.now,secret),b=new AccountStore(file,Date.now,secret);
 try{const first=new AdminUsers(new AdminStore(a)),second=new AdminUsers(new AdminStore(b)),u=login(a,'parallel@example.test');const c=command(u.user.id,{operation:'revoke'},()=>first.version(u.user.id));first.write(c,'entitlement');assert.throws(()=>second.write({...c,idempotencyKey:'cli-new',currentVersion:()=>second.version(u.user.id)},'entitlement'),(e:unknown)=>e instanceof AccountError&&e.status===409);assert.equal(second.version(u.user.id),1);}finally{a.close();b.close();rmSync(dir,{recursive:true,force:true});}
});
test('HTTP private screenshot, ownership, version/idempotency, strict body and credential revocation',async()=>{
 const f=fixture(),admin=login(f.a,'admin@example.test'),stranger=login(f.a,'stranger@example.test');f.admin.setMember(admin.user.id,true,'setup','test');
 const bytes=Buffer.alloc(45);Buffer.from('89504e470d0a1a0a','hex').copy(bytes);bytes.write('IHDR',12);bytes.write('IEND',37);const id=f.feedback.feedback.submit(f.u.user.id,{title:'Private screenshot fixture',description:'Reproducible example with attached private screenshot.',images:[{mime:'image/png',data:bytes.toString('base64')}]}).id;
 const server=http.createServer(createAdminHandler(f.admin,{current:null} as unknown as DatasetHolder,{origin:'http://localhost',secure:false}));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${(server.address() as import('node:net').AddressInfo).port}`;
 const get=(route:string,session=admin.session)=>fetch(base+'/api/admin/'+route,{headers:{Cookie:'maas_session='+session}});const post=(route:string,input:Record<string,unknown>,key='key')=>fetch(base+'/api/admin/'+route,{method:'POST',headers:{Cookie:'maas_session='+admin.session,Origin:'http://localhost','Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(input)});
 try{let response=await get(`feedback/${id}/images/0`);assert.equal(response.status,200);assert.equal(response.headers.get('cache-control'),'no-store');assert.ok(response.headers.get('content-security-policy')!.includes('sandbox'));assert.equal((await get(`feedback/${id}/images/0`,f.u.session)).status,403);assert.equal((await get(`feedback/${id}/images/0`,stranger.session)).status,403);assert.equal(f.feedback.feedback.screenshot(id,0,stranger.user.id),undefined);assert.ok(f.feedback.feedback.screenshot(id,0,f.u.user.id));assert.equal((await get(`feedback/${id}/images/3`)).status,404);
 const input={body:'private',reason:'triage',expectedVersion:0};assert.equal((await post(`feedback/${id}/notes`,input)).status,200);assert.equal((await post(`feedback/${id}/notes`,input)).status,200);assert.equal((await post(`feedback/${id}/notes`,input,'another')).status,409);assert.equal((await post(`feedback/${id}/notes`,{...input,actorId:'fake'},'fake')).status,400);assert.equal((await get('users/missing')).status,404);
 f.users.pro.activateBeta(f.u.user.id);const credential=f.users.pro.mint(f.u.user.id,'test','api');assert.equal((await post(`users/${f.u.user.id}/tokens/${credential.id}/revoke`,{reason:'disable credential',expectedVersion:0},'credential')).status,200);assert.equal(f.a.db.prepare('SELECT revoked FROM pro_tokens WHERE id=?').get(credential.id)!.revoked,1);assert.throws(()=>f.users.pro.authenticate(credential.token,'api'));
 }finally{await new Promise<void>(r=>server.close(()=>r()));f.a.close();}
});

test('real compatibility CLIs require versions, share audit, gate resolution and keep private export',()=>{
 const dir=mkdtempSync(path.join(tmpdir(),'t02-cli-')),file=path.join(dir,'accounts.sqlite'),a=new AccountStore(file,Date.now,secret);
 try{const u=login(a,'cli@example.test'),s=new AdminStore(a),users=new AdminUsers(s),feedback=new AdminFeedback(s),id=feedback.feedback.submit(u.user.id,{title:'CLI regression issue',description:'Existing status command must use the same versioned application service.'}).id;
 const run=(name:string,args:string[])=>spawnSync(process.execPath,[fileURLToPath(new URL('../'+name+'.js',import.meta.url)),...args],{env:{...process.env,MAAS_ACCOUNT_DB:file,MAAS_ACCOUNT_SECRET:secret},encoding:'utf8'});
 assert.equal(run('pro-cli',['grant','cli@example.test','2026-01-01T00:00:00Z','2027-01-01T00:00:00Z','operator','reason']).status,1);
 assert.equal(run('pro-cli',['grant','cli@example.test','2026-01-01T00:00:00Z','2027-01-01T00:00:00Z','operator','reason','--expected-version','0','--key','grant-key']).status,0);assert.equal(users.version(u.user.id),1);
 const flags=['--actor','cli-operator','--reason','processing','--expected-version','0'];assert.equal(run('feedback-cli',['status',id,'investigating','public explanation',...flags,'--key','status-key']).status,0);assert.equal(feedback.version(id),1);
 assert.equal(run('feedback-cli',['status',id,'open','stale explanation',...flags,'--key','stale-key']).status,1);assert.equal(feedback.feedback.detail(id)!.reply,'public explanation');
 assert.equal(run('feedback-cli',['status',id,'resolved','resolved explanation','--actor','cli-operator','--reason','resolve','--expected-version','1','--resolution-type','code']).status,1);
 const material={kind:'code',artifactRef:'commit-cli',releaseRef:'rl-cli',result:'passed',environment:'online',note:'Isolated verification fixture'};assert.equal(run('feedback-cli',['verify',id,JSON.stringify(material),'--actor','cli-operator','--reason','verify','--expected-version','1']).status,0);
 assert.equal(run('feedback-cli',['status',id,'resolved','resolved explanation','--actor','cli-operator','--reason','resolve','--expected-version','2','--resolution-type','code']).status,0);
 assert.ok(Array.isArray(JSON.parse(run('feedback-cli',['list']).stdout)));assert.ok(s.audit(new URLSearchParams()).items.some((r:any)=>r.actorType==='cli'&&r.action==='feedback.update'));
 const c=command(id,{body:'PRIVATE EXPORT EXCLUSION'},()=>feedback.version(id),'feedback.notes');feedback.write(c,'notes');assert.equal(run('feedback-cli',['export',id,path.join(dir,'export')]).status,0);
 const exportResult=run('feedback-cli',['detail',id]);assert.ok(exportResult.stdout.includes('PRIVATE EXPORT EXCLUSION'));
 }finally{a.close();rmSync(dir,{recursive:true,force:true});}
});
test('thousands of feedback rows page completely; latest failed verification blocks resolve at same millisecond',()=>{
 const a=new AccountStore(':memory:',()=>1780000000000,secret),admin=new AdminStore(a),users=new AdminUsers(admin),feedback=new AdminFeedback(admin),u=login(a,'scale@example.test');
 try{a.transaction(()=>{for(let i=0;i<3000;i++){const id='feedback-'+String(i).padStart(5,'0');a.db.prepare("INSERT INTO feedback VALUES(?,?,?,'description','','open','',?,?)").run(id,u.user.id,'title',i,i);}});
 let cursor:string|null=null,count=0;const seen=new Set<string>();do{const params=new URLSearchParams({limit:'100'});if(cursor)params.set('cursor',cursor);const p=feedback.list(params);for(const r of p.items){assert.equal(r.stage,'triage');assert.ok(!seen.has(r.id));seen.add(r.id);}count+=p.items.length;cursor=p.nextCursor;}while(cursor);assert.equal(count,3000);
 const id='feedback-00000',write=(input:Record<string,unknown>,op='update')=>feedback.write(command(id,input,()=>feedback.version(id),'feedback.'+op),op);
 const material={kind:'code',artifactRef:'fix',releaseRef:'release',environment:'online',result:'passed',note:'online fixture'};write(material,'verify');write({...material,result:'failed'},'verify');assert.throws(()=>write({stage:'resolved',resolutionType:'code',publicReply:'reply'}));write(material,'verify');write({stage:'resolved',resolutionType:'code',publicReply:'reply'});write({stage:'investigating'});assert.throws(()=>write({stage:'resolved'}));write(material,'verify');write({stage:'resolved'});
 const before=feedback.feedback.detail(id);a.db.exec("CREATE TRIGGER audit_failure BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'injected'); END");assert.throws(()=>write({stage:'triage',publicReply:'should rollback'}));assert.deepEqual(feedback.feedback.detail(id),before);
 }finally{a.close();}
});
