import { currentAccount, accountApi, refreshAccount, onAccountChange, openAccountLogin } from './account-client';
const buttons = [...document.querySelectorAll<HTMLButtonElement>('[data-model-follow]')];
let pending: HTMLButtonElement | null = null;
for (const button of buttons) {
  const en = document.documentElement.lang === 'en';
  const t = (zh: string, english: string) => en ? english : zh;
  const modelId = button.dataset.modelFollow!;
  const status = button.parentElement!.querySelector<HTMLElement>('[data-model-follow-status]')!;
  onAccountChange(me => {
    const followed = Boolean(me?.watches.some(w => w.modelId === modelId));
    button.setAttribute('aria-pressed', String(followed)); button.textContent = followed ? t('已关注 · 取消', 'Following · Unfollow') : t('关注模型', 'Follow model');
  });
  button.addEventListener('click', async () => {
    if (!currentAccount()) { pending = button; status.textContent = t('登录后将保存这个模型的关注', 'Sign in to save this model'); openAccountLogin(); return; }
    button.disabled = true;
    try {
      const followed = button.getAttribute('aria-pressed') === 'true';
      await accountApi(followed ? 'unwatch' : 'watch', { modelId }); await refreshAccount();
      status.textContent = followed ? t('已取消关注', 'Unfollowed') : t('已保存到你的账户', 'Saved to your account');
    } catch (error) { status.textContent = error instanceof Error ? error.message : 'Could not save'; }
    finally { button.disabled = false; }
  });
}
document.addEventListener('maas:signed-in', () => { const button = pending; pending = null; if (button) button.click(); });
