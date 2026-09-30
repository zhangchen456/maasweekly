// Thin Umami Cloud adapter: no identity storage, collector or retry queue.
export const TRACKER_URL = 'https://cloud.umami.is/script.js';
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MODEL_ID = /^[a-z0-9_-]+:[a-z0-9_.-]+$/;
const UTM = ['utm_source', 'utm_medium', 'utm_campaign'];
const COPY_KINDS = new Set(['content', 'url', 'brief']);

export function validateAnalyticsConfig(config) {
  if (typeof config?.enabled !== 'boolean' || typeof config.websiteId !== 'string') {
    throw new Error('Analytics requires enabled:boolean and websiteId:string');
  }
  if ((config.enabled || config.websiteId) && !UUID.test(config.websiteId)) {
    throw new Error('Analytics websiteId must be the public Umami website UUID');
  }
  return config;
}

export function pageType(path) {
  if (path === '/') return 'home';
  const section = path.split('/')[1];
  return ({ model: 'model_detail', models: 'model_catalog', changes: 'changes',
    pricing: 'prices', leaderboards: 'leaderboard', agent: 'agent',
    feed: 'feed', 'feed.xml': 'feed', 'maas-skill': 'skill' })[section] || 'other';
}

export function cleanPageUrl(value, base) {
  try {
    const url = new URL(value, base);
    if (url.origin !== new URL(base).origin) return null;
    const params = new URLSearchParams();
    for (const key of UTM) {
      const val = url.searchParams.get(key);
      if (val && /^[\p{L}\p{N}_. -]{1,80}$/u.test(val)) params.set(key, val);
    }
    return url.pathname + (params.size ? '?' + params.toString() : '');
  } catch { return null; }
}

export function cleanReferrer(value, base) {
  if (!value) return '';
  try {
    const url = new URL(value);
    if (!['http:', 'https:'].includes(url.protocol)) return '';
    return url.origin === new URL(base).origin ? url.origin + url.pathname : url.origin;
  } catch { return ''; }
}

function excluded(win) {
  if (win.navigator.doNotTrack === '1') return true;
  try { return Boolean(win.localStorage.getItem('umami.disabled')); }
  catch { return false; }
}

export function startAnalytics(win, config, canonicalUrl) {
  validateAnalyticsConfig(config);
  const canonical = new URL(canonicalUrl);
  if (!config.enabled || win.location.origin !== canonical.origin || excluded(win)) return null;
  if (win.__maasAnalyticsStarted) return null;
  win.__maasAnalyticsStarted = true;
  let lastPage = null;

  // The native tracker owns pageviews. Query-only filter changes and repeated
  // initialization are cancelled here; a fresh document/refresh is a new view.
  win.maasAnalyticsBeforeSend = (type, payload) => {
    if (type !== 'event' || excluded(win)) return false;
    const url = cleanPageUrl(payload.url, canonicalUrl);
    if (!url) return false;
    const path = new URL(url, canonicalUrl).pathname;
    if (path.startsWith('/admin') || path.startsWith('/api/')) return false;
    const result = { website: config.websiteId, hostname: canonical.hostname,
      url, referrer: cleanReferrer(payload.referrer, canonicalUrl), title: pageType(path) };
    if (/^[a-z0-9-]{1,24}$/i.test(payload.language || '')) result.language = payload.language;
    if (/^\d{1,5}x\d{1,5}$/.test(payload.screen || '')) result.screen = payload.screen;
    if (payload.name) {
      const data = payload.data || {};
      result.name = payload.name;
      result.data = { page_type: pageType(path) };
      if (payload.name === 'model_click' && MODEL_ID.test(data.model_id || '')) {
        result.data.model_id = data.model_id;
      } else if (payload.name === 'outbound_click' && typeof data.target_domain === 'string') {
        try {
          const target = new URL('https://' + data.target_domain);
          if (target.hostname !== data.target_domain || target.port || target.username) return false;
          result.data.target_domain = target.hostname;
        } catch { return false; }
      } else if (payload.name === 'copy' && COPY_KINDS.has(data.kind)) {
        result.data.kind = data.kind;
      } else return false;
    } else {
      if (path === lastPage) return false;
      lastPage = path;
    }
    return result;
  };

  const track = (name, data) => {
    if (excluded(win) || typeof win.umami?.track !== 'function') return;
    try {
      // Never wait for analytics inside the product's navigation/copy handlers.
      const pending = win.umami.track(name, data);
      pending?.catch?.(() => {});
    } catch { /* Provider failure must not change product behavior. */ }
  };

  const click = event => {
    if (event.button !== 0 && event.button !== 1) return;
    const target = event.target?.closest?.('[data-analytics-model-id], a[href]');
    if (!target || target.disabled) return;
    const annotated = target.getAttribute('data-analytics-model-id');
    if (annotated && MODEL_ID.test(annotated)) {
      track('model_click', { model_id: annotated });
      return;
    }
    if (!target.matches('a[href]')) return;
    try {
      const url = new URL(target.href, win.location.href);
      if (!['http:', 'https:'].includes(url.protocol)) return;
      if (url.hostname !== canonical.hostname) {
        track('outbound_click', { target_domain: url.hostname });
      } else {
        const match = url.pathname.match(/^\/model\/([^/]+)\/?$/);
        const modelId = match ? decodeURIComponent(match[1]) : '';
        if (MODEL_ID.test(modelId)) track('model_click', { model_id: modelId });
      }
    } catch { /* Not a trackable link. */ }
  };
  // Capture before filter handlers replace their DOM or change the query URL.
  win.document.addEventListener('click', click, true);
  win.document.addEventListener('auxclick', click, true);
  win.document.addEventListener('maas:copy-success', event => {
    if (COPY_KINDS.has(event.detail?.kind)) track('copy', { kind: event.detail.kind });
  });

  const script = win.document.createElement('script');
  script.src = TRACKER_URL;
  script.async = true;
  script.dataset.websiteId = config.websiteId;
  script.dataset.domains = canonical.hostname;
  script.dataset.beforeSend = 'maasAnalyticsBeforeSend';
  script.dataset.excludeHash = 'true';
  script.dataset.doNotTrack = 'true';
  win.document.head.append(script);
  return script;
}

// Static public module: Astro emits this tag only for an enabled configuration.
if (typeof window !== 'undefined') {
  const tag = document.querySelector('script[data-maas-analytics]');
  if (tag) {
    try {
      startAnalytics(window, { enabled: true, websiteId: tag.dataset.websiteId }, tag.dataset.canonicalUrl);
    } catch { /* Invalid runtime config cannot break the website. */ }
  }
}
