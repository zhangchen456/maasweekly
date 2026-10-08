import { createHmac } from 'node:crypto';
import { AccountError, hash } from './account-store.js';
import { AdminStore, adminText, timestamp } from './admin-store.js';
import { FeedbackStore } from './feedback-store.js';
import { ProStore } from './pro-store.js';
export const invalid=(message:string)=>new AccountError(400,'invalid_parameter',message);
export function migrateOperations(admin:AdminStore) {
  new ProStore(admin.accounts); new FeedbackStore(admin.accounts);
  admin.accounts.transaction(()=>{
    if(admin.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=2').get())return;
    admin.db.exec(`CREATE TABLE admin_user_versions(userId TEXT PRIMARY KEY REFERENCES users(id),version INTEGER NOT NULL);
      CREATE TABLE feedback_ops(feedbackId TEXT PRIMARY KEY REFERENCES feedback(id),stage TEXT NOT NULL,priority TEXT NOT NULL,version INTEGER NOT NULL,updatedAt INTEGER NOT NULL,operatorId TEXT,resolutionType TEXT,relatedFeedbackId TEXT REFERENCES feedback(id));
      CREATE TABLE feedback_notes(id TEXT PRIMARY KEY,feedbackId TEXT NOT NULL REFERENCES feedback(id),actorId TEXT NOT NULL,body TEXT NOT NULL,createdAt INTEGER NOT NULL);
      CREATE TABLE feedback_verifications(id TEXT PRIMARY KEY,feedbackId TEXT NOT NULL REFERENCES feedback(id),kind TEXT NOT NULL,artifactRef TEXT NOT NULL,releaseRef TEXT,result TEXT NOT NULL,checkedAt INTEGER NOT NULL,actorId TEXT NOT NULL,note TEXT NOT NULL);
      CREATE INDEX feedback_ops_order ON feedback_ops(stage,updatedAt DESC,feedbackId DESC);
      CREATE INDEX feedback_notes_order ON feedback_notes(feedbackId,createdAt DESC,id DESC);
      CREATE INDEX feedback_verifications_order ON feedback_verifications(feedbackId,checkedAt DESC,id DESC);
      CREATE INDEX pro_events_user ON pro_events(userId,created);
      CREATE INDEX pro_tokens_user ON pro_tokens(userId,created);
      INSERT INTO feedback_ops SELECT id,CASE status WHEN 'open' THEN 'triage' ELSE status END,'normal',0,updated,NULL,CASE WHEN status='resolved' THEN 'legacy' ELSE NULL END,NULL FROM feedback;`);
    admin.db.prepare('INSERT INTO admin_schema_migrations VALUES(2,?)').run(admin.accounts.now());
  });
}
export function query(params:URLSearchParams, allowed:string[]) {
  for(const key of params.keys())if(![...allowed,'cursor','limit'].includes(key)||params.getAll(key).length!==1)throw invalid('查询参数无效');
  const n=params.get('limit')??'25';if(!/^\d+$/.test(n)||Number(n)<1||Number(n)>100)throw invalid('分页大小需为1至100');
  return Number(n);
}
// Cursor explicitly binds query, ordering, and last row. All filtering happens before LIMIT.
export function page(admin:AdminStore,params:URLSearchParams,scope:string,sql:string,values:(string|number)[],order:string[],map:(row:any)=>any=(r)=>r) {
  const limit=Number(params.get('limit')??25), filters=new URLSearchParams(params);filters.delete('cursor');filters.delete('limit');filters.sort();
  const binding=hash(scope+':'+filters.toString()),sign=(s:string)=>createHmac('sha256',admin.accounts.codeSecret).update('admin-page:'+s).digest('base64url');
  let condition='',args=[...values];
  if(params.has('cursor'))try{
    const raw=params.get('cursor')!;if(raw.length>2048)throw Error();const [payload,sig,...extra]=raw.split('.');if(extra.length||sig!==sign(payload!))throw Error();
    const c=JSON.parse(Buffer.from(payload!,'base64url').toString());if(c.binding!==binding||!Array.isArray(c.values)||c.values.length!==order.length||c.values.some((v:any)=>typeof v!=='string'&&typeof v!=='number'))throw Error();
    condition=' WHERE '+order.map((key,i)=>'('+order.slice(0,i).map(k=>`${k}=?`).concat(`${key}<?`).join(' AND ')+')').join(' OR ');
    order.forEach((_,i)=>args.push(...c.values.slice(0,i+1)));
  }catch{throw invalid('分页游标无效或筛选已改变');}
  const rows=admin.db.prepare(`SELECT * FROM (${sql}) ${condition} ORDER BY ${order.map(k=>k+' DESC').join(',')} LIMIT ?`).all(...args,limit+1);
  const last=rows[limit-1];let nextCursor:string|null=null;
  if(rows.length>limit&&last){const payload=Buffer.from(JSON.stringify({binding,values:order.map(k=>last[k])})).toString('base64url');nextCursor=payload+'.'+sign(payload);}
  return {items:rows.slice(0,limit).map(map),nextCursor};
}
export function optionalText(value:unknown,max:number) {if(typeof value!=='string'||value.length>max||/[\x00-\x08\x0b\x0c\x0e-\x1f]/.test(value))throw invalid('文本无效或过长');return value.trim();}
export function reference(value:unknown,required=true) {const s=optionalText(value??'',500);if(required&&!s)throw invalid('引用不能为空');if(s&&(/^[a-z][a-z0-9+.-]*:/i.test(s)&&!/^https?:\/\//i.test(s)))throw invalid('仅允许http(s)链接或普通标识');if(/^https?:/i.test(s)){try{const u=new URL(s);if(!u.hostname||u.username||u.password)throw Error();}catch{throw invalid('链接无效');}}return s;}
export { adminText, timestamp };
