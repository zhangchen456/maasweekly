/** Reuse the existing digest queue, lease and acceptance ledger; one daily project batch per account. */
import {randomUUID} from 'node:crypto';
import type {ProjectStore} from './project-store.js';
import type {CostSnapshot} from './project-cost.js';
export class ProjectDelivery {
 readonly db;
 constructor(readonly projects:ProjectStore){this.db=projects.db;projects.accounts.transaction(()=>this.db.exec(`
 CREATE TABLE IF NOT EXISTS cost_mail_batches(jobId TEXT PRIMARY KEY REFERENCES mail_jobs(id),userId TEXT NOT NULL,day TEXT NOT NULL,eventIds TEXT NOT NULL,frozenIds TEXT,UNIQUE(userId,day));
 CREATE TABLE IF NOT EXISTS cost_mail_links(eventId TEXT PRIMARY KEY REFERENCES cost_events(id),jobId TEXT NOT NULL REFERENCES mail_jobs(id));
 `));
 projects.onSettingsChanged=id=>this.prune(id);
 projects.accounts.retainDigest=(_id,jobId)=>this.events(jobId).length>0;
 projects.accounts.onUnsubscribe=id=>{this.cancelAll(id);this.prune(id);};
 projects.accounts.mailEligible=(id,jobId)=>!!this.db.prepare('SELECT 1 FROM users WHERE id=? AND emailEnabled=1').get(id)||this.events(jobId).length>0;
 }
 events(jobId:string){
  const batch=this.db.prepare('SELECT eventIds,frozenIds,userId FROM cost_mail_batches WHERE jobId=?').get(jobId);if(!batch||this.projects.pro.entitlement(String(batch.userId)).status!=='active')return [];
  const rows: {id:string;projectId:string;revision:number;name:string;kind:string;next:CostSnapshot;previous:CostSnapshot;currency:string;created:number}[]=[];
  for(const id of JSON.parse(String(batch.frozenIds??batch.eventIds)) as string[]){
   const row=this.db.prepare("SELECT e.*,p.name FROM cost_events e JOIN cost_projects p ON p.id=e.projectId WHERE e.id=? AND p.userId=? AND p.status='active' AND p.emailEnabled=1 AND e.revision=p.revision AND e.created>=p.emailSince AND e.rowid>p.emailSinceSeq").get(id,String(batch.userId));if(!row)continue;
   rows.push({id:String(row.id),projectId:String(row.projectId),revision:Number(row.revision),name:String(row.name),kind:String(row.kind),next:JSON.parse(String(row.payload)).next,previous:JSON.parse(String(row.payload)).previous,currency:this.projects.baseline(String(row.projectId),Number(row.revision)).currency,created:Number(row.created)});
  }
  return rows;
 }
 freeze(jobId:string,mail:string,ids:string[]){this.projects.accounts.transaction(()=>{this.projects.accounts.freezeMail(jobId,mail);this.db.prepare('UPDATE cost_mail_batches SET frozenIds=COALESCE(frozenIds,?) WHERE jobId=?').run(JSON.stringify(ids),jobId);});}
 frozenMatches(jobId:string){const row=this.db.prepare('SELECT frozenIds FROM cost_mail_batches WHERE jobId=?').get(jobId);return !row||String(row.frozenIds??'[]')===JSON.stringify(this.events(jobId).map(e=>e.id));}
 hasBatch(id:string){return !!this.db.prepare('SELECT 1 FROM cost_mail_batches WHERE jobId=?').get(id);}
 prune(userId?:string){
  const jobs=this.db.prepare("SELECT j.id,j.userId,j.payload FROM mail_jobs j JOIN cost_mail_batches b ON b.jobId=j.id WHERE j.status='pending' AND j.lease=0").all();
  for(const j of jobs){if(userId&&j.userId!==userId)continue;if(!this.events(String(j.id)).length&&(!JSON.parse(String(j.payload)).length||!this.db.prepare('SELECT 1 FROM users WHERE id=? AND emailEnabled=1').get(String(j.userId))))this.db.prepare("UPDATE mail_jobs SET status='cancelled' WHERE id=?").run(String(j.id));}
 }
 enqueue(){return this.projects.accounts.transaction(()=>{
  this.prune();const now=this.projects.accounts.now(),day=new Date(now+8*3600000).toISOString().slice(0,10);let queued=0;
  const users=this.db.prepare("SELECT DISTINCT p.userId FROM cost_events e JOIN cost_projects p ON p.id=e.projectId LEFT JOIN cost_mail_links l ON l.eventId=e.id WHERE l.eventId IS NULL AND p.status='active' AND p.emailEnabled=1 AND e.revision=p.revision AND e.created>=p.emailSince AND e.rowid>p.emailSinceSeq").all();
  for(const user of users){const uid=String(user.userId);if(this.projects.pro.entitlement(uid).status!=='active'||this.db.prepare('SELECT 1 FROM cost_mail_batches WHERE userId=? AND day=?').get(uid,day))continue;
   const events=this.db.prepare("SELECT e.id,e.projectId FROM cost_events e JOIN cost_projects p ON p.id=e.projectId LEFT JOIN cost_mail_links l ON l.eventId=e.id WHERE p.userId=? AND p.status='active' AND p.emailEnabled=1 AND e.revision=p.revision AND e.created>=p.emailSince AND e.rowid>p.emailSinceSeq AND l.eventId IS NULL ORDER BY e.created DESC,e.rowid DESC LIMIT 500").all(uid);
   const latest=new Map<string,string>();for(const e of events)if(!latest.has(String(e.projectId)))latest.set(String(e.projectId),String(e.id));
   if(!latest.size)continue;
   // Attach to an unfrozen, unclaimed normal digest, preserving its model updates.
   const pending=this.db.prepare("SELECT id FROM mail_jobs WHERE userId=? AND status='pending' AND lease=0 AND mail IS NULL ORDER BY created LIMIT 1").get(uid);const id=pending?String(pending.id):randomUUID();
   if(!pending)this.db.prepare("INSERT INTO mail_jobs(id,userId,payload,created) VALUES(?,?,'[]',?)").run(id,uid,now);
   this.db.prepare('INSERT INTO cost_mail_batches(jobId,userId,day,eventIds) VALUES(?,?,?,?)').run(id,uid,day,JSON.stringify([...latest.values()]));
   for(const e of events)this.db.prepare('INSERT INTO cost_mail_links VALUES(?,?)').run(String(e.id),id);
   queued++;
  }return queued;
 });}
 text(jobId:string,origin:string){return this.events(jobId).map(e=>{
  const n=e.next;const money=(v:string|null)=>v===null?'暂不可计算':`${e.currency} ${Number(v).toLocaleString('zh-CN',{maximumFractionDigits:6})}`;
  const state=e.kind==='quote_attention'?'报价需核对':e.kind==='quote_recovered'?'报价恢复':'价格变化';
  const reasons=n.lines.map((l,i)=>{const before=e.previous.lines[i];const rate=(q:any,old:any)=>q?`${old?.amount??'?'} → ${q.amount} ${q.currency} / ${q.unitQuantity} tokens`:'不使用或暂不可核对';return `${l.label||l.modelName}（${l.platform}）：${l.state==='ok'?`${money(l.cost)}；输入 ${rate(l.input,before?.input)}；输出 ${rate(l.output,before?.output)}`:'报价缺失、陈旧或条件需核对'}`;}).join('\n');
  return `${e.name} · ${state}\n${n.complete?'预计月成本':'可计算部分（不是完整总额）'}：${money(n.cost)}\n相对当前基线：${money(n.baselineDelta)}\n${reasons}\n数据截至：${n.dataThrough}\n项目详情：${origin}/projects/?id=${encodeURIComponent(e.projectId)}`;
 }).join('\n\n');}
 cancelAll(userId:string){this.db.prepare('UPDATE cost_projects SET emailEnabled=0 WHERE userId=?').run(userId);}
}
