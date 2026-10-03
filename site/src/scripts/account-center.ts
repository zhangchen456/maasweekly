import { accountApi, announceAccountChange, onAccountChange, logoutAccount } from './account-client';
const root = document.querySelector('[data-account-center]');
if (root) {
  const en = document.documentElement.lang === 'en';
  const t = (zh: string, english: string) => en ? english : zh;
  const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  const status = el('profile-status');
  onAccountChange(me => {
    el('account-settings').hidden = !me;
    if (!me) return;
    el<HTMLInputElement>('profile-name').value = me.user.displayName || '';
    el('profile-email').textContent = me.user.email;
    el('profile-created').textContent = new Date(me.user.created).toLocaleDateString(en ? 'en-US' : 'zh-CN');
  });
  el<HTMLFormElement>('profile-form').addEventListener('submit', async event => {
    event.preventDefault(); const button = el<HTMLButtonElement>('profile-save'); button.disabled = true;
    try { await accountApi('profile', { displayName: el<HTMLInputElement>('profile-name').value }); await announceAccountChange(); status.textContent = t('昵称已保存', 'Name saved'); }
    catch (error) { status.textContent = error instanceof Error ? error.message : 'Could not save'; }
    finally { button.disabled = false; }
  });
  el('account-center-password').addEventListener('click', () => document.dispatchEvent(new CustomEvent('maas:password-setup')));
  el('account-export').addEventListener('click', async () => {
    try {
      const value = await accountApi('export'); const url = URL.createObjectURL(new Blob([JSON.stringify(value, null, 2)], { type: 'application/json' }));
      const link = document.createElement('a'); link.href = url; link.download = 'maas-daily-account.json'; link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
      status.textContent = t('账户数据已导出', 'Account data exported');
    } catch (error) { status.textContent = error instanceof Error ? error.message : 'Could not export'; }
  });
  el('account-logout-all').addEventListener('click', async () => {
    try { await logoutAccount(true); status.textContent = t('已退出所有设备，保存的数据仍保留', 'Signed out on all devices. Your saved data is retained.'); }
    catch (error) { status.textContent = error instanceof Error ? error.message : 'Could not sign out'; }
  });
}
