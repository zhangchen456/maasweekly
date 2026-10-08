import { AccountStore } from './account-store.js';
import { AdminStore, adminText } from './admin-store.js';
const [command,...args]=process.argv.slice(2);
if(!process.env.MAAS_ACCOUNT_DB) throw new Error('MAAS_ACCOUNT_DB required');
const options:Record<string,string>={};
for(let i=0;i<args.length;i+=2){const key=args[i];if(!key || !['--user-id','--actor','--reason'].includes(key) || !args[i+1] || options[key]) throw new Error('invalid arguments');options[key]=args[i+1]!;}
const accounts=new AccountStore(process.env.MAAS_ACCOUNT_DB);
try {
  const store=new AdminStore(accounts);
  if(command==='list') {if(args.length) throw new Error('list takes no arguments');console.log(JSON.stringify(store.list(),null,2));}
  else if(command==='grant' || command==='revoke') console.log(JSON.stringify(store.setMember(adminText(options['--user-id'],'账号'),command==='grant',adminText(options['--actor'],'运维身份'),adminText(options['--reason'],'原因',1000))));
  else throw new Error('admin grant|revoke --user-id ID --actor OPERATOR --reason REASON | list');
} finally {accounts.close();}
