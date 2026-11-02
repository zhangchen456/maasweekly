/** Isolated real-browser acceptance server. Never imported or run by production. */
import http from 'node:http';
import {readFileSync,writeFileSync,mkdtempSync,existsSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
const root=path.resolve(import.meta.dirname,'..'),load=p=>import(pathToFileURL(path.join(root,p)));
const {AccountStore}=await load('services/agent-api/dist/account-store.js'),{ProStore}=await load('services/agent-api/dist/pro-store.js'),{ProjectStore}=await load('services/agent-api/dist/project-store.js'),{ProjectDelivery}=await load('services/agent-api/dist/project-mail.js'),{deliverDigests}=await load('services/agent-api/dist/account-digest.js'),{createAccountHandler}=await load('services/agent-api/dist/account-http.js'),{DatasetHolder}=await load('services/agent-api/dist/dataset.js'),{ReleaseFixture}=await load('services/agent-api/dist/tests/fixture.js'),{createSiteHandler}=await load('services/agent-api/dist/site-http.js');
const dir=mkdtempSync(path.join(tmpdir(),'project-site-')),holder=new DatasetHolder(dir),fx=new ReleaseFixture(dir),day=new Date().toISOString().slice(0,10);
let revision=1,rate='2';const publish=()=>{fx.writeRelease('ds_'+String(revision++).repeat(64),{dataThrough:day,changes:[{id:'today',observationDate:day}],prices:[{factKey:'i',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'input',amount:rate},{factKey:'o',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'output',amount:'8'}],modelIdentities:{models:[{modelId:'openai:a',modelName:'Fixture Model'}],families:[]}});holder.reload();};publish();
const accounts=new AccountStore(':memory:',Date.now,'project-site-fixture-secret-more-than-32-characters'),plus=accounts.verify('plus@example.invalid',accounts.issueCode('plus@example.invalid')),free=accounts.verify('free@example.invalid',accounts.issueCode('free@example.invalid')),pro=new ProStore(accounts);pro.grant(plus.user.id,Date.now()-1000,Date.now()+86400000,'fixture','isolated acceptance');const projects=new ProjectStore(accounts,pro),delivery=new ProjectDelivery(projects),mails=[],mailer={send:async m=>{mails.push(m);}};
const bridge={version:1,membership:()=>({tier:'visitor',cutoff:day}),release:()=>holder.current,projection:()=>({texts:{}})};globalThis[Symbol.for('maas.site-data.v1')]=bridge;const {handler}=await load('site/dist/server/entry.mjs');const runtime={run:(_d,f)=>f(),bridge:{publicationKey:()=>holder.current.version}};
let accountHandler,site;
const server=http.createServer(async(req,res)=>{
 const url=new URL(req.url,'http://localhost');
 if(url.pathname.startsWith('/test-login/')){const u=url.pathname.endsWith('/plus')?plus:free;res.writeHead(302,{'Set-Cookie':`maas_session=${u.session}; Path=/; HttpOnly; SameSite=Lax`,Location:'/projects/'});res.end();return;}
 if(url.pathname==='/test-price'&&req.method==='POST'){rate=url.searchParams.get('rate')??'1.5';publish();projects.refreshAll(holder.current);res.writeHead(200,{'Content-Type':'application/json'});res.end('{}');return;}
 if(url.pathname==='/test-mail'&&req.method==='POST'){const result=await deliverDigests(accounts,mailer,[],'http://localhost',true,delivery);res.writeHead(200,{'Content-Type':'application/json'});res.end(JSON.stringify({...result,messages:mails.length,text:mails.at(-1)?.text??''}));return;}
 if(url.pathname.startsWith('/api/account/')){await accountHandler(req,res);return;}
 if(url.pathname.startsWith('/_astro/')||url.pathname.startsWith('/logos/')||url.pathname==='/analytics.js'||url.pathname==='/language.js'||url.pathname==='/time-display.js'){
  const base=path.join(root,'site/dist/client'),file=path.resolve(base,'.'+decodeURIComponent(url.pathname));if(!file.startsWith(base+'/')||!existsSync(file)){res.writeHead(404);res.end();return;}const type=file.endsWith('.css')?'text/css':file.endsWith('.js')?'text/javascript':file.endsWith('.svg')?'image/svg+xml':'application/octet-stream';res.writeHead(200,{'Content-Type':type});res.end(readFileSync(file));return;
 }
 await site.handle(req,res);
});await new Promise(r=>server.listen(0,'127.0.0.1',r));const origin=`http://127.0.0.1:${server.address().port}`;accountHandler=createAccountHandler(accounts,mailer,holder,{origin,secure:false},undefined,projects);site=createSiteHandler(holder,runtime,handler,origin);writeFileSync(process.argv[2],JSON.stringify({url:origin}),{mode:0o600});
process.on('SIGTERM',()=>{server.closeAllConnections();server.close(()=>{holder.close();accounts.close();rmSync(dir,{recursive:true,force:true});process.exit(0);});});
