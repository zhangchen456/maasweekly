import {parse} from 'parse5';
const han = /[\u3400-\u9fff]/;
const attributes = ['title','placeholder','aria-label','aria-roledescription','alt'];
const protectedTags = new Set(['script','style','pre','code','blockquote']);
export function displayTexts(html, { legacyEvidence = false } = {}) {
  const texts = [];
  function walk(node, protectedParent = false) {
    const attrs = Object.fromEntries((node.attrs ?? []).map(a => [a.name,a.value]));
    const original = protectedParent || protectedTags.has(node.tagName) || 'data-original-language' in attrs
      || (legacyEvidence && /(?:^|\s)line-list(?:\s|$)/.test(attrs.class ?? ''));
    // The Chinese language switch is intentionally named in its own language.
    const languageSwitch = attrs['data-language'] === 'zh';
    if (!original && !languageSwitch) {
      if (node.nodeName === '#text' && han.test(node.value)) texts.push(node.value.trim());
      if (node.tagName === 'meta' && ['description','og:title','og:description','twitter:title','twitter:description'].includes(attrs.name ?? attrs.property) && han.test(attrs.content ?? '')) texts.push(attrs.content.trim());
    }
    if(!protectedParent && !('data-original-language'in attrs) && !languageSwitch && !['script','style'].includes(node.tagName)) for (const attr of attributes) if (han.test(attrs[attr] ?? '')) texts.push(attrs[attr].trim());
    if (!languageSwitch) for (const child of node.childNodes ?? []) walk(child, original);
    if (node.content) walk(node.content, original);
  }
  walk(parse(html,{scriptingEnabled:false}));
  return texts.filter(Boolean);
}
