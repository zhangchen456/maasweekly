import { randomUUID } from 'node:crypto';
import type { IncomingMessage, ServerResponse } from 'node:http';
import type { DatasetHolder } from './dataset.js';
import { AccountError, AccountStore } from './account-store.js';
import type { Mailer } from './account-mail.js';
import { ClientRateLimiter } from './rate-limit.js';
import { validateAccountState } from './account-state.js';

export interface AccountConfig { origin: string; secure: boolean; trustProxy?: boolean }
const PREFIX = '/api/account/';
function email(value: unknown): string {
  if (typeof value !== 'string' || value.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim())) throw new AccountError(400, 'invalid_email', '请输入有效邮箱');
  return value.trim().toLowerCase();
}
async function body(req: IncomingMessage): Promise<Record<string, unknown>> {
  if (!req.headers['content-type']?.startsWith('application/json')) throw new AccountError(415, 'invalid_content_type', '请求需使用 JSON');
  const chunks: Buffer[] = []; let size = 0;
  for await (const chunk of req) {
    size += Buffer.byteLength(chunk);
    if (size > 8192) throw new AccountError(413, 'body_too_large', '请求过大');
    chunks.push(Buffer.from(chunk));
  }
  try {
    const result = JSON.parse(Buffer.concat(chunks).toString('utf8'));
    if (!result || typeof result !== 'object' || Array.isArray(result)) throw new Error();
    return result;
  } catch { throw new AccountError(400, 'invalid_json', '请求格式错误'); }
}
function reply(res: ServerResponse, status: number, value: unknown) {
  res.writeHead(status, { 'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store', 'Vary': 'Cookie', 'X-Content-Type-Options': 'nosniff' });
  res.end(JSON.stringify(value));
}
export function createAccountHandler(store: AccountStore | null, mailer: Mailer | null, holder: DatasetHolder, config: AccountConfig) {
  // A normal account session loads several views and saves workspace settings; OTP has its own stricter budget.
  const limiter = new ClientRateLimiter({ capacity: 120, refillPerMinute: 60, globalCapacity: 1000, globalRefillPerMinute: 300, trustLoopbackProxy: config.trustProxy });
  const authLimiter = new ClientRateLimiter({ capacity: 6, refillPerMinute: 1, globalCapacity: 100, globalRefillPerMinute: 20, trustLoopbackProxy: config.trustProxy });
  const cookieName = config.secure ? '__Host-maas_session' : 'maas_session';
  const cookie = (value: string, age: number) => `${cookieName}=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=${age}${config.secure ? '; Secure' : ''}`;
  return async (req: IncomingMessage, res: ServerResponse) => {
    try {
      const route = new URL(req.url ?? '/', config.origin).pathname.slice(PREFIX.length);
      if (route === 'status' && req.method === 'GET') { reply(res, 200, { enabled: Boolean(store), mailAvailable: Boolean(mailer), cadence: 'daily' }); return; }
      if (!store) throw new AccountError(503, 'account_unavailable', '账号服务尚未启用');
      const allowance = limiter.take(req);
      if (!allowance.allowed) { res.setHeader('Retry-After', allowance.retryAfterSeconds); throw new AccountError(429, 'rate_limited', '操作频繁，请稍后再试'); }
      if (!['GET', 'POST'].includes(req.method ?? '')) throw new AccountError(405, 'method_not_allowed', '不支持该请求方式');
      if (req.method === 'POST' && req.headers.origin !== config.origin) throw new AccountError(403, 'invalid_origin', '请从本站操作');
      if (req.headers['sec-fetch-site'] === 'cross-site') throw new AccountError(403, 'invalid_origin', '请从本站操作');
      const session = (req.headers.cookie ?? '').split(';').map(s => s.trim()).find(s => s.startsWith(`${cookieName}=`))?.slice(cookieName.length + 1) ?? '';
      const input = req.method === 'POST' ? await body(req) : {};
      if (route === 'request-code' && req.method === 'POST') {
        if (!mailer) throw new AccountError(503, 'mail_unavailable', '邮件服务尚未配置，请稍后再试');
        if (!authLimiter.take(req).allowed) throw new AccountError(429, 'rate_limited', '发送频繁，请稍后再试');
        const address = email(input.email), code = store.issueCode(address);
        try { await mailer.send({ to: address, subject: 'MaaS Daily 登录验证码', text: `你的登录验证码是 ${code}，10 分钟内有效。\n如果你没有请求登录，请忽略这封邮件。`, key: `login-${randomUUID()}` }); }
        catch { store.revokeCode(address, code); throw new AccountError(503, 'mail_delivery_failed', '邮件发送失败，请稍后重新获取'); }
        reply(res, 200, { message: '验证码已发送，请查看邮箱', retryAfter: 60 }); return;
      }
      if (route === 'verify' && req.method === 'POST') {
        const address = email(input.email);
        if (typeof input.code !== 'string' || !/^\d{6}$/.test(input.code)) throw new AccountError(400, 'invalid_code', '请输入六位验证码');
        const result = store.verify(address, input.code);
        if (session) store.logout(session);
        res.setHeader('Set-Cookie', cookie(result.session, 30 * 86400));
        reply(res, 200, { authenticated: true }); return;
      }
      if (route === 'login' && req.method === 'POST') {
        if (!authLimiter.take(req).allowed) throw new AccountError(429, 'rate_limited', '尝试频繁，请稍后再试');
        const result = await store.loginPassword(email(input.email), input.password);
        if (session) store.logout(session);
        res.setHeader('Set-Cookie', cookie(result.session, 30 * 86400));
        reply(res, 200, { authenticated: true }); return;
      }
      if (route === 'unsubscribe' && req.method === 'POST') {
        if (typeof input.token !== 'string' || input.token.length > 100 || !store.unsubscribe(input.token)) throw new AccountError(400, 'invalid_token', '退订链接无效');
        reply(res, 200, { message: '已关闭邮件提醒，关注列表仍保留' }); return;
      }
      const user = store.user(session);
      if (!user) throw new AccountError(401, 'unauthenticated', '请先登录');
      if (route === 'me' && req.method === 'GET') {
        reply(res, 200, { user: { id: user.id, email: user.email, organizationId: user.organizationId, plan: user.plan, hasPassword: store.hasPassword(user.id), ...store.profile(user) }, preferences: { emailEnabled: Boolean(user.emailEnabled) }, watches: store.watches(user.id), state: store.state(user.id) }); return;
      }
      if (route === 'password' && req.method === 'POST') {
        if (!authLimiter.take(req).allowed) throw new AccountError(429, 'rate_limited', '尝试频繁，请稍后再试');
        await store.setPassword(session, input.password);
        reply(res, 200, { saved: true }); return;
      }
      if (route === 'profile' && req.method === 'POST') {
        if (typeof input.displayName !== 'string' || input.displayName.trim().length > 60 || /[\u0000-\u001f]/.test(input.displayName)) throw new AccountError(400, 'invalid_profile', '昵称需在60个字符以内');
        reply(res, 200, store.updateProfile(user, input.displayName.trim())); return;
      }
      if (route === 'state' && req.method === 'POST') {
        const state = validateAccountState(input.key, input.value);
        store.saveState(user.id, state.key, state.value); reply(res, 200, { saved: true }); return;
      }
      if (route === 'export' && req.method === 'GET') {
        reply(res, 200, { user: { email: user.email, ...store.profile(user) }, preferences: { emailEnabled: Boolean(user.emailEnabled) }, watches: store.watches(user.id), state: store.state(user.id) }); return;
      }
      if (route === 'logout-all' && req.method === 'POST') {
        store.logoutAll(user.id); res.setHeader('Set-Cookie', cookie('', 0)); reply(res, 200, { authenticated: false }); return;
      }
      if (route === 'logout' && req.method === 'POST') {
        store.logout(session); res.setHeader('Set-Cookie', cookie('', 0)); reply(res, 200, { authenticated: false }); return;
      }
      if (route === 'preferences' && req.method === 'POST') {
        if (typeof input.emailEnabled !== 'boolean') throw new AccountError(400, 'invalid_preference', '请选择提醒方式');
        if (input.emailEnabled && !mailer) throw new AccountError(503, 'mail_unavailable', '邮件服务尚未配置');
        store.preferences(user.id, input.emailEnabled); reply(res, 200, { emailEnabled: input.emailEnabled }); return;
      }
      if ((route === 'watch' || route === 'unwatch') && req.method === 'POST') {
        if (typeof input.modelId !== 'string' || input.modelId.length > 200) throw new AccountError(400, 'invalid_model', '模型标识无效');
        if (route === 'watch') {
          if (!holder.current) throw new AccountError(503, 'data_unavailable', '模型目录暂不可用');
          store.watch(user.id, input.modelId, holder.current.modelIdentities);
        } else store.unwatch(user.id, input.modelId);
        reply(res, 200, { watches: store.watches(user.id) }); return;
      }
      if (route === 'changes' && req.method === 'GET') {
        if (!holder.current) throw new AccountError(503, 'data_unavailable', '变化数据暂不可用');
        const ids = new Set(store.watches(user.id).map(w => w.modelId));
        const items = holder.current.changes.filter(c => c.modelId && ids.has(c.modelId)).slice(0, 100);
        reply(res, 200, { items, dataThrough: holder.current.dataThrough }); return;
      }
      throw new AccountError(404, 'not_found', '页面不存在');
    } catch (error) {
      const e = error instanceof AccountError ? error : new AccountError(503, 'account_error', '服务暂不可用，请稍后再试');
      if (!res.headersSent) reply(res, e.status, { code: e.code, message: e.message });
      else res.end();
    }
  };
}
