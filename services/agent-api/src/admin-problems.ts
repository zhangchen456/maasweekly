import { randomUUID } from 'node:crypto';
import { readFileSync } from 'node:fs';
import { z } from 'zod';
import { AccountError, hash } from './account-store.js';
import { AdminStore, adminText, timestamp, type AdminCommand } from './admin-store.js';
import { AdminFeedback } from './admin-feedback.js';
import { AdminMonitor } from './admin-monitor.js';
import { EditorialStore } from './editorial-store.js';
import { AdminDelivery } from './admin-delivery.js';
import { invalid, query, page, reference, optionalText } from './admin-operations.js';
import { modelConfig, modelConfigSchema, estimate, prompt, type ModelInput } from './editorial-model.js';
export const repairStages=['pending','candidate','merged','released','verify_pending','verified'];
const text=z.string().min(1).max(2000), strings=z.array(text).max(30);
export const diagnosisSchema=z.object({facts:z.array(z.object({text,source:text}).strict()).max(30),missingInformation:strings,possibleCauses:z.array(z.object({cause:text,evidence:strings,uncertainty:text}).strict()).max(30),reproductionAndValidation:strings,repairDirections:z.array(z.object({direction:text,impact:text}).strict()).max(30)}).strict();
const materialSchema=z.object({description:z.string().min(1).max(4000),reproduction:z.string().max(4000).default(''),versions:z.string().max(2000).default(''),errorSummary:z.string().max(4000).default(''),redactionConfirmed:z.literal(true),screenshots:z.array(z.object({feedbackId:z.string(),index:z.number().int().min(0).max(2)}).strict()).max(3).default([])}).strict();
const requiredText=(value:unknown,label:string,max:number)=>{const result=optionalText(value,max);if(!result)throw invalid(label+'不能为空');return result;};
const auditFields=['id','version','entryId','repairStage','relatedId','kind','active'];
export class AdminProblems {
 readonly feedback:AdminFeedback;readonly monitor:AdminMonitor;
 constructor(readonly admin:AdminStore){this.feedback=new AdminFeedback(admin);new EditorialStore(admin);this.monitor=new AdminMonitor(admin);new AdminDelivery(admin);admin.accounts.transaction(()=>{
 if(admin.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=7').get())return;
 admin.db.exec(`CREATE TABLE problems(id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,reproduction TEXT NOT NULL DEFAULT '',versionInfo TEXT NOT NULL DEFAULT '',repairStage TEXT NOT NULL DEFAULT 'pending',selectedFixId TEXT REFERENCES problem_refs(id),selectedReleaseId TEXT REFERENCES problem_refs(id),version INTEGER NOT NULL DEFAULT 0,createdAt INTEGER NOT NULL,updatedAt INTEGER NOT NULL,actorId TEXT NOT NULL);
 CREATE INDEX problems_order ON problems(updatedAt DESC,id DESC);
 CREATE TABLE problem_links(problemId TEXT NOT NULL REFERENCES problems(id),kind TEXT NOT NULL,relatedId TEXT NOT NULL,active INTEGER NOT NULL CHECK(active IN (0,1)),actorId TEXT NOT NULL,updatedAt INTEGER NOT NULL,PRIMARY KEY(problemId,kind,relatedId));
 CREATE UNIQUE INDEX problem_feedback_active ON problem_links(relatedId) WHERE kind='feedback' AND active=1;
 CREATE TABLE problem_refs(id TEXT PRIMARY KEY,problemId TEXT NOT NULL REFERENCES problems(id),kind TEXT NOT NULL,value TEXT NOT NULL,trust TEXT NOT NULL CHECK(trust IN ('manual','verified','query_failed')),source TEXT NOT NULL,checkedAt INTEGER,actorId TEXT NOT NULL,createdAt INTEGER NOT NULL,active INTEGER NOT NULL DEFAULT 1);
 CREATE TABLE problem_checks(id TEXT PRIMARY KEY,problemId TEXT NOT NULL REFERENCES problems(id),refId TEXT NOT NULL REFERENCES problem_refs(id),releaseRefId TEXT NOT NULL REFERENCES problem_refs(id),result TEXT NOT NULL,environment TEXT NOT NULL,note TEXT NOT NULL,actorId TEXT NOT NULL,createdAt INTEGER NOT NULL);
 CREATE TABLE diagnostic_runs(id TEXT PRIMARY KEY,problemId TEXT NOT NULL REFERENCES problems(id),taskType TEXT NOT NULL DEFAULT 'problem_diagnosis',state TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 0,inputHash TEXT NOT NULL,config TEXT NOT NULL,budget REAL NOT NULL,reserved REAL NOT NULL,estimatedCost REAL,actualCost REAL,attempt INTEGER NOT NULL DEFAULT 0,leaseOwner TEXT,leaseUntil INTEGER NOT NULL DEFAULT 0,fencingVersion INTEGER NOT NULL DEFAULT 0,usage TEXT NOT NULL DEFAULT '[]',errorCode TEXT,result TEXT,createdAt INTEGER NOT NULL,startedAt INTEGER,finishedAt INTEGER,availableAt INTEGER NOT NULL DEFAULT 0,payload TEXT NOT NULL);
 CREATE INDEX diagnostic_runs_order ON diagnostic_runs(createdAt DESC,id DESC);
 CREATE UNIQUE INDEX diagnostic_runs_dedupe ON diagnostic_runs(problemId,inputHash) WHERE state IN ('queued','running','needs_review','succeeded');`);
 admin.db.prepare('INSERT INTO admin_schema_migrations VALUES(7,?)').run(admin.accounts.now());});}
 get db(){return this.admin.db;}
 problem(id:string){const r=this.db.prepare('SELECT * FROM problems WHERE id=?').get(id);if(!r)throw new AccountError(404,'not_found','问题不存在');return r;}
 version(id:string){return Number(this.problem(id).version);}
 list(params:URLSearchParams){query(params,['repairStage']);const stage=params.get('repairStage');if(stage&&!repairStages.includes(stage))throw invalid('进度无效');return page(this.admin,params,'problems','SELECT id,title,repairStage,version,updatedAt FROM problems'+(stage?' WHERE repairStage=?':''),stage?[stage]:[],['updatedAt','id']);}
 run(id:string){const r=this.db.prepare('SELECT * FROM diagnostic_runs WHERE id=?').get(id);if(!r)throw new AccountError(404,'not_found','诊断任务不存在');return r;}
 projectRun(r:any){const {payload,config,leaseOwner,...safe}=r;const material=JSON.parse(payload);return {...safe,usage:JSON.parse(String(r.usage)),result:r.result?JSON.parse(String(r.result)):null,promptVersion:'diagnosis-v1',material:{...material,screenshots:material.screenshots.map((s:any)=>({feedbackId:s.feedbackId,index:s.index}))},config:JSON.parse(config)};}
 detail(id:string){const problem=this.problem(id),links=this.db.prepare('SELECT * FROM problem_links WHERE problemId=? AND active=1 ORDER BY kind,relatedId').all(id);return {problem,links,relatedUsers:this.db.prepare("SELECT DISTINCT f.userId FROM problem_links l JOIN feedback f ON f.id=l.relatedId WHERE l.problemId=? AND l.kind='feedback' AND l.active=1 UNION SELECT relatedId FROM problem_links WHERE problemId=? AND kind='user' AND active=1").all(id,id),references:this.db.prepare('SELECT * FROM problem_refs WHERE problemId=? ORDER BY createdAt DESC,rowid DESC LIMIT 100').all(id),checks:this.db.prepare('SELECT * FROM problem_checks WHERE problemId=? ORDER BY rowid DESC LIMIT 100').all(id),runs:this.db.prepare('SELECT * FROM diagnostic_runs WHERE problemId=? ORDER BY createdAt DESC,id DESC LIMIT 25').all(id).map(r=>this.projectRun(r)),developerTask:`问题：${problem.title}\n描述：${problem.description}\n复现：${problem.reproduction}\n版本：${problem.versionInfo}\n要求：核对引用与影响范围，修复后独立确认合并、发布和逐条线上验证。AI建议不能证明根因。`};}
 validateLink(problemId:string,kind:string,id:string){
 if(kind==='feedback')this.feedback.ops(id);
 else if(kind==='user'){if(!this.db.prepare('SELECT 1 FROM users WHERE id=?').get(id))throw invalid('用户不存在');}
 else if(kind==='content'){const split=id.lastIndexOf('@'),version=Number(id.slice(split+1));if(split<1||!Number.isSafeInteger(version)||!this.db.prepare('SELECT 1 FROM pro_content WHERE id=? AND version=?').get(id.slice(0,split),version))throw invalid('内容版本不存在；格式 ID@VERSION');}
 else if(kind==='anomaly')this.monitor.anomalyVersion(id);
 else if(kind==='run')this.monitor.run(id);
 else if(kind==='problem'){this.problem(id);const visit=(current:string,seen:Set<string>)=>{if(current===problemId)throw invalid('问题关联不能循环');if(seen.has(current))return;seen.add(current);for(const r of this.db.prepare("SELECT relatedId FROM problem_links WHERE problemId=? AND kind='problem' AND active=1").all(current))visit(String(r.relatedId),seen);};visit(id,new Set());}
 else throw invalid('关联类型无效');
 }
 write(c:AdminCommand,op:string){c={...c,...(op==='create'?{}:{currentVersion:()=>this.version(c.targetId)})};return this.admin.command(c,auditFields,[...auditFields,'created','runId','state'],()=>{
 const id=c.targetId,i=c.input,now=this.admin.accounts.now();const before=op==='create'?null:{id,version:this.version(id),repairStage:this.problem(id).repairStage};let entryId:string|null=null,result:Record<string,unknown>={id};
 if(op==='create'){this.db.prepare('INSERT INTO problems(id,title,description,reproduction,versionInfo,createdAt,updatedAt,actorId) VALUES(?,?,?,?,?,?,?,?)').run(id,adminText(i.title,'标题',200),requiredText(i.description,'描述',4000),i.reproduction===undefined?'':optionalText(i.reproduction,4000),i.versionInfo===undefined?'':optionalText(i.versionInfo,2000),now,now,c.actor.id);result.created=true;}
 else if(op==='update'){const p=this.problem(id);this.db.prepare('UPDATE problems SET title=?,description=?,reproduction=?,versionInfo=? WHERE id=?').run(i.title===undefined?String(p.title):adminText(i.title,'标题',200),i.description===undefined?String(p.description):requiredText(i.description,'描述',4000),i.reproduction===undefined?String(p.reproduction):optionalText(i.reproduction,4000),i.versionInfo===undefined?String(p.versionInfo):optionalText(i.versionInfo,2000),id);}
 else if(op==='link'||op==='unlink'){
 const kind=adminText(i.kind,'关联类型',30),relatedId=adminText(i.relatedId,'关联ID',200);if(i.confirmed!==true)throw invalid('归并或解除需管理员明确确认');this.validateLink(id,kind,relatedId);
 if(op==='link'&&kind==='feedback'){const existing=this.db.prepare("SELECT problemId FROM problem_links WHERE kind='feedback' AND relatedId=? AND active=1").get(relatedId);if(existing&&existing.problemId!==id)throw invalid('反馈已关联其他问题，请先解除');}
 if(op==='unlink'&&!this.db.prepare('SELECT 1 FROM problem_links WHERE problemId=? AND kind=? AND relatedId=? AND active=1').get(id,kind,relatedId))throw invalid('关联不存在');
 this.db.prepare('INSERT INTO problem_links VALUES(?,?,?,?,?,?) ON CONFLICT(problemId,kind,relatedId) DO UPDATE SET active=excluded.active,actorId=excluded.actorId,updatedAt=excluded.updatedAt').run(id,kind,relatedId,op==='link'?1:0,c.actor.id,now);result={...result,kind,relatedId,active:op==='link'};
 }else if(op==='references'){
 const kind=String(i.kind),trust=String(i.trust);if(!['repository','issue','pr','commit','release'].includes(kind)||!['manual','verified','query_failed'].includes(trust))throw invalid('引用类型或来源状态无效');const value=reference(i.value),source=requiredText(i.source,'来源与核验材料',2000);let checkedAt:number|null=null;
 if(trust!=='manual'){checkedAt=timestamp(String(i.checkedAt));if(!Number.isFinite(checkedAt)||!/(Z|[+-]\d\d:\d\d)$/.test(String(i.checkedAt))||checkedAt>now)throw invalid('需实际查询时间');}
 entryId=randomUUID();this.db.prepare('INSERT INTO problem_refs VALUES(?,?,?,?,?,?,?,?,?,1)').run(entryId,id,kind,value,trust,source,checkedAt,c.actor.id,now);
 }else if(op==='remove-reference'){
 const ref=this.ref(id,String(i.refId));entryId=String(ref.id);this.db.prepare('UPDATE problem_refs SET active=0 WHERE id=?').run(entryId);this.db.prepare("UPDATE problems SET repairStage='pending',selectedFixId=NULL,selectedReleaseId=NULL WHERE id=?").run(id);
 }else if(op==='progress'){
 const stage=String(i.repairStage);if(!repairStages.includes(stage))throw invalid('修复进度无效');if(stage!=='pending'){
 const ref=this.ref(id,String(i.refId));if(ref.trust!=='verified'||!['pr','commit'].includes(String(ref.kind)))throw invalid('需查询验证的候选PR或提交');
 if(['released','verify_pending','verified'].includes(stage)){const release=this.ref(id,String(i.releaseRefId));if(release.kind!=='release'||release.trust!=='verified')throw invalid('需独立核验发布版本');}
 if(stage==='verified'){const check=this.db.prepare('SELECT * FROM problem_checks WHERE problemId=? ORDER BY rowid DESC LIMIT 1').get(id);if(!check||check.result!=='passed'||check.refId!==ref.id||check.releaseRefId!==i.releaseRefId)throw invalid('需对应修复与发布的最新通过验证');}
 if(['merged','released','verify_pending','verified'].includes(stage)&&i.confirmed!==true)throw invalid('必须明确确认实际合并或上线证据');
 }this.db.prepare('UPDATE problems SET repairStage=?,selectedFixId=?,selectedReleaseId=? WHERE id=?').run(stage,stage==='pending'?null:String(i.refId),['released','verify_pending','verified'].includes(stage)?String(i.releaseRefId):null,id);
 }else if(op==='verify'){
 const fix=this.ref(id,String(i.refId)),release=this.ref(id,String(i.releaseRefId));if(!['pr','commit'].includes(String(fix.kind))||release.kind!=='release'||fix.trust!=='verified'||release.trust!=='verified'||i.environment!=='online'||!['passed','failed'].includes(String(i.result)))throw invalid('验证需已核验的修复、发布和线上环境');entryId=randomUUID();this.db.prepare('INSERT INTO problem_checks VALUES(?,?,?,?,?,?,?,?,?)').run(entryId,id,String(fix.id),String(release.id),String(i.result),'online',requiredText(i.note,'验证说明',4000),c.actor.id,now);this.db.prepare('UPDATE problems SET repairStage=?,selectedFixId=?,selectedReleaseId=? WHERE id=?').run(i.result==='failed'?'pending':'verify_pending',String(fix.id),String(release.id),id);
 }else if(op==='cancel-run'||op==='reconcile-run'){
 const r=this.run(String(i.runId));if(r.problemId!==id)throw invalid('任务不属于问题');entryId=String(r.id);
 if(op==='cancel-run'){if(!['queued','running'].includes(String(r.state)))throw invalid('任务不在执行');this.db.prepare("UPDATE diagnostic_runs SET state='cancelled',errorCode=CASE WHEN state='running' THEN 'cancelled_outcome_unknown' ELSE errorCode END,fencingVersion=fencingVersion+1,version=version+1,finishedAt=? WHERE id=?").run(now,entryId);}
 else {if(!['needs_review','cancelled'].includes(String(r.state))||!['executed','not_executed'].includes(String(i.outcome)))throw invalid('需核对供应商实际执行结果');const note=adminText(i.note,'核查材料',2000),cost=i.actualCost;if(cost!==null&&(typeof cost!=='number'||!Number.isFinite(cost)||cost<0))throw invalid('费用无效');const usage=JSON.parse(String(r.usage));usage.push({reconciledBy:c.actor.id,outcome:i.outcome,note,actualCost:cost,at:now});this.db.prepare("UPDATE diagnostic_runs SET state='failed',errorCode='operator_reconciled',usage=?,actualCost=?,version=version+1,fencingVersion=fencingVersion+1 WHERE id=?").run(JSON.stringify(usage),cost===null?r.actualCost??null:cost,entryId);}
 }else if(op==='diagnose'){result={...result,...this.enqueue(id,i)};}
 else throw invalid('动作无效');
 if(op!=='create')this.db.prepare('UPDATE problems SET version=version+1,updatedAt=? WHERE id=?').run(now,id);
 if(entryId)result.entryId=entryId;result.version=this.version(id);result.repairStage=this.problem(id).repairStage;return {result,before,after:{id,version:this.version(id),repairStage:this.problem(id).repairStage,entryId}};
 });}
 ref(id:string,refId:string){const r=this.db.prepare('SELECT * FROM problem_refs WHERE id=? AND problemId=? AND active=1').get(refId,id);if(!r)throw invalid('修复引用不存在、已解除或属于其他问题');return r;}
 enqueue(id:string,input:Record<string,unknown>){const parsed=materialSchema.safeParse(input.material);if(!parsed.success)throw invalid('诊断材料需白名单字段与脱敏确认');const m=parsed.data;
 // Never auto-read descriptions, emails, notes, credentials or logs. Screenshots are separate explicit selections.
 const screenshots=m.screenshots.map(s=>{if(!this.db.prepare("SELECT 1 FROM problem_links WHERE problemId=? AND kind='feedback' AND relatedId=? AND active=1").get(id,s.feedbackId))throw invalid('截图必须来自关联反馈');const image=this.feedback.feedback.screenshot(s.feedbackId,s.index);if(!image)throw invalid('截图不存在');return {...s,mime:image.mime,data:Buffer.from(image.bytes).toString('base64')};});
 const cfg=process.env.MAAS_DIAGNOSTIC_CONFIG?modelConfigSchema.parse(JSON.parse(readFileSync(process.env.MAAS_DIAGNOSTIC_CONFIG,'utf8'))):modelConfigSchema.parse({...modelConfig(null),adapter:'mock'});
 const budget=Number(input.budget);if(!Number.isFinite(budget)||budget<0||budget>10000)throw invalid('预算无效');if(cfg.adapter!=='mock'&&estimate(cfg)===null)throw invalid('付费诊断需可核验价格配置');
 const material={...m,screenshots},inputHash=hash(JSON.stringify({material,cfg,prompt:'diagnosis-v1'}));if(this.db.prepare("SELECT 1 FROM diagnostic_runs WHERE problemId=? AND inputHash=? AND errorCode IN ('cancelled_outcome_unknown')").get(id,inputHash))throw invalid('执行结果未知，先核查供应商');const existing=this.db.prepare("SELECT id,state FROM diagnostic_runs WHERE problemId=? AND inputHash=? AND state IN ('queued','running','needs_review','succeeded')").get(id,inputHash);if(existing)return {runId:String(existing.id),state:String(existing.state)};
 if(Number(this.db.prepare('SELECT coalesce(sum(attempt),0) n FROM diagnostic_runs WHERE problemId=?').get(id)!.n)>=30)throw invalid('诊断已达30次调用上限');const cost=estimate(cfg),reserved=cost===null?0:cost*3,spent=Number(this.db.prepare('SELECT coalesce(sum(reserved),0) n FROM diagnostic_runs WHERE problemId=?').get(id)!.n);if(spent+reserved>budget)throw invalid('预算不足');
 const modelInput=this.modelInput(material);if(Buffer.byteLength(prompt(modelInput))+screenshots.reduce((n,s)=>n+Buffer.byteLength(s.data),0)>cfg.maxInputTokens)throw invalid('诊断输入超限；截图亦计入保守输入预算');const runId=randomUUID();this.db.prepare("INSERT INTO diagnostic_runs(id,problemId,state,inputHash,config,budget,reserved,estimatedCost,createdAt,payload) VALUES(?,?,'queued',?,?,?,?,?,?,?)").run(runId,id,inputHash,JSON.stringify(cfg),budget,reserved,cost,this.admin.accounts.now(),JSON.stringify(material));return {runId,state:'queued'};
 }
 modelInput(m:any):ModelInput{return {stage:'diagnose',periodEnd:'',windowFrom:'',windowTo:'',coverage:'',coverageNote:'',dataThrough:'',selection:'',inputs:[],upstream:null,diagnostic:{description:m.description,reproduction:m.reproduction,versions:m.versions,errorSummary:m.errorSummary,screenshotSources:m.screenshots.map((s:any)=>`${s.feedbackId}:${s.index}`)},screenshots:m.screenshots.map((s:any)=>({mime:s.mime,data:s.data}))};}
}
