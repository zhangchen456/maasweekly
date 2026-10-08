import { createHmac, randomUUID } from 'node:crypto';
import { AccountError, AccountStore, hash } from './account-store.js';

export interface AdminActor { type: 'user' | 'cli'; id: string }
export interface AdminCommand {
  actor: AdminActor; action: string; targetType: string; targetId: string; reason: string;
  requestId: string; idempotencyKey: string; input: Record<string, unknown>;
  expectedVersion?: number; currentVersion?: () => number;
}
export interface CommandResult<T> { result: T; before: Record<string, unknown> | null; after: Record<string, unknown> | null; audit?: false }
const fail = (message: string) => new AccountError(400, 'invalid_parameter', message);
export function adminText(value: unknown, label: string, max = 200): string {
  if (typeof value !== 'string' || !value.trim() || value.length > max || /[\x00-\x1f]/.test(value)) throw fail(`${label}无效`);
  return value.trim();
}
export function timestamp(value: string): number {
  const match=/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})(?:\.\d{1,3})?(Z|[+-]\d{2}:\d{2})$/.exec(value);
  const n=Date.parse(value);
  if (!match || !Number.isFinite(n)) throw fail('时间需为带时区的ISO格式');
  const [,year,month,day,hour,minute,second]=match;
  const date=new Date(`${year}-${month}-${day}T00:00:00Z`);
  if (date.getUTCFullYear()!==Number(year) || date.getUTCMonth()+1!==Number(month) || date.getUTCDate()!==Number(day) || Number(hour)>23 || Number(minute)>59 || Number(second)>59) throw fail('时间无效');
  return n;
}
function canonical(value: unknown): string {
  if (Array.isArray(value)) return '[' + value.map(canonical).join(',') + ']';
  if (value && typeof value === 'object') return '{' + Object.keys(value).sort().map(k => JSON.stringify(k)+':'+canonical((value as Record<string, unknown>)[k])).join(',') + '}';
  return JSON.stringify(value);
}
// Callers explicitly declare their safe audit and result fields; unknown fields fail closed.
function project(value: Record<string, unknown> | null, fields: readonly string[]) {
  if (value === null) return null;
  if (Object.keys(value).some(k => !fields.includes(k) || /password|secret|token|cookie|code|image/i.test(k))) throw fail('审计或结果字段不在白名单');
  const scalar = (v: unknown) => v === null || typeof v === 'string' || typeof v === 'boolean' || (typeof v === 'number' && Number.isFinite(v));
  if (Object.values(value).some(v => !scalar(v) && !(Array.isArray(v) && v.every(scalar)))) throw fail('审计与结果仅允许脱敏标量或标量数组');
  const json = JSON.stringify(value);
  if (Buffer.byteLength(json) > 4096) throw fail('审计或结果过大');
  return json;
}
export class AdminStore {
  readonly db;
  constructor(readonly accounts: AccountStore) {
    this.db = accounts.db;
    accounts.transaction(() => {
      this.db.exec('CREATE TABLE IF NOT EXISTS admin_schema_migrations(version INTEGER PRIMARY KEY, appliedAt INTEGER NOT NULL)');
      if (!this.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=1').get()) {
        this.db.exec(`CREATE TABLE admin_members(userId TEXT PRIMARY KEY REFERENCES users(id),role TEXT NOT NULL CHECK(role='administrator'),enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),createdAt INTEGER NOT NULL,updatedAt INTEGER NOT NULL);
        CREATE TABLE admin_audit(id TEXT PRIMARY KEY,actorType TEXT NOT NULL CHECK(actorType IN ('user','cli')),actorId TEXT NOT NULL,action TEXT NOT NULL,targetType TEXT NOT NULL,targetId TEXT NOT NULL,reason TEXT NOT NULL,beforeJson TEXT,afterJson TEXT,requestId TEXT NOT NULL,createdAt INTEGER NOT NULL);
        CREATE INDEX admin_audit_order ON admin_audit(createdAt DESC,id DESC);
        CREATE TABLE admin_commands(actorId TEXT NOT NULL,action TEXT NOT NULL,idempotencyKey TEXT NOT NULL,requestHash TEXT NOT NULL,resultJson TEXT NOT NULL,createdAt INTEGER NOT NULL,PRIMARY KEY(actorId,action,idempotencyKey));`);
        this.db.prepare('INSERT INTO admin_schema_migrations VALUES(1,?)').run(accounts.now());
      }
    });
  }
  member(id: string) { return this.db.prepare("SELECT userId,role,enabled,createdAt,updatedAt FROM admin_members WHERE userId=? AND enabled=1").get(id); }
  list() { return this.db.prepare('SELECT * FROM admin_members ORDER BY createdAt,userId').all(); }
  command<T extends Record<string, unknown>>(c: AdminCommand, fields: readonly string[], resultFields: readonly string[], work: () => CommandResult<T>): T {
    if (!['user','cli'].includes(c.actor.type)) throw fail('操作者类型无效');
    if (c.expectedVersion !== undefined && !c.currentVersion) throw fail('缺少版本读取器');
    adminText(c.actor.id,'操作者'); adminText(c.reason,'原因',1000); adminText(c.idempotencyKey,'幂等键',128);
    adminText(c.action,'动作'); adminText(c.targetType,'对象类型'); adminText(c.targetId,'对象'); adminText(c.requestId,'请求标识');
    const requestHash = hash(canonical({input:c.input,reason:c.reason,targetType:c.targetType,targetId:c.targetId,expectedVersion:c.expectedVersion ?? null}));
    return this.accounts.transaction(() => {
      if (c.actor.type === 'user' && !this.member(c.actor.id)) throw new AccountError(403,'forbidden','无后台访问权限');
      const actorId = `${c.actor.type}:${c.actor.id}`;
      const previous = this.db.prepare('SELECT requestHash,resultJson FROM admin_commands WHERE actorId=? AND action=? AND idempotencyKey=?').get(actorId,c.action,c.idempotencyKey);
      if (previous) {
        if (previous.requestHash !== requestHash) throw new AccountError(409,'idempotency_conflict','幂等键已用于其他请求');
        return JSON.parse(String(previous.resultJson)) as T;
      }
      if (c.currentVersion && (!Number.isSafeInteger(c.expectedVersion) || c.expectedVersion !== c.currentVersion())) throw new AccountError(409,'version_conflict','对象已更新，请重新读取');
      if (work.constructor.name === 'AsyncFunction') throw fail('事务回调必须同步');
      const output = work();
      if (output && typeof (output as unknown as {then?:unknown}).then === 'function') throw fail('事务回调必须同步');
      const before = project(output.before,fields), after = project(output.after,fields), result = project(output.result,resultFields)!;
      if(output.audit!==false)this.db.prepare('INSERT INTO admin_audit VALUES(?,?,?,?,?,?,?,?,?,?,?)').run(randomUUID(),c.actor.type,c.actor.id,c.action,c.targetType,c.targetId,c.reason,before,after,c.requestId,this.accounts.now());
      this.db.prepare('INSERT INTO admin_commands VALUES(?,?,?,?,?,?)').run(actorId,c.action,c.idempotencyKey,requestHash,result,this.accounts.now());
      return output.result;
    });
  }
  setMember(id: string, enabled: boolean, actor: string, reason: string) {
    return this.command({actor:{type:'cli',id:actor},action:enabled?'admin.grant':'admin.revoke',targetType:'admin_member',targetId:id,reason,requestId:randomUUID(),idempotencyKey:randomUUID(),input:{enabled}},['userId','role','enabled','createdAt','updatedAt'],['updated'],() => {
      if (!this.db.prepare('SELECT 1 FROM users WHERE id=?').get(id)) throw new AccountError(404,'not_found','账号不存在');
      const before = this.db.prepare('SELECT * FROM admin_members WHERE userId=?').get(id) ?? null;
      this.db.prepare("INSERT INTO admin_members VALUES(?,'administrator',?,?,?) ON CONFLICT(userId) DO UPDATE SET enabled=excluded.enabled,updatedAt=excluded.updatedAt").run(id,Number(enabled),this.accounts.now(),this.accounts.now());
      return {result:{updated:true},before,after:this.db.prepare('SELECT * FROM admin_members WHERE userId=?').get(id)!};
    });
  }
  audit(params: URLSearchParams) {
    const allowed = ['action','targetType','targetId','from','to','cursor','limit'];
    for (const key of params.keys()) if (!allowed.includes(key) || params.getAll(key).length !== 1) throw fail('查询参数无效');
    const limitText = params.get('limit') ?? '25';
    if (!/^\d+$/.test(limitText) || Number(limitText)<1 || Number(limitText)>100) throw fail('分页大小需为1至100');
    const limit=Number(limitText), filters: Record<string,string|number> = {}, where:string[]=[], values:(string|number)[]=[];
    for (const key of ['action','targetType','targetId']) if (params.has(key)) { const value=adminText(params.get(key),key); filters[key]=value; where.push(`${key}=?`); values.push(value); }
    for (const key of ['from','to']) if (params.has(key)) { const raw=params.get(key)!; const n=timestamp(raw); filters[key]=n; where.push(`createdAt${key==='from'?'>=':'<='}?`); values.push(n); }
    if (filters.from !== undefined && filters.to !== undefined && filters.from>filters.to) throw fail('时间范围无效');
    const filterHash=hash(canonical(filters));
    const sign=(s:string)=>createHmac('sha256',this.accounts.codeSecret).update('admin-cursor:'+s).digest('base64url');
    if (params.has('cursor')) {
      try {
        const raw=params.get('cursor')!; if(raw.length>2048) throw Error();
        const [payload,signature]=raw.split('.'); if(!payload || signature!==sign(payload)) throw Error();
        const c=JSON.parse(Buffer.from(payload,'base64url').toString());
        if(c.filters!==filterHash || !Number.isSafeInteger(c.createdAt) || typeof c.id!=='string') throw Error();
        where.push('(createdAt<? OR (createdAt=? AND id<?))'); values.push(c.createdAt,c.createdAt,c.id);
      } catch { throw fail('分页游标无效或筛选已改变'); }
    }
    const rows=this.db.prepare(`SELECT * FROM admin_audit ${where.length?'WHERE '+where.join(' AND '):''} ORDER BY createdAt DESC,id DESC LIMIT ?`).all(...values,limit+1);
    const items=rows.slice(0,limit).map(({beforeJson,afterJson,...row})=>({...row,before:beforeJson?JSON.parse(String(beforeJson)):null,after:afterJson?JSON.parse(String(afterJson)):null}));
    const last=rows[limit-1]; let nextCursor:string|null=null;
    if(rows.length>limit && last) {const payload=Buffer.from(JSON.stringify({filters:filterHash,createdAt:last.createdAt,id:last.id})).toString('base64url'); nextCursor=payload+'.'+sign(payload);}
    return {items,nextCursor};
  }
}
