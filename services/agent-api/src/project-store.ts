import {randomUUID} from 'node:crypto';
import {AccountError, type AccountStore} from './account-store.js';
import type {ProStore} from './pro-store.js';
import type {Dataset} from './dataset.js';
import {bindProject,parseProject,recalculate,digest,type Baseline,type CostSnapshot} from './project-cost.js';
interface Row {id:string;userId:string;name:string;status:string;revision:number;latest:string;emailEnabled:number;created:number;updated:number;emailSince:number;emailSinceSeq:number}
export class ProjectStore {
 readonly db;
 onSettingsChanged: (userId:string)=>void = ()=>{};
 constructor(readonly accounts:AccountStore,readonly pro:ProStore){this.db=accounts.db;accounts.transaction(()=>this.db.exec(`
 CREATE TABLE IF NOT EXISTS cost_projects(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,status TEXT NOT NULL,revision INTEGER NOT NULL,latest TEXT NOT NULL,emailEnabled INTEGER NOT NULL DEFAULT 0,emailSince INTEGER NOT NULL DEFAULT 0,emailSinceSeq INTEGER NOT NULL DEFAULT 0,created INTEGER NOT NULL,updated INTEGER NOT NULL);
 CREATE INDEX IF NOT EXISTS cost_projects_owner ON cost_projects(userId,status);
 CREATE TABLE IF NOT EXISTS cost_baselines(projectId TEXT NOT NULL REFERENCES cost_projects(id),revision INTEGER NOT NULL,userId TEXT NOT NULL,requestKey TEXT NOT NULL,payloadHash TEXT NOT NULL,payload TEXT NOT NULL,reason TEXT NOT NULL,created INTEGER NOT NULL,PRIMARY KEY(projectId,revision),UNIQUE(userId,requestKey));
 CREATE TABLE IF NOT EXISTS cost_events(id TEXT PRIMARY KEY,projectId TEXT NOT NULL REFERENCES cost_projects(id),revision INTEGER NOT NULL,kind TEXT NOT NULL,payload TEXT NOT NULL,created INTEGER NOT NULL);
 CREATE INDEX IF NOT EXISTS cost_events_project ON cost_events(projectId,created);
 `));}
 requirePlus(id:string){if(this.pro.entitlement(id).status!=='active')throw new AccountError(403,'plus_required','项目成本跟踪需要有效Plus订阅');}
 private owned(userId:string,id:string){const row=this.db.prepare('SELECT * FROM cost_projects WHERE id=? AND userId=?').get(id,userId) as unknown as Row|undefined;if(!row)throw new AccountError(404,'project_not_found','项目不存在');return row;}
 baseline(id:string,revision:number){const row=this.db.prepare('SELECT payload FROM cost_baselines WHERE projectId=? AND revision=?').get(id,revision);if(!row)throw new AccountError(503,'baseline_unavailable','基线暂不可用');return JSON.parse(String(row.payload)) as Baseline;}
 private capacity(userId:string){if(Number(this.db.prepare("SELECT COUNT(*) n FROM cost_projects WHERE userId=? AND status!='archived'").get(userId)?.n)>=5)throw new AccountError(409,'project_limit','最多保留5个在用项目，请先归档一个项目');}
 private view(row:Row){const latest=JSON.parse(row.latest) as CostSnapshot;return {id:row.id,name:row.name,status:row.status,revision:row.revision,emailEnabled:!!row.emailEnabled,created:row.created,updated:row.updated,serviceActive:this.pro.entitlement(row.userId).status==='active',baseline:this.baseline(row.id,row.revision),latest};}
 list(userId:string){return (this.db.prepare('SELECT * FROM cost_projects WHERE userId=? ORDER BY updated DESC,id LIMIT 500').all(userId) as unknown as Row[]).map(r=>this.view(r));}
 detail(userId:string,id:string){const row=this.owned(userId,id);return {...this.view(row),baselines:this.db.prepare('SELECT revision,reason,created,payload FROM cost_baselines WHERE projectId=? ORDER BY revision DESC LIMIT 50').all(id).map(r=>({revision:Number(r.revision),reason:String(r.reason),created:Number(r.created),payload:JSON.parse(String(r.payload))})),events:this.db.prepare('SELECT id,revision,kind,created,payload FROM cost_events WHERE projectId=? ORDER BY created DESC,rowid DESC LIMIT 100').all(id).map(r=>({id:String(r.id),kind:String(r.kind),revision:Number(r.revision),currency:this.baseline(id,Number(r.revision)).currency,created:Number(r.created),payload:JSON.parse(String(r.payload))}))};}
 preview(userId:string,value:unknown,ds:Dataset){this.requirePlus(userId);const baseline=bindProject(parseProject(value),ds,this.accounts.now());return {baseline,snapshot:recalculate(baseline,ds,this.accounts.now())};}
 save(userId:string,id:string|null,request:{project:unknown;datasetVersion:unknown;requestKey:unknown;revision?:unknown},ds:Dataset){
  this.requirePlus(userId);if(typeof request.requestKey!=='string'||!/^[a-zA-Z0-9_-]{16,80}$/.test(request.requestKey))throw new AccountError(400,'invalid_request_key','缺少保存请求标识');
  const parsed=parseProject(request.project),hash=digest({project:parsed,id,revision:request.revision??null});
  return this.accounts.transaction(()=>{
   const replay=this.db.prepare('SELECT projectId,payloadHash FROM cost_baselines WHERE userId=? AND requestKey=?').get(userId,String(request.requestKey));
   if(replay){if(replay.payloadHash!==hash)throw new AccountError(409,'request_conflict','同一保存标识对应不同内容');return this.detail(userId,String(replay.projectId));}
   if(request.datasetVersion!==ds.version)throw new AccountError(409,'quote_changed','报价已更新，请重新预览后确认保存');
   const old=id?this.owned(userId,id):null;if(old&&old.revision!==request.revision)throw new AccountError(409,'project_changed','项目已在其他页面修改，请刷新后重试');
   if(!old)this.capacity(userId);else if(old.status==='archived')throw new AccountError(409,'project_archived','请先恢复归档项目');
   const baseline=bindProject(parsed,ds,this.accounts.now()),snapshot=recalculate(baseline,ds,this.accounts.now()),projectId=id??randomUUID(),revision=(old?.revision??0)+1,now=this.accounts.now();
   if(old)this.db.prepare('UPDATE cost_projects SET name=?,revision=?,latest=?,updated=? WHERE id=?').run(parsed.name,revision,JSON.stringify(snapshot),now,projectId);
   else this.db.prepare("INSERT INTO cost_projects VALUES(?,?,?,'active',?,?,0,0,0,?,?)").run(projectId,userId,parsed.name,revision,JSON.stringify(snapshot),now,now);
   this.db.prepare('INSERT INTO cost_baselines VALUES(?,?,?,?,?,?,?,?)').run(projectId,revision,userId,String(request.requestKey),hash,JSON.stringify(baseline),old?'user_updated':'user_created',now);
   return this.detail(userId,projectId);
  });
 }
 action(userId:string,id:string,value:{action:unknown;revision:unknown;enabled?:unknown},ds:Dataset){return this.accounts.transaction(()=>{
  const row=this.owned(userId,id);if(row.revision!==value.revision)throw new AccountError(409,'project_changed','项目已修改，请刷新');
  const now=this.accounts.now();
  if(value.action==='email'){
   if(typeof value.enabled!=='boolean')throw new AccountError(400,'invalid_preference','请选择邮件开关');
   if(value.enabled){this.requirePlus(userId);if(row.status!=='active')throw new AccountError(409,'project_inactive','请先恢复跟踪');}
   this.db.prepare('UPDATE cost_projects SET emailEnabled=?,emailSince=CASE WHEN emailEnabled=0 AND ?=1 THEN ? ELSE emailSince END,emailSinceSeq=CASE WHEN emailEnabled=0 AND ?=1 THEN COALESCE((SELECT MAX(rowid) FROM cost_events WHERE projectId=cost_projects.id),0) ELSE emailSinceSeq END,updated=? WHERE id=?').run(Number(value.enabled),Number(value.enabled),now,Number(value.enabled),now,id);
  }else if(value.action==='pause'||value.action==='archive'){
   this.db.prepare('UPDATE cost_projects SET status=?,updated=? WHERE id=?').run(value.action==='pause'?'paused':'archived',now,id);
  }else if(value.action==='resume'){
   this.requirePlus(userId);if(row.status==='archived')this.capacity(userId);
   this.db.prepare("UPDATE cost_projects SET status='active',updated=? WHERE id=?").run(now,id);
   this.refreshInTransaction(id,ds);
  }else throw new AccountError(400,'invalid_action','不支持的项目操作');
  this.onSettingsChanged(userId);return this.detail(userId,id);
 });}
 refresh(id:string,ds:Dataset){return this.accounts.transaction(()=>this.refreshInTransaction(id,ds));}
 private refreshInTransaction(id:string,ds:Dataset){
  const row=this.db.prepare('SELECT * FROM cost_projects WHERE id=?').get(id) as unknown as Row|undefined;
  if(!row||row.status!=='active'||this.pro.entitlement(row.userId).status!=='active')return false;
  const baseline=this.baseline(id,row.revision),previous=JSON.parse(row.latest) as CostSnapshot,next=recalculate(baseline,ds,this.accounts.now(),previous);
  if(next.fingerprint!==previous.fingerprint){
   const kind=!next.complete?'quote_attention':!previous.complete?'quote_recovered':'price_changed';
   this.db.prepare('INSERT INTO cost_events VALUES(?,?,?,?,?,?)').run(randomUUID(),id,row.revision,kind,JSON.stringify({previous,next}),this.accounts.now());
  }
  this.db.prepare('UPDATE cost_projects SET latest=? WHERE id=?').run(JSON.stringify(next),id);return next.fingerprint!==previous.fingerprint;
 }
 refreshAll(ds:Dataset){let changed=0,failed=0;for(const row of this.db.prepare("SELECT id FROM cost_projects WHERE status='active' ORDER BY id").all()){try{if(this.refresh(String(row.id),ds))changed++;}catch{failed++;}}return {changed,failed};}
}
