import type { IncomingMessage } from 'node:http';
import { AccountError } from './account-store.js';
import type { AdminStore } from './admin-store.js';
export function authenticateAdmin(req: IncomingMessage, store: AdminStore, secure: boolean) {
  const name=secure?'__Host-maas_session':'maas_session';
  const session=(req.headers.cookie ?? '').split(';').map(v=>v.trim()).find(v=>v.startsWith(name+'='))?.slice(name.length+1) ?? '';
  const user=store.accounts.user(session);
  if(!user) throw new AccountError(401,'unauthenticated','请先登录');
  if(!store.member(user.id)) throw new AccountError(403,'forbidden','无后台访问权限');
  return user;
}
