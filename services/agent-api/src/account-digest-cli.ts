import {ProjectStore} from './project-store.js';
import {ProjectDelivery} from './project-mail.js';
import path from 'node:path';
import {Membership,membershipEnabled} from './membership.js';
import {ProStore} from './pro-store.js';
import { AccountStore } from './account-store.js';
import { createMailer } from './account-mail.js';
import { deliverDigests } from './account-digest.js';
import { DatasetHolder } from './dataset.js';

if (!process.env.MAAS_ACCOUNT_DB || !process.env.PUBLIC_DATA_ROOT) throw new Error('MAAS_ACCOUNT_DB and PUBLIC_DATA_ROOT required');
const mailer = createMailer();
if (!mailer) throw new Error('mail service not configured');
const holder = new DatasetHolder(path.resolve(process.env.PUBLIC_DATA_ROOT),{publicationFile:process.env.MAAS_RELEASE_DIR?'publication.json':'manifest.json'});
const store = new AccountStore(path.resolve(process.env.MAAS_ACCOUNT_DB));
if(membershipEnabled())new Membership(store,new ProStore(store),true);
const projectStore=new ProjectStore(store,new ProStore(store));
const projectDelivery=new ProjectDelivery(projectStore);
try {
  const result = await holder.reloadAsync();
  if (result === 'failed' || !holder.current) throw new Error('dataset unavailable');
  const projectRefresh=projectStore.refreshAll(holder.current);
  if(projectRefresh.failed)throw new Error('project refresh incomplete');
  const counts = await deliverDigests(store, mailer, holder.current.changes, process.env.MAAS_ACCOUNT_ORIGIN ?? 'https://daily.maas.click', !process.argv.includes('--retry-only'),projectDelivery);
  console.log(JSON.stringify(counts)); // Counts only; no email addresses, codes or tokens.
  if (counts.failed || counts.review) process.exitCode = 1;
} finally { store.close(); holder.close(); }
