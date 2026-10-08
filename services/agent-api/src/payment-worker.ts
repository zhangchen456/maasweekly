import {randomUUID} from 'node:crypto';
import {pathToFileURL} from 'node:url';
import {AccountStore,AccountError} from './account-store.js';
import {AdminStore,type AdminCommand} from './admin-store.js';
import {PaymentStore,type PaymentFact} from './payment-store.js';
import {PaymentSimulator} from './payment-simulator.js';

// Read-only provider lookup. This processor never submits charges, cancellations or refunds.
export interface PaymentLookup {lookup(objectId:string,signal:AbortSignal):Promise<PaymentFact>}
export function migratePaymentWorker(store:PaymentStore){store.admin.accounts.transaction(()=>{
 if(store.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=9').get())return;
 store.db.exec(`CREATE TABLE paid_event_jobs(eventId TEXT PRIMARY KEY REFERENCES paid_events(id),state TEXT NOT NULL,attempts INTEGER NOT NULL DEFAULT 0,fence INTEGER NOT NULL DEFAULT 0,lease INTEGER NOT NULL DEFAULT 0,availableAt INTEGER NOT NULL,version INTEGER NOT NULL DEFAULT 0,error TEXT);
 CREATE INDEX paid_event_jobs_ready ON paid_event_jobs(state,availableAt,eventId);`);
 store.db.prepare('INSERT INTO admin_schema_migrations VALUES(9,?)').run(store.admin.accounts.now());
});}
export class PaymentEventWorker {
 constructor(readonly store:PaymentStore,readonly provider:PaymentLookup,readonly timeoutMs=10000){if(!Number.isSafeInteger(timeoutMs)||timeoutMs<1||timeoutMs>30000)throw Error('invalid lookup timeout');migratePaymentWorker(store);}
 seed(){this.store.db.prepare("INSERT OR IGNORE INTO paid_event_jobs(eventId,state,availableAt) SELECT id,'queued',receivedAt FROM paid_events e WHERE coalesce((SELECT state FROM paid_event_results r WHERE r.eventId=e.id ORDER BY rowid DESC LIMIT 1),'pending')!='processed'").run();}
 claim(){return this.store.admin.accounts.transaction(()=>{
  this.seed();const now=this.store.admin.accounts.now();
  // Only read-only lookup is retried. An expired lease fences out its late result.
  this.store.db.prepare("UPDATE paid_event_jobs SET state=CASE WHEN attempts>=10 THEN 'needs_review' ELSE 'unknown' END,fence=fence+1,version=version+1,lease=0,error='lease_expired',availableAt=? WHERE state='running' AND lease<=?").run(now,now);
  const job=this.store.db.prepare("SELECT j.*,e.payload FROM paid_event_jobs j JOIN paid_events e ON e.id=j.eventId WHERE j.state IN ('queued','unknown') AND j.availableAt<=? AND j.attempts<10 ORDER BY j.availableAt,j.eventId LIMIT 1").get(now);if(!job)return null;
  this.store.db.prepare("UPDATE paid_event_jobs SET state='running',attempts=attempts+1,fence=fence+1,version=version+1,lease=? WHERE eventId=?").run(now+this.timeoutMs+1000,String(job.eventId));
  return {eventId:String(job.eventId),payload:String(job.payload),fence:Number(job.fence)+1,attempts:Number(job.attempts)+1};
 });}
 async once():Promise<{claimed:boolean;processed?:boolean;stale?:boolean;error?:string}>{const job=this.claim();if(!job)return {claimed:false};const eventId=String(job.eventId),controller=new AbortController();let timer:ReturnType<typeof setTimeout>|undefined;
  try{const input=JSON.parse(String(job.payload));if(typeof input.objectId!=='string')throw new AccountError(400,'invalid_event','缺少供应商对象');
   const fact=await Promise.race([this.provider.lookup(input.objectId,controller.signal),new Promise<never>((_,reject)=>{timer=setTimeout(()=>{controller.abort();reject(new AccountError(503,'provider_timeout','供应商核查超时'));},this.timeoutMs);})]);
   return this.store.admin.accounts.transaction(()=>{
    const current=this.store.db.prepare('SELECT * FROM paid_event_jobs WHERE eventId=?').get(eventId);if(current?.state!=='running'||current.fence!==job.fence||Number(current.lease)<=this.store.admin.accounts.now())return {claimed:true,stale:true};
    this.store.processInTransaction(eventId,fact);
    this.store.db.prepare("UPDATE paid_event_jobs SET state='processed',lease=0,error=NULL,version=version+1 WHERE eventId=?").run(eventId);return {claimed:true,processed:true};
   });
  }catch(error){const code=error instanceof AccountError?error.code:'lookup_failed';this.store.admin.accounts.transaction(()=>{const current=this.store.db.prepare('SELECT * FROM paid_event_jobs WHERE eventId=?').get(eventId);if(current?.state!=='running'||current.fence!==job.fence)return;
   this.store.db.prepare('INSERT INTO paid_event_results VALUES(?,?,?,?,?)').run(randomUUID(),eventId,'failed',code,this.store.admin.accounts.now());
   this.store.db.prepare("UPDATE paid_event_jobs SET state=CASE WHEN attempts>=10 OR ? IN ('invalid_event','invalid_payment') THEN 'needs_review' ELSE 'unknown' END,lease=0,fence=fence+1,availableAt=?,version=version+1,error=? WHERE eventId=?").run(code,this.store.admin.accounts.now()+60000,code,eventId);
  });return {claimed:true,processed:false,error:code};}finally{if(timer)clearTimeout(timer);controller.abort();}
 }
 retry(c:AdminCommand){return this.store.admin.command({...c,currentVersion:()=>Number(this.store.db.prepare('SELECT version FROM paid_event_jobs WHERE eventId=?').get(c.targetId)?.version??-1)},['state','version'],['updated','version'],()=>{const row=this.store.db.prepare('SELECT * FROM paid_event_jobs WHERE eventId=?').get(c.targetId);if(!row||!['unknown','needs_review'].includes(String(row.state)))throw new AccountError(409,'not_retryable','仅可重新核查未知/待核查事件');this.store.db.prepare("UPDATE paid_event_jobs SET state='queued',availableAt=?,attempts=0,lease=0,fence=fence+1,version=version+1 WHERE eventId=?").run(this.store.admin.accounts.now(),c.targetId);return {before:{state:String(row.state),version:Number(row.version)},after:{state:'queued',version:Number(row.version)+1},result:{updated:true,version:Number(row.version)+1}};});}
}
export function simulatorLookup(store:PaymentStore):PaymentLookup {const sim=new PaymentSimulator(store);return {lookup:async(id,signal)=>{if(signal.aborted)throw Error('aborted');return sim.lookup(id);}};}
async function main(){if(process.env.MAAS_PAYMENT_MODE!=='simulator'||!process.env.MAAS_ACCOUNT_DB)throw Error('isolated MAAS_PAYMENT_MODE=simulator and MAAS_ACCOUNT_DB required');const a=new AccountStore(process.env.MAAS_ACCOUNT_DB),p=new PaymentStore(new AdminStore(a)),worker=new PaymentEventWorker(p,simulatorLookup(p));let stop=false;process.on('SIGTERM',()=>stop=true);process.on('SIGINT',()=>stop=true);try{do{await worker.once();if(process.argv.includes('--once'))break;await new Promise(r=>setTimeout(r,1000));}while(!stop);}finally{a.close();}}
if(process.argv[1]&&import.meta.url===pathToFileURL(process.argv[1]).href)void main().catch(()=>{process.stderr.write('payment lookup worker unavailable\n');process.exitCode=1;});
