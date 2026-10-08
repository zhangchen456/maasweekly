import { MailLedger } from './mail-ledger.js';
import { AccountStore } from './account-store.js';
import type { Mail, Mailer } from './account-mail.js';
import type { ChangeEntity } from './public-contract/entities.js';

export async function deliverDigests(store: AccountStore, mailer: Mailer, changes: readonly ChangeEntity[], origin: string, enqueue = true) {
  const ledger=new MailLedger(store);
  store.cleanup();
  const queued = enqueue ? store.enqueue(changes) : 0;
  let sent = 0, failed = 0;
  for (let i = 0; i < 500; i++) {
    const job = store.claim(); if (!job) break;
    const watched = new Set(store.watches(job.userId).map(w => w.modelId));
    const latest = new Map(changes.map(c => [c.id, c]));
    const items = (JSON.parse(job.payload) as ChangeEntity[]).filter(c => c.modelId && watched.has(c.modelId) && (job.mail || !latest.has(c.id) || latest.get(c.id)!.revision <= c.revision));
    if (!items.length) { store.db.prepare("UPDATE mail_jobs SET status='cancelled',lease=0 WHERE id=?").run(job.id); continue; }
    const lines = items.map(c => `${c.status === 'withdrawn' ? '[已撤回] ' : ''}${c.title}\n${c.summary ?? ''}\n${new URL(`/item/${encodeURIComponent(c.id)}/`, origin).href}`);
    const unsubscribe = new URL('/account/unsubscribe/', origin);
    unsubscribe.hash = job.user.unsubscribeToken;
    const attempt=ledger.begin('digest',job.id,job.lease);
    try {
      const composed: Mail = { to: job.user.email, subject: `MaaS Daily · 你关注的模型有 ${items.length} 条变化`, key: `digest-${job.id}`,
        text: `你关注的模型有以下变化：\n\n${lines.join('\n\n')}\n\n查看我的关注：${origin}/account/\n关闭邮件提醒：${unsubscribe.href}\n\n仅匹配明确关联模型的记录；详情页包含最新修订和来源。` };
      const mail = job.mail ? JSON.parse(job.mail) as Mail : composed;
      if (!job.mail) store.freezeMail(job.id, JSON.stringify(mail));
      if(!store.db.prepare('SELECT 1 FROM users WHERE id=? AND emailEnabled=1').get(job.userId)){store.db.prepare("UPDATE mail_jobs SET status='cancelled' WHERE id=?").run(job.id);ledger.finish('digest',job.id,job.lease,attempt,'cancelled');continue;}
      await ledger.send('digest',job.id,job.lease,attempt,mailer,mail);
      if(ledger.state('digest',job.id)==='accepted')sent++;else failed++;
    } catch { ledger.finish('digest',job.id,job.lease,attempt,'unknown',undefined,'composition_failed');failed++; }
  }
  return { queued, sent, failed, review: Number(store.db.prepare("SELECT COUNT(*) AS count FROM mail_jobs WHERE status='review'").get()?.count ?? 0) };
}
