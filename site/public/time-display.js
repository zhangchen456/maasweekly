const DATE_ONLY = /^\d{4}-\d{2}-\d{2}$/;
const ZONED = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})$/i;
const TIMESTAMP_IN_TEXT = /\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})/gi;

export function browserTimeZone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC'; } catch { return 'UTC'; }
}

export function formatTimestamp(value, { locale = 'zh-CN', timeZone = browserTimeZone() } = {}) {
  if (value === null || value === undefined || value === '') return locale.startsWith('en') ? 'Unknown' : '未知';
  const raw = String(value);
  if (DATE_ONLY.test(raw)) return raw; // Calendar dates have no instant to convert.
  if (typeof value !== 'number' && !ZONED.test(raw)) {
    return raw + (locale.startsWith('en') ? ' (time zone unspecified)' : '（时区未注明）');
  }
  const date = new Date(value);
  if (!Number.isFinite(+date)) return locale.startsWith('en') ? 'Unknown' : '未知';
  try {
    return new Intl.DateTimeFormat(locale, { timeZone, year: 'numeric', month: '2-digit', day: '2-digit',
      hour: '2-digit', minute: '2-digit', hourCycle: 'h23', timeZoneName: 'shortOffset' }).format(date);
  } catch {
    return date.toISOString(); // A UTC fallback always carries its offset.
  }
}

export function nextDigestCheck(now = Date.now()) {
  const next = new Date(now);
  next.setUTCHours(1, 15, 0, 0); // Fixed 09:15 Asia/Shanghai; DST belongs to the display zone.
  if (+next <= now) next.setUTCDate(next.getUTCDate() + 1);
  return next.toISOString();
}

export function startTimeDisplay(win) {
  const doc = win.document;
  const options = () => ({ locale: doc.documentElement.lang.startsWith('en') ? 'en-US' : 'zh-CN', timeZone: browserTimeZone() });
  const formatNode = node => {
    const raw = node.getAttribute('data-time-value') ?? node.getAttribute('datetime');
    if (!raw) return;
    const { locale, timeZone } = options();
    if (DATE_ONLY.test(raw)) {
      node.title = locale.startsWith('en') ? 'Calendar date; not converted between time zones' : '日历日期，不进行时区换算';
      return;
    }
    const formatted = formatTimestamp(raw, { locale, timeZone });
    if (node.textContent !== formatted) node.textContent = formatted;
    node.title = `${raw} · ${timeZone}`;
  };
  const formatText = node => {
    // Only opt-in product metadata. Original articles, source text and billing schedules are untouched.
    for (const child of [...node.childNodes]) {
      if (child.nodeType !== 3 || !child.textContent.match(TIMESTAMP_IN_TEXT)) continue;
      const text = child.textContent;
      const fragment = doc.createDocumentFragment();
      let position = 0;
      for (const match of text.matchAll(TIMESTAMP_IN_TEXT)) {
        fragment.append(text.slice(position, match.index));
        const span = doc.createElement('time'); span.dateTime = match[0]; span.textContent = match[0];
        formatNode(span); fragment.append(span); position = match.index + match[0].length;
      }
      fragment.append(text.slice(position)); child.replaceWith(fragment);
    }
  };
  const render = root => {
    if (!root || (root.nodeType !== 1 && root.nodeType !== 9)) return;
    if (root.matches?.('time[datetime], [data-time-value]')) formatNode(root);
    root.querySelectorAll('time[datetime], [data-time-value]').forEach(formatNode);
    if (root.matches?.('[data-time-text]')) formatText(root);
    root.querySelectorAll('[data-time-text]').forEach(formatText);
  };
  const renderSchedule = () => {
    const { locale, timeZone } = options();
    doc.querySelectorAll('[data-browser-timezone]').forEach(node => { node.textContent = timeZone; });
    doc.querySelectorAll('[data-digest-next]').forEach(node => {
      const raw = nextDigestCheck(); node.setAttribute('datetime', raw); formatNode(node);
    });
    return locale;
  };
  render(doc); renderSchedule();
  const observer = new win.MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'attributes' || record.type === 'characterData') render(record.target.nodeType === 3 ? record.target.parentElement : record.target);
      else {
        for (const added of record.addedNodes) render(added.nodeType === 3 ? added.parentElement : added);
      }
    }
  });
  observer.observe(doc.body, { childList: true, subtree: true, characterData: true, attributes: true, attributeFilter: ['datetime', 'data-time-value'] });
  const interval = win.setInterval(() => { render(doc); renderSchedule(); }, 60000);
  const onFocus = () => { render(doc); renderSchedule(); };
  win.addEventListener('focus', onFocus);
  return () => { observer.disconnect(); win.clearInterval(interval); win.removeEventListener('focus', onFocus); };
}
