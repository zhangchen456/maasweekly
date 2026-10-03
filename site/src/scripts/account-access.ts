import { accountApi, announceAccountChange, onAccountChange, logoutAccount, flushAccountState } from './account-client';
const root = document.querySelector<HTMLElement>('[data-account-access]');
if (root) {
  const en = root.dataset.locale === 'en';
  const t = (zh: string, english: string) => en ? english : zh;
  const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  const dialog = el<HTMLDialogElement>('account-login-dialog');
  const open = el<HTMLButtonElement>('account-login-open');
  const menu = el<HTMLDetailsElement>('account-user-menu');
  const feedback = el('account-login-feedback');
  const email = el<HTMLInputElement>('account-login-email');
  const code = el<HTMLInputElement>('account-login-code');
  const send = el<HTMLButtonElement>('account-global-send');
  const verify = el<HTMLButtonElement>('account-global-verify');
  let busy = false, cooldown = 0;
  const show = (text: string, error = false) => { feedback.textContent = text; feedback.dataset.error = String(error); };
  onAccountChange(me => {
    open.hidden = Boolean(me); menu.hidden = !me;
    if (!me) { menu.open = false; for (const id of ['account-user-name', 'account-menu-name', 'account-avatar', 'account-menu-email']) el(id).textContent = ''; return; }
    const name = me.user.displayName || me.user.email.split('@')[0];
    el('account-user-name').textContent = name;
    el('account-menu-name').textContent = name;
    el('account-avatar').textContent = name.slice(0, 1).toUpperCase();
    el('account-menu-email').textContent = me.user.email;
  });
  open.addEventListener('click', () => { dialog.showModal(); email.focus(); });
  el('account-login-close').addEventListener('click', () => dialog.close());
  dialog.addEventListener('click', event => { if (event.target === dialog) { const r = dialog.getBoundingClientRect(); if (event.clientX < r.left || event.clientX > r.right || event.clientY < r.top || event.clientY > r.bottom) dialog.close(); } });
  document.addEventListener('click', event => { if (!menu.contains(event.target as Node)) menu.open = false; });
  document.addEventListener('keydown', event => { if (event.key === 'Escape') menu.open = false; });
  const buttons = () => { send.disabled = busy || cooldown > 0; verify.disabled = busy; };
  const tick = setInterval(() => { if (cooldown > 0) { cooldown--; send.textContent = cooldown ? t(`${cooldown}秒后重发`, `Resend in ${cooldown}s`) : t('重新发送验证码', 'Resend code'); buttons(); } }, 1000);
  window.addEventListener('pagehide', () => clearInterval(tick));
  send.addEventListener('click', async () => {
    if (busy || cooldown || !email.reportValidity()) return;
    busy = true; buttons(); show(t('正在发送…', 'Sending…'));
    try {
      const result = await accountApi<{ retryAfter: number }>('request-code', { email: email.value });
      el('account-global-code-fields').hidden = false; verify.hidden = false; code.required = true; code.focus();
      cooldown = result.retryAfter; show(t('验证码已发送，请查看邮箱。', 'Code sent. Check your inbox.'));
    } catch (error) { show(error instanceof Error ? error.message : t('发送失败', 'Could not send'), true); }
    finally { busy = false; buttons(); }
  });
  el<HTMLFormElement>('account-global-login').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    if (verify.hidden) { send.click(); return; }
    busy = true; buttons(); show(t('正在登录…', 'Signing in…'));
    try {
      await accountApi('verify', { email: email.value, code: code.value });
      await announceAccountChange(); dialog.close(); code.value = ''; show('');
      document.dispatchEvent(new CustomEvent('maas:signed-in'));
    } catch (error) { show(error instanceof Error ? error.message : t('登录失败', 'Could not sign in'), true); }
    finally { busy = false; buttons(); }
  });
  el('account-sign-out').addEventListener('click', async () => {
    try { await logoutAccount(); menu.open = false; } catch (error) { el('account-menu-status').textContent = error instanceof Error ? error.message : 'Sign out failed'; }
  });
  el('account-sync-retry').addEventListener('click', () => { void flushAccountState().catch(() => {}); });
  document.addEventListener('maas:account-sync', event => {
    const status = (event as CustomEvent<string>).detail;
    el('account-sync-status').textContent = status === 'saving' ? t('保存中', 'Saving') : status === 'saved' ? t('已同步', 'Saved') : status === 'error' ? t('保存失败，请重试', 'Could not save') : '';
    el('account-sync-retry').hidden = status !== 'error';
    el('account-sync-status').dataset.error = String(status === 'error');
  });
}
