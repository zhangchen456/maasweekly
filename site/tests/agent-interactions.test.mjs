import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
import { transform } from 'esbuild';
const html = fs.readFileSync(new URL('../dist/agent/index.html', import.meta.url), 'utf8');
async function script(file) {
  const source = fs.readFileSync(new URL(file, import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
  return (await transform(source, { loader: 'ts' })).code;
}
test('all methods remain readable without JavaScript; tabs support deep links, keyboard and history', async () => {
  const dom = new JSDOM(html, { url: 'https://daily.maas.click/agent/#method-mcp', runScripts: 'outside-only' });
  const { document, KeyboardEvent, HashChangeEvent } = dom.window;
  const panels = [...document.querySelectorAll('[data-panel]')];
  assert.equal(panels.length, 8);
  assert.equal(panels.filter(p => p.dataset.tier === 'free').length, 4);
  assert.equal(panels.filter(p => p.dataset.tier === 'plus').length, 4);
  assert.ok(panels.every(p => !p.hidden));
  dom.window.eval(await script('../src/pages/agent.astro'));
  assert.equal(panels.find(p => !p.hidden).dataset.panel, 'mcp');
  const tabs = [...document.querySelectorAll('[data-method]')];
  tabs[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(panels.find(p => !p.hidden).dataset.panel, 'rss');
  assert.equal(document.activeElement, tabs[2]);
  tabs[2].dispatchEvent(new KeyboardEvent('keydown', { key: 'Home', bubbles: true }));
  assert.equal(tabs[0].getAttribute('aria-selected'), 'true');
  assert.equal(tabs.filter(t => t.tabIndex === 0).length, 1);
  dom.window.location.hash = '#method-rest';
  dom.window.dispatchEvent(new HashChangeEvent('hashchange'));
  assert.equal(panels.find(p => !p.hidden).dataset.panel, 'rest');
  const selected = () => panels.filter(p => !p.hidden);
  const plans = [...document.querySelectorAll('[data-access-plan]')];
  assert.equal(selected().length, 1);
  plans.find(p => p.dataset.accessPlan === 'plus').click();
  assert.equal(selected()[0].id, 'plus-method-rest');
  assert.equal(dom.window.location.hash, '#plus-method-rest');
  assert.equal(plans.find(p => p.dataset.accessPlan === 'plus').getAttribute('aria-pressed'), 'true');
  assert.equal(tabs[3].getAttribute('aria-controls'), 'plus-method-rest');
  for (const tier of ['free', 'plus']) {
    plans.find(p => p.dataset.accessPlan === tier).click();
    for (const tab of tabs) {
      tab.click();
      assert.equal(selected().length, 1);
      assert.equal(selected()[0].dataset.tier, tier);
      assert.equal(selected()[0].dataset.panel, tab.dataset.method);
    }
  }
  dom.window.location.hash = '#plus-method-mcp';
  dom.window.dispatchEvent(new HashChangeEvent('hashchange'));
  assert.equal(selected()[0].id, 'plus-method-mcp');
  tabs[1].dispatchEvent(new KeyboardEvent('keydown', { key: 'ArrowRight', bubbles: true }));
  assert.equal(selected()[0].id, 'plus-method-rss');
  assert.equal(dom.window.location.hash, '#plus-method-rss');
  dom.window.location.hash = '#plus-access';
  dom.window.dispatchEvent(new HashChangeEvent('hashchange'));
  assert.equal(selected()[0].id, 'plus-method-skill');
  dom.window.close();
  const fresh = new JSDOM(html, { url: 'https://daily.maas.click/agent/#plus-method-mcp', runScripts: 'outside-only' });
  fresh.window.eval(await script('../src/pages/agent.astro'));
  assert.deepEqual([...fresh.window.document.querySelectorAll('[data-panel]')].filter(p => !p.hidden).map(p => p.id), ['plus-method-mcp']);
  fresh.window.close();
});
test('copy sends the complete local prompt and falls back to manual selection on failure', async () => {
  const dom = new JSDOM(html, { url: 'https://daily.maas.click/agent/', runScripts: 'outside-only' });
  let copied;
  Object.defineProperty(dom.window.navigator, 'clipboard', { value: { writeText: async text => { copied = text; } }, configurable: true });
  dom.window.eval(await script('../src/components/CopyBlock.astro'));
  const block = dom.window.document.querySelector('[data-copyblock]');
  const button = block.querySelector('button');
  button.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(copied, block.querySelector('[data-copy-source]').textContent);
  assert.ok(copied.includes('/maas-skill/README.md') && copied.includes('新会话中的验证问题'));
  assert.equal(button.textContent, '已复制 ✓');
  dom.window.navigator.clipboard.writeText = async () => { throw new Error('denied'); };
  button.click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(dom.window.getSelection().toString(), copied);
  assert.ok(block.querySelector('[data-copy-feedback]').textContent.includes('手动') || block.querySelector('[data-copy-feedback]').textContent.includes('Ctrl/⌘+C'));
  dom.window.close();
});
