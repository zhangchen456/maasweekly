import {test} from 'node:test';
import assert from 'node:assert/strict';
import {spawn} from 'node:child_process';
import {once} from 'node:events';
import http from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {AccountStore} from '../account-store.js';
import {ProStore} from '../pro-store.js';
import {ReleaseFixture} from './fixture.js';
test('real server automatically recalculates projects only after a new validated data release becomes active',async()=>{
 const root=mkdtempSync(path.join(tmpdir(),'project-publication-')),fx=new ReleaseFixture(root),db=path.join(root,'accounts.sqlite'),secret='project-server-secret-over-32-characters',now=Date.now(),day=new Date(now).toISOString().slice(0,10);
 const publish=(n:number,amount:string,tamper=false)=>fx.writeRelease('ds_'+String(n).repeat(64),{dataThrough:day,changes:[{id:'current',observationDate:day}],prices:[{factKey:'i',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'input',amount},{factKey:'o',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'output',amount:'8'}],modelIdentities:{models:[{modelId:'openai:a',modelName:'A'}],families:[]},tamper:tamper?'hash':null});publish(1,'2');
 const store=new AccountStore(db,Date.now,secret),user=store.verify('project@example.invalid',store.issueCode('project@example.invalid'));new ProStore(store).grant(user.user.id,now-1000,now+86400000,'test','test');
 const probe=http.createServer();probe.listen(0,'127.0.0.1');await once(probe,'listening');const port=(probe.address() as any).port;await new Promise<void>(r=>probe.close(()=>r()));const base=`http://127.0.0.1:${port}`;
 const child=spawn(process.execPath,[new URL('../server.js',import.meta.url).pathname],{env:{...process.env,PORT:String(port),HOST:'127.0.0.1',PUBLIC_DATA_ROOT:root,MAAS_ACCOUNT_DB:db,MAAS_ACCOUNT_SECRET:secret,MAAS_ACCOUNT_ORIGIN:base,MAAS_MEMBERSHIP_V2:'1',MAAS_DIAGNOSTICS:'0',MAAS_SITE_ENTRY:'',PRO_BETA_ENABLED:'false',RESEND_API_KEY:'',MAAS_MAIL_FROM:'',MAAS_MAIL_MODE:'',RELOAD_INTERVAL_MS:'100'},stdio:'ignore'});
 const headers={cookie:'maas_session='+user.session,origin:base,'content-type':'application/json'};const post=async(route:string,body:unknown)=>{const response=await fetch(base+'/api/account/'+route,{method:'POST',headers,body:JSON.stringify(body)});assert.equal(response.status,200,await response.clone().text());return response.json() as Promise<any>;};
 try{
  let ready=false;for(let n=0;n<100;n++){try{if((await fetch(base+'/api/account/status')).ok){ready=true;break;}}catch{}await new Promise(r=>setTimeout(r,25));}assert.ok(ready);
  const c=await (await fetch(base+'/api/account/projects/catalog',{headers})).json() as any,q=c.items[0];const project={name:'Publication test',usageNote:'Manual monthly estimate',currency:'USD',fx:'7',lines:[{label:'Primary',inputPriceId:q.inputPriceId,outputPriceId:q.outputPriceId,inputMillions:'100',outputMillions:'20'}]};
  const preview=await post('projects/preview',{project}),saved=await post('projects',{project,datasetVersion:preview.baseline.datasetVersion,requestKey:'project_publish_123456'});assert.equal(saved.latest.cost,'360.000000000000');
  publish(2,'1.5');let result:any;for(let n=0;n<100;n++){result=await (await fetch(base+'/api/account/projects/'+saved.id,{headers})).json();if(result.latest.cost==='310.000000000000')break;await new Promise(r=>setTimeout(r,30));}assert.equal(result.latest.cost,'310.000000000000');assert.equal(result.baseline.cost,'360.000000000000');assert.equal(result.events.length,1);
  publish(3,'0',true);await new Promise(r=>setTimeout(r,350));const after=await (await fetch(base+'/api/account/projects/'+saved.id,{headers})).json() as any;assert.equal(after.latest.cost,'310.000000000000','invalid candidate never becomes a zero-cost result');assert.equal(after.events.length,1);
 }finally{if(child.exitCode===null){child.kill('SIGTERM');await once(child,'exit');}store.close();rmSync(root,{recursive:true,force:true});}
});
