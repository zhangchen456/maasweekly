type Model = { modelId: string; modelName: string; familyName?: string };
type Watch = { modelId: string; since: number };
type Me = { user: { email: string }; preferences: { emailEnabled: boolean }; watches: Watch[] };
class ApiError extends Error { constructor(message: string, readonly status: number) { super(message); } }
export async function accountApi<T>(route: string, payload?: unknown): Promise<T> {
  const response = await fetch(`/api/account/${route}`, { credentials: 'same-origin', cache: 'no-store',
    ...(payload === undefined ? {} : { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) }) });
  let value; try { value = await response.json(); } catch { throw new ApiError('服务暂不可用，请稍后重试', response.status); }
  if (!response.ok) throw new ApiError(value.message ?? '操作失败，请稍后重试', response.status);
  return value;
}
const root = document.querySelector('[data-account-page]');
if (root) {
  const el = <T extends HTMLElement>(id: string) => document.getElementById(id) as T;
  const message = el('account-message');
  const show = (text: string, error = false) => { message.textContent = text; message.dataset.error = String(error); };
  let me: Me | null = null, models: Model[] = [], mailAvailable = false, busy = false;
  let cooldown: ReturnType<typeof setInterval> | undefined;
  const search = el<HTMLInputElement>('model-search');
  const email = el<HTMLInputElement>('email');
  const send = el<HTMLButtonElement>('send-code');
  const enabled = el<HTMLInputElement>('email-enabled');
  const action = async (fn: () => Promise<void>) => {
    if (busy) return; busy = true;
    root.querySelectorAll<HTMLButtonElement>('button').forEach(b => b.disabled = true);
    enabled.disabled = true;
    try { await fn(); } catch (error) {
      show(error instanceof Error ? error.message : '连接失败，请稍后再试', true);
      if (error instanceof ApiError && error.status === 401) { me = null; el('workspace').hidden = true; el('login-panel').hidden = false; }
    } finally {
      busy = false; root.querySelectorAll<HTMLButtonElement>('button').forEach(b => b.disabled = false);
      send.disabled = Boolean(cooldown) || !mailAvailable; enabled.disabled = !mailAvailable;
      // Restore preference after a failed save.
      if (me) enabled.checked = me.preferences.emailEnabled;
    }
  };
  const renderSearch = () => {
    const results = el('model-results'); results.replaceChildren();
    const term = search.value.trim().toLowerCase();
    const choices = models.filter(m => `${m.modelName} ${m.familyName ?? ''}`.toLowerCase().includes(term)).filter(m => !me?.watches.some(w => w.modelId === m.modelId));
    el('search-note').textContent = !models.length ? '目录暂不可用，请刷新重试' : !choices.length ? '没有匹配的未关注模型' : `显示 ${Math.min(choices.length, 8)} / ${choices.length} 个模型${term ? '' : '，输入名称缩小范围'}`;
    for (const model of choices.slice(0, 8)) {
      const row = document.createElement('div'); row.className = 'model-result';
      const name = document.createElement('span'); name.textContent = model.modelName;
      const add = document.createElement('button'); add.type = 'button'; add.disabled = busy; add.textContent = '关注'; add.setAttribute('aria-label', `关注 ${model.modelName}`);
      add.addEventListener('click', () => void action(async () => {
        const value = await accountApi<{ watches: Watch[] }>('watch', { modelId: model.modelId });
        me!.watches = value.watches; renderWatches(); await loadChanges(); show(`已关注 ${model.modelName}`);
      }));
      row.append(name, add); results.append(row);
    }
  };
  const renderWatches = () => {
    const list = el('watch-list'); list.replaceChildren(); el('watch-count').textContent = String(me?.watches.length ?? 0);
    if (!me?.watches.length) { const empty = document.createElement('p'); empty.className = 'watch-empty'; empty.textContent = '还没有关注模型。从“添加关注”开始，保存你正在使用的模型。'; list.append(empty); }
    for (const watch of me?.watches ?? []) {
      const model = models.find(m => m.modelId === watch.modelId);
      const row = document.createElement('div'); row.className = 'watch-row';
      const name = document.createElement('a'); name.textContent = model?.modelName ?? watch.modelId; name.href = `/model/${encodeURIComponent(watch.modelId)}/`;
      const remove = document.createElement('button'); remove.type = 'button'; remove.disabled = busy; remove.className = 'quiet'; remove.textContent = '取消关注'; remove.setAttribute('aria-label', `取消关注 ${name.textContent}`);
      remove.addEventListener('click', () => void action(async () => { const value = await accountApi<{ watches: Watch[] }>('unwatch', { modelId: watch.modelId }); me!.watches = value.watches; renderWatches(); await loadChanges(); show('已取消关注'); }));
      row.append(name, remove); list.append(row);
    }
    renderSearch();
  };
  const loadChanges = async () => {
    const value = await accountApi<{ items: { id: string; title: string; summary: string | null; observationDate: string; status: string }[]; dataThrough: string }>('changes');
    const list = el('watch-changes'); list.replaceChildren();
    el('changes-asof').textContent = `数据截至 ${value.dataThrough} · 最多展示 100 条历史记录`;
    if (!value.items.length) { const p = document.createElement('p'); p.className = 'watch-empty'; p.textContent = '当前没有匹配的变化记录。新变化被采集并关联后会出现在这里。'; list.append(p); }
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
    renderWatches(); await loadChanges(); show('关注列表已同步');
  };
  send.addEventListener('click', () => void action(async () => {
    if (!email.reportValidity()) return;
    await accountApi('request-code', { email: email.value }); el('code-fields').hidden = false;
    el<HTMLInputElement>('code').required = true; el<HTMLInputElement>('code').focus();
    let seconds = 60; send.textContent = `${seconds} 秒后重发`;
    cooldown = setInterval(() => { seconds--; send.textContent = seconds > 0 ? `${seconds} 秒后重发` : '重新发送验证码'; if (seconds <= 0) { clearInterval(cooldown); cooldown = undefined; send.disabled = busy || !mailAvailable; } }, 1000);
    show('验证码已发送，请查看邮箱和垃圾邮件');
  }));
  el<HTMLFormElement>('login-form').addEventListener('submit', event => { event.preventDefault(); void action(async () => { await accountApi('verify', { email: email.value, code: el<HTMLInputElement>('code').value }); el<HTMLInputElement>('code').value = ''; await loadWorkspace(); }); });
  el('logout').addEventListener('click', () => void action(async () => { await accountApi('logout', {}); me = null; el('workspace').hidden = true; el('login-panel').hidden = false; el('watch-list').replaceChildren(); el('watch-changes').replaceChildren(); el('user-email').textContent = ''; show('已退出登录'); }));
  enabled.addEventListener('change', () => void action(async () => { const result = await accountApi<{ emailEnabled: boolean }>('preferences', { emailEnabled: enabled.checked }); me!.preferences.emailEnabled = result.emailEnabled; show(result.emailEnabled ? '已开启每日邮件摘要，有变化时发送' : '已关闭邮件提醒'); }));
  search.addEventListener('input', renderSearch);
  void action(async () => {
    const status = await accountApi<{ enabled: boolean; mailAvailable: boolean }>('status'); mailAvailable = status.mailAvailable;
    if (!status.enabled) { show('账号服务尚未启用。你仍可浏览价格和全部变化。'); return; }
    try { await loadWorkspace(); }
    catch (error) { if (!(error instanceof ApiError) || error.status !== 401) throw error; el('login-panel').hidden = false; show(mailAvailable ? '登录后保存你的模型关注' : '邮件服务尚未配置，暂时无法发送验证码'); }
  });
}
