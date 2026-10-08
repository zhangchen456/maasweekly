import { editorialCoverage } from './editorial-coverage.js';
import { randomUUID } from 'node:crypto';
import { z } from 'zod';
import type { DatasetHolder } from './dataset.js';
import { type AdminCommand, adminText } from './admin-store.js';
import { EditorialStore, packageSchema, monday, bad, hash, type FrozenInput, type ContentPackage } from './editorial-store.js';
import { modelConfig, estimate, prompt, PROMPT_VERSION } from './editorial-model.js';
import { checkPackage, requireChecks, checklistKeys } from './editorial-checks.js';
import { ProStore } from './pro-store.js';
import { publishInTransaction } from './pro-publication.js';
const fields=['id','state','version','revision','inputHash','outputHash','publicationId','runId','created','queueMail'];
export class EditorialService {
 readonly pro:ProStore;
 constructor(readonly store:EditorialStore,readonly holder:DatasetHolder){this.pro=new ProStore(store.admin.accounts);}
 get db(){return this.store.db;}
 list(params:URLSearchParams){
  for(const k of params.keys())if(!['limit','cursor'].includes(k)||params.getAll(k).length!==1)throw bad('查询参数无效');
  const limit=Number(params.get('limit')??25),cursor=params.get('cursor');if(!Number.isInteger(limit)||limit<1||limit>100||cursor&&!/^\d{4}-\d{2}-\d{2}$/.test(cursor))throw bad('分页无效');
  const rows=this.db.prepare(`SELECT id,periodEnd,state,version,currentRevision,coverage,coverageNote,createdBy,createdAt,datasetVersion,(SELECT state FROM editorial_runs r WHERE r.issueId=i.id ORDER BY createdAt DESC,id DESC LIMIT 1) latestRunState,(SELECT sum(actualCost) FROM editorial_runs r WHERE r.issueId=i.id) actualCost FROM editorial_issues i ${cursor?'WHERE periodEnd<?':''} ORDER BY periodEnd DESC LIMIT ?`).all(...(cursor?[cursor]:[]),limit+1);
  return {items:rows.slice(0,limit),nextCursor:rows.length>limit?String(rows[limit-1]!.periodEnd):null};
 }
 detail(id:string){const issue=this.store.issue(id);const r=issue.currentRevision?this.store.revision(id):null;
  return {monitorCoverage:this.holder.current?editorialCoverage(this.store.admin,issue,this.holder.current):null,coverageBasisChanged:this.holder.current?JSON.parse(issue.coverageInfo).monitor?.basisHash!==editorialCoverage(this.store.admin,issue,this.holder.current).basisHash:true,issue:{...issue,config:JSON.parse(issue.config),coverageInfo:JSON.parse(issue.coverageInfo)},revision:r?{...r,payload:JSON.parse(r.payload),checks:JSON.parse(r.checks)}:null,reviews:this.db.prepare('SELECT * FROM editorial_reviews WHERE issueId=? ORDER BY createdAt DESC,id DESC LIMIT 25').all(id).map(r=>({...r,checklist:JSON.parse(String(r.checklist))})),runs:this.db.prepare('SELECT id FROM editorial_runs WHERE issueId=? ORDER BY createdAt DESC,id DESC LIMIT 25').all(id).map(r=>this.run(String(r.id))),publications:this.db.prepare('SELECT * FROM editorial_publications WHERE issueId=? ORDER BY revision DESC LIMIT 25').all(id).map(r=>({...r,contentRefs:JSON.parse(String(r.contentRefs)),summary:JSON.parse(String(r.summary))})),composition:this.composition(id)};
 }
 inputs(id:string,params:URLSearchParams){for(const k of params.keys())if(!['cursor','limit'].includes(k)||params.getAll(k).length!==1)throw bad('查询参数无效');const limit=Number(params.get('limit')??25),offset=Number(params.get('cursor')??0);if(!Number.isInteger(limit)||limit<1||limit>100||!Number.isSafeInteger(offset)||offset<0)throw bad('分页无效');const i=this.store.issue(id),total=Number(this.db.prepare('SELECT count(*) n FROM editorial_inputs WHERE issueId=? AND snapshotId=?').get(id,i.inputHash??'')!.n);return {items:this.db.prepare('SELECT payload FROM editorial_inputs WHERE issueId=? AND snapshotId=? ORDER BY position LIMIT ? OFFSET ?').all(id,i.inputHash??'',limit,offset).map(r=>JSON.parse(String(r.payload))),nextCursor:offset+limit<total?String(offset+limit):null,total,snapshotId:i.inputHash};}
 run(id:string){const {payload,...r}=this.store.run(id);const input=JSON.parse(String(payload));return {...r,inputCount:input.inputs.length,fullSnapshotCount:Number(this.db.prepare('SELECT count(*) n FROM editorial_inputs WHERE issueId=? AND snapshotId=?').get(String(r.issueId),String(input.snapshotHash))!.n),config:JSON.parse(String(r.config)),usage:JSON.parse(String(r.usage)),result:r.result?JSON.parse(String(r.result)):null};}
 composition(id:string){const i=this.store.issue(id);const existing=Number(this.db.prepare('SELECT count(*) n FROM pro_reports WHERE period=?').get(i.periodEnd)!.n);const eligible=this.db.prepare('SELECT userId FROM pro_settings').all().filter(r=>this.pro.entitlement(String(r.userId)).status==='active');const possible=eligible.filter(r=>!this.db.prepare('SELECT 1 FROM pro_reports WHERE userId=? AND period=?').get(String(r.userId),i.periodEnd)).length;return {existing,possible,contains:'仅组合匹配的 explainer/comparison，不包含统一 briefing 全文',mail:this.db.prepare('SELECT m.status,count(*) count,min(m.created) firstCreated,max(m.created) lastCreated FROM pro_mail m JOIN pro_reports r ON r.id=m.reportId WHERE r.period=? GROUP BY m.status').all(i.periodEnd),sentMeaning:'供应商已接受，不能据此确认已送达'};}
 write(c:AdminCommand,op:string){return this.store.admin.command(c,fields,fields,()=>{
  const id=c.targetId,input=c.input;let result:Record<string,unknown>;let audit:false|undefined;const before=op==='create'?null:{id,state:this.store.issue(id).state,version:this.store.issue(id).version};
  if(op==='create'){
   const period=adminText(input.periodEnd,'期次',10),window=monday(period);const selection=adminText(input.selection,'选题说明',2000),budget=Number(input.budget);if(!Number.isFinite(budget)||budget<0||budget>10000)throw bad('预算无效');
   const existing=this.db.prepare('SELECT id FROM editorial_issues WHERE periodEnd=?').get(period);
   if(existing)result={id:String(existing.id),created:false};else {const config=modelConfig();this.db.prepare("INSERT INTO editorial_issues(id,periodEnd,windowFrom,windowTo,coverage,coverageNote,selection,state,budget,config,createdBy,createdAt) VALUES(?,?,?,?,'partial','尚未冻结证据',?,'draft',?,?,?,?)").run(id,period,window.from,window.to,selection,budget,JSON.stringify(config),c.actor.id,this.store.now);result={id,created:true};}
  }else if(op==='prepare'){
   const i=this.store.issue(id),ds=this.holder.current;if(!ds)throw bad('有效数据集不可用','data_unavailable',503);
   if(!['normal','partial','failed'].includes(String(input.coverage)))throw bad('请选择覆盖状态');const note=adminText(input.coverageNote,'覆盖说明',2000);
   const cutoff=i.periodEnd,from=i.windowFrom.slice(0,10);const selected=ds.changes.filter(e=>e.status==='active'&&e.observationDate>=from&&e.observationDate<cutoff&&/^https?:/.test(e.links.sourceUrl??'')).slice(0,500);
   const inputs:FrozenInput[]=selected.map(e=>({id:e.id,revision:e.revision,url:e.links.sourceUrl!,observedAt:e.observedAt??e.observationDate,providerId:e.providerId,modelId:e.modelId??null,familyId:e.familyId??null,title:e.title,excerpt:([e.summary??'',...e.evidenceIds.map(id=>ds.evidenceById.get(id)?.excerptText??'')].join('\n')).slice(0,4000),price:e.price?{...e.price}:null,status:e.status,hash:hash(JSON.stringify(e))}));
   const monitor=editorialCoverage(this.store.admin,i,ds);
   if(monitor.limited&&(input.coverage==='normal'||input.monitorAcknowledgedHash!==monitor.basisHash))throw bad('同窗口相关来源失败或覆盖受限；选择partial/failed、披露限制并确认当前监控依据','monitor_coverage_conflict',409);
   const missingSources=ds.status.sourceStreams.filter(s=>monitor.sourceIds.includes(s.sourceId)&&s.state==='failing'&&s.lastAttemptDate!==null&&s.lastAttemptDate>=from&&s.lastAttemptDate<cutoff);
   if(input.coverage==='normal'&&(!inputs.length||ds.dataThrough.slice(0,10)<new Date(Date.parse(i.windowTo)-86400000).toISOString().slice(0,10)||missingSources.length))throw bad('覆盖不足，需选择partial/failed并披露限制');
   const inputHash=hash(JSON.stringify({version:ds.version,inputs,coverage:input.coverage,note,selection:i.selection,monitorHash:monitor.basisHash}));
   inputs.forEach((e,n)=>this.db.prepare('INSERT OR IGNORE INTO editorial_inputs VALUES(?,?,?,?)').run(id,inputHash,n,JSON.stringify(e)));
   this.db.prepare("UPDATE editorial_issues SET datasetVersion=?,coverage=?,coverageNote=?,dataThrough=?,inputHash=?,coverageInfo=?,state='draft',version=version+1 WHERE id=?").run(ds.version,String(input.coverage),note,ds.dataThrough,inputHash,JSON.stringify({monitor,missingSources,sourceCoverage:ds.coverage,truncated:selected.length===500,zeroEvidence:!inputs.length}),id);
   this.db.prepare("UPDATE editorial_runs SET errorCode=CASE WHEN state='running' AND json_extract(config,'$.adapter')='openai' THEN 'cancelled_outcome_unknown' ELSE errorCode END,state='cancelled',fencingVersion=fencingVersion+1,version=version+1,finishedAt=? WHERE issueId=? AND state IN ('queued','running')").run(this.store.now,id);
   result={id,inputHash,version:this.store.issue(id).version,state:'draft'};
  }else if(op==='revisions'){
   const parsed=packageSchema.safeParse(input.package);if(!parsed.success)throw bad('稿件包结构无效，需一份briefing及不超过12篇内容');result=this.saveRevision(id,parsed.data,c.actor.id);
  }else if(op==='review'){
   const i=this.store.issue(id),r=this.store.revision(id);if(input.revision!==r.revision||input.outputHash!==r.outputHash||r.inputHash!==i.inputHash)throw bad('稿件或证据已更新','version_conflict',409);
   const decision=String(input.decision);if(!['submit','approve','reject'].includes(decision))throw bad('审核决策无效');
   if(decision==='approve'){
    this.requireCoverageBasis(i);
    if(i.state!=='in_review')throw bad('先提交审核','invalid_state',409);
    const checks=checkPackage(packageSchema.parse(JSON.parse(r.payload)),i,this.store.inputs(id),this.holder.current??undefined);requireChecks(checks);
    if(!this.holder.current)throw bad('当前数据不可用','data_unavailable',503);
    if(!input.checklist||checklistKeys.some(k=>(input.checklist as Record<string,unknown>)[k]!==true))throw bad('必须完成全部人工检查');
   }
   this.db.prepare('INSERT INTO editorial_reviews VALUES(?,?,?,?,?,?,?,?,?)').run(randomUUID(),id,r.revision,r.outputHash,JSON.stringify(input.checklist??{}),decision,adminText(input.note,'审核意见',2000),c.actor.id,this.store.now);
   this.store.bump(id,decision==='approve'?'approved':decision==='submit'?'in_review':'draft');result={id,state:this.store.issue(id).state,version:this.store.issue(id).version};
  }else if(op==='publish'){
   const i=this.store.issue(id),r=this.store.revision(id);if(input.revision!==r.revision||input.outputHash!==r.outputHash)throw bad('审核版本不一致','version_conflict',409);
   const previous=this.db.prepare('SELECT id FROM editorial_publications WHERE issueId=? AND revision=?').get(id,r.revision);
   if(previous){result={publicationId:String(previous.id),id,state:'published'};audit=false;}
   else {
    if(i.state!=='approved'||r.inputHash!==i.inputHash||!this.db.prepare("SELECT 1 FROM editorial_reviews WHERE issueId=? AND revision=? AND outputHash=? AND decision='approve'").get(id,r.revision,r.outputHash))throw bad('当前版本尚未批准','review_required',409);
    this.requireCoverageBasis(i);
    const ds=this.holder.current;if(!ds)throw bad('当前数据不可用','data_unavailable',503);const pack=packageSchema.parse(JSON.parse(r.payload));requireChecks(checkPackage(pack,i,this.store.inputs(id),ds));
    const refs=[];for(const content of pack.contents){const next=Number(this.db.prepare('SELECT coalesce(max(version),0)+1 n FROM pro_content WHERE id=?').get(content.id)!.n);const formal={...content,version:next};this.pro.draftInTransaction(formal,c.actor.id);this.pro.transitionInTransaction(content.id,next,'review',c.actor.id,c.reason);publishInTransaction(this.pro,content.id,next,c.actor.id,c.reason,ds);refs.push({id:content.id,version:next,kind:content.kind});}
    const publicationId=randomUUID();this.db.prepare('INSERT INTO editorial_publications(id,issueId,revision,contentRefs,publishedAt,actorId) VALUES(?,?,?,?,?,?)').run(publicationId,id,r.revision,JSON.stringify(refs),this.store.now,c.actor.id);this.store.bump(id,'published');result={id,publicationId,state:'published',version:this.store.issue(id).version};
   }
  }else if(op==='compose'){
   const i=this.store.issue(id),p=this.db.prepare('SELECT id,compositionState FROM editorial_publications WHERE issueId=? AND revision=?').get(id,i.currentRevision);if(!p)throw bad('请先出版','publication_required',409);if(typeof input.queueMail!=='boolean')throw bad('请明确邮件入队选项');
   if(p.compositionState==='succeeded')result={id,created:0};else {const created=this.pro.composeInTransaction(i.periodEnd,i.coverage,input.queueMail);this.db.prepare("UPDATE editorial_publications SET compositionState='succeeded',queueMail=?,summary=? WHERE id=?").run(Number(input.queueMail),JSON.stringify({created}),String(p.id));this.store.bump(id,'published');result={id,created,queueMail:input.queueMail,version:this.store.issue(id).version};}
  }else if(op==='runs')result=this.enqueue(id,input);
  else throw bad('未知操作');
  return {result,before,audit,after:op==='create'?{id:String(result.id)}:{id,state:this.store.issue(id).state,version:this.store.issue(id).version}};
 });}
 requireCoverageBasis(i:import('./editorial-store.js').Issue){const ds=this.holder.current;if(!ds)throw bad('当前数据不可用','data_unavailable',503);const current=editorialCoverage(this.store.admin,i,ds),frozen=JSON.parse(i.coverageInfo).monitor;if(!frozen||current.basisHash!==frozen.basisHash)throw bad('来源/公开投影或数据版本的放行依据已变化；重新冻结、编辑和审核','coverage_basis_changed',409);if(current.limited&&i.coverage==='normal')throw bad('相关来源受限，不能normal出版','monitor_coverage_conflict',409);}
 saveRevision(id:string,pack:ContentPackage,actor:string,runId:string|null=null){const i=this.store.issue(id);if(!i.inputHash)throw bad('请先冻结素材');const checks=checkPackage(pack,i,this.store.inputs(id));
  // Cross-issue IDs cannot overwrite another issue or a CLI-owned content stream.
  const allowed=`editorial-${i.periodEnd}-`;if(pack.contents.some(c=>!c.id.startsWith(allowed)))throw bad(`内容ID必须以 ${allowed} 开头`);
  const revision=i.currentRevision+1,payload=JSON.stringify(pack),outputHash=hash(payload);this.db.prepare('INSERT INTO editorial_revisions VALUES(?,?,?,?,?,?,?,?,?)').run(id,revision,payload,i.inputHash,outputHash,actor,this.store.now,runId,JSON.stringify(checks));this.db.prepare("UPDATE editorial_issues SET currentRevision=?,state='draft',version=version+1 WHERE id=?").run(revision,id);
  this.db.prepare("UPDATE editorial_runs SET state='cancelled',fencingVersion=fencingVersion+1,version=version+1,finishedAt=? WHERE issueId=? AND stage='verify' AND state IN ('queued','running')").run(this.store.now,id);
  return {id,revision,outputHash,version:this.store.issue(id).version,state:'draft'};
 }
 enqueue(id:string,input:Record<string,unknown>){const i=this.store.issue(id),stage=String(input.stage);if(!['prepare','curate','analyze','verify'].includes(stage)||!i.inputHash)throw bad('阶段无效或尚未冻结素材');
  let upstream:unknown=null;if(stage==='analyze'){const row=this.db.prepare("SELECT result FROM editorial_runs WHERE issueId=? AND stage='curate' AND state='succeeded' AND json_extract(payload,'$.snapshotHash')=? ORDER BY finishedAt DESC LIMIT 1").get(id,i.inputHash);if(!row)throw bad('请先完成选题阶段');upstream=JSON.parse(String(row.result));}if(stage==='verify')upstream=JSON.parse(this.store.revision(id).payload);
  const config=JSON.parse(i.config),inputs=this.store.inputs(id);const inputHash=hash(JSON.stringify({snapshotHash:i.inputHash,stage,upstream,prompt:PROMPT_VERSION,config}));
  if(this.db.prepare("SELECT 1 FROM editorial_runs WHERE issueId=? AND stage=? AND inputHash=? AND errorCode IN ('provider_outcome_unknown','lease_expired_outcome_unknown','usage_unknown','cancelled_outcome_unknown')").get(id,stage,inputHash))throw bad('供应商执行状态未知，先核对并记录恢复材料','recovery_required',409);
  const existing=this.db.prepare("SELECT id,state FROM editorial_runs WHERE issueId=? AND stage=? AND inputHash=? AND state IN ('queued','running','needs_review','succeeded') ORDER BY createdAt DESC LIMIT 1").get(id,stage,inputHash);if(existing)return {runId:String(existing.id),state:String(existing.state)};
  const attempts=Number(this.db.prepare('SELECT coalesce(sum(attempt),0) n FROM editorial_runs WHERE issueId=?').get(id)!.n);if(attempts>=30)throw bad('本期已达30次调用硬限制','call_limit',409);
  const cost=stage==='prepare'?0:estimate(config);const spent=Number(this.db.prepare('SELECT coalesce(sum(reserved),0) n FROM editorial_runs WHERE issueId=?').get(id)!.n);if(cost!==null&&spent+cost*3>i.budget)throw bad('预算不足，未创建任务','budget_exceeded',409);
  const runId=randomUUID(),payload={stage,periodEnd:i.periodEnd,windowFrom:i.windowFrom,windowTo:i.windowTo,coverage:i.coverage,coverageNote:i.coverageNote,dataThrough:i.dataThrough!,selection:i.selection,inputs,upstream,baseRevision:i.currentRevision,snapshotHash:i.inputHash};
  while(payload.inputs.length&&Buffer.byteLength(prompt(payload))>config.maxInputTokens)payload.inputs=payload.inputs.slice(0,-1);
  if(stage!=='prepare'&&!payload.inputs.length)throw bad('输入超限，无法容纳单条素材','input_limit',409);
  this.db.prepare("INSERT INTO editorial_runs(id,issueId,stage,state,inputHash,config,budget,reserved,estimatedCost,createdAt,payload) VALUES(?,?,?,'queued',?,?,?,?,?,?,?)").run(runId,id,stage,inputHash,i.config,i.budget,cost===null?0:cost*3,cost,this.store.now,JSON.stringify(payload));this.store.bump(id,i.state);return {runId,state:'queued',version:this.store.issue(id).version};
 }
 reconcile(c:AdminCommand){return this.store.admin.command(c,['id','state','version'],['id','state','version'],()=>{const r=this.store.run(c.targetId);if(!['needs_review','cancelled'].includes(String(r.state))||!['not_executed','executed'].includes(String(c.input.outcome)))throw bad('需明确供应商已执行或未执行结果');adminText(c.input.note,'供应商核对材料',2000);const cost=c.input.actualCost;if(cost!==null&&(typeof cost!=='number'||!Number.isFinite(cost)||cost<0))throw bad('实际费用无效');const usage=JSON.parse(String(r.usage));usage.push({reconciledBy:c.actor.id,outcome:c.input.outcome,note:c.input.note,actualCost:cost,at:this.store.now});this.db.prepare("UPDATE editorial_runs SET state='failed',errorCode='operator_reconciled',usage=?,actualCost=?,version=version+1,fencingVersion=fencingVersion+1 WHERE id=?").run(JSON.stringify(usage),cost===null?(r.actualCost??null):cost,c.targetId);return {result:{id:c.targetId,state:'failed',version:Number(r.version)+1},before:{id:c.targetId,state:String(r.state),version:Number(r.version)},after:{id:c.targetId,state:'failed',version:Number(r.version)+1}};});}

 cancel(c:AdminCommand){return this.store.admin.command(c,['id','state','version'],['id','state','version'],()=>{const r=this.store.run(c.targetId);if(!['queued','running','needs_review'].includes(String(r.state)))throw bad('任务已结束','invalid_state',409);this.db.prepare("UPDATE editorial_runs SET errorCode=CASE WHEN state='running' AND json_extract(config,'$.adapter')='openai' THEN 'cancelled_outcome_unknown' ELSE errorCode END,state='cancelled',fencingVersion=fencingVersion+1,version=version+1,finishedAt=? WHERE id=?").run(this.store.now,c.targetId);return {result:{id:c.targetId,state:'cancelled',version:Number(r.version)+1},before:{id:c.targetId,state:String(r.state),version:Number(r.version)},after:{id:c.targetId,state:'cancelled',version:Number(r.version)+1}};});}
}
