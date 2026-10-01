export function preferredLanguage({ explicit, saved, country, browser }) {
  if (explicit === 'zh' || explicit === 'en') return explicit;
  if (saved === 'zh' || saved === 'en') return saved;
  if (/^[A-Z]{2}$/.test(country || '')) return country === 'CN' ? 'zh' : 'en';
  return browser ? (/^zh(?:-|$)/i.test(browser) ? 'zh' : 'en') : 'zh';
}
export function readPreference(win) {
  try {
    const value = JSON.parse(win.localStorage.getItem('maas-language') || 'null');
    return value?.expires > Date.now() && ['zh', 'en'].includes(value.locale) ? value.locale : null;
  } catch { return null; }
}
export function savePreference(win, locale) {
  try { win.localStorage.setItem('maas-language', JSON.stringify({ locale, expires: Date.now() + 180 * 86400000 })); } catch {}
}
export function switchUrl(win, link) {
  const next = new URL(link.href, win.location.href);
  const params = new URL(win.location.href).searchParams;
  params.delete('lang');
  if (link.dataset.translated === 'true') {
    next.search = params.toString(); next.hash = new URL(win.location.href).hash;
  } else next.searchParams.set('untranslated', '1');
  // Explicit parameter also works when preference storage is blocked.
  if (next.pathname === '/' || next.pathname === '/en/') next.searchParams.set('lang', link.dataset.language);
  return next.href;
}
export async function startLanguage(win) {
  for (const link of win.document.querySelectorAll('[data-language]')) {
    link.addEventListener('click', event => {
      // Persist only the human action, never a visit to a language URL.
      savePreference(win, link.dataset.language);
      if (event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey) {
        event.preventDefault(); win.location.assign(switchUrl(win, link));
      }
    });
  }
  const url = new URL(win.location.href);
  if (url.searchParams.get('untranslated') === '1') {
    const note = win.document.getElementById('language-note');
    if (note) { note.hidden = false; note.textContent = url.pathname.startsWith('/en/')
      ? 'This content is not available in English yet. You can browse the English homepage below.'
      : '该内容暂未提供中文译本，已进入中文首页。'; }
  }
  if (!['/', '/en/'].includes(url.pathname)) return;
  const explicit = url.searchParams.get('lang');
  if (['zh', 'en'].includes(explicit)) {
    savePreference(win, explicit);
    const target = explicit === 'en' ? '/en/' : '/';
    if (url.pathname !== target) { url.pathname = target; win.__maasLanguageRedirecting = true; win.location.replace(url.href); }
    return;
  }
  // /en/ is always an explicit English URL.
  if (url.pathname !== '/') return;
  let saved = readPreference(win), country = null;
  if (!saved) {
    try {
      const response = await win.fetch('/_locale/country', { signal: win.AbortSignal.timeout(1000), cache: 'no-store' });
      if (response.ok) country = (await response.json()).country;
    } catch {}
    // A concurrent manual choice wins over an in-flight country request.
    saved = readPreference(win);
  }
  if (preferredLanguage({ saved, country, browser: win.navigator.languages?.[0] || win.navigator.language }) === 'en') {
    url.pathname = '/en/'; win.__maasLanguageRedirecting = true; win.location.replace(url.href);
  }
}
if (typeof window !== 'undefined') window.__maasLanguageReady = startLanguage(window);
