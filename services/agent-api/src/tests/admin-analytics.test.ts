import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {AccountStore,AccountError} from '../account-store.js';
import {AdminStore} from '../admin-store.js';
import {ProStore} from '../pro-store.js';
import {migrateOperations} from '../admin-operations.js';
import {analyticsRange,analyticsBusiness,migrateAnalytics,trackAnalyticsRequest} from '../admin-analytics.js';
import {AdminUmami} from '../admin-umami.js';
import {createAdminHandler} from '../admin-http.js';
import type {DatasetHolder} from '../dataset.js';
const DAY=86400000,secret='analytics-isolated-fixed-clock-secret-32',at=(s:string)=>Date.parse(s+'T00:00:00+08:00');
function fixture(initial=at('2026-08-01')){let clock=initial;const accounts=new AccountStore(':memory:',()=>clock,secret),admin=new AdminStore(accounts);migrateOperations(admin);migrateAnalytics(admin);const login=(email:string)=>accounts.verify(email,accounts.issueCode(email));return {accounts,admin,login,now:()=>clock,set:(n:number)=>{clock=n;}};}
test('Beijing date boundaries, leap day, inclusive custom end, presets and strict parameters',()=>{
 const now=Date.parse('2026-10-04T00:01:00+08:00');const r=analyticsRange(new URLSearchParams(),now);assert.equal(r.start,at('2026-09-28'));assert.equal(r.end,now);assert.equal(r.timezone,'Asia/Shanghai');
 const custom=analyticsRange(new URLSearchParams({from:'2026-09-30',to:'2026-10-01'}),now);assert.equal(custom.start,at('2026-09-30'));assert.equal(custom.end,at('2026-10-02'));
 assert.equal(analyticsRange(new URLSearchParams({preset:'28'}),now).start,at('2026-09-07'));
 assert.equal(analyticsRange(new URLSearchParams({from:'2024-02-29',to:'2024-02-29'}),now).end,at('2024-03-01'));
 for(const q of ['from=2026-02-29&to=2026-03-01','from=2026-02-31&to=2026-03-01','from=2026-10-05&to=2026-10-05','from=2026-10-02&to=2026-10-01','from=2024-01-01&to=2026-01-01','preset=7&from=2026-10-01','preset=8','preset=7&preset=28','unknown=1','from=2026-10-01'])assert.throws(()=>analyticsRange(new URLSearchParams(q),now),AccountError);
});
test('future real registration is atomic and deduplicated; legacy profile never backfills registration',()=>{
 const a=new AccountStore(':memory:',()=>at('2026-08-01'),secret);try{const old=a.verify('old@example.test',a.issueCode('old@example.test'));const admin=new AdminStore(a);migrateOperations(admin);migrateAnalytics(admin);migrateAnalytics(admin);assert.equal(a.db.prepare('SELECT count(*) AS n FROM account_registrations').get()!.n,0);a.db.prepare('DELETE FROM send_limits WHERE email=?').run('old@example.test');a.verify('old@example.test',a.issueCode('old@example.test'));assert.equal(a.db.prepare('SELECT count(*) AS n FROM account_registrations').get()!.n,0);const u=a.verify('new@example.test',a.issueCode('new@example.test'));assert.equal(a.db.prepare('SELECT created FROM account_registrations WHERE userId=?').get(u.user.id)!.created,at('2026-08-01'));assert.ok(a.profile(old.user));a.db.exec("CREATE TRIGGER fail_registration BEFORE INSERT ON account_registrations BEGIN SELECT RAISE(ABORT,'test'); END");assert.throws(()=>a.verify('fail@example.test',a.issueCode('fail@example.test')));assert.equal(a.db.prepare('SELECT 1 FROM users WHERE email=?').get('fail@example.test'),undefined);}finally{a.close();}
});
test('fixed event boundaries, unique readers, cross-day return and zero/mature/immature activation denominator',()=>{
 const f=fixture(),db=f.accounts.db;try{
 const users=Array.from({length:7},(_,i)=>f.login('activation'+i+'@example.test').user.id);
 for(let i=0;i<5;i++)db.prepare('UPDATE account_registrations SET created=? WHERE userId=?').run(at('2026-09-01'),users[i]!);
 db.prepare('UPDATE account_registrations SET created=? WHERE userId=?').run(at('2026-09-08'),users[5]!);
 db.prepare('UPDATE account_registrations SET created=? WHERE userId=?').run(at('2026-09-10'),users[6]!);
 db.prepare('INSERT INTO pro_beta_access VALUES(?,?)').run(users[0]!,at('2026-09-08')-1);db.prepare('INSERT INTO pro_beta_access VALUES(?,?)').run(users[1]!,at('2026-09-08'));
 db.prepare('INSERT INTO pro_events VALUES(?,?,?,?)').run('weekly_read','2026-09-07',users[0]!,at('2026-09-01')-1);
 for(const time of [at('2026-09-01'),at('2026-09-01')+1,at('2026-09-02'),at('2026-09-15')])db.prepare('INSERT INTO pro_events VALUES(?,?,?,?)').run('weekly_read','2026-09-07',users[0]!,time);
 db.prepare('INSERT INTO pro_events VALUES(?,?,?,?)').run('weekly_read','2026-09-07',users[1]!,at('2026-09-01'));
 f.set(at('2026-09-15'));const result=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams({from:'2026-09-01',to:'2026-09-14'}),f.now()),f.now());
 assert.deepEqual(result.professionalReads,{requests:4,accounts:2});assert.equal(result.weekly.items[0]!.readers,2);assert.equal(result.weekly.items[0]!.returningReaders,1);assert.equal(result.activation7d.numerator,1);assert.equal(result.activation7d.denominator,6);assert.equal(result.activation7d.immature,1);assert.equal(result.activation7d.rate,1/6);
 const empty=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams({from:'2026-09-14',to:'2026-09-14'}),f.now()),f.now());assert.equal(empty.activation7d.rate,null);assert.equal(empty.activation7d.status,'no_denominator');const small=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams({from:'2026-09-08',to:'2026-09-08'}),f.now()),f.now());assert.equal(small.activation7d.denominator,1);assert.equal(small.activation7d.status,'insufficient_sample');assert.equal(small.activation7d.rate,null);
 }finally{f.accounts.close();}
});
test('week4 retention excludes legacy, respects 21/28-day edges and only fully observed cohorts',()=>{
 const f=fixture(),db=f.accounts.db;try{const ids=Array.from({length:7},(_,i)=>f.login('retention'+i+'@example.test').user.id);const add=(i:number,t:number)=>db.prepare('INSERT INTO pro_events VALUES(?,?,?,?)').run('content_read','content',ids[i]!,t);
 for(let i=0;i<5;i++)add(i,at('2026-08-02'));
 add(0,at('2026-08-23'));add(1,at('2026-08-30')-1);add(2,at('2026-08-23')-1);add(3,at('2026-08-30'));add(5,at('2026-08-05'));add(6,at('2026-07-31'));add(6,at('2026-08-02'));
 f.set(at('2026-08-30'));const r=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams({from:'2026-08-01',to:'2026-08-29'}),f.now()),f.now());assert.equal(r.retentionWeek4.denominator,5);assert.equal(r.retentionWeek4.numerator,2);assert.equal(r.retentionWeek4.immature,1);assert.equal(r.retentionWeek4.rate,.4);
 const partial=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams({from:'2026-07-20',to:'2026-08-29'}),f.now()),f.now());assert.equal(partial.coverage.availability,'partial');assert.equal(partial.retentionWeek4.denominator,5);
 }finally{f.accounts.close();}
});
test('Umami bounded server-only query, exact boundary adapter, cache/single-flight and missing/failure freshness',async()=>{
 const f=fixture();let calls=0,fail=false;const urls:URL[]=[],headers:string[]=[];
 const mock=(async(input:Parameters<typeof fetch>[0],init?:RequestInit)=>{calls++;const u=new URL(String(input));urls.push(u);headers.push(String((init!.headers as Record<string,string>).Authorization));await new Promise(r=>setTimeout(r,2));if(fail)return new Response('{}',{status:503});return new Response(JSON.stringify(u.pathname.endsWith('stats')?{pageviews:{value:12},visitors:{value:3},visits:{value:5}}:[{x:u.searchParams.get('type')==='referrer'?'https://user:pass@example.com/path?secret=1':'/pro/?token=secret',y:4}]));}) as typeof fetch;
 try{const u=new AdminUmami(f.admin,{endpoint:'https://api.umami.is/v1/us',websiteId:'test',token:'PRIVATE_TOKEN',version:'v3'},mock),r=analyticsRange(new URLSearchParams({from:'2026-07-30',to:'2026-07-30'}),f.now());
 const [a,b]=await Promise.all([u.query(r),u.query(r)]);assert.deepEqual(a,b);assert.equal(calls,3);assert.ok(!JSON.stringify(a).includes('PRIVATE_TOKEN'));assert.ok(!JSON.stringify(a).includes('secret'));assert.ok(!JSON.stringify(a).includes('pass'));assert.equal(urls[0]!.searchParams.get('endAt'),String(r.end-1));assert.equal(headers[0],'Bearer PRIVATE_TOKEN');assert.equal((a as any).rankingUnit,'views');assert.equal((a as any).stats.visitors,3);await u.query(r);assert.equal(calls,3);
 f.set(f.now()+60001);fail=true;const failed=await u.query(r) as any;assert.equal(failed.availability,'unavailable');assert.equal(failed.stats,null);assert.ok(failed.lastSuccessAt);assert.equal((await new AdminUmami(f.admin,null,mock).query(r) as any).reason,'not_configured');
 const bad=new AdminUmami(f.admin,{endpoint:'https://api.umami.is/v1/us',websiteId:'bad',token:'x',version:'v2'},(async()=>new Response('{"pageviews":{"value":0}}')) as typeof fetch);assert.equal((await bad.query(r) as any).availability,'unavailable');
 }finally{f.accounts.close();}
});
test('HTTP analytics permission, unknown parameters, no cache, revoked and session-cleared access',async()=>{
 const f=fixture(),free=f.login('free@example.test'),admin=f.login('admin@example.test');new ProStore(f.accounts).grant(free.user.id,f.now()-1,f.now()+DAY,'ops','test');f.admin.setMember(admin.user.id,true,'ops','test');
 const server=http.createServer(createAdminHandler(f.admin,{current:null} as unknown as DatasetHolder,{origin:'http://localhost',secure:false}));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${(server.address() as any).port}`;const get=(session='',query='')=>fetch(base+'/api/admin/analytics'+query,{headers:{Cookie:'maas_session='+session}});
 try{assert.equal((await get()).status,401);assert.equal((await get(free.session)).status,403);const response=await get(admin.session);assert.equal(response.status,200);assert.equal(response.headers.get('cache-control'),'no-store');assert.equal(response.headers.get('vary'),'Cookie');assert.ok(response.headers.get('x-request-id'));assert.equal((await response.json() as any).website.availability,'unavailable');assert.equal((await get(admin.session,'?preset=7&token=x')).status,400);f.admin.setMember(admin.user.id,false,'ops','revoke');assert.equal((await get(admin.session)).status,403);f.accounts.logout(admin.session);assert.equal((await get(admin.session)).status,401);}finally{await new Promise<void>(r=>server.close(()=>r()));f.accounts.close();}
});
test('request collection counts one finish per HTTP request, separates channels and records HTTP status without identities',async()=>{
 const f=fixture();const server=http.createServer((req,res)=>{trackAnalyticsRequest(f.admin,req,res);res.statusCode=req.url?.includes('fail')?503:200;res.end('{}');});await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${(server.address() as any).port}`;
 try{for(const route of ['/api/v1/status?secret=x','/api/mcp','/api/mcp?fail=1','/api/pro/mcp','/api/admin/analytics'])await fetch(base+route);await fetch(base+'/api/pro/catalog',{headers:{Authorization:'Bearer secret'}});await fetch(base+'/api/pro/catalog');const rows=f.accounts.db.prepare('SELECT * FROM analytics_requests ORDER BY channel,status').all();assert.equal(rows.reduce((n,r)=>n+Number(r.count),0),5);assert.equal(rows.length,5);assert.ok(!JSON.stringify(rows).includes('secret'));const r=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams(),f.now()+1),f.now()+1);assert.equal(r.agents.items.find(x=>x.channel==='public_mcp')!.requests,2);assert.equal(r.agents.items.find(x=>x.channel==='public_mcp')!.httpSuccess,1);}finally{await new Promise<void>(r=>server.close(()=>r()));f.accounts.close();}
});
test('migration failure is atomic and repeatable',()=>{const a=new AccountStore(':memory:',Date.now,secret),s=new AdminStore(a);migrateOperations(s);try{a.db.exec('CREATE TABLE analytics_requests(x TEXT)');assert.throws(()=>migrateAnalytics(s));assert.equal(a.db.prepare("SELECT 1 FROM sqlite_master WHERE name='account_registrations'").get(),undefined);assert.equal(a.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=4').get(),undefined);a.db.exec('DROP TABLE analytics_requests');migrateAnalytics(s);migrateAnalytics(s);assert.equal(a.db.prepare('SELECT count(*) AS n FROM admin_schema_migrations WHERE version=4').get()!.n,1);}finally{a.close();}});

test('published weekly with no reads is zero, samples excluded, multiple revisions do not duplicate issues',()=>{
 const f=fixture(),db=f.accounts.db;try{const payload=(sample=false)=>JSON.stringify({kind:'briefing',sample});for(const version of [1,2])db.prepare('INSERT INTO pro_content VALUES(?,?,?,\'published\',NULL,NULL,?)').run('zero-read',version,payload(),f.now());db.prepare('INSERT INTO pro_content VALUES(?,?,?,\'published\',NULL,NULL,?)').run('sample',1,payload(true),f.now());
 const user=f.login('sample-export@example.test').user.id;db.prepare('INSERT INTO pro_events VALUES(?,?,?,?)').run('content_export','sample',user,f.now());const result=analyticsBusiness(f.admin,analyticsRange(new URLSearchParams(),f.now()+1),f.now()+1);assert.equal(result.exports.requests,0);assert.equal(result.weekly.items.length,1);assert.equal(result.weekly.items[0]!.id,'zero-read');assert.equal(result.weekly.items[0]!.readers,0);assert.equal(result.weekly.items[0]!.returningReaders,0);
 }finally{f.accounts.close();}
});
test('v2 uses url and visitors, no implicit zero or unsafe redirects; calls remain bounded',async()=>{
 const f=fixture();let calls=0;const config={endpoint:'https://api.umami.is/v1/us',websiteId:'v2',token:'x',version:'v2' as const};const mock=(async(input:any,init:any)=>{calls++;assert.equal(init.redirect,'error');const url=new URL(input);if(url.pathname.endsWith('/stats'))return new Response(JSON.stringify({pageviews:{value:0},visitors:{value:0},visits:{value:0}}));assert.ok(['url','referrer'].includes(url.searchParams.get('type')!));return new Response('[]');}) as typeof fetch;
 try{const u=new AdminUmami(f.admin,config,mock);for(let i=0;i<10;i++){const r=analyticsRange(new URLSearchParams({from:'2026-07-'+String(1+i).padStart(2,'0'),to:'2026-07-'+String(1+i).padStart(2,'0')}),f.now());const value=await u.query(r) as any;assert.equal(value.availability,'available');assert.equal(value.rankingUnit,'visitors');assert.equal(value.stats.visitors,0);}const denied=await u.query(analyticsRange(new URLSearchParams({from:'2026-07-20',to:'2026-07-20'}),f.now())) as any;assert.equal(denied.reason,'busy');assert.equal(calls,30);}finally{f.accounts.close();}
});

test('admin revocation during external await rejects the finished aggregation',async()=>{
 const f=fixture(),u=f.login('await-admin@example.test');f.admin.setMember(u.user.id,true,'ops','grant');let release!:()=>void,seen!:()=>void;const held=new Promise<void>(r=>{release=r;}),ready=new Promise<void>(r=>{seen=r;});let requests=0;
 const external=http.createServer((req,res)=>{requests++;if(requests===3)seen();void held.then(()=>{res.setHeader('Content-Type','application/json');res.end(req.url?.includes('/stats?')?JSON.stringify({pageviews:{value:1},visitors:{value:1},visits:{value:1}}):'[]');});});await new Promise<void>(r=>external.listen(0,'127.0.0.1',r));
 const original={endpoint:process.env.MAAS_UMAMI_ENDPOINT,token:process.env.MAAS_UMAMI_TOKEN,version:process.env.MAAS_UMAMI_VERSION};process.env.MAAS_UMAMI_ENDPOINT=`http://127.0.0.1:${(external.address() as any).port}/api`;process.env.MAAS_UMAMI_TOKEN='isolated';process.env.MAAS_UMAMI_VERSION='v3';
 const handler=createAdminHandler(f.admin,{current:null} as unknown as DatasetHolder,{origin:'http://localhost',secure:false});for(const [k,v] of Object.entries({MAAS_UMAMI_ENDPOINT:original.endpoint,MAAS_UMAMI_TOKEN:original.token,MAAS_UMAMI_VERSION:original.version})){if(v===undefined)delete process.env[k];else process.env[k]=v;}
 const server=http.createServer(handler);await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
 try{const promise=fetch(`http://127.0.0.1:${(server.address() as any).port}/api/admin/analytics`,{headers:{Cookie:'maas_session='+u.session}});await ready;f.admin.setMember(u.user.id,false,'ops','revoked during query');release();const response=await promise;assert.equal(response.status,403);assert.equal((await response.json() as any).code,'forbidden');}finally{release();server.closeAllConnections();external.closeAllConnections();await Promise.all([new Promise<void>(r=>server.close(()=>r())),new Promise<void>(r=>external.close(()=>r()))]);f.accounts.close();}
});
