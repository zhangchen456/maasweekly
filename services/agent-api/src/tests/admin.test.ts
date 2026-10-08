import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { AccountStore, AccountError } from '../account-store.js';
import { authenticateAdmin } from '../admin-auth.js';
import { AdminStore, type AdminCommand } from '../admin-store.js';
import { createAdminHandler, adminBody, adminWriteInput } from '../admin-http.js';
import { FeedbackStore } from '../feedback-store.js';
import { ProStore } from '../pro-store.js';
import type { DatasetHolder } from '../dataset.js';
const secret='isolated-admin-test-secret-32-characters';
const login=(a:AccountStore,email:string)=>a.verify(email,a.issueCode(email));
const fixture=()=>new AccountStore(':memory:',()=>1780000000000,secret);

test('additive repeatable migration preserves account, sessions, feedback and pro tables',()=>{
  const dir=mkdtempSync(path.join(tmpdir(),'admin-upgrade-'));const file=path.join(dir,'old.sqlite');
  try {let a=new AccountStore(file,Date.now,secret);const user=login(a,'old@example.test');a.saveState(user.user.id,'test',{saved:true});new FeedbackStore(a).submit(user.user.id,{title:'Old feedback fixture',description:'Existing feedback must survive the additive migration.',page:'/account/'});new ProStore(a).grant(user.user.id,Date.now()-1000,Date.now()+86400000,'old-operator','existing entitlement');const tables=a.db.prepare("SELECT name FROM sqlite_master WHERE type='table'").all();const snapshots=new Map(tables.map(table=>[String(table.name),a.db.prepare(`SELECT * FROM "${String(table.name)}"`).all()]));a.close();a=new AccountStore(file,Date.now,secret);new AdminStore(a);new AdminStore(a);assert.equal(a.user(user.session)?.id,user.user.id);assert.deepEqual(a.state(user.user.id),{test:{saved:true}});for(const table of tables){assert.ok(a.db.prepare("SELECT 1 FROM sqlite_master WHERE name=?").get(String(table.name)));assert.deepEqual(a.db.prepare(`SELECT * FROM "${String(table.name)}"`).all(),snapshots.get(String(table.name)));}assert.equal(a.db.prepare('SELECT count(*) AS n FROM admin_schema_migrations').get()?.n,1);a.close();}finally{rmSync(dir,{recursive:true,force:true});}
});
test('commands deduplicate, bind actor type, enforce versions and rollback business/audit/results',()=>{
  const a=fixture(),s=new AdminStore(a),u=login(a,'admin@example.test');s.setMember(u.user.id,true,'operator','initial grant');a.db.exec('CREATE TABLE demo(id TEXT PRIMARY KEY, version INTEGER NOT NULL); INSERT INTO demo VALUES(\'one\',1)');
  const c:AdminCommand={actor:{type:'user',id:u.user.id},action:'demo.update',targetType:'demo',targetId:'one',reason:'test',requestId:'request-test',idempotencyKey:'same',input:{value:2},expectedVersion:1,currentVersion:()=>Number(a.db.prepare('SELECT version FROM demo').get()?.version)};
  let calls=0;const work=()=>{calls++;a.db.exec('UPDATE demo SET version=2');return {result:{version:2},before:{version:1},after:{version:2}};};
  try{assert.deepEqual(s.command(c,['version'],['version'],work),{version:2});assert.deepEqual(s.command({...c,input:{value:2}},['version'],['version'],work),{version:2});assert.equal(calls,1);assert.throws(()=>s.command({...c,input:{value:3}},['version'],['version'],work),(e:unknown)=>e instanceof AccountError&&e.status===409);assert.throws(()=>s.command({...c,idempotencyKey:'new'},['version'],['version'],work),(e:unknown)=>e instanceof AccountError&&e.code==='version_conflict');
  const rollback={...c,idempotencyKey:'rollback',expectedVersion:2};assert.throws(()=>s.command(rollback,['version'],['version'],()=>{a.db.exec('UPDATE demo SET version=3');throw Error('business failed');}));assert.equal(a.db.prepare('SELECT version FROM demo').get()?.version,2);
  a.db.exec("CREATE TRIGGER audit_failure BEFORE INSERT ON admin_audit BEGIN SELECT RAISE(ABORT,'audit failed'); END");assert.throws(()=>s.command(rollback,['version'],['version'],()=>{a.db.exec('UPDATE demo SET version=3');return {result:{version:3},before:{version:2},after:{version:3}};}));assert.equal(a.db.prepare('SELECT count(*) AS n FROM admin_commands').get()?.n,2);a.db.exec('DROP TRIGGER audit_failure');
  assert.throws(()=>s.command(rollback,['version'],['version'],()=>{a.db.exec('UPDATE demo SET version=4');return {result:{version:4},before:null,after:{password:'forbidden'}};}));assert.equal(a.db.prepare('SELECT version FROM demo').get()?.version,2);
  const auditsBefore=a.db.prepare('SELECT count(*) AS n FROM admin_audit').get()?.n;
  a.db.exec("CREATE TRIGGER command_failure BEFORE INSERT ON admin_commands BEGIN SELECT RAISE(ABORT,'result failed'); END");
  assert.throws(()=>s.command(rollback,['version'],['version'],()=>{a.db.exec('UPDATE demo SET version=5');return {result:{version:5},before:{version:2},after:{version:5}};}));
  assert.equal(a.db.prepare('SELECT version FROM demo').get()?.version,2);assert.equal(a.db.prepare('SELECT count(*) AS n FROM admin_audit').get()?.n,auditsBefore);a.db.exec('DROP TRIGGER command_failure');
  s.setMember(u.user.id,false,'operator','revoke');assert.throws(()=>s.command(c,['version'],['version'],work),(e:unknown)=>e instanceof AccountError&&e.status===403);
  }finally{a.close();}
});
test('actual HTTP authorization, revocation, errors, bounded body and stable signed pagination',async()=>{
  const a=fixture(),s=new AdminStore(a),free=login(a,'free@example.test'),plus=login(a,'plus@example.test'),admin=login(a,'admin@example.test');a.db.prepare("UPDATE users SET plan='plus' WHERE id=?").run(plus.user.id);new ProStore(a).grant(plus.user.id,a.now()-1000,a.now()+86400000,'ops','isolated Plus test');s.setMember(admin.user.id,true,'ops','grant');
  const rejected:Record<string,unknown>[]=[];
  const server=http.createServer(createAdminHandler(s,{current:null} as unknown as DatasetHolder,{origin:'http://localhost',secure:false},event=>{rejected.push(event);}));await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const base=`http://127.0.0.1:${(server.address() as import('node:net').AddressInfo).port}`;
  const request=(route:string,session='',extra:RequestInit={})=>fetch(base+'/api/admin/'+route,{...extra,headers:{Cookie:'maas_session='+session,...extra.headers}});
  try{
    for(const [session,status]of [['',401],[free.session,403],[plus.session,403]] as const){const r=await request('me',session);assert.equal(r.status,status);assert.equal(r.headers.get('cache-control'),'no-store');assert.equal(r.headers.get('vary'),'Cookie');assert.equal(r.headers.get('x-content-type-options'),'nosniff');assert.ok((await r.json() as {requestId:string}).requestId);}
    assert.equal((await request('me',admin.session)).status,200);assert.equal((await request('me','',{headers:{Authorization:'Bearer '+admin.session}})).status,401);
    assert.equal((await request('grant',free.session,{method:'POST',headers:{Origin:'http://localhost','Content-Type':'application/json'},body:JSON.stringify({actor:admin.user.id,role:'administrator'})})).status,403);
    assert.equal((await request('grant',admin.session,{method:'POST',headers:{Origin:'https://evil.test'}})).status,403);assert.equal((await request('me',admin.session,{method:'PUT'})).status,405);
    const overview=await (await request('overview',admin.session)).json() as Record<string,{availability:string}>;assert.equal(overview.releaseVersion?.availability,'not_provided');assert.equal(overview.datasetVersion?.availability,'unavailable');
    for(let i=0;i<8;i++)s.setMember(free.user.id,true,'ops','pagination '+i);
    let cursor:string|null=null;const ids:string[]=[];do{const r=await request('audit?limit=2'+(cursor?'&cursor='+encodeURIComponent(cursor):''),admin.session);assert.equal(r.status,200);const page=await r.json() as {items:{id:string}[];nextCursor:string|null};ids.push(...page.items.map(x=>x.id));cursor=page.nextCursor;}while(cursor);assert.equal(ids.length,9);assert.equal(new Set(ids).size,9);
    const page=await (await request('audit?limit=2',admin.session)).json() as {nextCursor:string};assert.equal((await request('audit?action=other&cursor='+encodeURIComponent(page.nextCursor),admin.session)).status,400);
    for(const query of ['limit=101','limit=0','cursor=bad','actor=evil','limit=2&limit=3','from=bad','from=2026-02-31T00:00:00Z','from=2026-10-02T00:00:00','from=2026-10-02T00:00:00Z&to=2026-10-01T00:00:00Z'])assert.equal((await request('audit?'+query,admin.session)).status,400);
    s.setMember(admin.user.id,false,'ops','revocation');assert.equal((await request('me',admin.session)).status,403);s.setMember(admin.user.id,true,'ops','restore');a.logout(admin.session);assert.equal((await request('me',admin.session)).status,401);
    assert.ok(rejected.length); for(const event of rejected)assert.deepEqual(Object.keys(event).sort(),['code','kind','requestId']);
  }finally{await new Promise<void>(resolve=>server.close(()=>resolve()));a.close();}
  const bodyServer=http.createServer(async(req,res)=>{try{res.end(JSON.stringify(req.url==='/write'?await adminWriteInput(req,['value'],'verified-user','request','demo.change','demo','one',()=>1):await adminBody(req,['reason','expectedVersion'])));}catch(e){res.statusCode=(e as AccountError).status;res.end();}});await new Promise<void>(resolve=>bodyServer.listen(0,'127.0.0.1',resolve));const url=`http://127.0.0.1:${(bodyServer.address() as import('node:net').AddressInfo).port}`;
  try{for(const [body,status,type]of [['{}',200,'application/json'],['{"actor":"fake"}',400,'application/json'],['[]',400,'application/json'],['{}',415,'text/plain'],[JSON.stringify({reason:'a'.repeat(17000)}),413,'application/json']] as const)assert.equal((await fetch(url,{method:'POST',headers:{'Content-Type':type},body})).status,status);
    for(const [body,key,status]of [[{reason:'test',expectedVersion:1,value:2},'same',200],[{reason:'test',expectedVersion:1},'',400],[{expectedVersion:1},'same',400],[{reason:'test',expectedVersion:'1'},'same',400],[{reason:'test',expectedVersion:1,actor:'fake'},'same',400]] as const) assert.equal((await fetch(url+'/write',{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':key},body:JSON.stringify(body)})).status,status);
  }finally{await new Promise<void>(resolve=>bodyServer.close(()=>resolve()));}
});

test('two SQLite connections serialize versions, idempotency and immediate revocation',()=>{
  const dir=mkdtempSync(path.join(tmpdir(),'admin-connections-'));const file=path.join(dir,'accounts.sqlite');const a=new AccountStore(file,Date.now,secret),b=new AccountStore(file,Date.now,secret);
  try{const first=new AdminStore(a),second=new AdminStore(b),u=login(a,'connections@example.test');first.setMember(u.user.id,true,'ops','grant');a.db.exec("CREATE TABLE demo(version INTEGER NOT NULL);INSERT INTO demo VALUES(1)");
  const command:AdminCommand={actor:{type:'user',id:u.user.id},action:'demo.change',targetType:'demo',targetId:'one',reason:'change',requestId:'connection-test',idempotencyKey:'key',input:{version:2},expectedVersion:1,currentVersion:()=>Number(a.db.prepare('SELECT version FROM demo').get()?.version)};
  first.command(command,['version'],['version'],()=>{a.db.exec('UPDATE demo SET version=2');return {result:{version:2},before:{version:1},after:{version:2}};});
  assert.deepEqual(second.command({...command,currentVersion:()=>Number(b.db.prepare('SELECT version FROM demo').get()?.version)},['version'],['version'],()=>{throw Error('must not replay');}),{version:2});
  assert.throws(()=>second.command({...command,idempotencyKey:'other',currentVersion:()=>Number(b.db.prepare('SELECT version FROM demo').get()?.version)},['version'],['version'],()=>{throw Error('must not overwrite');}),(e:unknown)=>e instanceof AccountError&&e.code==='version_conflict');
  second.setMember(u.user.id,false,'ops','revoke');assert.equal(first.member(u.user.id),undefined);
  }finally{a.close();b.close();rmSync(dir,{recursive:true,force:true});}
});

test('migration failure rolls back all foundation tables and can retry',()=>{
  const a=fixture();try{a.db.exec('CREATE TABLE admin_audit(id TEXT)');assert.throws(()=>new AdminStore(a));assert.equal(a.db.prepare("SELECT name FROM sqlite_master WHERE name='admin_members'").get(),undefined);assert.equal(a.db.prepare("SELECT name FROM sqlite_master WHERE name='admin_schema_migrations'").get(),undefined);a.db.exec('DROP TABLE admin_audit');new AdminStore(a);assert.ok(a.db.prepare('SELECT version FROM admin_schema_migrations').get());}finally{a.close();}
});

test('secure cookie mode rejects insecure and bearer credentials',()=>{
  const a=fixture(),s=new AdminStore(a),u=login(a,'secure@example.test');
  try{s.setMember(u.user.id,true,'ops','grant');
    const req=(headers:http.IncomingHttpHeaders)=>({headers} as http.IncomingMessage);
    assert.equal(authenticateAdmin(req({cookie:'__Host-maas_session='+u.session}),s,true).id,u.user.id);
    for(const headers of [{cookie:'maas_session='+u.session},{authorization:'Bearer '+u.session},{cookie:'__Host-maas_session=fake'}]) assert.throws(()=>authenticateAdmin(req(headers),s,true),(e:unknown)=>e instanceof AccountError&&e.status===401);
  }finally{a.close();}
});
