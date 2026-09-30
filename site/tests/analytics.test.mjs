import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import zlib from 'node:zlib';
import { JSDOM } from 'jsdom';
import { transform } from 'esbuild';
import { cleanPageUrl, cleanReferrer, pageType, startAnalytics, validateAnalyticsConfig } from '../public/analytics.js';

const ID = '94db1cb1-74f4-4a40-ad6c-962362670409'; // Test UUID, never a production website.
const BASE = 'https://daily.maas.click';
const enabled = { enabled: true, websiteId: ID };
function browser(html = '', url = BASE + '/changes/') {
  return new JSDOM(html, { url, runScripts: 'outside-only' });
}
function payload(url = '/changes/') {
  return { website: ID, url, hostname: 'daily.maas.click', title: 'Private arbitrary text',
    referrer: 'https://www.google.com/search?q=private@example.com', language: 'zh-CN', screen: '1920x1080' };
}
function provider(win, events, mode = 'ok') {
  win.umami = { track(name, data) {
    if (mode === 'throw') throw new Error('blocked');
    if (mode === 'reject') return Promise.reject(new Error('offline'));
    const p = win.maasAnalyticsBeforeSend('event', { ...payload(win.location.href), name, data });
    if (p) events.push(p);
    return Promise.resolve();
  } };
}

test('disabled, preview host and excluded visitors never load the provider', () => {
  for (const [config, url, exclude] of [
    [{ enabled: false, websiteId: '' }, BASE, false],
    [enabled, 'https://preview.example.com/', false],
    [enabled, BASE, true],
  ]) {
    const dom = browser('', url);
    if (exclude) dom.window.localStorage.setItem('umami.disabled', '1');
    assert.equal(startAnalytics(dom.window, config, BASE), null);
    assert.equal(dom.window.document.querySelector('script'), null);
    dom.window.close();
  }
});

test('invalid configuration fails before tracker creation', () => {
  assert.throws(() => validateAnalyticsConfig({ enabled: true, websiteId: '' }));
  assert.throws(() => validateAnalyticsConfig({ enabled: true, websiteId: '<script>' }));
  assert.throws(() => validateAnalyticsConfig({ enabled: 'true', websiteId: ID }));
  assert.deepEqual(validateAnalyticsConfig({ enabled: false, websiteId: '' }), { enabled: false, websiteId: '' });
});

test('only approved UTM is retained; hashes, search terms, tokens and referrer queries are discarded', () => {
  assert.equal(cleanPageUrl('/changes/?q=private&token=secret&utm_source=github&utm_campaign=launch#email', BASE),
    '/changes/?utm_source=github&utm_campaign=launch');
  assert.equal(cleanPageUrl('/?utm_source=private%40example.com', BASE), '/');
  assert.equal(cleanPageUrl('https://foreign.example.com/', BASE), null);
  assert.equal(cleanReferrer('https://chatgpt.com/c/private-id?token=secret', BASE), 'https://chatgpt.com');
  assert.equal(cleanReferrer(BASE + '/agent/?token=secret#key', BASE), BASE + '/agent/');
  assert.equal(cleanReferrer('javascript:secret', BASE), '');
});

test('native pageviews have one entry point; filter/query changes do not count as new views', () => {
  const dom = browser();
  const script = startAnalytics(dom.window, enabled, BASE);
  assert.equal(script.async, true);
  assert.equal(script.dataset.beforeSend, 'maasAnalyticsBeforeSend');
  assert.equal(script.dataset.autoTrack, undefined); // Native tracker initializes pageviews.
  assert.equal(startAnalytics(dom.window, enabled, BASE), null);
  assert.equal(dom.window.document.querySelectorAll('script').length, 1);
  const send = dom.window.maasAnalyticsBeforeSend;
  const initial = send('event', payload('/changes/?q=private'));
  assert.equal(initial.url, '/changes/');
  assert.equal(initial.title, 'changes');
  assert.equal(initial.referrer, 'https://www.google.com');
  assert.equal(send('event', payload('/changes/?modelId=openai:gpt-4.1')), false);
  assert.ok(send('event', payload('/pricing/')));
  assert.ok(send('event', payload('/changes/')));
  assert.equal(send('identify', { email: 'private@example.com' }), false);
  assert.equal(send('event', payload('/admin/analytics/')), false);
  dom.window.close();
  const refresh = browser();
  startAnalytics(refresh.window, enabled, BASE);
  assert.ok(refresh.window.maasAnalyticsBeforeSend('event', payload()));
  refresh.window.close();
});

test('dynamic model filter clicks retain canonical identity even when their handler removes the button', () => {
  const dom = browser('<button data-analytics-model-id="openai:gpt-4.1">model</button>');
  const events = [];
  startAnalytics(dom.window, enabled, BASE);
  provider(dom.window, events);
  const button = dom.window.document.querySelector('button');
  button.onclick = () => button.remove();
  button.click();
  assert.equal(events.length, 1);
  assert.equal(events[0].name, 'model_click');
  assert.deepEqual(events[0].data, { page_type: 'changes', model_id: 'openai:gpt-4.1' });
  dom.window.close();
});

test('links track model IDs or external domains only; navigation is not prevented', () => {
  const dom = browser('<a id="model" href="/model/openai%3Agpt-4.1/">model</a><a id="out" href="https://github.com/u/r?token=secret">out</a><a id="internal" href="/pricing/">internal</a><a id="mail" href="mailto:private@example.com">mail</a>');
  const events = [];
  startAnalytics(dom.window, enabled, BASE);
  provider(dom.window, events);
  for (const id of ['model', 'out', 'internal', 'mail']) {
    const event = new dom.window.MouseEvent('click', { bubbles: true, cancelable: true, button: 0 });
    // Prevent jsdom's asynchronous navigation after observing analytics behavior.
    dom.window.document.getElementById(id).addEventListener('click', e => {
      assert.equal(e.defaultPrevented, false); e.preventDefault();
    });
    dom.window.document.getElementById(id).dispatchEvent(event);
  }
  assert.deepEqual(events.map(e => e.name), ['model_click', 'outbound_click']);
  assert.deepEqual(events[1].data, { page_type: 'changes', target_domain: 'github.com' });
  dom.window.close();
});

test('middle-click is counted once and right-click is ignored', () => {
  const dom = browser('<a href="https://github.com/">out</a>');
  const events = [];
  startAnalytics(dom.window, enabled, BASE);
  provider(dom.window, events);
  for (const button of [1, 2]) dom.window.document.querySelector('a').dispatchEvent(
    new dom.window.MouseEvent('auxclick', { bubbles: true, button }));
  assert.equal(events.length, 1);
  dom.window.close();
});

test('event allowlist strips copied text, arbitrary properties and unsupported events', () => {
  const dom = browser();
  startAnalytics(dom.window, enabled, BASE);
  const send = dom.window.maasAnalyticsBeforeSend;
  const copy = send('event', { ...payload(), name: 'copy', data: { kind: 'url', text: 'secret', email: 'private' }, id: 'user-id' });
  assert.deepEqual(copy.data, { page_type: 'changes', kind: 'url' });
  assert.equal(copy.id, undefined);
  assert.equal(send('event', { ...payload(), name: 'copy', data: { kind: 'secret text' } }), false);
  assert.equal(send('event', { ...payload(), name: 'scroll_depth', data: { depth: 75 } }), false);
  assert.equal(send('event', { ...payload(), name: 'outbound_click', data: { target_domain: 'user:password@github.com' } }), false);
  dom.window.close();
});

test('missing/throwing/rejecting provider cannot break product click or successful copy', async () => {
  for (const mode of ['missing', 'throw', 'reject']) {
    const dom = browser('<button data-analytics-model-id="openai:gpt-4.1">model</button>');
    startAnalytics(dom.window, enabled, BASE);
    if (mode !== 'missing') provider(dom.window, [], mode);
    let clicked = 0;
    dom.window.document.querySelector('button').onclick = () => clicked++;
    dom.window.document.querySelector('button').click();
    dom.window.document.dispatchEvent(new dom.window.CustomEvent('maas:copy-success', { detail: { kind: 'content' } }));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(clicked, 1);
    dom.window.close();
  }
});

test('CopyBlock reports exactly one successful copy and none on clipboard rejection', async () => {
  const dom = browser('<div data-copyblock><button data-copy-btn>复制</button><pre data-copy-source>private prompt</pre><span data-copy-feedback></span></div>', BASE + '/agent/');
  const events = [];
  startAnalytics(dom.window, enabled, BASE);
  provider(dom.window, events);
  let copied;
  Object.defineProperty(dom.window.navigator, 'clipboard', { value: { writeText: async text => { copied = text; } } });
  const source = fs.readFileSync(new URL('../src/components/CopyBlock.astro', import.meta.url), 'utf8').match(/<script>([\s\S]*?)<\/script>/)[1];
  dom.window.eval((await transform(source, { loader: 'ts' })).code);
  dom.window.document.querySelector('button').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(copied, 'private prompt');
  assert.equal(events.length, 1);
  assert.deepEqual(events[0].data, { page_type: 'agent', kind: 'content' });
  dom.window.navigator.clipboard.writeText = async () => { throw new Error('denied'); };
  dom.window.document.querySelector('button').click();
  await new Promise(resolve => setImmediate(resolve));
  assert.equal(events.length, 1);
  assert.equal(dom.window.getSelection().toString(), copied);
  dom.window.close();
});

test('DNT and opt-out set after initialization cancel all subsequent events', () => {
  const dom = browser();
  startAnalytics(dom.window, enabled, BASE);
  dom.window.localStorage.setItem('umami.disabled', '1');
  assert.equal(dom.window.maasAnalyticsBeforeSend('event', payload()), false);
  dom.window.close();
  const dnt = browser();
  Object.defineProperty(dnt.window.navigator, 'doNotTrack', { value: '1' });
  assert.equal(startAnalytics(dnt.window, enabled, BASE), null);
  dnt.window.close();
});

test('page semantics use real routes and the adapter remains a small standalone file', () => {
  assert.equal(pageType('/model/openai:gpt-4.1/'), 'model_detail');
  assert.equal(pageType('/pricing/'), 'prices');
  assert.equal(pageType('/leaderboards/'), 'leaderboard');
  const source = fs.readFileSync(new URL('../public/analytics.js', import.meta.url));
  assert.ok(zlib.gzipSync(source).length < 3072, 'adapter exceeds 3 KiB gzip budget');
});
