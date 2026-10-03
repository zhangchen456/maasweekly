import { savedState, currentAccount } from './account-client';
const search = document.querySelector<HTMLInputElement>('#signal-search')!;
const platform = document.querySelector<HTMLSelectElement>('#platform-filter')!;
const following = document.querySelector<HTMLButtonElement>('#following-filter')!;
const cards = [...document.querySelectorAll<HTMLElement>('.platform-card')];
const sources = [...document.querySelectorAll<HTMLElement>('.signal-platform')];
const filters = [...document.querySelectorAll<HTMLButtonElement>('[data-filter]')];
let selectedType = 'all';
let onlyFollowing = false;
let followed = new Set<string>();
try {
  const saved = JSON.parse(localStorage.getItem('maas-followed') || '[]');
  if (Array.isArray(saved)) followed = new Set(saved.filter((v) => typeof v === 'string'));
} catch {}
const followButtons = [...document.querySelectorAll<HTMLButtonElement>('[data-follow]')];
function updateFollowButtons() {
  followButtons.forEach((button) => {
    const name = button.dataset.follow!;
    const active = followed.has(name);
    button.setAttribute('aria-pressed', String(active));
    button.setAttribute('aria-label', `${active ? '取消关注' : '关注'} ${name}`);
    button.textContent = active ? '✓ 已关注' : '＋ 关注';
  });
}
function update() {
  const query = search.value.trim().toLocaleLowerCase();
  let count = 0;
  const matchingPlatforms = new Set<string>();
  cards.forEach((card) => {
    const name = card.dataset.platform!;
    const allowed = (!platform.value || platform.value === name) && (!onlyFollowing || followed.has(name));
    let visible = 0;
    card.querySelectorAll<HTMLElement>('.pc-item').forEach((item) => {
      const matches = allowed && (selectedType === 'all' || item.dataset.type === selectedType) && `${name} ${item.textContent}`.toLocaleLowerCase().includes(query);
      item.hidden = !matches;
      if (matches) visible++;
    });
    card.hidden = visible === 0;
    if (visible) matchingPlatforms.add(name);
    count += visible;
  });
  let sourceCount = 0;
  sources.forEach((group) => {
    const name = group.dataset.platform!;
    const allowed = (!platform.value || platform.value === name) && (!onlyFollowing || followed.has(name)) && (selectedType === 'all' || matchingPlatforms.has(name));
    let visible = 0;
    group.querySelectorAll<HTMLDetailsElement>('details').forEach((item) => {
      const matches = allowed && (matchingPlatforms.has(name) || `${name} ${item.textContent}`.toLocaleLowerCase().includes(query));
      item.hidden = !matches;
      if (matches) visible++;
    });
    group.hidden = visible === 0;
    sourceCount += visible;
  });
  document.querySelector('#filter-status')!.textContent = `${count} 条要点 · ${sourceCount} 项变化依据${onlyFollowing ? (currentAccount() ? ' · 已同步账户关注' : ' · 关注保存在此浏览器，登录后可同步') : ''}`;
  (document.querySelector('#filter-empty') as HTMLElement).hidden = count > 0 || sourceCount > 0;
  (document.querySelector('#digest') as HTMLElement).hidden = count === 0;
  (document.querySelector('#signals') as HTMLElement).hidden = sourceCount === 0;
  filters.forEach((button) => button.setAttribute('aria-pressed', String(button.dataset.filter === selectedType)));
  following.setAttribute('aria-pressed', String(onlyFollowing));
}
search.maxLength = 200;
let save = (_value: ExploreState) => {};
type ExploreState = { followed: string[]; query: string; platform: string; type: string; onlyFollowing: boolean };
const persist = () => save({ followed: [...followed], query: search.value, platform: platform.value, type: selectedType, onlyFollowing });
search.addEventListener('input', () => { update(); persist(); });
platform.addEventListener('change', () => { update(); persist(); });
filters.forEach((button) => button.addEventListener('click', () => { selectedType = button.dataset.filter!; update(); persist(); }));
following.addEventListener('click', () => { onlyFollowing = !onlyFollowing; update(); persist(); });
followButtons.forEach((button) => button.addEventListener('click', () => {
  const name = button.dataset.follow!;
  followed.has(name) ? followed.delete(name) : followed.add(name);
  updateFollowButtons(); update(); persist();
}));
document.querySelector('#reset-filters')?.addEventListener('click', () => { search.value = ''; platform.value = ''; selectedType = 'all'; onlyFollowing = false; update(); persist(); search.focus(); });
document.addEventListener('keydown', (event) => {
  const target = event.target as HTMLElement;
  if (event.key === '/' && !event.metaKey && !event.ctrlKey && !event.altKey && !target.closest('input, textarea, select, [contenteditable="true"]')) { event.preventDefault(); search.focus(); }
  if (event.key === 'Escape' && document.activeElement === search) { search.value = ''; update(); persist(); search.blur(); }
});
document.querySelector('#copy-brief')?.addEventListener('click', async () => {
  const visible = cards.filter((card) => !card.hidden);
  const text = ['MaaS Daily · ' + document.querySelector('.edition time')?.textContent, ...visible.map((card) => `${card.dataset.platform}\n${[...card.querySelectorAll<HTMLElement>('.pc-item')].filter((item) => !item.hidden).map((item) => '• ' + item.textContent?.trim()).join('\n')}`)].join('\n\n');
  const status = document.querySelector('#copy-status')!;
  if (!visible.length) { status.textContent = '当前筛选下没有可复制的要点'; return; }
  try { await navigator.clipboard.writeText(text); document.dispatchEvent(new CustomEvent('maas:copy-success', { detail: { kind: 'brief' } })); status.textContent = '已复制当前筛选的简报'; } catch { status.textContent = '浏览器未允许复制，请选中文字复制'; }
});
updateFollowButtons(); update();

save = savedState<ExploreState>('explore', { followed: [], query: '', platform: '', type: 'all', onlyFollowing: false }, value => {
  followed = new Set(value.followed); search.value = value.query; platform.value = value.platform;
  selectedType = filters.some(b => b.dataset.filter === value.type) ? value.type : 'all'; onlyFollowing = value.onlyFollowing;
  updateFollowButtons(); update();
});
