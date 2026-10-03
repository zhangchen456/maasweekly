type Model = { modelId: string; modelName: string; familyName?: string };
type Watch = { modelId: string; since: number };
type Me = { user: { id: string; email: string }; preferences: { emailEnabled: boolean }; watches: Watch[] };
import { accountApi, AccountApiError as ApiError, announceAccountChange, onAccountChange, logoutAccount } from './account-client';
export { accountApi } from './account-client';
const root = document.querySelector('[data-account-page]');
if (root) {
  const en = document.documentElement.lang === 'en';
  const t = (zh: string, english: string) => en ? english : zh;
  const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  const message = el('account-message');
  const show = (text: string, error = false) => { message.textContent = text; message.dataset.error = String(error); };
  let me: Me | null = null, models: Model[] = [], mailAvailable = false, busy = false;
  const search = el<HTMLInputElement>('model-search');
  const enabled = el<HTMLInputElement>('email-enabled');
  const action = async (fn: () => Promise<void>) => {
    if (busy) return; busy = true;
    root.querySelectorAll<HTMLButtonElement>('button').forEach(b => b.disabled = true);
    enabled.disabled = true;
    try { await fn(); } catch (error) {
      show(error instanceof Error ? error.message : t('连接失败，请稍后再试', 'Connection failed. Please try again.'), true);
      if (error instanceof ApiError && error.status === 401) { me = null; el('workspace').hidden = true; el('login-panel').hidden = false; }
    } finally {
      busy = false; root.querySelectorAll<HTMLButtonElement>('button').forEach(b => b.disabled = false);
      enabled.disabled = !mailAvailable;
      // Restore preference after a failed save.
      if (me) enabled.checked = me.preferences.emailEnabled;
    }
  };
  const renderSearch = () => {
    const results = el('model-results'); results.replaceChildren();
    const term = search.value.trim().toLowerCase();
    const choices = models.filter(m => `${m.modelName} ${m.familyName ?? ''}`.toLowerCase().includes(term)).filter(m => !me?.watches.some(w => w.modelId === m.modelId));
    el('search-note').textContent = !models.length ? t('目录暂不可用，请刷新重试', 'Catalog unavailable. Please reload.') : !choices.length ? t('没有匹配的未关注模型', 'No matching models to follow.') : `显示 ${Math.min(choices.length, 8)} / ${choices.length} 个模型${term ? '' : '，输入名称缩小范围'}`;
    for (const model of choices.slice(0, 8)) {
      const row = document.createElement('div'); row.className = 'model-result';
      const name = document.createElement('span'); name.textContent = model.modelName;
      const add = document.createElement('button'); add.type = 'button'; add.disabled = busy; add.textContent = t('关注', 'Follow'); add.setAttribute('aria-label', t(`关注 ${model.modelName}`, `Follow ${model.modelName}`));
      add.addEventListener('click', () => void action(async () => {
        const value = await accountApi<{ watches: Watch[] }>('watch', { modelId: model.modelId });
        me!.watches = value.watches; renderWatches(); await loadChanges(); show(t(`已关注 ${model.modelName}`, `Following ${model.modelName}`));
      }));
      row.append(name, add); results.append(row);
    }
  };
  const renderWatches = () => {
    const list = el('watch-list'); list.replaceChildren(); el('watch-count').textContent = String(me?.watches.length ?? 0);
    if (!me?.watches.length) { const empty = document.createElement('p'); empty.className = 'watch-empty'; empty.textContent = t('还没有关注模型。从“添加关注”开始，保存你正在使用的模型。', 'No followed models yet. Add a model to get started.'); list.append(empty); }
    for (const watch of me?.watches ?? []) {
      const model = models.find(m => m.modelId === watch.modelId);
      const row = document.createElement('div'); row.className = 'watch-row';
      const name = document.createElement('a'); name.textContent = model?.modelName ?? watch.modelId; name.href = `${en ? '/en' : ''}/model/${encodeURIComponent(watch.modelId)}/`;
      const remove = document.createElement('button'); remove.type = 'button'; remove.disabled = busy; remove.className = 'quiet'; remove.textContent = t('取消关注', 'Unfollow'); remove.setAttribute('aria-label', t(`取消关注 ${name.textContent}`, `Unfollow ${name.textContent}`));
      remove.addEventListener('click', () => void action(async () => { const value = await accountApi<{ watches: Watch[] }>('unwatch', { modelId: watch.modelId }); me!.watches = value.watches; renderWatches(); await loadChanges(); show(t('已取消关注', 'Unfollowed')); }));
      row.append(name, remove); list.append(row);
    }
    renderSearch();
  };
  const loadChanges = async () => {
    const value = await accountApi<{ items: { id: string; title: string; summary: string | null; observationDate: string; status: string }[]; dataThrough: string }>('changes');
    const list = el('watch-changes'); list.replaceChildren();
    el('changes-asof').textContent = t(`数据截至 ${value.dataThrough} · 最多展示 100 条历史记录`, `Data through ${value.dataThrough} · Up to 100 historical changes`);
    if (!value.items.length) { const p = document.createElement('p'); p.className = 'watch-empty'; p.textContent = t('当前没有匹配的变化记录。新变化被采集并关联后会出现在这里。', 'No matching changes yet. New changes will appear here.'); list.append(p); }
    for (const item of value.items) {
      const article = document.createElement('article'); article.className = 'watch-change';
      const link = document.createElement('a'); link.href = `/item/${encodeURIComponent(item.id)}/`; link.textContent = `${item.status === 'withdrawn' ? '[已撤回] ' : ''}${item.title}`;
      const small = document.createElement('small'); small.textContent = item.observationDate;
      article.append(small, document.createElement('br'), link);
      if (item.summary) { const p = document.createElement('p'); p.textContent = item.summary; article.append(p); }
      list.append(article);
    }
  };
  const loadWorkspace = async () => {
    me = await accountApi<Me>('me'); el('login-panel').hidden = true; el('workspace').hidden = false;
    el('user-email').textContent = me.user.email; enabled.checked = me.preferences.emailEnabled;
    try {
      const response = await fetch('/api/v1/models'); if (!response.ok) throw new Error();
      models = (await response.json()).models;
    } catch { models = []; }
    const requested = new URL(location.href).searchParams.get('model');
    if (requested) search.value = models.find(m => m.modelId === requested)?.modelName ?? '';
    renderWatches(); await loadChanges(); show(t('关注列表已同步', 'Followed models synced'));
  };
  el('account-center-login').addEventListener('click', () => document.getElementById('account-login-open')?.click());
  el('logout').addEventListener('click', () => void action(async () => { await logoutAccount(); me = null; el('workspace').hidden = true; el('login-panel').hidden = false; el('watch-list').replaceChildren(); el('watch-changes').replaceChildren(); el('user-email').textContent = ''; show(t('已退出登录', 'Signed out')); }));
  enabled.addEventListener('change', () => void action(async () => { const result = await accountApi<{ emailEnabled: boolean }>('preferences', { emailEnabled: enabled.checked }); me!.preferences.emailEnabled = result.emailEnabled; show(result.emailEnabled ? t('已开启每日邮件摘要，有变化时发送', 'Daily email enabled. We email you when there are changes.') : t('已关闭邮件提醒', 'Email notifications disabled')); }));
  search.addEventListener('input', renderSearch);
  onAccountChange(user => { if (!user) { me = null; el('workspace').hidden = true; el('login-panel').hidden = false; el('watch-list').replaceChildren(); el('watch-changes').replaceChildren(); el('user-email').textContent = ''; } else if (me?.user.id !== user.user.id) { void action(loadWorkspace); } });
  document.addEventListener('maas:signed-in', () => void action(loadWorkspace));
  void action(async () => {
    const status = await accountApi<{ enabled: boolean; mailAvailable: boolean }>('status'); mailAvailable = status.mailAvailable;
    if (!status.enabled) { show(t('账号服务尚未启用。你仍可浏览价格和全部变化。', 'Account service unavailable. You can still browse prices and changes.')); return; }
    try { await loadWorkspace(); }
    catch (error) { if (!(error instanceof ApiError) || error.status !== 401) throw error; el('login-panel').hidden = false; show(mailAvailable ? t('登录后保存你的模型关注', 'Sign in to save your followed models') : t('邮件服务尚未配置，暂时无法发送验证码', 'Email delivery unavailable. Please try later.')); }
  });
}
