import { DatasetHolder } from './dataset.js';
import { validateEditorial } from './pro-editorial.js';
import { contentSchema } from './pro-store.js';
import { readFileSync } from 'node:fs';
import { AccountStore } from './account-store.js';
import { ProStore } from './pro-store.js';
import { deliverPro } from './pro-digest.js';
import { createMailer } from './account-mail.js';

const [command,...args] = process.argv.slice(2);
if (!process.env.MAAS_ACCOUNT_DB) throw new Error('MAAS_ACCOUNT_DB required');
const accounts = new AccountStore(process.env.MAAS_ACCOUNT_DB), store = new ProStore(accounts);
try {
  let result: unknown;
  switch (command) {
    case 'draft': result=store.draft(JSON.parse(readFileSync(args[0]!, 'utf8')),args[1] ?? ''); result={id:(result as {id:string}).id,state:'draft'}; break;
    case 'review': case 'publish': case 'withdraw':
      if (command === 'publish') {
        if (!process.env.PUBLIC_DATA_ROOT) throw new Error('PUBLIC_DATA_ROOT required for publication validation');
        const holder=new DatasetHolder(process.env.PUBLIC_DATA_ROOT);
        try {
          await holder.reloadAsync(); if (!holder.current) throw new Error('validated dataset unavailable');
          const row=store.db.prepare('SELECT payload FROM pro_content WHERE id=? AND version=?').get(args[0]!,Number(args[1]));
          if (!row) throw new Error('draft not found');
          validateEditorial(contentSchema.parse(JSON.parse(String(row.payload))),holder.current);
        } finally {holder.close();}
      }
      store.transition(args[0]!,Number(args[1]),command,args[2] ?? '',args[3] ?? ''); result={state:command}; break;
    case 'grant': case 'revoke': {
      const user=accounts.db.prepare('SELECT id FROM users WHERE email=?').get(args[0]!) as {id:string}|undefined;
      if (!user) throw new Error('registered user not found');
      store.grant(user.id,Date.parse(args[1]!),Date.parse(args[2]!),args[3] ?? '',args[4] ?? '',command==='revoke'); result={updated:true}; break;
    }
    case 'applications': result=accounts.db.prepare('SELECT u.email,a.scenario,a.created FROM pro_applications a JOIN users u ON u.id=a.userId').all(); break;
    case 'compose': {
      if (!['normal','partial','failed'].includes(args[1] ?? '')) throw new Error('coverage required');
      const queue = args.includes('--queue');
      result={created:store.compose(args[0]!,args[1] as 'normal'|'partial'|'failed',queue)}; break;
    }
    case 'deliver': {
      const mailer=createMailer(); if (!mailer) throw new Error('mail adapter required');
      const origin=process.env.MAAS_ACCOUNT_ORIGIN ?? 'https://daily.maas.click';
      const counts=await deliverPro(store,mailer,origin); result=counts; if (counts.failed || counts.review) process.exitCode=1; break;
    }
    case 'metrics': result=store.metrics(); break;
    case 'audit': result=accounts.db.prepare('SELECT * FROM pro_audit ORDER BY created DESC LIMIT 100').all(); break;
    default: throw new Error('commands: draft FILE ACTOR | review/publish/withdraw ID VERSION ACTOR NOTE | grant/revoke EMAIL START END ACTOR NOTE | applications | compose MONDAY normal/partial/failed [--queue] | deliver | audit');
  }
  process.stdout.write(JSON.stringify(result,null,2)+'\n');
} finally { accounts.close(); }
