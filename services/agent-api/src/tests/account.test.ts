import { test } from 'node:test';
import assert from 'node:assert/strict';
import http from 'node:http';
import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { AccountStore, AccountError } from '../account-store.js';
import { createAccountHandler } from '../account-http.js';
import { deliverDigests } from '../account-digest.js';
import { createMailer, type Mail } from '../account-mail.js';
import type { DatasetHolder } from '../dataset.js';
import type { ChangeEntity } from '../public-contract/entities.js';

const SECRET = 'test-account-secret-32-characters-minimum';
const catalog = { models: [{ modelId: 'openai:gpt-test', modelName: 'GPT test' }, { modelId: 'deepseek:test', modelName: 'DeepSeek test' }], families: [] };
const start = Date.parse('2026-10-02T08:00:00Z');
function change(id: string, time: number, modelId: string | null = 'openai:gpt-test', revision = 1) {
  return { id, modelId, revision, status: 'active', observationDate: '2026-10-02', updatedAt: new Date(time).toISOString(), title: '价格更新', summary: '输入价格调整', links: { permalink: `/item/${id}/` } } as ChangeEntity;
}
function login(store: AccountStore, email = 'a@example.com') { const code = store.issueCode(email); return store.verify(email, code); }

test('codes expire, persist failed attempts, cannot replay, and preserve identity', () => {
  let now = start; const store = new AccountStore(':memory:', () => now, SECRET);
  try {
    const code = store.issueCode('a@example.com');
    assert.throws(() => store.issueCode('a@example.com'), AccountError);
    const wrong = code === '000000' ? '111111' : '000000';
    for (let i=0; i<5; i++) assert.throws(() => store.verify('a@example.com', wrong));
    assert.throws(() => store.verify('a@example.com', code));
    now += 61000;
    const result = login(store);
    assert.throws(() => store.verify('a@example.com', code));
    assert.equal(store.user(result.session)?.email, 'a@example.com');
    now += 61000;
    assert.equal(login(store).user.id, result.user.id);
    now += 61000;
    const expired = store.issueCode('b@example.com'); now += 600001;
    assert.throws(() => store.verify('b@example.com', expired));
    assert.equal(store.db.prepare('SELECT hash FROM sessions LIMIT 1').get()?.hash === result.session, false);
    store.logout(result.session); assert.equal(store.user(result.session), undefined);
  } finally { store.close(); }
});

test('SQLite sessions and watches survive restart; two connections share state', () => {
  const root = mkdtempSync(path.join(tmpdir(), 'account-db-'));
  let first: AccountStore | undefined, second: AccountStore | undefined;
  try {
    first = new AccountStore(path.join(root, 'account.sqlite'), () => start, SECRET);
    const { user, session } = login(first); first.watch(user.id, catalog.models[0]!.modelId, catalog);
    first.close(); first = undefined;
    second = new AccountStore(path.join(root, 'account.sqlite'), () => start, SECRET);
    assert.equal(second.user(session)?.id, user.id); assert.equal(second.watches(user.id).length, 1);
    first = new AccountStore(path.join(root, 'account.sqlite'), () => start, SECRET);
    first.unwatch(user.id, catalog.models[0]!.modelId); assert.equal(second.watches(user.id).length, 0);
  } finally { first?.close(); second?.close(); rmSync(root, { recursive: true, force: true }); }
});

test('digest opt-in, baseline, exact identity, revision dedup, unsubscribe and re-enable', async () => {
  let now = start; const store = new AccountStore(':memory:', () => now, SECRET); const messages: Mail[] = [];
  const mailer = { async send(mail: Mail) { messages.push(mail); } };
  try {
    const { user } = login(store); store.watch(user.id, 'openai:gpt-test', catalog);
    const items = [change('old', start-1), change('new', start+1000), change('unresolved', start+2000, null), change('other', start+2000, 'deepseek:test')];
    now += 3000;
    assert.equal((await deliverDigests(store, mailer, items, 'https://daily.maas.click')).sent, 0);
    store.preferences(user.id, true);
    const future = [...items, change('future', now+1000)]; now += 2000;
    assert.equal((await deliverDigests(store, mailer, future, 'https://daily.maas.click')).sent, 1);
    assert.ok(messages[0]!.text.includes('/item/future/')); assert.ok(!messages[0]!.text.includes('/item/old/'));
    assert.ok(messages[0]!.text.includes(`/account/unsubscribe/#${user.unsubscribeToken}`));
    assert.equal((await deliverDigests(store, mailer, future, 'https://daily.maas.click')).sent, 0);
    const revised = [change('future', now+1000, 'openai:gpt-test', 2)]; now+=2000;
    assert.equal((await deliverDigests(store, mailer, revised, 'https://daily.maas.click')).sent, 1);
    assert.equal(store.unsubscribe('invalid'), false); assert.equal(store.unsubscribe(user.unsubscribeToken), true);
    assert.equal(store.watches(user.id).length, 1);
    assert.equal((await deliverDigests(store, mailer, [change('later', now+1000)], 'https://daily.maas.click')).sent, 0);
    now += 2000; store.preferences(user.id, true);
    assert.equal((await deliverDigests(store, mailer, [change('later', now-1000)], 'https://daily.maas.click')).sent, 0);
  } finally { store.close(); }
});

test('failed email retries with identical payload and key; lease blocks concurrent sends', async () => {
  let now=start; const store = new AccountStore(':memory:', () => now, SECRET); const attempts: Mail[] = [];
  try {
    const { user } = login(store); store.watch(user.id, 'openai:gpt-test', catalog); store.preferences(user.id, true);
    now+=2000;
    const items = [change('a', now-1000)];
    const failing = { async send(mail: Mail) { attempts.push(mail); throw new Error('timeout'); } };
    assert.equal((await deliverDigests(store, failing, items, 'https://daily.maas.click')).failed, 1);
    assert.equal(store.claim(), null);
    now+=300001;
    const result = await deliverDigests(store, { async send(mail) { attempts.push(mail); } }, [{...items[0]!,title:'modified'}], 'https://daily.maas.click');
    assert.equal(result.sent, 1); assert.deepEqual(attempts[0], attempts[1]);
    assert.equal((await deliverDigests(store, failing, items, 'https://daily.maas.click')).failed, 0);
  } finally { store.close(); }
});

test('uncertain delivery beyond idempotency window requires review', async () => {
  let now=start; const store = new AccountStore(':memory:', () => now, SECRET);
  try {
    const { user }=login(store); store.watch(user.id, 'openai:gpt-test', catalog); store.preferences(user.id, true); now+=2000;
    const items=[change('a',now-1000)];
    await deliverDigests(store,{async send(){throw new Error('timeout');}},items,'https://daily.maas.click');
    now+=24*3600000;
    let sends=0; const result=await deliverDigests(store,{async send(){sends++;}},items,'https://daily.maas.click');
    assert.equal(result.review,1);assert.equal(sends,0);
  } finally {store.close();}
});

test('private HTTP: cookie security, CSRF, isolation, no-store, no leaked codes, logout', async () => {
  const store = new AccountStore(':memory:', () => start, SECRET); const messages: Mail[] = [];
  const holder = { current: { modelIdentities: catalog, changes: [change('a',start)], dataThrough:'2026-10-02' } } as unknown as DatasetHolder;
  const handler = createAccountHandler(store, {async send(mail) {messages.push(mail);}}, holder, { origin:'https://daily.maas.click', secure:true });
  const server = http.createServer(handler);
  await new Promise<void>(r => server.listen(0,'127.0.0.1',r));
  const base = `http://127.0.0.1:${(server.address() as {port:number}).port}/api/account/`;
  const post = (route:string,data:unknown,cookie='',origin='https://daily.maas.click') => fetch(base+route,{method:'POST',headers:{Origin:origin,'Content-Type':'application/json',Cookie:cookie},body:JSON.stringify(data)});
  try {
    assert.equal((await post('request-code',{email:'a@example.com'},'','https://evil.example')).status,403);
    const request = await post('request-code',{email:' A@EXAMPLE.COM '}); assert.equal(request.status,200);
    assert.ok(!JSON.stringify(await request.json()).includes('code'));
    const code = messages[0]!.text.match(/\b\d{6}\b/)![0];
    const verified = await post('verify',{email:'a@example.com',code}); assert.equal(verified.status,200);
    const setCookie = verified.headers.get('set-cookie')!;
    assert.match(setCookie,/__Host-maas_session=/);assert.match(setCookie,/HttpOnly/);assert.match(setCookie,/Secure/);assert.match(setCookie,/SameSite=Lax/);
    const cookie = setCookie.split(';')[0]!;
    const me = await fetch(base+'me',{headers:{Cookie:cookie}});assert.equal(me.status,200);assert.equal(me.headers.get('cache-control'),'no-store');assert.equal(me.headers.get('access-control-allow-origin'),null);
    assert.ok(!JSON.stringify(await me.json()).includes('unsubscribeToken'));
    assert.equal((await post('watch',{modelId:'openai:gpt-test'},cookie)).status,200);
    assert.equal((await post('watch',{modelId:'unknown'},cookie)).status,400);
    assert.equal((await post('watch',{modelId:'openai:gpt-test'})).status,401);
    const other = login(store,'b@example.com'); const otherCookie=`__Host-maas_session=${other.session}`;
    const otherMe = await fetch(base+'me',{headers:{Cookie:otherCookie}});assert.equal((await otherMe.json() as {watches:unknown[]}).watches.length,0);
    await post('unwatch',{modelId:'openai:gpt-test',userId:store.user(cookie.split('=')[1]!)!.id},otherCookie);
    assert.equal((await (await fetch(base+'me',{headers:{Cookie:cookie}})).json() as {watches:unknown[]}).watches.length,1);
    assert.equal((await post('preferences',{emailEnabled:true},cookie)).status,200);
    const changes=await fetch(base+'changes',{headers:{Cookie:cookie}});assert.equal((await changes.json() as {items:unknown[]}).items.length,1);
    await post('logout',{},cookie);assert.equal((await fetch(base+'me',{headers:{Cookie:cookie}})).status,401);
    const tooLarge=await post('verify',{email:'a@example.com',padding:'x'.repeat(9000)}); assert.equal(tooLarge.status,413);
  } finally {server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));store.close();}
});

test('unconfigured account/mail status is honest; production refuses local outbox', async () => {
  assert.equal(createMailer({}),null);
  assert.throws(()=>createMailer({MAAS_MAIL_MODE:'outbox',MAAS_MAIL_OUTBOX:'/tmp/test',NODE_ENV:'production'}));
  const handler=createAccountHandler(null,null,{} as DatasetHolder,{origin:'https://daily.maas.click',secure:true});
  const server=http.createServer(handler);await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
  const base=`http://127.0.0.1:${(server.address() as {port:number}).port}/api/account/`;
  try {assert.deepEqual(await (await fetch(base+'status')).json(),{enabled:false,mailAvailable:false,cadence:'daily'});assert.equal((await fetch(base+'me')).status,503);}
  finally {server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));}
});

test('queued superseded revisions and cancelled model watches do not generate stale alerts', async () => {
  let now = start; const store = new AccountStore(':memory:', () => now, SECRET); const mails: Mail[]=[];
  try {
    const {user}=login(store);store.watch(user.id,'openai:gpt-test',catalog);store.preferences(user.id,true);now+=2000;
    store.enqueue([change('a',now-1000)]);
    const revised=change('a',now-500,'openai:gpt-test',2);
    const result=await deliverDigests(store,{async send(mail){mails.push(mail);}},[revised],'https://daily.maas.click');
    assert.equal(result.sent,1);assert.equal(mails.length,1);
    store.enqueue([change('b',now-500)]);store.unwatch(user.id,'openai:gpt-test');
    assert.equal((await deliverDigests(store,{async send(mail){mails.push(mail);}},[],'https://daily.maas.click')).sent,0);
    assert.equal(mails.length,1);
  } finally {store.close();}
});

test('retry-only run retries existing job and leaves new changes for daily digest', async () => {
  let now=start;const store=new AccountStore(':memory:',()=>now,SECRET);const mails:Mail[]=[];
  try {
    const {user}=login(store);store.watch(user.id,'openai:gpt-test',catalog);store.preferences(user.id,true);now+=2000;
    const first=change('a',now-1000);
    await deliverDigests(store,{async send(){throw new Error('timeout');}},[first],'https://daily.maas.click');
    now+=300001;const second=change('b',now-1000);
    const result=await deliverDigests(store,{async send(mail){mails.push(mail);}},[first,second],'https://daily.maas.click',false);
    assert.equal(result.queued,0);assert.equal(result.sent,1);assert.ok(!mails[0]!.text.includes('/item/b/'));
    assert.equal((await deliverDigests(store,{async send(mail){mails.push(mail);}},[first,second],'https://daily.maas.click')).sent,1);
  } finally {store.close();}
});

test('account profile and workspace data persist, isolate users, export safely, and revoke all sessions', async () => {
  const directory = mkdtempSync(path.join(tmpdir(),'maas-account-state-'));
  const filename = path.join(directory,'accounts.sqlite');
  let now = start;
  let store = new AccountStore(filename,()=>now,SECRET);
  const a=login(store,'profile-a@example.com'), b=login(store,'profile-b@example.com');
  now += 61000; const another=login(store,'profile-a@example.com');
  store.updateProfile(a.user,'工作账户');
  store.saveState(a.user.id,'homePrices',{currency:'USD',fx:7.2});
  store.close(); store=new AccountStore(filename,()=>now,SECRET);
  const holder={current:{modelIdentities:catalog,changes:[],dataThrough:'2026-10-03'}} as unknown as DatasetHolder;
  const server=http.createServer(createAccountHandler(store,{async send(){}},holder,{origin:'https://daily.maas.click',secure:true}));
  await new Promise<void>(resolve=>server.listen(0,'127.0.0.1',resolve));
  const base=`http://127.0.0.1:${(server.address() as {port:number}).port}/api/account/`;
  const cookie=(session:string)=>`__Host-maas_session=${session}`;
  const post=(route:string,data:unknown,session=a.session)=>fetch(base+route,{method:'POST',headers:{Origin:'https://daily.maas.click','Content-Type':'application/json',Cookie:cookie(session)},body:JSON.stringify(data)});
  try {
    const me=await(await fetch(base+'me',{headers:{Cookie:cookie(a.session)}})).json() as {user:{displayName:string};state:Record<string,unknown>};
    assert.equal(me.user.displayName,'工作账户');assert.deepEqual(me.state.homePrices,{currency:'USD',fx:7.2});
    assert.equal((await post('state',{key:'admin',value:{role:'admin'}})).status,400);
    assert.equal((await post('state',{key:'homePrices',value:{currency:'USD',fx:0}})).status,400);
    assert.equal((await post('profile',{displayName:'x'.repeat(61)})).status,400);
    assert.equal((await post('state',{key:'appearance',value:{theme:['dark']}})).status,400);
    assert.equal((await post('state',{key:'appearance',value:{theme:'dark'},userId:a.user.id},b.session)).status,200);
    const other=await(await fetch(base+'me',{headers:{Cookie:cookie(b.session)}})).json() as {state:Record<string,unknown>};
    assert.deepEqual(other.state,{appearance:{theme:'dark'}});assert.equal(store.state(a.user.id).appearance,undefined);
    const exported=JSON.stringify(await(await fetch(base+'export',{headers:{Cookie:cookie(a.session)}})).json());
    assert.ok(exported.includes('工作账户'));assert.ok(!exported.includes('unsubscribeToken'));assert.ok(!exported.includes(a.session));
    assert.equal((await post('logout-all',{})).status,200);assert.equal(store.user(a.session),undefined);assert.equal(store.user(another.session),undefined);assert.ok(store.user(b.session));
    assert.deepEqual(store.state(a.user.id).homePrices,{currency:'USD',fx:7.2});
  } finally {server.closeAllConnections();await new Promise<void>(r=>server.close(()=>r()));store.close();rmSync(directory,{recursive:true,force:true});}
});

test('password setup, login, recovery, throttling and restart preserve legacy account data', async () => {
  let now = start;
  const directory = mkdtempSync(path.join(tmpdir(), 'maas-password-'));
  const filename = path.join(directory, 'account.sqlite');
  let store = new AccountStore(filename, () => now, SECRET);
  try {
    const legacy = login(store); store.watch(legacy.user.id, 'openai:gpt-test', catalog);
    assert.equal(store.hasPassword(legacy.user.id), false);
    await assert.rejects(store.setPassword(legacy.session, 'short'), AccountError);
    await store.setPassword(legacy.session, 'correct horse battery');
    const stored = store.db.prepare('SELECT * FROM passwords').get()!;
    assert.ok(!JSON.stringify(stored).includes('correct horse battery'));
    await assert.rejects(store.setPassword(legacy.session, 'unauthorized overwrite'), AccountError);
    const first = await store.loginPassword('a@example.com', 'correct horse battery');
    assert.equal(store.user(first.session)?.id, legacy.user.id);
    assert.equal(store.watches(legacy.user.id).length, 1);
    await assert.rejects(store.setPassword(first.session, 'unauthorized overwrite'), AccountError);
    for (let i = 0; i < 10; i++) await assert.rejects(store.loginPassword('a@example.com', 'wrong password'), AccountError);
    await assert.rejects(store.loginPassword('a@example.com', 'correct horse battery'), (e: unknown) => e instanceof AccountError && e.status === 429);
    now += 16 * 60000;
    const recovered = login(store);
    await store.setPassword(recovered.session, 'replacement password');
    assert.equal(store.user(first.session), undefined);
    await assert.rejects(store.loginPassword('a@example.com', 'correct horse battery'), AccountError);
    store.close(); store = new AccountStore(filename, () => now, SECRET);
    const restored = await store.loginPassword('a@example.com', 'replacement password');
    assert.equal(store.user(restored.session)?.id, legacy.user.id);
    assert.equal(store.watches(legacy.user.id).length, 1);
    now += 60000;
    const expiredProof = login(store, 'new@example.com'); now += 11 * 60000;
    await assert.rejects(store.setPassword(expiredProof.session, 'long enough password'), AccountError);
  } finally { store.close(); rmSync(directory, {recursive: true, force: true}); }
});

test('password HTTP supports email verification then password login without mail', async () => {
  const store = new AccountStore(':memory:', () => start, SECRET);
  const verified = login(store);
  const server = http.createServer(createAccountHandler(store, null, {} as DatasetHolder, {origin: 'https://daily.maas.click', secure: true}));
  await new Promise<void>(resolve => server.listen(0, '127.0.0.1', resolve));
  const base = `http://127.0.0.1:${(server.address() as {port:number}).port}/api/account/`;
  const post = (route: string, body: unknown, cookie = '') => fetch(base + route, {method: 'POST', headers: {Origin: 'https://daily.maas.click', 'Content-Type': 'application/json', Cookie: cookie}, body: JSON.stringify(body)});
  try {
    assert.equal((await post('password', {password: 'strong password'})).status, 401);
    const cookie = `__Host-maas_session=${verified.session}`;
    assert.equal((await post('password', {password: 'strong password'}, cookie)).status, 200);
    assert.equal((await post('login', {email: 'a@example.com', password: 'wrong'})).status, 401);
    const response = await post('login', {email: ' A@EXAMPLE.COM ', password: 'strong password'});
    assert.equal(response.status, 200); assert.match(response.headers.get('set-cookie')!, /HttpOnly/);
    const me = await (await fetch(base + 'me', {headers: {Cookie: response.headers.get('set-cookie')!.split(';')[0]!}})).json() as {user: {hasPassword: boolean}};
    assert.equal(me.user.hasPassword, true); assert.ok(!JSON.stringify(me).includes('digest'));
  } finally { server.closeAllConnections(); await new Promise<void>(resolve => server.close(() => resolve())); store.close(); }
});
