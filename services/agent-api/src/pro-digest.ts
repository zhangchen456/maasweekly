import { MailLedger } from './mail-ledger.js';
import type { Mail, Mailer } from './account-mail.js';
import { ProStore } from './pro-store.js';
export async function deliverPro(store: ProStore, mailer: Mailer, origin: string) {
  const ledger=new MailLedger(store.accounts);
  let sent=0,failed=0;
  for (let i=0;i<500;i++) {
    const job = store.accounts.transaction(() => {
      store.db.prepare("UPDATE pro_mail SET status='review' WHERE status='pending' AND lease>0 AND lease<=?").run(store.now);
      store.db.prepare("UPDATE pro_mail SET status='cancelled' WHERE status='pending' AND userId IN (SELECT userId FROM pro_settings WHERE emailEnabled=0)").run();
      const row = store.db.prepare("SELECT * FROM pro_mail WHERE status='pending' AND lease=0 AND created<=? ORDER BY created LIMIT 1").get(store.now) as {id:string;userId:string;reportId:string;mail:string|null}|undefined;
      if (!row) return null;
      if (store.entitlement(row.userId).status !== 'active' || !store.settings(row.userId)?.emailEnabled) { store.db.prepare("UPDATE pro_mail SET status='cancelled' WHERE id=?").run(row.id); return {cancelled:true} as const; }
      const lease=store.now+5*60000;store.db.prepare('UPDATE pro_mail SET lease=? WHERE id=?').run(lease,row.id); return {...row,lease};
    });
    if (!job) break; if ('cancelled' in job) continue;
    const attempt=ledger.begin('pro',job.id,job.lease);
    try {
      const report = store.report(job.userId,job.reportId);
      const user = store.db.prepare('SELECT email FROM users WHERE id=?').get(job.userId) as {email:string};
      const unsubscribe = `${origin}/pro/unsubscribe/#${store.settings(job.userId)!.unsubscribe}`;
      const mail: Mail = job.mail ? JSON.parse(job.mail) : {to:user.email,subject:`MaaS 专业简报 · ${job.id.startsWith('correction-') ? '重要更正 · ' : ''}${report.period}`,key:`pro-${job.id}`,text:`统计周截至 ${report.period}（Asia/Shanghai）\n范围快照：${JSON.stringify(report.scope)}\n覆盖状态：${report.coverage}\n\n${report.items.length ? report.items.map(c => 'withdrawn' in c ? `${c.id}：内容已撤回` : `${c.title}\n${c.preview}\n${c.correction ? '更正：'+c.correction+'\n' : ''}适用条件：${c.conditions}\n来源：${c.evidence.map(e => e.url).join(' ')}\n${origin}/pro/?content=${encodeURIComponent(c.id)}`).join('\n\n') : report.coverage === 'normal' ? '本期没有匹配的重要变化。' : '本期信源覆盖异常，不能认定为没有变化。'}\n\n邮件为简报摘要，完整表格和分析请登录：${origin}/pro/?report=${job.reportId}\n关闭专业邮件：${unsubscribe}`};
      store.db.prepare('UPDATE pro_mail SET mail=COALESCE(mail,?) WHERE id=?').run(JSON.stringify(mail),job.id);
      // Recheck after composition, before handing to the mail adapter.
      if (store.entitlement(job.userId).status !== 'active' || !store.settings(job.userId)?.emailEnabled) { store.db.prepare("UPDATE pro_mail SET status='cancelled' WHERE id=?").run(job.id);ledger.finish('pro',job.id,job.lease,attempt,'cancelled'); continue; }
      await ledger.send('pro',job.id,job.lease,attempt,mailer,mail);if(ledger.state('pro',job.id)==='accepted')sent++;else failed++;
    } catch {ledger.finish('pro',job.id,job.lease,attempt,'unknown',undefined,'composition_failed');failed++; }
  }
  return {sent,failed,review:Number(store.db.prepare("SELECT COUNT(*) AS n FROM pro_mail WHERE status='review'").get()?.n)};
}
