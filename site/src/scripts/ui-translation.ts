import { englishUi, englishHref } from '../lib/ui-translation';
if (document.documentElement.lang === 'en') {
  const root = document.getElementById('main-content')!;
  const protectedSelector = 'script,style,pre,code,blockquote,[data-original-language]';
  const translate = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      if (!node.parentElement?.closest(protectedSelector)) { const next = englishUi(node.textContent ?? ''); if (next !== node.textContent) node.textContent = next; }
    } else if (node instanceof Element && !node.closest(protectedSelector)) {
      for (const key of ['title','placeholder','aria-label','alt']) { const before = node.getAttribute(key); if (before) { const next = englishUi(before); if (before !== next) node.setAttribute(key,next); } }
      if (node instanceof HTMLAnchorElement) { const before = node.getAttribute('href'); if (before) { const next = englishHref(before); if (next !== before) node.setAttribute('href',next); } }
      for (const child of node.childNodes) translate(child);
    }
  };
  translate(root);
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'childList') for (const node of record.addedNodes) translate(node);
      else translate(record.target);
    }
  }).observe(root, { subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['title','placeholder','aria-label','alt','href'] });
}
