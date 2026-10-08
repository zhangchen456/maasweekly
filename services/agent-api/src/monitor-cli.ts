import {openSync,readFileSync,closeSync,fstatSync,lstatSync,realpathSync,constants} from 'node:fs';
import {resolve,isAbsolute} from 'node:path';
import {AccountStore} from './account-store.js';
import {AdminStore} from './admin-store.js';
import {AdminMonitor} from './admin-monitor.js';
// Fixed private inbox + basename. Never accept an arbitrary path from the web or CLI.
const [command,name,...extra]=process.argv.slice(2),root=process.env.MAAS_MONITOR_INBOX;
if(command!=='import'||extra.length||!name||!/^[a-zA-Z0-9_-]{1,100}\.json$/.test(name)||!root||!isAbsolute(root)||!process.env.MAAS_ACCOUNT_DB)throw Error('monitor import BATCH.json requires MAAS_MONITOR_INBOX and MAAS_ACCOUNT_DB');
if(lstatSync(root).isSymbolicLink()||realpathSync(root)!==resolve(root))throw Error('inbox must be a real directory');
const fd=openSync(resolve(root,name),constants.O_RDONLY|constants.O_NOFOLLOW);
let value:unknown;try{const stat=fstatSync(fd);if(!stat.isFile()||stat.size>4*1024*1024)throw Error('invalid report file');const raw=readFileSync(fd);if(raw.length>4*1024*1024)throw Error('report too large');value=JSON.parse(raw.toString());}finally{closeSync(fd);}
const accounts=new AccountStore(process.env.MAAS_ACCOUNT_DB);
try{console.log(JSON.stringify(new AdminMonitor(new AdminStore(accounts)).ingest(value)));}finally{accounts.close();}
