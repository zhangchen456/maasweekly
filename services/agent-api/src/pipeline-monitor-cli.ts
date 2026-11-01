/** Fixed local inbox polling; no credentials, raw logs, or arbitrary command execution. */
import {openSync,closeSync,fstatSync,readFileSync,readdirSync,lstatSync,realpathSync,constants,statfsSync} from 'node:fs';
import {join,resolve} from 'node:path';
import {pathToFileURL} from 'node:url';
import {AccountStore} from './account-store.js';
import {AdminStore} from './admin-store.js';
import {AdminMonitor} from './admin-monitor.js';
import {ingestPipelineReport,savePipelineSample,type PipelineSample} from './pipeline-monitor.js';

export function readLocalJson(file:string, limit=4*1024*1024):any {
  const fd=openSync(file,constants.O_RDONLY|constants.O_NOFOLLOW|constants.O_NONBLOCK);
  try {
    const stat=fstatSync(fd);
    if(!stat.isFile()||stat.size>limit)throw Error('invalid monitor file');
    const body=readFileSync(fd);
    if(body.length>limit)throw Error('monitor file too large');
    return JSON.parse(body.toString());
  }finally{closeSync(fd);}
}
export function jobAlive(job:any, read=(file:string)=>readFileSync(file,'utf8')) {
  if(!Number.isSafeInteger(job.pid)||job.pid<=1||typeof job.processStart!=='string'||!/^\d+$/.test(job.processStart))return false;
  try{return read(`/proc/${job.pid}/stat`).split(')').pop()!.trim().split(/\s+/)[19]===job.processStart;}
  catch{return false;}
}
export function jobAlerts(job:any, now:number, alive:boolean):string[] {
  if(!job)return ['pipeline_state_missing'];
  if(job.state==='failed')return ['pipeline_last_run_failed'];
  if(job.state==='running'&&!alive)return ['pipeline_interrupted'];
  if(job.state==='running'&&now-job.startedAt>100*60000)return ['pipeline_timeout'];
  return [];
}
export function paymentAlerts(admin:AdminStore):string[]{
  try {
    if(!admin.db.prepare("SELECT 1 FROM sqlite_master WHERE name='waffo_checkouts'").get())return [];
    const issues=admin.db.prepare("SELECT count(*) AS n FROM waffo_checkouts WHERE environment='prod' AND (error IS NOT NULL OR (state NOT IN ('expired','canceled','closed') AND coalesce(nullif(checked,0),created)<?))").get(admin.accounts.now()-10*60000);
    return Number(issues?.n)>0?['payment_verification_pending']:[];
  }catch{return ['payment_monitor_failed'];}
}
export async function relay(monitor:AdminMonitor, shared='/srv/maasweekly/shared') {
  const root=join(shared,'pipeline-monitor'),inbox=join(root,'inbox');
  const sample:PipelineSample={alerts:[],currentJob:null,runtime:null,disk:null,importedReports:0};
  try {
    if(lstatSync(inbox).isSymbolicLink()||realpathSync(inbox)!==resolve(inbox))throw Error('unsafe monitor inbox');
    const pending=readdirSync(inbox).filter(n=>/^report_[a-f0-9]{64}\.json$/.test(n))
      .filter(n=>!monitor.db.prepare('SELECT 1 FROM monitor_pipeline_reports WHERE name=?').get(n)).sort();
    for(const name of pending.slice(0,250)){
      try{ingestPipelineReport(monitor,name,readLocalJson(join(inbox,name)));sample.importedReports++;}
      catch{sample.alerts.push('monitor_sync_failed');}
    }
    if(pending.length>250)sample.alerts.push('monitor_backlog');
  }catch{sample.alerts.push('monitor_sync_failed');}
  try {
    const job=readLocalJson(join(root,'current.json'),65536);
    if(job.schemaVersion!==1||!/^pipeline_[a-f0-9]{32}$/.test(job.id)||!['running','succeeded','failed'].includes(job.state)
      ||!Number.isSafeInteger(job.startedAt)||!Number.isSafeInteger(job.updatedAt)||!Number.isSafeInteger(job.pid)
      ||!/^[-a-z]+$/.test(job.stage)||!/^[a-f0-9]{40}$/.test(job.codeCommit))throw Error('invalid pipeline state');
    const {id,state,stage,startedAt,updatedAt,codeCommit}=job;
    sample.currentJob={id,state,stage,startedAt,updatedAt,codeCommit};
    sample.alerts.push(...jobAlerts(job,monitor.admin.accounts.now(),jobAlive(job)));
  }catch{sample.alerts.push('pipeline_state_missing');}
  try {
    const state=readLocalJson(join(shared,'runtime.json'),65536);
    const publication=readLocalJson(join(shared,'public-data/v1/publication.json'),1024*1024);
    if(!Number.isSafeInteger(state.port)||state.port<1024||state.port>65535||!/^[a-f0-9]{40}$/.test(state.code))throw Error('invalid runtime');
    const response=await fetch(`http://127.0.0.1:${state.port}/_runtime/health`,{signal:AbortSignal.timeout(5000)});
    const health:any=await response.json();
    if(!response.ok||health.schemaVersion!==1||!health.publication||!/^[a-f0-9]{40}$/.test(health.processCode))throw Error('runtime unavailable');
    const expected={datasetVersion:publication.datasetVersion,inputVersion:publication.site.inputVersion,codeCommit:publication.site.codeCommit,formatVersion:publication.site.formatVersion};
    if(!health.ready||health.lastReloadError||health.processCode!==state.code
      ||Object.entries(expected).some(([k,v])=>health.publication[k]!==v))sample.alerts.push('runtime_mismatch');
    if(health.freshness?.freshness!=='fresh')sample.alerts.push('source_stale');
    if(!/^\d{4}-\d{2}-\d{2}$/.test(health.latestWeeklyId??'')
      ||monitor.admin.accounts.now()-Date.parse(health.latestWeeklyId+'T23:59:59+08:00')>10*86400000)sample.alerts.push('weekly_stale');
    sample.runtime={processCode:health.processCode,publication:Object.fromEntries(Object.keys(expected).map(k=>[k,health.publication[k]])),dataThrough:health.dataThrough,latestWeeklyId:health.latestWeeklyId};
  }catch{sample.alerts.push('runtime_unavailable');}
  try {
    const stat=statfsSync(shared);sample.disk={freeBytes:stat.bavail*stat.bsize,totalBytes:stat.blocks*stat.bsize,freeInodes:stat.ffree};
    if(sample.disk.freeBytes<Math.max(2*1024**3,sample.disk.totalBytes*.05)||sample.disk.freeInodes<10000)sample.alerts.push('disk_capacity_low');
  }catch{sample.alerts.push('disk_measurement_failed');}
  sample.alerts.push(...paymentAlerts(monitor.admin));
  sample.alerts=[...new Set(sample.alerts)].sort();
  savePipelineSample(monitor.admin,sample);
  return sample;
}

if(process.argv[1]&&import.meta.url===pathToFileURL(realpathSync(process.argv[1])).href){
  if(process.argv.length!==2||!process.env.MAAS_ACCOUNT_DB)throw Error('configured monitor service required');
  const accounts=new AccountStore(process.env.MAAS_ACCOUNT_DB);
  try {
    const result=await relay(new AdminMonitor(new AdminStore(accounts)));
    console.log(JSON.stringify({kind:'pipeline.monitor',importedReports:result.importedReports,alerts:result.alerts}));
    if(result.alerts.length)process.exitCode=1;
  }finally{accounts.close();}
}
