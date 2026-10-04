import { DatabaseSync } from 'node:sqlite';
import { createHash, createHmac, randomBytes, randomInt, randomUUID, timingSafeEqual, scrypt } from 'node:crypto';
import { mkdirSync, chmodSync } from 'node:fs';
import path from 'node:path';
import type { ChangeEntity, ModelIdentityCatalog } from './public-contract/entities.js';

export const hash = (s: string) => createHash('sha256').update(s).digest('hex');
const token = () => randomBytes(32).toString('base64url');
const MINUTE = 60000;
export class AccountError extends Error {
  constructor(public status: number, public code: string, message: string) { super(message); }
}
export interface User { id: string; email: string; organizationId: string; plan: string; emailEnabled: number; emailSince: number; unsubscribeToken: string }
interface Challenge { hash: string; expires: number; attempts: number }
interface Job { id: string; userId: string; payload: string; created: number; lease: number; status: string; mail: string | null }
export class AccountStore {
  readonly db: DatabaseSync;
  constructor(filename: string, readonly now = Date.now, readonly codeSecret = process.env.MAAS_ACCOUNT_SECRET ?? '') {
    if (codeSecret.length < 32) throw new Error('MAAS_ACCOUNT_SECRET must contain at least 32 characters');
    if (filename !== ':memory:') mkdirSync(path.dirname(filename), { recursive: true, mode: 0o700 });
    this.db = new DatabaseSync(filename);
    if (filename !== ':memory:') chmodSync(filename, 0o600);
    this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;
      CREATE TABLE IF NOT EXISTS organizations(id TEXT PRIMARY KEY, name TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY, email TEXT NOT NULL UNIQUE, organizationId TEXT NOT NULL REFERENCES organizations(id), plan TEXT NOT NULL DEFAULT 'free', emailEnabled INTEGER NOT NULL DEFAULT 0, emailSince INTEGER NOT NULL DEFAULT 0, unsubscribeToken TEXT NOT NULL UNIQUE);
      CREATE TABLE IF NOT EXISTS challenges(email TEXT PRIMARY KEY, hash TEXT NOT NULL, expires INTEGER NOT NULL, attempts INTEGER NOT NULL DEFAULT 0);
      CREATE TABLE IF NOT EXISTS send_limits(email TEXT PRIMARY KEY, lastSent INTEGER NOT NULL, windowStart INTEGER NOT NULL, count INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS passwords(userId TEXT PRIMARY KEY REFERENCES users(id), salt TEXT NOT NULL, digest TEXT NOT NULL);
      CREATE TABLE IF NOT EXISTS password_attempts(email TEXT PRIMARY KEY, count INTEGER NOT NULL, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS email_proofs(sessionHash TEXT PRIMARY KEY REFERENCES sessions(hash) ON DELETE CASCADE, expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, userId TEXT NOT NULL REFERENCES users(id), expires INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS account_profiles(userId TEXT PRIMARY KEY REFERENCES users(id), displayName TEXT NOT NULL DEFAULT '', created INTEGER NOT NULL);
      CREATE TABLE IF NOT EXISTS account_state(userId TEXT NOT NULL REFERENCES users(id), key TEXT NOT NULL, value TEXT NOT NULL, updated INTEGER NOT NULL, PRIMARY KEY(userId,key));
      CREATE TABLE IF NOT EXISTS watches(userId TEXT NOT NULL REFERENCES users(id), modelId TEXT NOT NULL, since INTEGER NOT NULL, PRIMARY KEY(userId, modelId));
      CREATE TABLE IF NOT EXISTS mail_jobs(id TEXT PRIMARY KEY, userId TEXT NOT NULL REFERENCES users(id), payload TEXT NOT NULL, created INTEGER NOT NULL, lease INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL DEFAULT 'pending', mail TEXT);
      CREATE TABLE IF NOT EXISTS mail_items(userId TEXT NOT NULL REFERENCES users(id), eventKey TEXT NOT NULL, jobId TEXT NOT NULL REFERENCES mail_jobs(id), PRIMARY KEY(userId,eventKey));
      CREATE INDEX IF NOT EXISTS sessions_expiry ON sessions(expires);
      CREATE INDEX IF NOT EXISTS jobs_pending ON mail_jobs(status, lease);`);
  }
  close() { this.db.close(); }
  transaction<T>(fn: () => T): T {
    this.db.exec('BEGIN IMMEDIATE');
    try { const result = fn(); this.db.exec('COMMIT'); return result; }
    catch (e) { this.db.exec('ROLLBACK'); throw e; }
  }
  codeHash(email: string, code: string) { return createHmac('sha256', this.codeSecret).update(`${email}:${code}`).digest('hex'); }
  issueCode(email: string) {
    return this.transaction(() => {
      const now = this.now();
      const budget = this.db.prepare('SELECT * FROM send_limits WHERE email=?').get(email) as { lastSent: number; windowStart: number; count: number } | undefined;
      if (budget && (now - budget.lastSent < MINUTE || (now - budget.windowStart < 60 * MINUTE && budget.count >= 5))) throw new AccountError(429, 'email_rate_limited', '发送频繁，请稍后再试');
      const fresh = !budget || now - budget.windowStart >= 60 * MINUTE;
      this.db.prepare('INSERT OR REPLACE INTO send_limits VALUES(?,?,?,?)').run(email, now, fresh ? now : budget.windowStart, fresh ? 1 : budget.count + 1);
      const code = String(randomInt(0, 1000000)).padStart(6, '0');
      this.db.prepare('INSERT OR REPLACE INTO challenges VALUES(?,?,?,0)').run(email, this.codeHash(email, code), now + 10 * MINUTE);
      this.cleanup();
      return code;
    });
  }
  revokeCode(email: string, code: string) { this.db.prepare('DELETE FROM challenges WHERE email=? AND hash=?').run(email, this.codeHash(email, code)); }
  verify(email: string, code: string) {
    // Failed attempts must commit as well: return an error marker from the transaction.
    const result = this.transaction(() => {
      const row = this.db.prepare('SELECT * FROM challenges WHERE email=?').get(email) as unknown as Challenge | undefined;
      if (!row || row.expires <= this.now() || row.attempts >= 5) return null;
      if (!timingSafeEqual(Buffer.from(row.hash), Buffer.from(this.codeHash(email, code)))) {
        this.db.prepare('UPDATE challenges SET attempts=attempts+1 WHERE email=?').run(email); return null;
      }
      this.db.prepare('DELETE FROM challenges WHERE email=?').run(email);
      let user = this.db.prepare('SELECT * FROM users WHERE email=?').get(email) as unknown as User | undefined;
      if (!user) {
        const org = randomUUID(), id = randomUUID();
        this.db.prepare('INSERT INTO organizations VALUES(?,?)').run(org, '个人空间');
        this.db.prepare('INSERT INTO users(id,email,organizationId,unsubscribeToken) VALUES(?,?,?,?)').run(id, email, org, token());
        user = this.db.prepare('SELECT * FROM users WHERE id=?').get(id) as unknown as User;
      }
      this.profile(user);
      const session = token();
      this.db.prepare('INSERT INTO sessions VALUES(?,?,?)').run(hash(session), user.id, this.now() + 30 * 24 * 60 * MINUTE);
      this.db.prepare('INSERT INTO email_proofs VALUES(?,?)').run(hash(session), this.now() + 10 * MINUTE);
      // Limit live sessions per user without changing the current session.
      this.db.prepare('DELETE FROM sessions WHERE userId=? AND hash NOT IN (SELECT hash FROM sessions WHERE userId=? ORDER BY expires DESC, rowid DESC LIMIT 10)').run(user.id, user.id);
      return { user, session };
    });
    if (!result) throw new AccountError(400, 'invalid_code', '验证码错误或已过期，请重新获取');
    return result;
  }
  hasPassword(id: string) { return Boolean(this.db.prepare('SELECT 1 FROM passwords WHERE userId=?').get(id)); }
  async derive(password: string, salt: string): Promise<Buffer> {
    return new Promise((resolve, reject) => scrypt(password, salt, 64, { N: 16384, r: 8, p: 1 }, (error, key) => error ? reject(error) : resolve(key)));
  }
  async loginPassword(email: string, password: unknown) {
    if (typeof password !== 'string' || password.length > 128) throw new AccountError(401, 'invalid_credentials', '邮箱或密码错误');
    const limit = this.db.prepare('SELECT count,expires FROM password_attempts WHERE email=?').get(email) as {count: number; expires: number} | undefined;
    if (limit && limit.expires > this.now() && limit.count >= 10) throw new AccountError(429, 'rate_limited', '尝试过多，请15分钟后再试');
    this.db.prepare('INSERT INTO password_attempts VALUES(?,1,?) ON CONFLICT(email) DO UPDATE SET count=CASE WHEN expires<=? THEN 1 ELSE count+1 END,expires=CASE WHEN expires<=? THEN excluded.expires ELSE expires END').run(email, this.now() + 15 * MINUTE, this.now(), this.now());
    const row = this.db.prepare('SELECT u.id,p.salt,p.digest FROM users u JOIN passwords p ON p.userId=u.id WHERE u.email=?').get(email) as {id: string; salt: string; digest: string} | undefined;
    const key = await this.derive(password, row?.salt ?? 'maas-dummy-password-salt');
    if (!row || !timingSafeEqual(key, Buffer.from(row.digest, 'hex'))) throw new AccountError(401, 'invalid_credentials', '邮箱或密码错误');
    const session = token();
    this.transaction(() => {
      const current = this.db.prepare('SELECT digest FROM passwords WHERE userId=?').get(row.id) as {digest: string} | undefined;
      if (current?.digest !== row.digest) throw new AccountError(401, 'invalid_credentials', '密码已更新，请重新登录');
      this.db.prepare('DELETE FROM password_attempts WHERE email=?').run(email);
      this.db.prepare('INSERT INTO sessions VALUES(?,?,?)').run(hash(session), row.id, this.now() + 30 * 24 * 60 * MINUTE);
      this.db.prepare('DELETE FROM sessions WHERE userId=? AND hash NOT IN (SELECT hash FROM sessions WHERE userId=? ORDER BY expires DESC,rowid DESC LIMIT 10)').run(row.id, row.id);
    });
    return { session };
  }
  async setPassword(session: string, password: unknown) {
    if (typeof password !== 'string' || password.length < 8 || password.length > 128) throw new AccountError(400, 'invalid_password', '密码需为8至128个字符');
    const salt = randomBytes(16).toString('hex'), digest = (await this.derive(password, salt)).toString('hex');
    return this.transaction(() => {
      const user = this.user(session);
      const proof = this.db.prepare('SELECT 1 FROM email_proofs WHERE sessionHash=? AND expires>?').get(hash(session), this.now());
      if (!user || !proof) throw new AccountError(403, 'verification_required', '请先验证邮箱，再设置密码');
      this.db.prepare('INSERT INTO passwords VALUES(?,?,?) ON CONFLICT(userId) DO UPDATE SET salt=excluded.salt,digest=excluded.digest').run(user.id, salt, digest);
      this.db.prepare('DELETE FROM sessions WHERE userId=? AND hash<>?').run(user.id, hash(session));
      this.db.prepare('DELETE FROM email_proofs WHERE sessionHash=?').run(hash(session));
      this.db.prepare('DELETE FROM password_attempts WHERE email=?').run(user.email);
    });
  }
  user(session: string): User | undefined {
    return this.db.prepare('SELECT u.* FROM users u JOIN sessions s ON s.userId=u.id WHERE s.hash=? AND s.expires>?').get(hash(session), this.now()) as unknown as User | undefined;
  }
  logout(session: string) { this.db.prepare('DELETE FROM sessions WHERE hash=?').run(hash(session)); }
  logoutAll(id: string) { this.db.prepare('DELETE FROM sessions WHERE userId=?').run(id); }
  profile(user: User) {
    this.db.prepare('INSERT OR IGNORE INTO account_profiles VALUES(?,?,?)').run(user.id, '', this.now());
    return this.db.prepare('SELECT displayName,created FROM account_profiles WHERE userId=?').get(user.id) as { displayName: string; created: number };
  }
  updateProfile(user: User, displayName: string) {
    this.profile(user);
    this.db.prepare('UPDATE account_profiles SET displayName=? WHERE userId=?').run(displayName, user.id);
    return this.profile(user);
  }
  state(id: string): Record<string, unknown> {
    const rows = this.db.prepare('SELECT key,value FROM account_state WHERE userId=?').all(id) as { key: string; value: string }[];
    return Object.fromEntries(rows.map(row => [row.key, JSON.parse(row.value)]));
  }
  saveState(id: string, key: string, value: unknown) {
    this.db.prepare('INSERT INTO account_state VALUES(?,?,?,?) ON CONFLICT(userId,key) DO UPDATE SET value=excluded.value,updated=excluded.updated').run(id, key, JSON.stringify(value), this.now());
  }
  watches(id: string) { return this.db.prepare('SELECT modelId,since FROM watches WHERE userId=? ORDER BY since DESC,modelId').all(id) as unknown as {modelId: string; since: number}[]; }
  watch(id: string, modelId: string, catalog: ModelIdentityCatalog) {
    if (!catalog.models.some(m => m.modelId === modelId)) throw new AccountError(400, 'unknown_model', '请选择目录中的模型');
    this.transaction(() => {
      if (this.watches(id).length >= 50 && !this.watches(id).some(w => w.modelId === modelId)) throw new AccountError(400, 'watch_limit', '最多关注 50 个模型');
      this.db.prepare('INSERT OR IGNORE INTO watches VALUES(?,?,?)').run(id, modelId, this.now());
    });
  }
  unwatch(id: string, modelId: string) { this.db.prepare('DELETE FROM watches WHERE userId=? AND modelId=?').run(id, modelId); }
  preferences(id: string, enabled: boolean) {
    this.transaction(() => {
      this.db.prepare('UPDATE users SET emailSince=CASE WHEN emailEnabled=0 AND ?=1 THEN ? ELSE emailSince END,emailEnabled=? WHERE id=?').run(Number(enabled), this.now(), Number(enabled), id);
      if (!enabled) this.cancelPending(id);
    });
  }
  cancelPending(id: string) {
    this.db.prepare("UPDATE mail_jobs SET status='cancelled' WHERE userId=? AND status='pending'").run(id);
  }
  unsubscribe(value: string): boolean {
    const user = this.db.prepare('SELECT * FROM users WHERE unsubscribeToken=?').get(value) as unknown as User | undefined;
    if (!user) return false;
    this.preferences(user.id, false); return true;
  }
  enqueue(changes: readonly ChangeEntity[]) {
    return this.transaction(() => {
      let count = 0;
      const users = this.db.prepare('SELECT * FROM users WHERE emailEnabled=1').all() as unknown as User[];
      for (const user of users) {
        const watches = new Map(this.watches(user.id).map(w => [w.modelId, Math.max(w.since, user.emailSince)]));
        const items = changes.filter(c => {
          const since = c.modelId ? watches.get(c.modelId) : undefined;
          const when = Date.parse(c.updatedAt ?? c.observedAt ?? `${c.observationDate}T00:00:00+08:00`);
          return since !== undefined && when > since && !this.db.prepare('SELECT 1 FROM mail_items WHERE userId=? AND eventKey=?').get(user.id, `${c.id}:${c.revision}`);
        }).sort((a,b) => a.id.localeCompare(b.id)).slice(0, 50);
        if (!items.length) continue;
        const id = hash(`${user.id}:${items.map(c => `${c.id}:${c.revision}`).join(',')}`);
        this.db.prepare('INSERT INTO mail_jobs(id,userId,payload,created) VALUES(?,?,?,?)').run(id, user.id, JSON.stringify(items), this.now());
        for (const c of items) this.db.prepare('INSERT INTO mail_items VALUES(?,?,?)').run(user.id, `${c.id}:${c.revision}`, id);
        count++;
      }
      return count;
    });
  }
  claim(): (Job & { user: User }) | null {
    return this.transaction(() => {
      // Resend idempotency expires after 24h. Uncertain older attempts require review.
      this.db.prepare("UPDATE mail_jobs SET status='review' WHERE status='pending' AND lease>0 AND created<?").run(this.now() - 23 * 60 * MINUTE);
      const job = this.db.prepare("SELECT j.* FROM mail_jobs j JOIN users u ON u.id=j.userId WHERE j.status='pending' AND u.emailEnabled=1 AND j.lease<? ORDER BY j.created LIMIT 1").get(this.now()) as unknown as Job | undefined;
      if (!job) return null;
      this.db.prepare('UPDATE mail_jobs SET lease=? WHERE id=?').run(this.now() + 5 * MINUTE, job.id);
      const user = this.db.prepare('SELECT * FROM users WHERE id=?').get(job.userId) as unknown as User;
      return { ...job, user };
    });
  }
  freezeMail(id: string, mail: string) { this.db.prepare('UPDATE mail_jobs SET mail=COALESCE(mail,?) WHERE id=?').run(mail, id); }
  sent(id: string) { this.db.prepare("UPDATE mail_jobs SET status='sent',lease=0 WHERE id=?").run(id); }
  cleanup() {
    this.db.prepare('DELETE FROM sessions WHERE expires<=?').run(this.now());
    this.db.prepare('DELETE FROM challenges WHERE expires<=?').run(this.now());
    this.db.prepare('DELETE FROM send_limits WHERE windowStart<?').run(this.now() - 24 * 60 * MINUTE);
  }
}
