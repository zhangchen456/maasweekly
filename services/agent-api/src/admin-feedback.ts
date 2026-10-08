import { randomUUID } from 'node:crypto';
import { AccountError } from './account-store.js';
import { AdminStore,type AdminCommand } from './admin-store.js';
import { ProStore } from './pro-store.js';
import { FeedbackStore } from './feedback-store.js';
import { migrateOperations,query,page,invalid,optionalText,reference,timestamp } from './admin-operations.js';
export const stages=['triage','investigating','waiting_user','fix_pending','release_pending','verify_pending','resolved'];
export const priorities=['urgent','high','normal','low'];
export class AdminFeedback {
  readonly feedback:FeedbackStore;
  constructor(readonly admin:AdminStore){migrateOperations(admin);this.feedback=new FeedbackStore(admin.accounts);}
  ops(id:string){const f=this.feedback.detail(id);if(!f)throw new AccountError(404,'not_found','反馈不存在');return this.admin.db.prepare('SELECT * FROM feedback_ops WHERE feedbackId=?').get(id)??{feedbackId:id,stage:'triage',priority:'normal',version:0,updatedAt:f.updated,operatorId:null,resolutionType:null,relatedFeedbackId:null};}
  version(id:string){return Number(this.ops(id).version);}
  list(params:URLSearchParams){query(params,['userId','stage','priority','from','to']);const where:string[]=[],values:(string|number)[]=[];
    for(const key of ['userId','stage','priority'])if(params.has(key)){const v=params.get(key)!;if(key==='stage'&&!stages.includes(v)||key==='priority'&&!priorities.includes(v))throw invalid('筛选无效');where.push(key+'=?');values.push(v);}
    for(const key of ['from','to'])if(params.has(key)){where.push(`created${key==='from'?'>=':'<='}?`);values.push(timestamp(params.get(key)!));}if(params.has('from')&&params.has('to')&&timestamp(params.get('from')!)>timestamp(params.get('to')!))throw invalid('时间范围无效');
    return page(this.admin,params,'feedback:unfinished,updatedAt,id',`SELECT * FROM (SELECT f.id,f.userId,u.email,f.title,f.status,f.created,coalesce(o.stage,'triage') AS stage,coalesce(o.priority,'normal') AS priority,coalesce(o.version,0) AS version,coalesce(o.updatedAt,f.updated) AS updatedAt,CASE WHEN coalesce(o.stage,'triage')='resolved' THEN 0 ELSE 1 END AS unfinished FROM feedback f JOIN users u ON u.id=f.userId LEFT JOIN feedback_ops o ON o.feedbackId=f.id) ${where.length?'WHERE '+where.join(' AND '):''}`,values,['unfinished','updatedAt','id']);
  }
  records(id:string,kind:'notes'|'verifications',params:URLSearchParams){this.ops(id);query(params,[]);return page(this.admin,params,'feedback:'+id+':'+kind,`SELECT * FROM feedback_${kind} WHERE feedbackId=?`,[id],[kind==='notes'?'createdAt':'checkedAt','id']);}
  detail(id:string){const ops=this.ops(id),item=this.feedback.detail(id)!;const userId=String(item.userId);const problems=this.admin.db.prepare("SELECT 1 FROM sqlite_master WHERE name='problem_links'").get()?this.admin.db.prepare("SELECT p.id,p.title,p.repairStage FROM problem_links l JOIN problems p ON p.id=l.problemId WHERE l.kind='feedback' AND l.relatedId=? AND l.active=1").all(id):[];return {...item,problems,userSummary:{id:userId,email:item.email,profile:this.admin.db.prepare('SELECT displayName,created AS profileCreated FROM account_profiles WHERE userId=?').get(userId)??null,effectiveEntitlement:new ProStore(this.admin.accounts).entitlement(userId),watchCount:this.admin.db.prepare('SELECT count(*) AS n FROM watches WHERE userId=?').get(userId)!.n},ops,notes:this.records(id,'notes',new URLSearchParams()),verifications:this.records(id,'verifications',new URLSearchParams())};}
  write(c:AdminCommand,operation:string){c={...c,currentVersion:()=>this.version(c.targetId)};return this.admin.command(c,['stage','priority','version','resolutionType','relatedFeedbackId','entryId'],['updated','version','stage'],()=>{
    const id=c.targetId,db=this.admin.db,before=this.ops(id),version=Number(before.version)+1,now=this.admin.accounts.now(),input=c.input;
    db.prepare("INSERT OR IGNORE INTO feedback_ops VALUES(?,'triage','normal',0,?,NULL,NULL,NULL)").run(id,now);
    let stage=String(before.stage),priority=String(before.priority),resolution=before.resolutionType,related=before.relatedFeedbackId,entryId:string|null=null;
    if(operation==='notes'){
      const body=this.feedback.text(input.body,1,4000,'内部备注需为1至4000字');entryId=randomUUID();db.prepare('INSERT INTO feedback_notes VALUES(?,?,?,?,?)').run(entryId,id,c.actor.id,body,now);
    }else if(operation==='verify'){
      const kind=String(input.kind),result=String(input.result);if(!['code','content','data','other'].includes(kind)||!['passed','failed'].includes(result))throw invalid('验证类型或结果无效');
      const artifact=reference(input.artifactRef),release=reference(input.releaseRef,false),note=this.feedback.text(input.note,1,4000,'验证说明需为1至4000字');if(kind==='code'&&(!release||input.environment!=='online'))throw invalid('代码问题需发布版本与线上验证');
      entryId=randomUUID();db.prepare('INSERT INTO feedback_verifications VALUES(?,?,?,?,?,?,?,?,?)').run(entryId,id,kind,artifact,release||null,result,now,c.actor.id,(kind==='code'?'[online] ':'')+note);
    }else if(operation==='update'){
      if(input.stage!==undefined){stage=String(input.stage);if(!stages.includes(stage))throw invalid('阶段无效');}if(input.priority!==undefined){priority=String(input.priority);if(!priorities.includes(priority))throw invalid('优先级无效');}
      if(input.resolutionType!==undefined){resolution=String(input.resolutionType);if(!['code','content','data','other'].includes(String(resolution)))throw invalid('解决类型无效');}
      if(input.relatedFeedbackId!==undefined){related=input.relatedFeedbackId===null?null:reference(input.relatedFeedbackId);if(related){let current=String(related);const seen=new Set([id]);while(current){if(seen.has(current))throw invalid('重复反馈关联不能形成循环');seen.add(current);this.ops(current);current=String(db.prepare('SELECT relatedFeedbackId FROM feedback_ops WHERE feedbackId=?').get(current)?.relatedFeedbackId??'');}if(resolution!=='other')throw invalid('重复反馈需使用other处理依据');}}
      const reply=input.publicReply===undefined?String(this.feedback.detail(id)!.reply):optionalText(input.publicReply,2000);
      if(stage==='resolved'){
        if(!reply||!['code','content','data','other'].includes(String(resolution)))throw invalid('解决反馈需公开说明、解决类型及验证记录');
        const verification=db.prepare('SELECT * FROM feedback_verifications WHERE feedbackId=? AND kind=? ORDER BY rowid DESC LIMIT 1').get(id,String(resolution));
        if(!verification||verification.result!=='passed'||(resolution==='code'&&(!verification.releaseRef||!String(verification.note).startsWith('[online] '))))throw invalid('缺少通过的验证记录；代码问题还需发布版本与线上验证');
        // Reopened feedback cannot reuse verification from a previous resolution.
        const reopenedVersion=Number(db.prepare("SELECT max(json_extract(afterJson,'$.version')) AS n FROM admin_audit WHERE targetType='feedback' AND targetId=? AND json_extract(beforeJson,'$.stage')='resolved' AND json_extract(afterJson,'$.stage')!='resolved'").get(id)?.n??0);
        const verifiedVersion=Number(db.prepare("SELECT json_extract(afterJson,'$.version') AS n FROM admin_audit WHERE targetType='feedback' AND targetId=? AND json_extract(afterJson,'$.entryId')=?").get(id,String(verification.id))?.n??0);
        if(before.stage!=='resolved'&&verifiedVersion<=reopenedVersion)throw invalid('重开后需重新验证');
      }
      db.prepare('UPDATE feedback SET status=?,reply=?,updated=? WHERE id=?').run(stage==='triage'?'open':stage==='resolved'?'resolved':'investigating',reply,now,id);
    }else throw invalid('动作无效');
    db.prepare('UPDATE feedback_ops SET stage=?,priority=?,version=?,updatedAt=?,operatorId=?,resolutionType=?,relatedFeedbackId=? WHERE feedbackId=?').run(stage,priority,version,now,c.actor.id,resolution,related,id);
    const state=(r:any)=>({stage:r.stage,priority:r.priority,version:r.version,resolutionType:r.resolutionType,relatedFeedbackId:r.relatedFeedbackId});
    return {result:{updated:true,version,stage},before:state(before),after:{...state(this.ops(id)),entryId}};
  });}
}
