export interface AccountMe {
  user: { id: string; email: string; displayName: string; created: number; plan: string; hasPassword: boolean };
  preferences: { emailEnabled: boolean };
  watches: { modelId: string; since: number }[];
  state: Record<string, unknown>;
}
export class AccountApiError extends Error { constructor(message: string, readonly status: number) { super(message); } }
export async function accountApi<T>(route: string, payload?: unknown, keepalive = false): Promise<T> {
  const response = await fetch(`/api/account/${route}`, { credentials: 'same-origin', cache: 'no-store', keepalive,
    ...(payload === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) });
  let value; try { value = await response.json(); } catch { throw new AccountApiError('服务暂不可用，请稍后重试', response.status); }
  if (!response.ok) throw new AccountApiError(value.message ?? '操作失败，请稍后重试', response.status);
  return value;
}
let me: AccountMe | null = null;
const listeners = new Set<(value: AccountMe | null) => void>();
let generation = 0;
let queue: Promise<unknown> = Promise.resolve();
type PendingWrite = { owner: string; value: unknown };
const writes = new Map<string, PendingWrite>();
const timers = new Map<string, ReturnType<typeof setTimeout>>();
function syncStatus(status: string) { document.dispatchEvent(new CustomEvent('maas:account-sync', { detail: status })); }
function notify() { for (const listener of listeners) listener(me); }
export async function refreshAccount() {
  const version = ++generation;
  try {
    const value = await accountApi<AccountMe>('me');
    if (version !== generation) return me;
    if (me && me.user.id !== value.user.id) { for (const timer of timers.values()) clearTimeout(timer); timers.clear(); writes.clear(); }
    for (const [key, write] of writes) if (write.owner === value.user.id) value.state[key] = write.value;
    me = value;
  } catch (error) {
    if (version !== generation) return me;
    if (!(error instanceof AccountApiError) || error.status !== 401) { syncStatus('error'); return me; }
    for (const timer of timers.values()) clearTimeout(timer); timers.clear(); writes.clear();
    me = null;
  }
  notify(); return me;
}
export const accountReady = refreshAccount();
export function currentAccount() { return me; }
export function onAccountChange(listener: (value: AccountMe | null) => void) { listeners.add(listener); void accountReady.then(() => listener(me)); }
export function announceAccountChange() {
  try { localStorage.setItem('maas-auth-event', String(Date.now()) + Math.random()); } catch {}
  return refreshAccount();
}
window.addEventListener('storage', event => { if (event.key === 'maas-auth-event') void refreshAccount(); });
document.addEventListener('visibilitychange', () => { if (document.visibilityState === 'visible') void refreshAccount(); });
window.addEventListener('pageshow', event => { if (event.persisted) void refreshAccount(); });
export async function logoutAccount(all = false) {
  await flushAccountState();
  for (const timer of timers.values()) clearTimeout(timer); timers.clear(); writes.clear();
  await accountApi(all ? 'logout-all' : 'logout', {});
  me = null; generation++; notify(); syncStatus('guest');
  try { localStorage.setItem('maas-auth-event', String(Date.now()) + Math.random()); } catch {}
}
function writeState(key: string, write: PendingWrite) {
  queue = queue.catch(() => {}).then(async () => {
    if (me?.user.id !== write.owner) return;
    try {
      await accountApi('state', { key, value: write.value }, true);
      if (writes.get(key) === write) writes.delete(key);
      if (me?.user.id === write.owner) syncStatus(writes.size ? 'saving' : 'saved');
    } catch (error) {
      if (me?.user.id !== write.owner) return;
      syncStatus('error');
      if (error instanceof AccountApiError && error.status === 401) { writes.clear(); void refreshAccount(); }
      throw error;
    }
  });
  return queue;
}
export async function flushAccountState() {
  for (const timer of timers.values()) clearTimeout(timer); timers.clear();
  for (const [key, write] of writes) void writeState(key, write).catch(() => {});
  await queue;
}
window.addEventListener('pagehide', () => { void flushAccountState().catch(() => {}); });
// Finish short pending saves before normal internal navigation, including immediate clicks.
document.addEventListener('click', event => {
  const mouse = event as MouseEvent;
  const link = (event.target as HTMLElement).closest<HTMLAnchorElement>('a[href]');
  if (!writes.size || !link || event.defaultPrevented || mouse.button !== 0 || mouse.metaKey || mouse.ctrlKey || mouse.shiftKey || mouse.altKey || link.target || link.download) return;
  const url = new URL(link.href);
  if (url.origin !== location.origin || (url.pathname === location.pathname && url.search === location.search)) return;
  event.preventDefault();
  void flushAccountState().then(() => location.assign(url.href)).catch(() => syncStatus('error'));
});
export function savedState<T>(key: string, defaults: T, apply: (value: T) => void) {
  const guestKey = `maas-guest-${key}`;
  const readGuest = () => { try { return JSON.parse(localStorage.getItem(guestKey) ?? 'null') ?? defaults; } catch { return defaults; } };
  apply(readGuest());
  onAccountChange(user => apply(user ? (user.state[key] as T ?? defaults) : readGuest()));
  return (next: T) => {
    if (!me) { try { localStorage.setItem(guestKey, JSON.stringify(next)); } catch {} return; }
    const write = { owner: me.user.id, value: next };
    me.state[key] = next; writes.set(key, write);
    const old = timers.get(key); if (old) clearTimeout(old);
    syncStatus('saving');
    timers.set(key, setTimeout(() => {
      timers.delete(key); void writeState(key, write).catch(() => {});
    }, 600));
  };
}
export function openAccountLogin() { document.querySelector<HTMLDialogElement>('#account-login-dialog')?.showModal(); }
