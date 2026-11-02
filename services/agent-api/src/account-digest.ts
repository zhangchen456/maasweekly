import type {ProjectDelivery} from './project-mail.js';
import { MailLedger } from './mail-ledger.js';
import { AccountStore } from './account-store.js';
import type { Mail, Mailer } from './account-mail.js';
import type { ChangeEntity } from './public-contract/entities.js';

export async function deliverDigests(store: AccountStore, mailer: Mailer, changes: readonly ChangeEntity[], origin: string, enqueue = true, projects?:ProjectDelivery) {
  const ledger=new MailLedger(store);
  store.cleanup();
  const queued = enqueue ? store.enqueue(changes)+(projects?.enqueue()??0) : 0;
  let sent = 0, failed = 0;
  for (let i = 0; i < 500; i++) {
    const job = store.claim(); if (!job) break;
    const watched = new Set(store.effectiveWatches(job.userId).map(w => w.modelId));
    const latest = new Map(changes.map(c => [c.id, c]));
    const projectEvents=projects?.events(job.id)??[],covered=new Set(projectEvents.flatMap(e=>e.next.lines.flatMap(l=>[l.input?.factKey,l.output?.factKey].filter(Boolean))));
    const items = (JSON.parse(job.payload) as ChangeEntity[]).filter(c => !!job.user.emailEnabled && c.modelId && !(c.recordType==='price_change'&&c.price&&covered.has(c.price.factKey)) && watched.has(c.modelId) && (job.mail || !latest.has(c.id) || latest.get(c.id)!.revision <= c.revision));
    if (!items.length&&!projectEvents.length) { store.db.prepare("UPDATE mail_jobs SET status='cancelled',lease=0 WHERE id=?").run(job.id); continue; }
    const lines = items.map(c => `${c.status === 'withdrawn' ? '[已撤回] ' : ''}${c.title}\n${c.summary ?? ''}\n${new URL(`/item/${encodeURIComponent(c.id)}/`, origin).href}`);
    const unsubscribe = new URL('/account/unsubscribe/', origin);
    unsubscribe.hash = job.user.unsubscribeToken;
    const attempt=ledger.begin('digest',job.id,job.lease);
    try {
      const composed: Mail = { to: job.user.email, subject: projectEvents.length?`MaaS Daily · ${projectEvents.length} 个项目成本／报价变化`:`MaaS Daily · 你关注的模型有 ${items.length} 条变化`, key: `digest-${job.id}`,
        text: `${projectEvents.length?'项目成本跟踪（按保存的月用量估算，不代表真实账单）：\n\n'+projects!.text(job.id,origin)+'\n\n':''}${lines.length?'其他关注模型变化：\n\n'+lines.join('\n\n'):''}\n\n查看我的关注：${origin}/account/\n关闭邮件提醒：${unsubscribe.href}\n\n仅匹配明确关联模型的记录；项目按保存用量估算，详情页包含条件与来源。项目邮件可在项目页关闭；上方退订链接关闭此账户的模型及项目汇总邮件。` };
      const mail = job.mail ? JSON.parse(job.mail) as Mail : composed;
      if (!job.mail) store.freezeMail(job.id, JSON.stringify(mail));
      if(!store.mailEligible(job.userId,job.id)||(job.mail&&projects?.hasBatch(job.id)&&projectEvents.length!==JSON.parse(String(store.db.prepare('SELECT eventIds FROM cost_mail_batches WHERE jobId=?').get(job.id)?.eventIds??'[]')).length)){store.db.prepare("UPDATE mail_jobs SET status='cancelled' WHERE id=?").run(job.id);ledger.finish('digest',job.id,job.lease,attempt,'cancelled');continue;}
      await ledger.send('digest',job.id,job.lease,attempt,mailer,mail);
      if(ledger.state('digest',job.id)==='accepted')sent++;else failed++;
    } catch { ledger.finish('digest',job.id,job.lease,attempt,'unknown',undefined,'composition_failed');failed++; }
  }
  return { queued, sent, failed, review: Number(store.db.prepare("SELECT COUNT(*) AS count FROM mail_jobs WHERE status='review'").get()?.count ?? 0) };
}
