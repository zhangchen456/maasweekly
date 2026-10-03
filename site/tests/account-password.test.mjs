import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
import { transform } from 'esbuild';

async function setup() {
  const source = fs.readFileSync(new URL('../src/components/AccountAccess.astro', import.meta.url), 'utf8');
  const markup = source.split('---')[2].split('<script>')[0];
  const dom = new JSDOM(markup, {url: 'https://daily.maas.click/', runScripts: 'outside-only'});
  const calls = [];
  const win = dom.window;
  win.HTMLDialogElement.prototype.showModal = function () { this.open = true; };
  win.HTMLDialogElement.prototype.close = function () { this.open = false; };
  win.accountApi = async (route, data) => { calls.push({route, data}); return {retryAfter: 60}; };
  win.announceAccountChange = async () => {};
  win.onAccountChange = () => {};
  win.logoutAccount = async () => {};
  win.flushAccountState = async () => {};
  const script = fs.readFileSync(new URL('../src/scripts/account-access.ts', import.meta.url), 'utf8').replace(/^import .*;\n/, '');
  win.eval((await transform(script, {loader: 'ts'})).code);
  const el = id => win.document.getElementById(id);
  const submit = async () => { el('account-global-login').dispatchEvent(new win.Event('submit', {bubbles:true,cancelable:true})); await new Promise(resolve => setImmediate(resolve)); };
  return {win, el, calls, submit};
}

test('default login sends password; registration verifies email then sets matching password', async () => {
  const {win, el, calls, submit} = await setup();
  try {
    el('account-login-open').click();
    el('account-login-email').value = 'a@example.com';
    el('account-login-password').value = 'existing password';
    await submit(); assert.equal(calls[0].route, 'login'); assert.equal(calls[0].data.password, 'existing password');
    el('account-mode-register').click();
    assert.equal(el('account-login-password').required, false);
    el('account-global-send').click(); await new Promise(resolve => setImmediate(resolve));
    assert.equal(calls[1].route, 'request-code');
    el('account-login-code').value = '123456'; await submit();
    assert.equal(calls[2].route, 'verify'); assert.equal(el('account-password-confirm-fields').hidden, false);
    assert.equal(el('account-login-email').disabled, true);
    el('account-login-password').value = 'my new password'; el('account-password-confirm').value = 'different'; await submit();
    assert.equal(calls.length, 3); assert.match(el('account-login-feedback').textContent, /不一致/);
    el('account-password-confirm').value = 'my new password'; await submit();
    assert.equal(calls[3].route, 'password'); assert.equal(el('account-login-password').value, '');
    assert.equal(el('account-login-dialog').open, false);
  } finally { win.close(); }
});

test('account center opens email recovery and returning to login disables OTP validation', async () => {
  const {win, el} = await setup();
  try {
    win.document.dispatchEvent(new win.CustomEvent('maas:password-setup'));
    assert.equal(el('account-login-dialog').open, true); assert.equal(el('account-global-send').hidden, false);
    el('account-mode-login').click();
    assert.equal(el('account-global-code-fields').hidden, true); assert.equal(el('account-login-code').required, false);
    assert.equal(el('account-login-password').required, true); assert.equal(el('account-login-password').autocomplete, 'current-password');
  } finally { win.close(); }
});
