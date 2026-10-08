import { mkdir, writeFile } from 'node:fs/promises';
import path from 'node:path';
import { randomUUID } from 'node:crypto';
import { MailSendError } from './mail-ledger.js';

export interface Mail { to: string; subject: string; text: string; key: string }
export interface MailAcceptance {provider:string;messageId:string}
export interface Mailer { readonly provider?:'local'|'resend'; send(mail: Mail): Promise<void|MailAcceptance> }
export function createMailer(env = process.env): Mailer | null {
  if (env.MAAS_MAIL_MODE === 'outbox') {
    if (env.MAAS_RELEASE_DIR || env.NODE_ENV === 'production') throw new Error('outbox is local-only');
    if (!env.MAAS_MAIL_OUTBOX) throw new Error('MAAS_MAIL_OUTBOX required');
    const root = path.resolve(env.MAAS_MAIL_OUTBOX);
    return { provider:'local', async send(mail) {
      await mkdir(root, { recursive: true, mode: 0o700 });
      const messageId=randomUUID();
      await writeFile(path.join(root, `${messageId}.json`), JSON.stringify(mail, null, 2), { mode: 0o600 });
      return {provider:'local',messageId};
    } };
  }
  if (!env.RESEND_API_KEY || !env.MAAS_MAIL_FROM) return null;
  return { provider:'resend', async send(mail) {
    const response = await fetch('https://api.resend.com/emails', {
      method: 'POST', signal: AbortSignal.timeout(15000),
      headers: { Authorization: `Bearer ${env.RESEND_API_KEY}`, 'Content-Type': 'application/json', 'Idempotency-Key': mail.key },
      body: JSON.stringify({ from: env.MAAS_MAIL_FROM, to: [mail.to], subject: mail.subject, text: mail.text }),
    });
    if (!response.ok) throw new MailSendError('provider_rejected', [400,401,403,422,429].includes(response.status));
    const data=await response.json() as {id?:unknown};
    if(typeof data.id!=='string'||!/^[a-zA-Z0-9_-]{1,128}$/.test(data.id))throw new MailSendError('invalid_acceptance');
    return {provider:'resend',messageId:data.id};
  } };
}
