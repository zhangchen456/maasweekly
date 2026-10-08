import { AccountError } from './account-store.js';
import { AdminStore, type AdminCommand } from './admin-store.js';
import { ProStore } from './pro-store.js';
import { migrateOperations,query,page,invalid,timestamp } from './admin-operations.js';
export class AdminUsers {
  readonly pro:ProStore;
  constructor(readonly admin:AdminStore){migrateOperations(admin);this.pro=new ProStore(admin.accounts);}
  require(id:string){const row=this.admin.db.prepare('SELECT id,email,emailEnabled,emailSince FROM users WHERE id=?').get(id);if(!row)throw new AccountError(404,'not_found','用户不存在');return row;}
  version(id:string){this.require(id);return Number(this.admin.db.prepare('SELECT version FROM admin_user_versions WHERE userId=?').get(id)?.version??0);}
  list(params:URLSearchParams){query(params,['q','entitlementStatus','source']);const status=params.get('entitlementStatus'),source=params.get('source');if(status&&!['active','free'].includes(status))throw invalid('权益筛选无效');if(source&&!['beta','manual','paid'].includes(source))throw invalid('来源筛选无效');
    
    this.admin.db.function('admin_effective',{deterministic:true},(userId,_starts,_ends,_revoked,_created)=>{return JSON.stringify(this.pro.entitlement(String(userId)));});
    const where:string[]=[],values:(string|number)[]=[];if(params.has('q')){const q=params.get('q')!;if(q.length>200)throw invalid('检索过长');where.push('(instr(lower(email),lower(?))>0 OR id=?)');values.push(q,q);}if(status){where.push("json_extract(effectiveEntitlement,'$.status')"+(status==='active'?"='active'":"!='active'"));}if(source){where.push("json_extract(effectiveEntitlement,'$.source')=?");values.push(source);}
    return page(this.admin,params,'users:id',`SELECT * FROM (SELECT u.id,u.email,p.displayName,p.created AS profileCreated,(SELECT count(*) FROM watches w WHERE w.userId=u.id) AS watchCount,admin_effective(u.id,e.starts,e.ends,e.revoked,b.created) AS effectiveEntitlement FROM users u LEFT JOIN account_profiles p ON p.userId=u.id LEFT JOIN pro_entitlements e ON e.userId=u.id LEFT JOIN pro_beta_access b ON b.userId=u.id) ${where.length?'WHERE '+where.join(' AND '):''}`,values,['id'],r=>({...r,effectiveEntitlement:JSON.parse(r.effectiveEntitlement)}));
  }
  detail(id:string){const user=this.require(id),db=this.admin.db;return {...user,profile:db.prepare('SELECT displayName,created AS profileCreated FROM account_profiles WHERE userId=?').get(id)??null,effectiveEntitlement:this.pro.entitlement(id),manual:db.prepare('SELECT starts,ends,revoked FROM pro_entitlements WHERE userId=?').get(id)??null,beta:db.prepare('SELECT created FROM pro_beta_access WHERE userId=?').get(id)??null,betaAvailable:this.pro.betaAvailable,adminVersion:this.version(id),watchCount:db.prepare('SELECT count(*) AS n FROM watches WHERE userId=?').get(id)!.n,professionalEmail:db.prepare('SELECT scope,emailEnabled,emailSince FROM pro_settings WHERE userId=?').get(id)??null,credentials:db.prepare('SELECT id,name,purpose,created,expires,revoked,used FROM pro_tokens WHERE userId=? ORDER BY created DESC LIMIT 100').all(id),events:db.prepare('SELECT event,count(*) AS count FROM pro_events WHERE userId=? AND created>=? GROUP BY event ORDER BY event LIMIT 100').all(id,this.admin.accounts.now()-30*86400000),history:this.admin.audit(new URLSearchParams({targetType:'user',targetId:id}))};}
  write(c:AdminCommand,operation:string,credentialId?:string){c={...c,currentVersion:()=>this.version(c.targetId)};return this.admin.command(c,['version','status','source','operation'],['updated','version','status','source'],()=>{
    const id=c.targetId,version=this.version(id),before=this.pro.entitlement(id);const input=c.input;
    if(operation==='entitlement'){
      if(!['grant','revoke'].includes(String(input.operation)))throw invalid('授权动作无效');
      const manual=this.admin.db.prepare('SELECT starts,ends FROM pro_entitlements WHERE userId=?').get(id);
      const revoked=input.operation==='revoke';const starts=revoked?Number(manual?.starts??this.admin.accounts.now()):timestamp(String(input.starts)),ends=revoked?Number(manual?.ends??starts+1):timestamp(String(input.ends));
      this.pro.grantInTransaction(id,starts,ends,c.actor.id,c.reason,revoked);
    }else if(operation==='revoke-sessions')this.admin.accounts.logoutAll(id);
    else if(operation==='credential'){
      if(!this.admin.db.prepare('SELECT 1 FROM pro_tokens WHERE id=? AND userId=?').get(credentialId!,id))throw new AccountError(404,'not_found','专业凭证不存在');this.pro.revoke(id,credentialId!);
    }else throw invalid('动作无效');
    this.admin.db.prepare('INSERT INTO admin_user_versions VALUES(?,?) ON CONFLICT(userId) DO UPDATE SET version=excluded.version').run(id,version+1);
    const after=this.pro.entitlement(id);return {result:{updated:true,version:version+1,status:after.status,source:after.source},before:{version,status:before.status,source:before.source},after:{version:version+1,status:after.status,source:after.source,operation:credentialId?operation+':'+credentialId:operation}};
  });}
}
