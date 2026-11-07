/** Real dispatcher plus production packet CLI: changing visitor auth must not strand operators. */
import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn,spawnSync} from 'node:child_process';
import {mkdtempSync,readFileSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import net from 'node:net';
import {fileURLToPath} from 'node:url';
import {ReleaseFixture} from './fixture.js';
const repo=fileURLToPath(new URL('../../../..',import.meta.url));
test('membership-enabled production dispatcher keeps machine auth, public freshness and fixed snapshot operations distinct',{timeout:20000},async()=>{
 const root=mkdtempSync(path.join(tmpdir(),'operations-access-'));
 const today=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date());
 const end=new Date(today+'T00:00:00Z');end.setUTCDate(end.getUTCDate()-((end.getUTCDay()-2+7)%7||7));const endDay=end.toISOString().slice(0,10);
 const rows=Array.from({length:7},(_,i)=>{const d=new Date(end);d.setUTCDate(d.getUTCDate()-6+i);return {id:'obs_'+String(i+1).repeat(64),observationDate:d.toISOString().slice(0,10)};});
 new ReleaseFixture(root).writeRelease('ds_'+'d'.repeat(64),{dataThrough:today,changes:rows,weekly:[endDay]});
 const manifest=JSON.parse(readFileSync(path.join(root,'manifest.json'),'utf8'));manifest.coverage={...manifest.coverage,weekly:{count:1,latestId:endDay},changes:{count:7,from:rows[0]!.observationDate,to:today}};
 writeFileSync(path.join(root,'manifest.json'),JSON.stringify(manifest));writeFileSync(path.join(root,'publication.json'),JSON.stringify(manifest));
 const reservation=net.createServer();await new Promise<void>(r=>reservation.listen(0,'127.0.0.1',r));const port=(reservation.address() as net.AddressInfo).port;await new Promise<void>(r=>reservation.close(()=>r()));
 const env={...process.env,HOST:'127.0.0.1',PORT:String(port),PUBLIC_DATA_ROOT:root,MAAS_ACCOUNT_DB:path.join(root,'accounts.sqlite'),MAAS_ACCOUNT_SECRET:'fixture-secret-more-than-thirty-two-characters',MAAS_MEMBERSHIP_V2:'1',MAAS_ACCOUNT_ORIGIN:'http://127.0.0.1:'+port,MAAS_DIAGNOSTICS:'0',RELOAD_INTERVAL_MS:'0'};
 for(const key of ['MAAS_SITE_ENTRY','MAAS_SITE_DATABASE_URL','RESEND_API_KEY','SMTP_URL'])delete (env as Record<string,unknown>)[key];
 const child=spawn(process.execPath,[fileURLToPath(new URL('../server.js',import.meta.url))],{env,stdio:'ignore'});
 const base='http://127.0.0.1:'+port;
 try{
  let ready=false;for(let i=0;i<100;i++){if(child.exitCode!==null)throw Error('fixture server exited');try{ready=(await fetch(base+'/api/v1/status')).ok;}catch{}if(ready)break;await new Promise(r=>setTimeout(r,50));}assert(ready);
  assert.equal((await fetch(base+'/api/v1/changes')).status,401);
  assert.equal((await fetch(base+'/api/browser/weekly?limit=1')).status,200);
  assert.equal((await fetch(base+'/api/pro/weekly/'+endDay)).status,401);
  const freshness=spawnSync('python3',[path.join(repo,'ops/check-formal-weekly.py'),'--root',base+'/api/browser'],{encoding:'utf8'});
  // Do not block the parent event loop while asking its own server: child server is separate.
  assert.equal(freshness.status,0,freshness.stderr);
  const packet=spawnSync('python3',[path.join(repo,'ops/weekly-editorial.py'),'export','--public-root',root],{encoding:'utf8'});
  assert.equal(packet.status,0,packet.stderr);assert.equal(JSON.parse(packet.stdout).observations.length,7);
 }finally{if(child.exitCode===null){const exited=new Promise(r=>child.once('exit',r));child.kill('SIGTERM');await exited;}rmSync(root,{recursive:true,force:true});}
});
