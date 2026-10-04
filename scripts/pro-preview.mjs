/** Local acceptance fixture: ephemeral accounts, no external mail, no production writes. */
import http from 'node:http';
import { randomBytes } from 'node:crypto';
import { mkdtempSync, readFileSync, readdirSync, writeFileSync, rmSync, statSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { AccountStore } from '../services/agent-api/dist/account-store.js';
import { ProStore, contentSchema } from '../services/agent-api/dist/pro-store.js';
import { validateEditorial } from '../services/agent-api/dist/pro-editorial.js';
import { createProHandler } from '../services/agent-api/dist/pro-http.js';
import { createAccountHandler } from '../services/agent-api/dist/account-http.js';
import { DatasetHolder } from '../services/agent-api/dist/dataset.js';
import { createHandler } from '../services/agent-api/dist/http.js';
import { createMcpHandler, DEFAULT_MCP_CONFIG } from '../services/agent-api/dist/mcp.js';
const temp=mkdtempSync(path.join(tmpdir(),'maas-pro-preview-'));
const account=new AccountStore(path.join(temp,'account.sqlite'),Date.now,randomBytes(32).toString('hex'));
const store=new ProStore(account), holder=new DatasetHolder(path.resolve('data/public/v1'));
if (!holder.reload()) throw new Error(holder.lastReloadError);
const paid=account.verify('paid@example.test',account.issueCode('paid@example.test'));
const tester=account.verify('tester@example.test',account.issueCode('tester@example.test'));
const free=account.verify('free@example.test',account.issueCode('free@example.test'));
store.grant(paid.user.id,Date.now()-86400000,Date.now()+30*86400000,'fixture','local acceptance only');
for (const file of readdirSync('docs/product/maas-pro-briefing-v1/samples').filter(f=>f.endsWith('.json'))) {
  const c=contentSchema.parse(JSON.parse(readFileSync('docs/product/maas-pro-briefing-v1/samples/'+file,'utf8')));
  validateEditorial(c,holder.current); store.draft(c,'local-editor'); store.transition(c.id,1,'review','local-reviewer','sample sources and limitations checked'); store.transition(c.id,1,'publish','local-editor','local sample only');
}
store.configure(paid.user.id,{providers:['xai','kimi','anthropic'],models:[],families:[],topics:['price','billing','lifecycle','capability']},false);
store.compose('2026-10-05','partial',false);
const config={origin:'http://localhost',secure:false};
const pro=createProHandler(store,holder,config,true);
const plusMcp=createMcpHandler(holder,DEFAULT_MCP_CONFIG,{store,config});
const publicMcp=createMcpHandler(holder,DEFAULT_MCP_CONFIG);
const accountHandler=createAccountHandler(account,{async send(){}},holder,config);
const rest=createHandler(holder,{rateLimit:{capacity:10000,refillPerMinute:10000}});
const staticRoot=path.resolve('site/dist');
const server=http.createServer((req,res)=>{
  const previewPath=(req.url??'').split('?')[0];
  if (['/_preview/free','/_preview/plus','/_preview/guest','/_preview/tester'].includes(previewPath)) {
    const session=previewPath.endsWith('/tester') ? tester.session : previewPath.endsWith('/plus') ? paid.session : previewPath.endsWith('/free') ? free.session : '';
    res.writeHead(302,{'Set-Cookie':`maas_session=${session}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${session ? 86400 : 0}`,'Location':'/subscription/','Cache-Control':'no-store'});res.end();return;
  }
  if(previewPath==='/api/pro/mcp')return void plusMcp(req,res);
  if(previewPath==='/api/mcp')return void publicMcp(req,res);
  if(req.url.startsWith('/api/pro/'))return void pro(req,res);
  if(req.url.startsWith('/api/account/'))return void accountHandler(req,res);
  if(req.url.startsWith('/api/v1/'))return void rest(req,res);
  try {
    let file=path.resolve(staticRoot,'.'+decodeURIComponent(new URL(req.url,config.origin).pathname));
    if (!file.startsWith(staticRoot+path.sep) && file!==staticRoot)throw new Error();
    if(statSync(file).isDirectory())file=path.join(file,'index.html');
    const types={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.css':'text/css; charset=utf-8','.json':'application/json','.png':'image/png','.svg':'image/svg+xml'};
    res.writeHead(200,{'Content-Type':types[path.extname(file)]??'application/octet-stream'});res.end(readFileSync(file));
  } catch {res.writeHead(404).end();}
});
await new Promise(r=>server.listen(Number(process.env.PRO_PREVIEW_PORT ?? 0),'127.0.0.1',r));
config.origin=`http://127.0.0.1:${server.address().port}`;
writeFileSync(path.join(temp,'fixture.json'),JSON.stringify({origin:config.origin,paid:paid.session,free:free.session}),{mode:0o600});
process.stdout.write(temp+'\n');
function stop(){server.closeAllConnections();server.close(()=>{account.close();holder.close();rmSync(temp,{recursive:true,force:true});process.exit(0);});}
process.on('SIGINT',stop);process.on('SIGTERM',stop);
