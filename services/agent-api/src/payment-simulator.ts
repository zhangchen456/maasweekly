import {randomUUID} from 'node:crypto';
import {PaymentStore,paymentFactSchema,type PaymentFact} from './payment-store.js';
import {AccountError} from './account-store.js';
// Explicit local simulator only. This adapter does not call any merchant or payment network.
export class PaymentSimulator {
 constructor(readonly store:PaymentStore){}
 publish(input:unknown){const f=paymentFactSchema.parse(input);const old=this.store.db.prepare('SELECT payload FROM paid_simulator_objects WHERE id=?').get(f.id);const payload=JSON.stringify(f);if(old&&old.payload!==payload)throw new AccountError(409,'simulator_conflict','模拟事实不可修改');this.store.db.prepare('INSERT OR IGNORE INTO paid_simulator_objects VALUES(?,?,?)').run(f.id,payload,this.store.admin.accounts.now());return f;}
 lookup(id:string):PaymentFact {const row=this.store.db.prepare('SELECT payload FROM paid_simulator_objects WHERE id=?').get(id);if(!row)throw new AccountError(503,'provider_unknown','模拟供应商结果未知');return paymentFactSchema.parse(JSON.parse(String(row.payload)));}
 deliver(id:string,eventKey=id){const f=this.lookup(id),event=this.store.receive('simulator',eventKey,Buffer.from(JSON.stringify({objectId:id})));return this.store.process(event,f);}
 recover(){
  const events=this.store.db.prepare("SELECT e.* FROM paid_events e WHERE coalesce((SELECT state FROM paid_event_results r WHERE r.eventId=e.id ORDER BY rowid DESC LIMIT 1),'pending')!='processed' ORDER BY coalesce((SELECT max(createdAt) FROM paid_event_results r WHERE r.eventId=e.id),e.receivedAt),e.id LIMIT 100").all();
  let processed=0,failed=0;
  for(const e of events){let fact:PaymentFact;try{const input=JSON.parse(String(e.payload));fact=this.lookup(input.objectId);}catch(error){this.store.db.prepare('INSERT INTO paid_event_results VALUES(?,?,?,?,?)').run(randomUUID(),String(e.id),'failed',error instanceof AccountError?error.code:'invalid_event',this.store.admin.accounts.now());failed++;continue;}
   try{this.store.process(String(e.id),fact);processed++;}catch{failed++;}
  }
  return {processed,failed};
 }

 action(orderId:string,kind:PaymentFact['kind'],amount=0,objectId?:string) {
  const stable=['cancel','terminate'].includes(kind)?'sim_'+kind+'_'+orderId:undefined;
  const existing=stable?this.store.db.prepare('SELECT id FROM paid_simulator_objects WHERE id=?').get(stable):undefined;
  if(existing)return this.deliver(String(existing.id));
  const o=this.store.order(orderId),now=this.store.admin.accounts.now(),f=this.publish({id:stable??randomUUID(),kind,orderId,subscriptionId:o.subscriptionId,objectId:objectId??stable??randomUUID(),currency:o.currency,amount,starts:now,ends:now+1,occurredAt:now});return this.deliver(f.id);
 }

 completeRefund(id:string,outcome:'succeeded'|'failed'){
  const db=this.store.db,r=db.prepare('SELECT * FROM paid_refunds WHERE id=?').get(id);if(!r)throw new AccountError(404,'not_found','退款不存在');
  const last=db.prepare('SELECT state FROM paid_refund_results WHERE refundId=? ORDER BY rowid DESC LIMIT 1').get(id);if(last?.state==='succeeded'||last?.state==='failed'){if(last.state!==outcome)throw new AccountError(409,'refund_final','退款已终结');return;}
  if(outcome==='succeeded'){const existing=db.prepare("SELECT payload FROM paid_simulator_objects WHERE json_extract(payload,'$.kind')='refund' AND json_extract(payload,'$.objectId')=?").get(id);if(existing)this.deliver(JSON.parse(String(existing.payload)).id);else this.action(String(r.orderId),'refund',Number(r.amount),id);return;}
  if(db.prepare("SELECT 1 FROM paid_simulator_objects WHERE json_extract(payload,'$.kind')='refund' AND json_extract(payload,'$.objectId')=?").get(id))throw new AccountError(409,'refund_final','模拟供应商已有成功退款结果，请恢复核验');
  db.prepare('INSERT INTO paid_refund_results VALUES(?,?,?,?,?)').run(randomUUID(),id,outcome,'simulator_lookup',this.store.admin.accounts.now());
 }
}
