import path from 'node:path';
import { AccountStore } from './account-store.js';
import { createMailer } from './account-mail.js';
import { deliverDigests } from './account-digest.js';
import { DatasetHolder } from './dataset.js';

if (!process.env.MAAS_ACCOUNT_DB || !process.env.PUBLIC_DATA_ROOT) throw new Error('MAAS_ACCOUNT_DB and PUBLIC_DATA_ROOT required');
const mailer = createMailer();
if (!mailer) throw new Error('mail service not configured');
const holder = new DatasetHolder(path.resolve(process.env.PUBLIC_DATA_ROOT));
const store = new AccountStore(path.resolve(process.env.MAAS_ACCOUNT_DB));
try {
  const result = await holder.reloadAsync();
  if (result === 'failed' || !holder.current) throw new Error('dataset unavailable');
  const counts = await deliverDigests(store, mailer, holder.current.changes, process.env.MAAS_ACCOUNT_ORIGIN ?? 'https://daily.maas.click', !process.argv.includes('--retry-only'));
  console.log(JSON.stringify(counts)); // Counts only; no email addresses, codes or tokens.
  if (counts.failed || counts.review) process.exitCode = 1;
} finally { store.close(); holder.close(); }
