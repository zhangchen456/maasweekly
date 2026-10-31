import {test} from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import {mkdtempSync,readFileSync,writeFileSync,rmSync,symlinkSync} from 'node:fs';
import {tmpdir} from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {fileURLToPath} from 'node:url';
import {DatasetHolder} from '../dataset.js';
import {ReleaseFixture} from './fixture.js';
import {runtimeHealth,createRuntimeHealthHandler,runtimeIdentity} from '../runtime-health.js';
import {AccountStore} from '../account-store.js';
import {AdminStore} from '../admin-store.js';
import {AdminMonitor} from '../admin-monitor.js';
import {ingestPipelineReport,pipelineHealth,savePipelineSample} from '../pipeline-monitor.js';
import {jobAlive,jobAlerts} from '../pipeline-monitor-cli.js';
const code='a'.repeat(40),ds='ds_'+'b'.repeat(64),input='in_'+'c'.repeat(64),at=Date.parse('2026-11-01T00:00:00Z');
test('health exposes the loaded input and failed reload even when public dataset is unchanged; proxy requests denied',async()=>{
 const root=mkdtempSync(path.join(tmpdir(),'runtime-health-'));const fx=new ReleaseFixture(root);let reject=false;
 const holder=new DatasetHolder(root,{publicationFile:'publication.json',prepare:async()=>{if(reject)throw Error('PRIVATE_ERROR');}});
 const bind=(version:string)=>{const m=JSON.parse(readFileSync(path.join(root,'manifest.json'),'utf8'));m.site={inputVersion:version,codeCommit:code,formatVersion:1};writeFileSync(path.join(root,'publication.json'),JSON.stringify(m));};
 const server=http.createServer(createRuntimeHealthHandler(holder,code));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
 const url=`http://127.0.0.1:${(server.address() as any).port}/_runtime/health`;
 try{
  fx.writeRelease(ds,{changes:[{id:'obs_'+'a'.repeat(64),observationDate:'2026-09-10'}]});bind(input);assert.equal(await holder.reloadAsync(),'changed',holder.lastReloadError??'');assert.equal(runtimeHealth(holder,code).ready,true);
  bind('in_'+'d'.repeat(64));reject=true;assert.equal(await holder.reloadAsync(),'failed');
  const health=runtimeHealth(holder,code);assert.equal(health.ready,false);assert.equal(health.publication?.inputVersion,input);assert.equal(health.lastReloadError,'dataset_load_failed');assert.ok(!JSON.stringify(health).includes('PRIVATE_ERROR'));
  assert.equal((await fetch(url)).status,200);
  for(const key of ['x-forwarded-for','x-maas-client-ip'])assert.equal((await fetch(url,{headers:{[key]:'untrusted'}})).status,404);
  const status=await new Promise<number>(resolve=>{http.get(url,{headers:{host:'daily.maas.click'}},response=>{response.resume();resolve(response.statusCode!);});});assert.equal(status,404);
  reject=false;await holder.reloadAsync();assert.equal(runtimeHealth(holder,code).publication?.inputVersion,'in_'+'d'.repeat(64));
  assert.equal(runtimeIdentity('/runtime/'+code),code);assert.equal(runtimeIdentity('/tmp/dev'),'local');
 }finally{holder.close();await new Promise<void>(r=>server.close(()=>r()));rmSync(root,{recursive:true,force:true});}
});
function report(id='run1') {return {schemaVersion:'pipeline-report-v1',batch:{schemaVersion:1,batchId:id,sources:[],runs:[{id,kind:'data-pipeline',trigger:'manual',state:'succeeded',stage:'rebuild',startedAt:at-1000,finishedAt:at,observedAt:at,inputVersion:input,outputVersion:input,result:'partial',validation:'passed',publication:'completed',errorCode:'execution_failed',runLink:null,sources:[]}]},contexts:[{runId:id,codeCommit:code,datasetVersion:ds,elapsedMs:1000}]};}
test('pipeline receipts and contexts commit atomically, reject conflicting replay and do not refresh source times',()=>{
 const accounts=new AccountStore(':memory:',()=>at,'test-secret-more-than-thirty-two-characters'),admin=new AdminStore(accounts),monitor=new AdminMonitor(admin),name='report_'+'a'.repeat(64)+'.json';
 try{
  const first=report();assert.equal(ingestPipelineReport(monitor,name,first).duplicate,false);assert.equal(ingestPipelineReport(monitor,name,first).duplicate,true);
  assert.equal(monitor.runs(new URLSearchParams()).items[0].codeCommit,code);
  assert.equal(monitor.runs(new URLSearchParams()).items[0].publication,'completed');
  const invalid=report('run2');invalid.contexts[0]!.elapsedMs=-1;
  assert.throws(()=>ingestPipelineReport(monitor,'report_'+'b'.repeat(64)+'.json',invalid));assert.equal(accounts.db.prepare("SELECT 1 FROM monitor_runs WHERE id='run2'").get(),undefined);
  const conflict=report();conflict.contexts[0]!.codeCommit='c'.repeat(40);assert.throws(()=>ingestPipelineReport(monitor,'report_'+'c'.repeat(64)+'.json',conflict));
  assert.equal(pipelineHealth(admin).stale,true);
  savePipelineSample(admin,{alerts:['source_stale'],currentJob:null,runtime:null,disk:null,importedReports:1});assert.deepEqual(pipelineHealth(admin).alerts,['source_stale']);assert.equal(pipelineHealth(admin).stale,false);
  accounts.db.prepare('UPDATE monitor_pipeline_health SET checkedAt=?').run(at-16*60000);assert.ok(pipelineHealth(admin).alerts.includes('monitor_collector_stale'));
 }finally{accounts.close();}
});
test('dead jobs, PID reuse and deadlines are visible without inventing completed runs',()=>{
 const proc='123 (worker) '+Array.from({length:22},(_,i)=>i===19?'456':'0').join(' ');
 assert.equal(jobAlive({pid:123,processStart:'456'},()=>proc),true);assert.equal(jobAlive({pid:123,processStart:'789'},()=>proc),false);
 assert.deepEqual(jobAlerts({state:'running',startedAt:at},at,false),['pipeline_interrupted']);
 assert.deepEqual(jobAlerts({state:'running',startedAt:at-101*60000},at,true),['pipeline_timeout']);
 assert.deepEqual(jobAlerts({state:'failed'},at,false),['pipeline_last_run_failed']);
});

test('monitor CLI runs when invoked through the production current symlink',()=>{
 const root=mkdtempSync(path.join(tmpdir(),'monitor-entry-'));
 try{const entry=path.join(root,'entry.js');symlinkSync(fileURLToPath(new URL('../pipeline-monitor-cli.js',import.meta.url)),entry);
  const env={...process.env};delete env.MAAS_ACCOUNT_DB;
  const child=spawnSync(process.execPath,[entry],{env,encoding:'utf8'});
  assert.notEqual(child.status,0);assert.match(child.stderr,/configured monitor service required/);
 }finally{rmSync(root,{recursive:true,force:true});}
});
