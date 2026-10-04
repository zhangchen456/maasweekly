import { mkdtempSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { AccountStore } from '/srv/maasweekly/current/agent-api/dist/account-store.js';
import { createMailer } from '/srv/maasweekly/current/agent-api/dist/account-mail.js';
import { deliverDigests } from '/srv/maasweekly/current/agent-api/dist/account-digest.js';
import { DatasetHolder } from '/srv/maasweekly/current/agent-api/dist/dataset.js';
const recipient = process.env.MAAS_ACCOUNT_ALERT_TO;
if (!recipient) throw new Error('MAAS_ACCOUNT_ALERT_TO required');
const root = mkdtempSync(path.join(tmpdir(), 'maas-digest-acceptance-'));
let now = Date.now();
const store = new AccountStore(path.join(root,'accounts.sqlite'), () => now);
const holder = new DatasetHolder('/srv/maasweekly/current/data/public/v1');
const originalFetch = globalThis.fetch;
let emailId;
globalThis.fetch = async (...args) => {
  const response = await originalFetch(...args);
  if (args[0] === 'https://api.resend.com/emails' && response.ok) emailId = (await response.clone().json()).id;
  return response;
};
try {
  await holder.reloadAsync();
  const actual = holder.current.changes.find(c => c.modelId && c.status !== 'withdrawn' && Date.parse(c.updatedAt ?? c.observedAt ?? `${c.observationDate}T00:00:00+08:00`) <= now);
  if (!actual) throw new Error('no model-linked fixture');
  const user = store.verify(recipient, store.issueCode(recipient)).user;
  store.db.prepare('INSERT INTO watches VALUES(?,?,?)').run(user.id, actual.modelId, now);
  store.preferences(user.id, true);
  const mailer = createMailer();
  const acceptanceMailer = {send: mail => mailer.send({...mail, subject:'[验收] ' + mail.subject,
    text:'这是账号摘要投递验收邮件。引用真实模型记录，在隔离数据库中模拟关注后的变化；不修改公开数据或任何真实账号。\n\n' + mail.text,
    key:'acceptance-' + mail.key})};
  const baseline = await deliverDigests(store, acceptanceMailer, [actual], 'https://daily.maas.click');
  now += 2000;
  const change = {...actual, updatedAt: new Date(now).toISOString()};
  const first = await deliverDigests(store, acceptanceMailer, [change], 'https://daily.maas.click');
  const duplicate = await deliverDigests(store, acceptanceMailer, [change], 'https://daily.maas.click');
  store.unsubscribe(user.unsubscribeToken);
  const unsubscribed = await deliverDigests(store, acceptanceMailer, [{...change, revision:change.revision+1}], 'https://daily.maas.click');
  if (baseline.sent || first.sent !== 1 || duplicate.sent || unsubscribed.sent) throw new Error('acceptance counts failed');
  console.log(JSON.stringify({scope:'Production code and Resend, isolated DB, controlled timestamp on real model-linked record', baseline,first,duplicate,unsubscribed,emailId}));
} finally {store.close();holder.close();rmSync(root,{recursive:true,force:true});}
