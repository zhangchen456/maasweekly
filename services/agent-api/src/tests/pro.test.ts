import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { AccountStore } from '../account-store.js';
import { ProStore, matches, contentSchema, csv } from '../pro-store.js';
import { createProHandler } from '../pro-http.js';
import { createMcpHandler, DEFAULT_MCP_CONFIG } from '../mcp.js';
import { deliverPro } from '../pro-digest.js';
import type { Mail } from '../account-mail.js';
import type { DatasetHolder } from '../dataset.js';

const start=Date.parse('2026-10-03T00:00:00Z');
const scope={providers:['openai'],models:[],families:[],topics:['price' as const]};
function setup(){let now=start;const account=new AccountStore(':memory:',()=>now,'test-pro-secret-32-characters-minimum');const pro=new ProStore(account);const login=(email:string)=>account.verify(email,account.issueCode(email));const a=login('a@example.com'),b=login('b@example.com');pro.grant(a.user.id,now-1,now+30*86400000,'operator','test service');return {account,pro,a,b,setNow:(value:number)=>{now=value;}};}
function content(version=1,sample=false){return contentSchema.parse({id:'change-one',version,kind:'explainer',title:'Test explainer',preview:'Public preview',body:`PRIVATE_BODY_SENTINEL_v${version}`,providers:['openai'],models:[],families:[],topics:['price'],period:{from:'2026-09-28T00:00:00+08:00',to:'2026-10-05T00:00:00+08:00'},dataThrough:'2026-10-03T00:00:00Z',coverage:'normal',coverageNote:'test coverage',evidence:[{id:'evidence-one',url:'https://example.com/official',observedAt:'2026-10-02',note:'test evidence'}],conditions:'Only comparable units',limitations:'No performance claims',rows:[{price:'=1+1'}],sample,correction:version>1?'Corrected price':'',critical:version>1});}
function publish(pro:ProStore,c=content()){pro.draft(c,'editor');pro.transition(c.id,c.version,'review','reviewer','sources, conditions, attribution checked');pro.transition(c.id,c.version,'publish','publisher','publication approved');}

test('review required, monotonic immutable versions, audit, withdrawal never falls back',()=>{const s=setup();try{s.pro.draft(content(),'editor');assert.throws(()=>s.pro.transition('change-one',1,'publish','editor','skip review'));s.pro.transition('change-one',1,'review','reviewer','evidence checked');s.pro.transition('change-one',1,'publish','editor','approved');assert.throws(()=>s.pro.draft(content(),'editor'));publish(s.pro,content(2));assert.equal(s.pro.contents().length,1);assert.equal(s.pro.get('change-one',s.a.user.id).version,2);s.pro.transition('change-one',2,'withdraw','editor','source withdrawn');assert.throws(()=>s.pro.get('change-one',s.a.user.id));assert.equal(s.pro.db.prepare('SELECT COUNT(*) AS n FROM pro_audit').get()?.n,8);}finally{s.account.close();}});

test('object union with topic intersection; unresolved model never matches model-only scope',()=>{const c=content();assert.equal(matches(c,scope),true);assert.equal(matches(c,{...scope,providers:[],models:['openai:test']}),false);assert.equal(matches(c,{...scope,topics:['billing']}),false);assert.equal(matches({...c,families:['family-one']},{...scope,providers:[],families:['family-one']}),true);assert.throws(()=>safelyConfigureEmpty());function safelyConfigureEmpty(){const s=setup();try{s.pro.configure(s.a.user.id,{...scope,providers:[]},false);}finally{s.account.close();}}});

test('expiry and revocation checked per request; scoped hashed credentials and encrypted RSS rotation',()=>{const s=setup();try{const api=s.pro.mint(s.a.user.id,'test','api'),rss=s.pro.mint(s.a.user.id,'feed','rss');assert.equal(s.pro.authenticate(api.token,'api').id,s.a.user.id);assert.throws(()=>s.pro.authenticate(rss.token,'api'));assert.throws(()=>s.pro.authenticate(api.token,'rss'));assert.equal(s.pro.rssSecret(s.a.user.id),rss.token);const raw=JSON.stringify(s.pro.db.prepare('SELECT * FROM pro_tokens').all());assert.ok(!raw.includes(api.token));assert.ok(!raw.includes(rss.token));assert.equal(s.pro.tokens(s.b.user.id).length,0);const second=s.pro.mint(s.a.user.id,'rotated','rss');assert.throws(()=>s.pro.authenticate(rss.token,'rss'));assert.equal(s.pro.rssSecret(s.a.user.id),second.token);s.pro.revoke(s.b.user.id,api.id);assert.equal(s.pro.authenticate(api.token,'api').id,s.a.user.id);s.setNow(start+31*86400000);assert.throws(()=>s.pro.authenticate(api.token,'api'));assert.equal(s.pro.entitlement(s.a.user.id).status,'expired');assert.ok(s.account.user(s.a.session)===undefined); }finally{s.account.close();}});

test('reports freeze scope and selected versions; corrections use latest, account isolation and independent unsubscribe',async()=>{const s=setup();const mails:Mail[]=[];try{publish(s.pro);s.pro.configure(s.a.user.id,scope,true);s.account.preferences(s.a.user.id,true);assert.equal(s.pro.compose('2026-10-05','normal',true),1);assert.equal(s.pro.compose('2026-10-05','normal',true),0);const id=String(s.pro.reports(s.a.user.id)[0]!.id);assert.throws(()=>s.pro.report(s.b.user.id,id));assert.equal((await deliverPro(s.pro,{async send(m){mails.push(m);}},'https://daily.maas.click')).sent,1);assert.equal((await deliverPro(s.pro,{async send(m){mails.push(m);}},'https://daily.maas.click')).sent,0);s.pro.configure(s.a.user.id,{...scope,providers:['deepseek']},true);assert.deepEqual(s.pro.report(s.a.user.id,id).scope,scope);publish(s.pro,content(2));assert.equal(s.pro.report(s.a.user.id,id).items[0]!.version,2);assert.equal((await deliverPro(s.pro,{async send(m){mails.push(m);}},'https://daily.maas.click')).sent,1);assert.ok(mails[1]!.subject.includes('重要更正'));s.pro.transition('change-one',2,'withdraw','editor','source withdrawn');assert.equal((await deliverPro(s.pro,{async send(m){mails.push(m);}},'https://daily.maas.click')).sent,1);assert.ok(mails[2]!.text.includes('已撤回'));s.pro.unsubscribe(s.pro.settings(s.a.user.id)!.unsubscribe);assert.equal(s.account.user(s.a.session)!.emailEnabled,1);assert.equal(s.pro.settings(s.a.user.id)!.emailEnabled,false);assert.ok(csv(content()).includes("'=1+1"));}finally{s.account.close();}});

test('normal empty and failed coverage distinguished; expired users cannot receive pending mail',async()=>{const s=setup();const mails:Mail[]=[];try{s.pro.configure(s.a.user.id,scope,true);s.pro.compose('2026-10-05','failed',true);await deliverPro(s.pro,{async send(m){mails.push(m);}},'https://daily.maas.click');assert.ok(mails[0]!.text.includes('不能认定为没有变化'));s.pro.compose('2026-10-12','normal',true);s.setNow(start+31*86400000);await deliverPro(s.pro,{async send(m){mails.push(m);}},'https://daily.maas.click');assert.equal(mails.length,1);}finally{s.account.close();}});

test('unknown preserves frozen message without automatic retry',async()=>{const s=setup();try{s.pro.configure(s.a.user.id,scope,true);s.pro.compose('2026-10-05','normal',true);let frozen:Mail|undefined;await deliverPro(s.pro,{async send(m){frozen=m;throw new Error('network');}},'https://daily.maas.click');s.setNow(start+6*60000);await deliverPro(s.pro,{async send(m){assert.deepEqual(m,frozen);}},'https://daily.maas.click');s.pro.compose('2026-10-12','normal',true);await deliverPro(s.pro,{async send(){throw new Error('uncertain');}},'https://daily.maas.click');s.setNow(start+24*3600000);assert.equal((await deliverPro(s.pro,{async send(){throw new Error('must not send');}},'https://daily.maas.click')).review,2);}finally{s.account.close();}});

test('HTTP and MCP protected content, previews, exports, private RSS, same origin management',async()=>{const s=setup();publish(s.pro);s.pro.configure(s.a.user.id,scope,false);const holder={current:null} as DatasetHolder;const config={origin:'http://localhost',secure:false};const proHandler=createProHandler(s.pro,holder,config,true);const mcpHandler=createMcpHandler(holder,DEFAULT_MCP_CONFIG,{store:s.pro,config});const server=http.createServer((req,res)=>{void (req.url==='/api/mcp'?mcpHandler:proHandler)(req,res);});await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));const origin=`http://127.0.0.1:${(server.address() as {port:number}).port}`;const get=(route:string,headers:Record<string,string>={})=>fetch(`${origin}/api/pro/${route}`,{headers});const cookie={Cookie:`maas_session=${s.a.session}`};try{let r=await get('catalog');assert.ok(!(await r.text()).includes('PRIVATE_BODY'));r=await get('content/change-one');assert.equal(r.status,401);r=await get('content/change-one',{Cookie:`maas_session=${s.b.session}`});assert.equal(r.status,403);r=await get('content/change-one',cookie);assert.equal(r.status,200);assert.ok(r.headers.get('cache-control')?.includes('no-store'));assert.ok((await r.text()).includes('PRIVATE_BODY'));r=await get('content/change-one?format=markdown',cookie);assert.ok((await r.text()).includes('Only comparable units'));const api=s.pro.mint(s.a.user.id,'agent','api'),rss=s.pro.mint(s.a.user.id,'rss','rss');r=await get('feed?token='+rss.token);assert.equal(r.status,200);assert.ok(!(await r.text()).includes('PRIVATE_BODY'));r=await get('feed?token='+api.token);assert.equal(r.status,401);r=await get('content/change-one',{Authorization:`Bearer ${api.token}`});assert.equal(r.status,200);r=await fetch(origin+'/api/pro/token',{method:'POST',headers:{...cookie,'Content-Type':'application/json',Origin:'https://evil.example'},body:JSON.stringify({name:'stolen',purpose:'api'})});assert.equal(r.status,403);
const rpc=async(auth?:string)=>fetch(origin+'/api/mcp',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json, text/event-stream',...(auth?{Authorization:`Bearer ${auth}`}:{})},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name:'maas_pro_read',arguments:{id:'change-one'}}})});let result=await (await rpc()).json() as any;assert.equal(result.result.isError,true);result=await (await rpc(api.token)).json() as any;assert.ok(JSON.stringify(result).includes('PRIVATE_BODY'));assert.equal(s.pro.db.prepare("SELECT count(*) AS n FROM pro_events WHERE event='agent_tool_success' AND target='maas_pro_read'").get()!.n,1);assert.equal(s.pro.db.prepare("SELECT count(*) AS n FROM pro_events WHERE event='content_read' AND userId=?").get(s.a.user.id)!.n,3);r=await get('content/change-one?format=invalid',cookie);assert.equal(r.status,200);assert.equal(s.pro.db.prepare("SELECT count(*) AS n FROM pro_events WHERE event='content_export'").get()!.n,1);s.pro.grant(s.a.user.id,start,start+86400000,'operator','revoke',true);r=await get('content/change-one',cookie);assert.equal(r.status,403);r=await get('feed?token='+rss.token);assert.equal(r.status,403);publish(s.pro,{...content(),id:'public-sample',sample:true});r=await get('content/public-sample');assert.equal(r.status,200);
}finally{server.closeAllConnections();await new Promise<void>(resolve=>server.close(()=>resolve()));s.account.close();}});


test('additive schema survives restart, free account data remains usable, snapshots exclude public samples', async()=>{
  const {mkdtempSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os');const path=await import('node:path');
  const root=mkdtempSync(path.join(tmpdir(),'pro-persist-'));const filename=path.join(root,'account.sqlite');
  const secret='test-pro-persistence-secret-32-characters';let account=new AccountStore(filename,()=>start,secret);
  try {const result=account.verify('persistent@example.com',account.issueCode('persistent@example.com'));account.saveState(result.user.id,'theme','light');let pro=new ProStore(account);pro.grant(result.user.id,start-1,start+86400000,'operator','test service');pro.configure(result.user.id,scope,false);publish(pro);publish(pro,{...content(),id:'sample-only',sample:true});pro.compose('2026-10-05','normal');const token=pro.mint(result.user.id,'persistent','api');account.close();account=new AccountStore(filename,()=>start,secret);pro=new ProStore(account);assert.equal(pro.authenticate(token.token,'api').id,result.user.id);assert.equal(account.state(result.user.id).theme,'light');assert.equal(pro.report(result.user.id,String(pro.reports(result.user.id)[0]!.id)).items.length,1);pro.grant(result.user.id,start-1,start+86400000,'operator','expired service',true);assert.equal(account.user(result.session)?.id,result.user.id);assert.equal(account.state(result.user.id).theme,'light');assert.throws(()=>pro.get('change-one',result.user.id));assert.equal(pro.get('sample-only').sample,true);assert.throws(()=>pro.draft({...content(2),id:'sample-only',sample:false},'editor'));}finally{account.close();rmSync(root,{recursive:true,force:true});}
});

test('beta access is separate, idempotent, switchable and respects revocation',()=>{
 const s=setup();const previous=process.env.PRO_BETA_ENABLED;
 try{
  process.env.PRO_BETA_ENABLED='true';
  assert.equal(s.pro.activateBeta(s.b.user.id).source,'beta');
  assert.equal(s.pro.activateBeta(s.b.user.id).status,'active');
  assert.equal(s.pro.db.prepare("SELECT COUNT(*) AS n FROM pro_events WHERE event='beta_activated'").get()?.n,1);
  assert.equal(s.pro.db.prepare('SELECT COUNT(*) AS n FROM pro_entitlements WHERE userId=?').get(s.b.user.id)?.n,0);
  process.env.PRO_BETA_ENABLED='false';assert.equal(s.pro.entitlement(s.b.user.id).status,'pending');assert.throws(()=>s.pro.activateBeta(s.b.user.id));
  assert.equal(s.pro.entitlement(s.a.user.id).status,'active');
  process.env.PRO_BETA_ENABLED='true';s.pro.grant(s.b.user.id,start-1,start+86400000,'operator','revoked',true);assert.equal(s.pro.entitlement(s.b.user.id).status,'revoked');assert.throws(()=>s.pro.activateBeta(s.b.user.id));
 }finally{if(previous===undefined)delete process.env.PRO_BETA_ENABLED;else process.env.PRO_BETA_ENABLED=previous;s.account.close();}
});

test('weekly full text requires Plus; anonymous query hides analysis',async()=>{
 const {mkdtempSync,writeFileSync,rmSync}=await import('node:fs');const {tmpdir}=await import('node:os');const path=await import('node:path');const {publicWeekly}=await import('../query.js');
 const s=setup(),root=mkdtempSync(path.join(tmpdir(),'weekly-access-')),previous=process.env.PRIVATE_WEEKLY_ROOT;
 const server=http.createServer(createProHandler(s.pro,{current:null} as DatasetHolder,{origin:'http://localhost',secure:false},false));
 try{process.env.PRIVATE_WEEKLY_ROOT=root;writeFileSync(path.join(root,'2026-09-01.html'),'<p>PRIVATE_WEEKLY_SENTINEL</p>');await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const url=`http://127.0.0.1:${(server.address() as {port:number}).port}/api/pro/weekly/2026-09-01`;
 assert.equal((await fetch(url)).status,401);assert.equal((await fetch(url,{headers:{Cookie:`maas_session=${s.b.session}`}})).status,403);
 let r=await fetch(url,{headers:{Cookie:`maas_session=${s.a.session}`}});assert.equal(r.status,200);assert.match(r.headers.get('cache-control')! ,/no-store/);assert.match(await r.text(),/PRIVATE_WEEKLY_SENTINEL/);
 s.pro.activateBeta(s.b.user.id);assert.equal((await fetch(url,{headers:{Cookie:`maas_session=${s.b.session}`}})).status,200);
 const raw={id:'2026-09-01',headline:[{title:'Title',detail_markdown:'SECRET'}],platforms:[{analysis:'SECRET'}],summary_table:{secret:'SECRET'},trends:['SECRET'],watchpoints:'SECRET',event_index:['SECRET']} as any;
 assert.ok(!JSON.stringify(publicWeekly(raw)).includes('SECRET'));assert.equal(publicWeekly({...raw,id:'2026-05-03'}).trends[0],'SECRET');
 }finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));if(previous===undefined)delete process.env.PRIVATE_WEEKLY_ROOT;else process.env.PRIVATE_WEEKLY_ROOT=previous;s.account.close();rmSync(root,{recursive:true,force:true});}
});

test('Plus MCP weekly returns full structured report only with current entitlement',async()=>{
 const s=setup();
 const raw={id:'2026-09-01',date:'2026-09-01',title:'Weekly',headline:[{title:'Headline',detail_markdown:'PRIVATE_WEEKLY_MCP'}],platforms:[],trends:['PRIVATE_TREND']};
 const fixture={current:{version:'test-dataset',dataThrough:'2026-10-03',weekly:[raw],weeklyDescending:[raw]} as any};
 const holder=fixture as DatasetHolder;
 const handler=createMcpHandler(holder,DEFAULT_MCP_CONFIG,{store:s.pro,config:{origin:'http://localhost',secure:false}});
 const server=http.createServer((req,res)=>void handler(req,res));
 await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
 const origin=`http://127.0.0.1:${(server.address() as {port:number}).port}`;
 const rpc=async(token?:string,args:Record<string,unknown>={},name='maas_pro_weekly',cookie?:string)=>{
  const r=await fetch(origin+'/api/pro/mcp',{method:'POST',headers:{'Content-Type':'application/json',Accept:'application/json, text/event-stream',...(token?{Authorization:`Bearer ${token}`}:{Cookie:cookie ?? ''})},body:JSON.stringify({jsonrpc:'2.0',id:1,method:'tools/call',params:{name,arguments:args}})});
  assert.match(r.headers.get('cache-control')!,/no-store/);return await r.json() as any;
 };
 const denied=async(token?:string,args:Record<string,unknown>={},code?:string)=>{const result=await rpc(token,args);assert.equal(result.result.isError,true);assert.ok(!JSON.stringify(result).includes('PRIVATE_WEEKLY_MCP'));if(code)assert.match(JSON.stringify(result),new RegExp(code));};
 try {
  await denied(undefined,{},'unauthenticated');
  const free=await rpc(undefined,{},'maas_pro_weekly',`maas_session=${s.b.session}`);assert.equal(free.result.isError,true);assert.ok(!JSON.stringify(free).includes('PRIVATE_WEEKLY_MCP'));
  const malformed=await rpc('not-a-valid-token');assert.equal(malformed.result.isError,true);
  const api=s.pro.mint(s.a.user.id,'agent','api'),rss=s.pro.mint(s.a.user.id,'feed','rss');
  await denied(rss.token,{},'invalid_token');
  let result=await rpc(api.token);assert.ok(JSON.stringify(result).includes('PRIVATE_WEEKLY_MCP'));assert.ok(JSON.stringify(result).includes('PRIVATE_TREND'));assert.ok(JSON.stringify(result).includes('test-dataset'));
  result=await rpc(api.token,{id:raw.id});assert.equal(result.result.isError,undefined);
  await denied(api.token,{id:'2026-01-01'},'not_found');
  const dataset=fixture.current;fixture.current=null;await denied(api.token,{},'data_unavailable');fixture.current=dataset;
  const invalid=await rpc(api.token,{id:'../../secret'});assert.ok(invalid.error || invalid.result.isError);
  s.pro.revoke(s.a.user.id,api.id);await denied(api.token);
  s.pro.activateBeta(s.b.user.id);const beta=s.pro.mint(s.b.user.id,'beta-agent','api');assert.ok(JSON.stringify(await rpc(beta.token)).includes('PRIVATE_WEEKLY_MCP'));
  s.pro.grant(s.b.user.id,start-1,start+86400000,'operator','revoked',true);await denied(beta.token);
  const expiring=s.pro.mint(s.a.user.id,'expiry','api');s.setNow(start+31*86400000);await denied(expiring.token);
 } finally {server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));s.account.close();}
});
