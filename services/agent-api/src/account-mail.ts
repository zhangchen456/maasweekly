import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';

export interface Mail { to: string; subject: string; text: string; key: string }
export interface Mailer { send(mail: Mail): Promise<void> }
export function createMailer(env = process.env): Mailer | null {
  if (env.MAAS_MAIL_MODE === 'outbox') {
    if (env.MAAS_RELEASE_DIR || env.NODE_ENV === 'production') throw new Error('outbox is local-only');
    if (!env.MAAS_MAIL_OUTBOX) throw new Error('MAAS_MAIL_OUTBOX required');
    const root = path.resolve(env.MAAS_MAIL_OUTBOX);
    return { async send(mail) {
      await mkdir(root, { recursive: true, mode: 0o700 });
      await writeFile(path.join(root, `${randomUUID()}.json`), JSON.stringify(mail, null, 2), { mode: 0o600 });
    } };
  }
  if (!env.RESEND_API_KEY || !env.MAAS_MAIL_FROM) return null;
  return { async send(mail) {
    const response = await fetch('https://api.resend.com/emails', {
      method: 'POST', signal: AbortSignal.timeout(15000),
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json', 'Idempotency-Key': mail.key },
      body: JSON.stringify({ from: env.MAAS_MAIL_FROM, to: [mail.to], subject: mail.subject, text: mail.text }),
    });
    if (!response.ok) throw new Error('mail_delivery_failed');
  } };
}
