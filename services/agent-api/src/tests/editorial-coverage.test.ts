import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {fileURLToPath} from 'node:url';
import {randomUUID} from 'node:crypto';
import {AccountStore} from '../account-store.js';
import {AdminStore} from '../admin-store.js';
import {AdminMonitor} from '../admin-monitor.js';
import {EditorialStore} from '../editorial-store.js';
import {EditorialService} from '../editorial-service.js';
import {Dataset,type DatasetHolder} from '../dataset.js';
import {MockModel} from '../editorial-model.js';
import {createAdminHandler} from '../admin-http.js';
import {editorialCoverage} from '../editorial-coverage.js';
function record(id:string,sourceId='google-vertex-changelog',at=Date.parse('2026-09-27T10:00Z'),outcome='fetch_failed',version:string|null=null){return {schemaVersion:1,batchId:id,sources:[{id:sourceId,name:sourceId,platform:'google',kind:'changelog',budgetHours:48}],runs:[{id,kind:'prices',trigger:'manual',state:outcome==='fetch_failed'?'failed':'succeeded',stage:'fetch',startedAt:at,finishedAt:at+60000,observedAt:at+60000,inputVersion:version,outputVersion:null,result:outcome==='fetch_failed'?'failed':'success',validation:'unknown',publication:'not_run',errorCode:null,runLink:null,sources:[{sourceId,attemptAt:at,successAt:['success','unchanged'].includes(outcome)?at:null,dataThrough:null,outcome,coverage:outcome==='fetch_failed'?'missing':'full',errorCode:null}]}]};}
test('D01 real HTTP rejects stale normal approval/publication, allows acknowledged partial and excludes unrelated observations',async()=>{
 const a=new AccountStore(':memory:',()=>Date.parse('2026-10-04T08:00Z'),'d01-isolated-secret-at-least-32-chars'),ad=new AdminStore(a),m=new AdminMonitor(ad),st=new EditorialStore(ad),ds=Dataset.load(fileURLToPath(new URL('../../../../data/public/v1',import.meta.url)));ds.status.sourceStreams=[];const holder={current:ds} as DatasetHolder,s=new EditorialService(st,holder),user=a.verify('d01@example.test',a.issueCode('d01@example.test'));ad.setMember(user.user.id,true,'operator','isolated D01');const config={origin:'',secure:false},server=http.createServer(createAdminHandler(ad,holder,config));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));config.origin=`http://127.0.0.1:${(server.address() as {port:number}).port}`;const id='weekly-2026-09-28';
 const post=async(op:string,input:Record<string,unknown>)=>{const r=await fetch(config.origin+'/api/admin/weekly'+(op==='create'?'':'/'+id+'/'+op),{method:'POST',headers:{Cookie:'maas_session='+user.session,Origin:config.origin,'Content-Type':'application/json','Idempotency-Key':randomUUID()},body:JSON.stringify({...input,reason:'D01 integration',...(op==='create'?{}:{expectedVersion:st.issue(id).version})})});return {status:r.status,value:await r.json() as any};};
 const prepare=(coverage='normal',ack?:string)=>post('prepare',{coverage,coverageNote:'Google Vertex采集失败；投影未同步，覆盖受限，不代表无变化',monitorAcknowledgedHash:ack});
 const draft=async()=>{const i=st.issue(id),pack=(await new MockModel().call({stage:'analyze',periodEnd:i.periodEnd,windowFrom:i.windowFrom,windowTo:i.windowTo,dataThrough:i.dataThrough!,coverage:i.coverage,coverageNote:i.coverageNote,selection:i.selection,inputs:st.inputs(id),upstream:null})).output;assert.equal((await post('revisions',{package:pack})).status,200);};
 const review=async(decision:string)=>{const r=st.revision(id);return post('review',{revision:r.revision,outputHash:r.outputHash,decision,note:'核对限制',checklist:{sources:true,conditions:true,conclusions:true,coverage:true,preview:true,attribution:true}});};
 const publish=()=>{const r=st.revision(id);return post('publish',{revision:r.revision,outputHash:r.outputHash});};
 try{
  assert.equal((await post('create',{periodEnd:'2026-09-28',selection:'D01 real historical material',budget:0})).status,200);assert.equal((await prepare()).status,200);await draft();await review('submit');await review('approve');
  ds.status.sourceStreams=[{sourceId:'google-vertex-changelog',providerId:'google',state:'failing',lastAttemptDate:'2026-09-27',lastSuccessDate:null,reason:'synthetic projection failure'}];assert.equal((await publish()).value.code,'coverage_basis_changed');ds.status.sourceStreams=[];
  m.ingest(record('failure'));assert.equal((await publish()).value.code,'coverage_basis_changed');assert.equal(s.pro.contents().length,0);const related=editorialCoverage(ad,st.issue(id),ds);assert.equal(related.limited,true);assert.equal(related.items[0]!.projectionConflict,true);assert.equal(related.items[0]!.versionRelation,'unknown');
  assert.equal((await prepare()).value.code,'monitor_coverage_conflict');assert.equal((await prepare('partial')).status,409);assert.equal((await prepare('partial',related.basisHash)).status,200);await draft();await review('submit');
  m.ingest(record('later-failure','google-vertex-changelog',Date.parse('2026-09-27T12:00Z')));assert.equal((await review('approve')).value.code,'coverage_basis_changed');const updated=editorialCoverage(ad,st.issue(id),ds);await prepare('partial',updated.basisHash);await draft();await review('submit');assert.equal((await review('approve')).status,200);assert.equal((await publish()).status,200);
  const stable=editorialCoverage(ad,st.issue(id),ds).basisHash;
  m.ingest(record('unrelated','unrelated-source'));m.ingest(record('old','google-vertex-changelog',Date.parse('2026-09-20T10:00Z')));m.ingest(record('other-version','google-vertex-changelog',Date.parse('2026-09-27T13:00Z'),'fetch_failed','ds_other'));m.ingest(record('not-run','google-vertex-changelog',Date.parse('2026-09-27T14:00Z'),'not_run'));
  assert.equal(editorialCoverage(ad,st.issue(id),ds).basisHash,stable);
  m.ingest(record('recovered','google-vertex-changelog',Date.parse('2026-09-27T15:00Z'),'unchanged',ds.version));assert.equal(editorialCoverage(ad,st.issue(id),ds).limited,false);assert.equal((await prepare()).status,200);
 }finally{server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));a.close();}
});
