import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtempSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {AccountStore} from '../account-store.js';
import {ProStore} from '../pro-store.js';
import {ProjectStore} from '../project-store.js';
import {DatasetHolder} from '../dataset.js';
import {ReleaseFixture} from './fixture.js';
import {createAccountHandler} from '../account-http.js';
test('project HTTP workflow requires session, Plus and origin; preview/save versions and ownership cannot be forged',async()=>{
 const root=mkdtempSync(path.join(tmpdir(),'project-http-')),holder=new DatasetHolder(root),now=Date.parse('2026-11-02T02:00:00Z');
 const fx=new ReleaseFixture(root);fx.writeRelease('ds_'+'1'.repeat(64),{dataThrough:'2026-11-02',changes:[{id:'recent',observationDate:'2026-11-02'}],prices:[{factKey:'i',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'input',amount:'2'},{factKey:'o',providerId:'openai',modelKey:'a',modelId:'openai:a',component:'output',amount:'8'}],modelIdentities:{models:[{modelId:'openai:a',modelName:'A'}],families:[]}});holder.reload();
 const accounts=new AccountStore(':memory:',()=>now,'project-http-secret-more-than-32-characters'),owner=accounts.verify('a@example.com',accounts.issueCode('a@example.com')),free=accounts.verify('b@example.com',accounts.issueCode('b@example.com')),pro=new ProStore(accounts);pro.grant(owner.user.id,now-1,now+86400000,'test','test');const projects=new ProjectStore(accounts,pro),handler=createAccountHandler(accounts,null,holder,{origin:'http://localhost',secure:false},undefined,projects);
 const server=http.createServer((q,r)=>void handler(q,r));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));const base=`http://127.0.0.1:${(server.address() as any).port}/api/account/`;
 const headers={'content-type':'application/json',origin:'http://localhost',cookie:'maas_session='+owner.session};
 const post=(route:string,body:any,h=headers)=>fetch(base+route,{method:'POST',headers:h,body:JSON.stringify(body)});
 try{
  assert.equal((await fetch(base+'projects')).status,401);const catalog=await (await fetch(base+'projects/catalog',{headers})).json() as any;const q=catalog.items[0];const project={name:'Customer support',usageNote:'October estimate',currency:'USD',fx:'7',lines:[{label:'Primary',inputPriceId:q.inputPriceId,outputPriceId:q.outputPriceId,inputMillions:'100',outputMillions:'20'}]};
  assert.equal((await post('projects/preview',{project},{...headers,cookie:'maas_session='+free.session})).status,403);assert.equal((await post('projects/preview',{project},{...headers,origin:'https://evil.example'})).status,403);
  assert.equal((await post('projects/preview',{project:{...project,userId:owner.user.id}})).status,400);
  const preview=await post('projects/preview',{project});assert.equal(preview.status,200);const p=await preview.json() as any;assert.equal(p.baseline.cost,'360.000000000000');
  assert.equal((await post('projects',{project,datasetVersion:'ds_'+'0'.repeat(64),requestKey:'project_create_123456'})).status,409);
  const saved=await post('projects',{project,datasetVersion:p.baseline.datasetVersion,requestKey:'project_create_123456'});assert.equal(saved.status,200);const result=await saved.json() as any;
  assert.equal((await fetch(base+'projects/'+result.id,{headers:{...headers,cookie:'maas_session='+free.session}})).status,404);
  assert.equal((await post('projects/'+result.id+'/action',{action:'email',enabled:true,revision:1})).status,503,'mail cannot be enabled without mail service');
  assert.equal((await fetch(base+'projects/'+result.id,{headers:{authorization:'Bearer invalid'}})).status,401,'machine credentials cannot manage projects');
 }finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));accounts.close();holder.close();rmSync(root,{recursive:true,force:true});}
});
