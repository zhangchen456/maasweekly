import {PaymentEventWorker,simulatorLookup} from './payment-worker.js';
import {readFileSync} from 'node:fs';
import {AccountStore} from './account-store.js';
import {AdminStore} from './admin-store.js';
import {PaymentStore} from './payment-store.js';
import {PaymentSimulator} from './payment-simulator.js';
import {reconcilePayments} from './payment-reconciliation.js';
// All simulator inputs must be local files. No secrets, network or live merchant operations.
const [op,arg,outcome]=process.argv.slice(2);
if(!process.env.MAAS_ACCOUNT_DB)throw Error('MAAS_ACCOUNT_DB required; use isolated sandbox DB');
if(process.env.MAAS_PAYMENT_MODE!=='simulator')throw Error('MAAS_PAYMENT_MODE=simulator required; no live support');
const a=new AccountStore(process.env.MAAS_ACCOUNT_DB),p=new PaymentStore(new AdminStore(a)),sim=new PaymentSimulator(p);
try{let result:unknown;switch(op){case 'publish':result=sim.publish(JSON.parse(readFileSync(arg!,'utf8')));break;case 'deliver':result=sim.deliver(arg!);break;case 'recover':result=sim.recover();break;case 'retry-lookup':{const worker=new PaymentEventWorker(p,simulatorLookup(p));worker.seed();const [actor,reason,version,key]=process.argv.slice(4);if(!actor||!reason||!version||!key)throw Error('retry-lookup EVENT_ID ACTOR REASON EXPECTED_VERSION KEY required');result=worker.retry({actor:{type:'cli',id:actor},action:'payments.retry-lookup',targetType:'payment_event',targetId:arg!,reason,requestId:crypto.randomUUID(),idempotencyKey:key,expectedVersion:Number(version),input:{}});break;}case 'refund-result':if(!['succeeded','failed'].includes(outcome!))throw Error('succeeded|failed required');sim.completeRefund(arg!,outcome as 'succeeded'|'failed');result={updated:true};break;case 'reconcile':result=reconcilePayments(p,JSON.parse(readFileSync(arg!,'utf8')));break;default:throw Error('publish FILE | deliver ID | recover | refund-result ID succeeded|failed | reconcile FILE');}process.stdout.write(JSON.stringify(result)+'\n');}finally{a.close();}
