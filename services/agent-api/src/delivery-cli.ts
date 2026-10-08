import {openSync,readFileSync,closeSync,fstatSync,lstatSync,realpathSync,constants} from 'node:fs';
import {resolve,isAbsolute} from 'node:path';
import {AccountStore} from './account-store.js';
import {AdminStore} from './admin-store.js';
import {AdminMonitor} from './admin-monitor.js';
import {AdminDelivery} from './admin-delivery.js';
import {importReceipt} from './mail-receipt.js';
import {queryMail} from './mail-query.js';
// Fixed private inbox + basename. Never accept an arbitrary path from the web or CLI.
const [command,name,...extra]=process.argv.slice(2),root=process.env.MAAS_DELIVERY_INBOX;
let value:unknown;
if(command==='query'){if(extra.length||!name||!process.env.MAAS_ACCOUNT_DB)throw Error('delivery query JOB_ID requires MAAS_ACCOUNT_DB');}
else {
 if(!['health','receipt','local-receipt'].includes(command??'')||extra.length||!name||!/^[a-zA-Z0-9_-]{1,100}\.json$/.test(name)||!root||!isAbsolute(root)||!process.env.MAAS_ACCOUNT_DB)throw Error('delivery health|receipt BATCH.json requires MAAS_DELIVERY_INBOX and MAAS_ACCOUNT_DB');
 if(lstatSync(root).isSymbolicLink()||realpathSync(root)!==resolve(root))throw Error('inbox must be a real directory');
 const fd=openSync(resolve(root,name),constants.O_RDONLY|constants.O_NOFOLLOW);
 try{const stat=fstatSync(fd);if(!stat.isFile()||stat.size>4*1024*1024)throw Error('invalid report file');const raw=readFileSync(fd);if(raw.length>4*1024*1024)throw Error('report too large');value=JSON.parse(raw.toString());}finally{closeSync(fd);}
}
const accounts=new AccountStore(process.env.MAAS_ACCOUNT_DB!);
try{const admin=new AdminStore(accounts);new AdminMonitor(admin);const delivery=new AdminDelivery(admin);if(command==='local-receipt'&&(process.env.NODE_ENV==='production'||process.env.MAAS_RELEASE_DIR))throw Error('local receipt prohibited in production');console.log(JSON.stringify(command==='query'?await queryMail(delivery,name!,process.env.RESEND_API_KEY??''):command==='health'?delivery.healthImport(value):importReceipt(delivery,value,process.env.MAAS_MAIL_RECEIPT_SECRET??'',command==='local-receipt')));}finally{accounts.close();}
