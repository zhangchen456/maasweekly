import { paidEntitlement } from './payment-store.js';
import { randomBytes, randomUUID, createCipheriv, createDecipheriv, createHash } from 'node:crypto';
import { z } from 'zod';
import { AccountStore, AccountError, hash, type User } from './account-store.js';

const id = z.string().min(1).max(200).regex(/^[a-zA-Z0-9:_-]+$/);
export const topics = ['price', 'billing', 'lifecycle', 'capability'] as const;
export const scopeSchema = z.object({ providers: z.array(id).max(50), models: z.array(id).max(50), families: z.array(id).max(50), topics: z.array(z.enum(topics)).min(1).max(4) }).strict().refine(s => s.providers.length + s.models.length + s.families.length > 0, '请选择至少一个关注对象');
export type Scope = z.infer<typeof scopeSchema>;
const instant = z.string().datetime({ offset: true });
export const contentSchema = z.object({
  id, version: z.number().int().positive(), kind: z.enum(['explainer', 'comparison', 'briefing']),
  title: z.string().min(1).max(200), preview: z.string().min(1).max(2000), body: z.string().min(1).max(100000),
  providers: z.array(id).min(1).max(50), models: z.array(id).max(50), families: z.array(id).max(50), topics: z.array(z.enum(topics)).min(1).max(4),
  period: z.object({ from: instant, to: instant }).refine(p => Date.parse(p.from) < Date.parse(p.to)),
  dataThrough: z.union([instant,z.string().regex(/^\d{4}-\d{2}-\d{2}$/)]), coverage: z.enum(['normal', 'partial', 'failed']), coverageNote: z.string().min(1).max(2000),
  evidence: z.array(z.object({ id, url: z.string().url().refine(s => /^https?:/.test(s)), observedAt: z.string().min(10).max(40), note: z.string().min(1).max(2000) }).strict()).min(1).max(100),
  conditions: z.string().min(1).max(10000), limitations: z.string().min(1).max(10000),
  rows: z.array(z.record(z.string().max(100), z.string().max(2000))).max(500),
  sample: z.boolean().default(false), correction: z.string().max(2000).default(''), critical: z.boolean().default(false),
}).strict();
export type ProContent = z.infer<typeof contentSchema>;
type ContentRow = { id: string; version: number; payload: string; state: string; reviewer: string | null; reviewed: number | null; published: number | null };
export const parseScope = (v: unknown): Scope => { const p = scopeSchema.safeParse(v); if (!p.success) throw new AccountError(400, 'invalid_scope', '请选择关注对象和有效主题'); return p.data; };
export function matches(c: Pick<ProContent, 'providers'|'models'|'families'|'topics'>, s: Scope) {
  return c.topics.some(t => s.topics.includes(t)) && (c.providers.some(p => s.providers.includes(p)) || c.models.some(m => s.models.includes(m)) || c.families.some(f => s.families.includes(f)));
}
export const xml = (s: string) => s.replace(/[<>&"']/g, c => ({ '<':'&lt;', '>':'&gt;', '&':'&amp;', '"':'&quot;', "'":'&apos;' }[c]!));
export function markdown(c: ProContent) { return `# ${c.title}\n\n版本：${c.version}｜统计：${c.period.from} — ${c.period.to}\n数据截至：${c.dataThrough}\n覆盖：${c.coverage} · ${c.coverageNote}\n\n${c.body}\n\n## 适用条件\n${c.conditions}\n\n## 局限\n${c.limitations}\n\n## 来源\n${c.evidence.map(e => `- ${e.id} ${e.url}（${e.observedAt}）${e.note}`).join('\n')}\n${c.correction ? `\n## 更正\n${c.correction}\n` : ''}`; }
export function csv(c: ProContent) {
  const rows = (c.rows.length ? c.rows : [{}]).map(r => ({ ...r, contentId: c.id, version: String(c.version), from: c.period.from, to: c.period.to, dataThrough: c.dataThrough, conditions: c.conditions, limitations: c.limitations, coverage:c.coverage, evidence:JSON.stringify(c.evidence), sources: c.evidence.map(e => e.url).join(' ') }));
  return csvRows(rows);
}
export function csvRows(rows: Record<string,string>[]) {
  const keys = [...new Set(rows.flatMap(r => Object.keys(r)))];
  const cell = (s: string) => `"${(/^[=+@\-\t\r]/.test(s) ? "'" : '') + s.replace(/"/g, '""')}"`;
  return [keys.map(cell).join(','), ...rows.map(r => keys.map(k => cell(r[k] ?? '')).join(','))].join('\r\n');
}

export function effectiveEntitlement(e: {starts:number;ends:number;revoked:number}|undefined, beta: {created:number}|undefined, available:boolean, now:number) {
  if (beta && available && !e?.revoked) return {status:'active',starts:beta.created,ends:null,source:'beta'};
  return {source:'manual',status:!e?'pending':e.revoked?'revoked':e.starts>now?'pending':e.ends<=now?'expired':'active',starts:e?.starts??null,ends:e?.ends??null};
}

export class ProStore {
  constructor(readonly accounts: AccountStore) {
    accounts.db.exec(`
      CREATE TABLE IF NOT EXISTS pro_beta_access(userId TEXT PRIMARY KEY REFERENCES users(id),created INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS pro_events(event TEXT NOT NULL,target TEXT NOT NULL,userId TEXT,created INTEGER NOT NULL);
      CREATE INDEX IF NOT EXISTS pro_events_created ON pro_events(created);
      CREATE TABLE IF NOT EXISTS pro_entitlements(userId TEXT PRIMARY KEY REFERENCES users(id),starts INTEGER NOT NULL,ends INTEGER NOT NULL,revoked INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS pro_audit(id TEXT PRIMARY KEY,actor TEXT NOT NULL,action TEXT NOT NULL,target TEXT NOT NULL,note TEXT NOT NULL,created INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS pro_content(id TEXT NOT NULL,version INTEGER NOT NULL,payload TEXT NOT NULL,state TEXT NOT NULL,reviewer TEXT,reviewed INTEGER,published INTEGER,PRIMARY KEY(id,version));
      CREATE INDEX IF NOT EXISTS pro_content_state ON pro_content(state);
      CREATE TABLE IF NOT EXISTS pro_settings(userId TEXT PRIMARY KEY REFERENCES users(id),scope TEXT NOT NULL,emailEnabled INTEGER NOT NULL DEFAULT 0,emailSince INTEGER NOT NULL DEFAULT 0,unsubscribe TEXT NOT NULL UNIQUE);
      CREATE TABLE IF NOT EXISTS pro_tokens(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),name TEXT NOT NULL,purpose TEXT NOT NULL,hash TEXT NOT NULL UNIQUE,encrypted TEXT,created INTEGER NOT NULL,expires INTEGER NOT NULL,revoked INTEGER NOT NULL DEFAULT 0,used INTEGER);
      CREATE TABLE IF NOT EXISTS pro_applications(userId TEXT PRIMARY KEY REFERENCES users(id),scenario TEXT NOT NULL,created INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS pro_reports(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),period TEXT NOT NULL,scope TEXT NOT NULL,refs TEXT NOT NULL,coverage TEXT NOT NULL,created INTEGER NOT NULL,UNIQUE(userId,period));
      CREATE TABLE IF NOT EXISTS pro_mail(id TEXT PRIMARY KEY,userId TEXT NOT NULL REFERENCES users(id),reportId TEXT NOT NULL REFERENCES pro_reports(id),created INTEGER NOT NULL,status TEXT NOT NULL DEFAULT 'pending',lease INTEGER NOT NULL DEFAULT 0,mail TEXT);
    `);
  }
  get db() { return this.accounts.db; }
  get now() { return this.accounts.now(); }
  event(event: string, target = '', userId?: string) { this.db.prepare('INSERT INTO pro_events VALUES(?,?,?,?)').run(event,target,userId ?? null,this.now); }
  metrics() { return this.db.prepare('SELECT event,COUNT(*) AS count,COUNT(DISTINCT userId) AS accounts FROM pro_events WHERE created>? GROUP BY event').all(this.now-30*86400000); }
  audit(actor: string, action: string, target: string, note: string) {
    if (!actor.trim() || !note.trim()) throw new AccountError(400, 'audit_required', '操作人和原因不能为空');
    this.db.prepare('INSERT INTO pro_audit VALUES(?,?,?,?,?,?)').run(randomUUID(), actor, action, target, note, this.now);
  }
  entitlement(userId: string) {
    const e = this.db.prepare('SELECT starts,ends,revoked FROM pro_entitlements WHERE userId=?').get(userId) as {starts:number;ends:number;revoked:number} | undefined;
    const beta = this.db.prepare('SELECT created FROM pro_beta_access WHERE userId=?').get(userId) as {created:number} | undefined;
    return paidEntitlement(this.db,userId,this.now) ?? effectiveEntitlement(e,beta,this.betaAvailable,this.now);
  }
  get betaAvailable() { return process.env.PRO_BETA_ENABLED !== 'false'; }
  activateBeta(userId: string) {
    if (!this.betaAvailable) throw new AccountError(403,'beta_closed','公测开通已暂停');
    if (this.entitlement(userId).status === 'revoked') throw new AccountError(403,'pro_revoked','账户权益已撤销，请联系支持');
    this.accounts.transaction(() => {
      const result = this.db.prepare('INSERT OR IGNORE INTO pro_beta_access VALUES(?,?)').run(userId,this.now);
      if (result.changes) { this.audit(userId,'beta_activate',userId,'Free public beta; no payment or automatic renewal'); this.event('beta_activated','',userId); }
    });
    return this.entitlement(userId);
  }
  require(userId: string) { if (this.entitlement(userId).status !== 'active') throw new AccountError(403, 'pro_required', '专业服务未生效或已到期，请查看账户权益'); }
  grant(userId: string, starts: number, ends: number, actor: string, note: string, revoked = false) {
    if (!Number.isSafeInteger(starts) || !Number.isSafeInteger(ends) || starts >= ends) throw new Error('invalid service period');
    this.accounts.transaction(() => this.grantInTransaction(userId,starts,ends,actor,note,revoked));
  }
  grantInTransaction(userId:string,starts:number,ends:number,actor:string,note:string,revoked=false) {
    if (!Number.isSafeInteger(starts) || !Number.isSafeInteger(ends) || starts >= ends) throw new AccountError(400,'invalid_period','服务期无效');
      this.audit(actor, revoked ? 'revoke' : 'grant', userId, note);
      this.db.prepare('INSERT INTO pro_entitlements VALUES(?,?,?,?) ON CONFLICT(userId) DO UPDATE SET starts=excluded.starts,ends=excluded.ends,revoked=excluded.revoked').run(userId, starts, ends, Number(revoked));
      this.event(revoked ? 'entitlement_revoked' : 'entitlement_granted','',userId);
      if (revoked && this.entitlement(userId).status !== 'active') this.db.prepare("UPDATE pro_mail SET status='cancelled' WHERE userId=? AND status='pending'").run(userId);
  }
  draft(input: unknown, actor: string) {
    const c = contentSchema.parse(input);
    this.accounts.transaction(() => this.draftInTransaction(c, actor)); return c;
  }
  draftInTransaction(input: unknown, actor: string) {
    const c = contentSchema.parse(input);
      const latest = this.db.prepare('SELECT MAX(version) AS version FROM pro_content WHERE id=?').get(c.id)?.version as number | null;
      if (c.version !== (latest ?? 0) + 1) throw new Error('version must increment by one');
      if (latest && !c.sample && this.db.prepare("SELECT 1 FROM pro_content WHERE id=? AND json_extract(payload,'$.sample')=1").get(c.id)) throw new Error('public sample cannot become private');
      if (latest && !c.correction.trim()) throw new Error('revision requires correction note');
      this.audit(actor, 'draft', `${c.id}:${c.version}`, c.correction || 'initial draft');
      this.db.prepare("INSERT INTO pro_content(id,version,payload,state) VALUES(?,?,?,'draft')").run(c.id,c.version,JSON.stringify(c));
    return c;
  }
  transition(id: string, version: number, action: 'review'|'publish'|'withdraw', actor: string, note: string) {
    this.accounts.transaction(() => this.transitionInTransaction(id,version,action,actor,note));
  }
  transitionInTransaction(id: string, version: number, action: 'review'|'publish'|'withdraw', actor: string, note: string) {
      const row = this.db.prepare('SELECT * FROM pro_content WHERE id=? AND version=?').get(id,version) as ContentRow | undefined;
      if (!row) throw new Error('content not found');
      if (action === 'review' && row.state !== 'draft' || action === 'publish' && row.state !== 'in_review' || action === 'withdraw' && row.state !== 'published') throw new Error('invalid editorial transition');
      if (action === 'publish' && this.db.prepare("SELECT 1 FROM pro_content WHERE id=? AND version>? AND state='published'").get(id,version)) throw new Error('cannot publish older version');
      contentSchema.parse(JSON.parse(row.payload));
      this.audit(actor,action,`${id}:${version}`,note);
      this.db.prepare('UPDATE pro_content SET state=?,reviewer=COALESCE(reviewer,?),reviewed=COALESCE(reviewed,?),published=CASE WHEN ?=1 THEN ? ELSE published END WHERE id=? AND version=?').run(action === 'review' ? 'in_review' : action === 'publish' ? 'published' : 'withdrawn',actor,this.now,Number(action === 'publish'),this.now,id,version);
      if (action !== 'review') {
        // Invalidate earlier versions; old copies remain audit material, never a fallback after withdrawal.
        this.db.prepare("UPDATE pro_content SET state='superseded' WHERE id=? AND version<? AND state='published'").run(id,version);
        this.propagate(id, version, action, action === 'withdraw' || JSON.parse(row.payload).critical);
      }
  }
  contents(): (ProContent & {reviewedAt:number;publishedAt:number})[] { return (this.db.prepare("SELECT payload,reviewed,published FROM pro_content WHERE state='published' ORDER BY published DESC,id").all() as {payload:string;reviewed:number;published:number}[]).map(r => ({...JSON.parse(r.payload),reviewedAt:r.reviewed,publishedAt:r.published})); }
  feedContents() { return (this.db.prepare("SELECT payload,state FROM pro_content WHERE state IN ('published','withdrawn') AND version=(SELECT MAX(version) FROM pro_content c WHERE c.id=pro_content.id AND c.state IN ('published','withdrawn')) ORDER BY published DESC LIMIT 500").all() as {payload:string;state:string}[]).map(r => ({...JSON.parse(r.payload) as ProContent,withdrawn:r.state === 'withdrawn'})); }
  get(id: string, userId?: string) {
    const row=this.db.prepare("SELECT payload,reviewed,published FROM pro_content WHERE id=? AND state='published'").get(id) as {payload:string;reviewed:number;published:number}|undefined;
    const c=row ? {...JSON.parse(row.payload) as ProContent,reviewedAt:row.reviewed,publishedAt:row.published} : undefined;
    if (!c) throw new AccountError(404, 'not_found', '内容不存在或已撤回');
    if (!c.sample) { if (!userId) throw new AccountError(401, 'unauthenticated', '请先登录或配置访问凭证'); this.require(userId); }
    return c;
  }
  settings(userId: string) {
    const row = this.db.prepare('SELECT scope,emailEnabled,emailSince,unsubscribe FROM pro_settings WHERE userId=?').get(userId) as {scope:string;emailEnabled:number;emailSince:number;unsubscribe:string} | undefined;
    return row ? { ...row, scope: JSON.parse(row.scope) as Scope, emailEnabled: Boolean(row.emailEnabled) } : null;
  }
  configure(userId: string, input: unknown, enabled: boolean) {
    this.require(userId); const scope = parseScope(input);
    this.accounts.transaction(() => {
      this.db.prepare('INSERT INTO pro_settings VALUES(?,?,?,?,?) ON CONFLICT(userId) DO UPDATE SET scope=excluded.scope,emailSince=CASE WHEN pro_settings.emailEnabled=0 AND excluded.emailEnabled=1 THEN excluded.emailSince ELSE pro_settings.emailSince END,emailEnabled=excluded.emailEnabled').run(userId,JSON.stringify(scope),Number(enabled),this.now,randomBytes(32).toString('base64url'));
      if (!enabled) this.db.prepare("UPDATE pro_mail SET status='cancelled' WHERE userId=? AND status='pending'").run(userId);
    }); return this.settings(userId);
  }
  unsubscribe(token: string) {
    const row = this.db.prepare('SELECT userId FROM pro_settings WHERE unsubscribe=?').get(token) as {userId:string}|undefined;
    if (!row) throw new AccountError(400, 'invalid_token', '退订链接无效');
    this.accounts.transaction(() => {
      this.db.prepare('UPDATE pro_settings SET emailEnabled=0 WHERE userId=?').run(row.userId);
      this.db.prepare("UPDATE pro_mail SET status='cancelled' WHERE userId=? AND status='pending'").run(row.userId);
    });
  }
  apply(userId: string, scenario: string) {
    if (!scenario.trim() || scenario.length > 500) throw new AccountError(400, 'invalid_application', '请填写500字以内的使用场景');
    this.db.prepare('INSERT INTO pro_applications VALUES(?,?,?) ON CONFLICT(userId) DO UPDATE SET scenario=excluded.scenario,created=excluded.created').run(userId,scenario.trim(),this.now);
    this.event('application','',userId);
  }
  private key() { return createHash('sha256').update(this.accounts.codeSecret).update(':pro-rss').digest(); }
  private encrypt(value: string) { const iv = randomBytes(12), cipher = createCipheriv('aes-256-gcm',this.key(),iv); const encrypted = Buffer.concat([cipher.update(value,'utf8'),cipher.final()]); return Buffer.concat([iv,cipher.getAuthTag(),encrypted]).toString('base64url'); }
  rssSecret(userId: string) {
    const row = this.db.prepare("SELECT encrypted FROM pro_tokens WHERE userId=? AND purpose='rss' AND revoked=0 AND expires>? ORDER BY created DESC LIMIT 1").get(userId,this.now) as {encrypted:string}|undefined;
    if (!row) return null;
    const b = Buffer.from(row.encrypted,'base64url'), decipher = createDecipheriv('aes-256-gcm',this.key(),b.subarray(0,12)); decipher.setAuthTag(b.subarray(12,28)); return Buffer.concat([decipher.update(b.subarray(28)),decipher.final()]).toString('utf8');
  }
  tokens(userId: string) { return this.db.prepare('SELECT id,name,purpose,created,expires,revoked,used FROM pro_tokens WHERE userId=? ORDER BY created DESC LIMIT 100').all(userId); }
  mint(userId: string, name: string, purpose: 'api'|'rss', days = 30) {
    this.require(userId);
    if (!name.trim() || name.length > 60 || !Number.isInteger(days) || days < 1 || days > 365) throw new AccountError(400,'invalid_token','凭证名称或期限无效');
    if (Number(this.db.prepare('SELECT COUNT(*) AS n FROM pro_tokens WHERE userId=? AND revoked=0 AND expires>?').get(userId,this.now)?.n) >= 20) throw new AccountError(400,'token_limit','请先撤销不用的凭证');
    const secret = randomBytes(32).toString('base64url'), tokenId = randomUUID();
    this.accounts.transaction(() => {
      if (purpose === 'rss') this.db.prepare("UPDATE pro_tokens SET revoked=1 WHERE userId=? AND purpose='rss'").run(userId);
      this.db.prepare('INSERT INTO pro_tokens(id,userId,name,purpose,hash,encrypted,created,expires) VALUES(?,?,?,?,?,?,?,?)').run(tokenId,userId,name.trim(),purpose,hash(secret),purpose === 'rss' ? this.encrypt(secret) : null,this.now,this.now+days*86400000);
    }); return {id:tokenId, token:secret};
  }
  revoke(userId: string, id: string) { this.db.prepare('UPDATE pro_tokens SET revoked=1 WHERE id=? AND userId=?').run(id,userId); }
  authenticate(secret: string, purpose: 'api'|'rss'): User {
    if (!/^[A-Za-z0-9_-]{43}$/.test(secret)) throw new AccountError(401,'invalid_token','访问凭证无效，请重新配置');
    const row = this.db.prepare('SELECT u.* FROM pro_tokens t JOIN users u ON u.id=t.userId WHERE t.hash=? AND t.purpose=? AND t.revoked=0 AND t.expires>?').get(hash(secret),purpose,this.now) as unknown as (User & {id:string})|undefined;
    if (!row) throw new AccountError(401,'invalid_token','访问凭证无效，请重新配置');
    this.require(row.id); this.db.prepare('UPDATE pro_tokens SET used=? WHERE hash=?').run(this.now,hash(secret)); return row;
  }
  reports(userId: string) { return (this.db.prepare('SELECT id,period,scope,coverage,created FROM pro_reports WHERE userId=? ORDER BY period DESC LIMIT 100').all(userId) as unknown as {id:string;period:string;scope:string;coverage:string;created:number}[]).map(r => ({...r,scope:JSON.parse(r.scope) as Scope})); }
  report(userId: string, id: string) {
    this.require(userId);
    const row = this.db.prepare('SELECT * FROM pro_reports WHERE id=? AND userId=?').get(id,userId) as {id:string;period:string;scope:string;refs:string;coverage:string;created:number}|undefined;
    if (!row) throw new AccountError(404,'not_found','简报不存在');
    const refs = JSON.parse(row.refs) as {id:string;version:number}[];
    return {...row,scope:JSON.parse(row.scope),refs,items:refs.map(r => {
      try { return {...this.get(r.id,userId),selectedVersion:r.version}; }
      catch (error) { if (!(error instanceof AccountError) || error.status !== 404) throw error; return {id:r.id,version:r.version,withdrawn:true,title:'内容已撤回'}; }
    })};
  }
  compose(period: string, coverage: 'normal'|'partial'|'failed', queueMail = false) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(period) || !Number.isFinite(Date.parse(period))) throw new Error('period must be Monday YYYY-MM-DD');
    const to = Date.parse(`${period}T00:00:00+08:00`); if (new Date(to+8*3600000).getUTCDay() !== 1) throw new Error('period must end on Monday');
    return this.accounts.transaction(() => this.composeInTransaction(period,coverage,queueMail));
  }
  composeInTransaction(period: string, coverage: 'normal'|'partial'|'failed', queueMail=false) {
    const to=Date.parse(`${period}T00:00:00+08:00`);
      let count = 0;
      const settings = this.db.prepare('SELECT userId FROM pro_settings').all() as {userId:string}[];
      for (const {userId} of settings) {
        if (this.entitlement(userId).status !== 'active') continue;
        const s = this.settings(userId)!;
        const refs = this.contents().filter(c => !c.sample && c.kind !== 'briefing' && Date.parse(c.period.to) > to-7*86400000 && Date.parse(c.period.to) <= to && matches(c,s.scope)).map(c => ({id:c.id,version:c.version}));
        const reportId = hash(`${userId}:${period}`);
        const inserted = this.db.prepare('INSERT OR IGNORE INTO pro_reports VALUES(?,?,?,?,?,?,?)').run(reportId,userId,period,JSON.stringify(s.scope),JSON.stringify(refs),coverage,this.now);
        if (!inserted.changes) continue; count++;
        if (queueMail && s.emailEnabled) this.db.prepare('INSERT OR IGNORE INTO pro_mail(id,userId,reportId,created) VALUES(?,?,?,?)').run(`report-${reportId}`,userId,reportId,this.now);
      } return count;
  }
  private propagate(contentId: string, version: number, action: 'publish'|'withdraw', critical: boolean) {
    if (!critical) return;
    const rows = this.db.prepare('SELECT id,userId,refs FROM pro_reports').all() as {id:string;userId:string;refs:string}[];
    for (const r of rows) if ((JSON.parse(r.refs) as {id:string}[]).some(ref => ref.id === contentId) && this.settings(r.userId)?.emailEnabled && this.entitlement(r.userId).status === 'active') {
      this.db.prepare('INSERT OR IGNORE INTO pro_mail(id,userId,reportId,created) VALUES(?,?,?,?)').run(`correction-${r.id}-${contentId}-${version}-${action}`,r.userId,r.id,this.now);
    }
  }
}
