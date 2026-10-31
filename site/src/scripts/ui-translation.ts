async function startEnglishTranslation() {
  if (document.documentElement.lang !== 'en') return;
  const { englishUi, englishHref } = await import('../lib/ui-translation');
  const root = document.body;
  const protectedSelector = 'script,style,pre,code,blockquote,[data-original-language],[data-language="zh"],#account-user-name,#account-menu-name,#account-avatar,#account-menu-email';
  const translate = (node: Node) => {
    if (node.nodeType === Node.TEXT_NODE) {
      if (!node.parentElement?.closest(protectedSelector)) { const next = englishUi(node.textContent ?? ''); if (next !== node.textContent) node.textContent = next; }
    } else if (node instanceof Element && !node.parentElement?.closest(protectedSelector) && !node.matches('[data-original-language]')) {
      for (const key of ['title','placeholder','aria-label','aria-roledescription','alt']) { const before = node.getAttribute(key); if (before) { const next = englishUi(before); if (before !== next) node.setAttribute(key,next); } }
      if (node instanceof HTMLAnchorElement) { const before = node.getAttribute('href'); if (before) { const next = englishHref(before); if (next !== before) node.setAttribute('href',next); } }
      if (!node.matches(protectedSelector)) for (const child of node.childNodes) translate(child);
    }
  };
  translate(root);
  new MutationObserver(records => {
    for (const record of records) {
      if (record.type === 'childList') for (const node of record.addedNodes) translate(node);
      else translate(record.target);
    }
  }).observe(root, { subtree:true, childList:true, characterData:true, attributes:true, attributeFilter:['title','placeholder','aria-label','aria-roledescription','alt','href'] });
}
void startEnglishTranslation();
