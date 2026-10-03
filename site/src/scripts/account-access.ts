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
  const password = el<HTMLInputElement>('account-login-password');
  const confirm = el<HTMLInputElement>('account-password-confirm');
  let mode: 'login' | 'register' | 'recover' | 'setup' = 'login';
  let busy = false, cooldown = 0;
  const setMode = (next: typeof mode) => {
    mode = next; password.value = ''; confirm.value = ''; code.value = ''; show('');
    email.disabled = next === 'setup';
    el('account-password-fields').hidden = next === 'register' || next === 'recover';
    el('account-password-confirm-fields').hidden = next !== 'setup';
    password.required = next === 'login' || next === 'setup'; confirm.required = next === 'setup';
    password.minLength = next === 'setup' ? 8 : 0;
    password.autocomplete = next === 'setup' ? 'new-password' : 'current-password';
    el('account-global-code-fields').hidden = true; code.required = false;
    send.hidden = next === 'login' || next === 'setup'; verify.hidden = next === 'register' || next === 'recover';
    verify.textContent = next === 'setup' ? t('设置密码并完成', 'Set password and finish') : t('登录', 'Sign in');
    el('account-login-title').textContent = next === 'setup' ? t('设置你的密码', 'Set your password') : next === 'register' ? t('注册账号', 'Create account') : next === 'recover' ? t('验证邮箱并设置密码', 'Verify email and set password') : t('登录你的账户', 'Sign in to your account');
    for (const kind of ['login', 'register', 'recover']) el(`account-mode-${kind}`).hidden = next === kind || (next === 'setup' && kind !== 'login');
  };
  for (const kind of ['login', 'register', 'recover'] as const) el(`account-mode-${kind}`).addEventListener('click', () => { if (!busy) setMode(kind); });
  document.addEventListener('maas:password-setup', () => { if (busy) return; setMode('recover'); dialog.showModal(); email.focus(); });

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
      el('account-global-code-fields').hidden = false; verify.hidden = false; verify.textContent = t('验证邮箱', 'Verify email'); code.required = true; code.focus();
      cooldown = result.retryAfter; show(t('验证码已发送，请查看邮箱。', 'Code sent. Check your inbox.'));
    } catch (error) { show(error instanceof Error ? error.message : t('发送失败', 'Could not send'), true); }
    finally { busy = false; buttons(); }
  });
  el<HTMLFormElement>('account-global-login').addEventListener('submit', async event => {
    event.preventDefault(); if (busy) return;
    if (verify.hidden) { send.click(); return; }
    busy = true; buttons(); show(t('正在登录…', 'Signing in…'));
    try {
      if (mode === 'register' || mode === 'recover') {
        await accountApi('verify', { email: email.value, code: code.value });
        setMode('setup'); show(t('邮箱已验证，请设置8至128个字符的密码。', 'Email verified. Set a password of 8–128 characters.')); password.focus(); return;
      }
      if (mode === 'setup') {
        if (password.value !== confirm.value) throw new Error(t('两次输入的密码不一致', 'Passwords do not match'));
        await accountApi('password', { password: password.value });
      } else await accountApi('login', { email: email.value, password: password.value });
      await announceAccountChange(); dialog.close(); setMode('login');
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
