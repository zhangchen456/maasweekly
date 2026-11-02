import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import http from 'node:http';
import {once} from 'node:events';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {AccountStore} from '../account-store.js';
import {ProStore} from '../pro-store.js';
import {Membership} from '../membership.js';
import {ReleaseFixture} from './fixture.js';

test('real dispatcher enforces credentials, history and metering across REST and MCP while public browser queries stay usable',async()=>{
 const root=mkdtempSync(path.join(tmpdir(),'membership-server-')),secret='test-membership-server-secret-over-32-characters',db=path.join(root,'account.sqlite');
 new ReleaseFixture(root).writeRelease('ds_'+'1'.repeat(64),{dataThrough:'2026-11-02',changes:[{id:'recent',observationDate:'2026-11-02'},{id:'old',observationDate:'2026-10-01'}]});
 const accounts=new AccountStore(db,Date.now,secret),user=accounts.verify('test@example.com',accounts.issueCode('test@example.com')),membership=new Membership(accounts,new ProStore(accounts),false),token=membership.mint(user.user.id,'Agent');
 const probe=http.createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');const port=(probe.address() as any).port;await new Promise<void>(r=>probe.close(()=>r()));
 const origin=`http://localhost:${port}`,base=`http://127.0.0.1:${port}`;
 const child=spawn(process.execPath,[new URL('../server.js',import.meta.url).pathname],{env:{...process.env,PORT:String(port),HOST:'127.0.0.1',PUBLIC_DATA_ROOT:root,MAAS_ACCOUNT_DB:db,MAAS_ACCOUNT_SECRET:secret,MAAS_ACCOUNT_ORIGIN:origin,MAAS_MEMBERSHIP_V2:'1',MAAS_DIAGNOSTICS:'0',MAAS_SITE_ENTRY:'',PRO_BETA_ENABLED:'false',RELOAD_INTERVAL_MS:'0'},stdio:'ignore'});
 const auth={authorization:`Bearer ${token.token}`};
 try{
  let ready=false;for(let n=0;n<100;n++){try{const r=await fetch(base+'/api/v1/status');if(r.ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,25));}assert.ok(ready,'test server ready');
  const webhook=await fetch(base+'/api/payment/webhook',{method:'POST',headers:{authorization:'Bearer provider-specific-credential','content-type':'application/json'},body:'{}'});assert.notEqual((await webhook.json()).code,'invalid_token','provider callbacks bypass account bearer authentication');
  assert.equal((await fetch(base+'/api/v1/changes')).status,401);
  const visitor=await fetch(base+'/api/browser/changes');assert.equal(visitor.status,200);assert.equal(((await visitor.json()) as any).items.length,1);assert.match(visitor.headers.get('cache-control')??'',/no-store/);
  assert.equal((await fetch(base+'/api/browser/changes?from=2026-10-01&to=2026-11-03')).status,403);
  assert.equal((await fetch(base+'/api/browser/changes',{headers:auth})).status,403);
  assert.equal((await fetch(base+'/api/v1/changes',{headers:auth})).status,200);assert.equal(membership.usage(user.user.id).used,1);
  const rpc=(body:unknown,headers:Record<string,string>=auth)=>fetch(base+'/api/mcp',{method:'POST',headers:{...headers,'content-type':'application/json',accept:'application/json, text/event-stream'},body:JSON.stringify(body)});
  assert.equal((await rpc({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'test',version:'1'}}},{})).status,401);
  assert.equal((await rpc({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-03-26',capabilities:{},clientInfo:{name:'test',version:'1'}}})).status,200);assert.equal(membership.usage(user.user.id).used,1);
  assert.equal((await rpc({jsonrpc:'2.0',id:2,method:'tools/list',params:{}})).status,200);assert.equal(membership.usage(user.user.id).used,1);
  const call=await rpc({jsonrpc:'2.0',id:3,method:'tools/call',params:{name:'maas_get_changes',arguments:{}}});assert.equal(call.status,200);assert.ok(!((await call.json()) as any).result.isError);assert.equal(membership.usage(user.user.id).used,2);
  const failed=await rpc({jsonrpc:'2.0',id:4,method:'tools/call',params:{name:'maas_get_item',arguments:{id:'missing'}}});assert.ok(((await failed.json()) as any).result.isError);assert.equal(membership.usage(user.user.id).used,2);
  membership.revoke(user.user.id,token.id);assert.equal((await fetch(base+'/api/v1/changes',{headers:auth})).status,401);
 }finally{if(child.exitCode===null){child.kill('SIGTERM');await once(child,'exit');}accounts.close();rmSync(root,{recursive:true,force:true});}
});
