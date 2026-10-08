import {migratePaymentWorker} from './payment-worker.js';
import {randomUUID} from 'node:crypto';
import {AdminStore,type AdminCommand} from './admin-store.js';
import {PaymentStore,checkedMinorTotal} from './payment-store.js';
import {query,page,invalid,timestamp,adminText} from './admin-operations.js';
export class AdminPayments {
 readonly payments:PaymentStore;
 constructor(readonly admin:AdminStore){this.payments=new PaymentStore(admin);migratePaymentWorker(this.payments);}
 list(kind:string,params:URLSearchParams){
  const tables:Record<string,string>={orders:'paid_orders',subscriptions:'paid_subscriptions',refunds:'paid_refunds',differences:'paid_differences',events:'paid_events',reconciliations:'paid_reconciliations'};
  const table=tables[kind];if(!table)throw invalid('支付对象无效');query(params,['q','currency','userId','from','to']);
  const where:string[]=[],args:(string|number)[]=[];
  if(params.has('q')){const q=adminText(params.get('q'),'对象ID',200);where.push('id=?');args.push(q);}
  if(params.has('currency')){const c=params.get('currency')!;if(!['orders','refunds','reconciliations'].includes(kind)||! /^[A-Z]{3}$/.test(c))throw invalid('币种筛选无效');where.push('currency=?');args.push(c);}
  if(params.has('userId')){if(!['orders','subscriptions','refunds'].includes(kind))throw invalid('该对象不支持用户筛选');where.push(kind==='refunds'?'orderId IN (SELECT id FROM paid_orders WHERE userId=?)':'userId=?');args.push(adminText(params.get('userId'),'用户ID'));}
  for(const k of ['from','to'])if(params.has(k)){if(kind==='differences')throw invalid('差异不支持时间筛选');where.push((kind==='events'?'receivedAt':'createdAt')+(k==='from'?'>=':'<')+'?');args.push(timestamp(params.get(k)!));}
  if(params.has('from')&&params.has('to')&&timestamp(params.get('from')!)>=timestamp(params.get('to')!))throw invalid('时间范围无效');
  return page(this.admin,params,'payments:'+kind,`SELECT * FROM ${table} ${where.length?'WHERE '+where.join(' AND '):''}`,args,['id'],r=>{
   if(kind==='orders')return this.payments.orderProjection(String(r.id));
   if(kind==='subscriptions')return this.payments.subscription(String(r.id));
   if(kind==='refunds')return this.payments.refundProjection(String(r.id));
   if(kind==='events'){const {payload,...safe}=r;return {...safe,job:this.admin.db.prepare('SELECT state,attempts,fence,lease,availableAt,version,error FROM paid_event_jobs WHERE eventId=?').get(r.id)??null,results:this.admin.db.prepare('SELECT state,error,createdAt FROM paid_event_results WHERE eventId=? ORDER BY rowid DESC LIMIT 10').all(r.id)};}
   if(kind==='differences')return {...r,currency:this.admin.db.prepare('SELECT currency FROM paid_reconciliations WHERE id=?').get(r.reconciliationId)!.currency,actionCount:this.admin.db.prepare('SELECT count(*) n FROM paid_difference_actions WHERE differenceId=?').get(r.id)!.n};
   return r;
  });
 }
 detail(id:string,kind='orders'){
  const db=this.admin.db;
  if(kind==='orders')return {order:this.payments.orderProjection(id),subscription:this.payments.subscription(String(this.payments.order(id).subscriptionId)),facts:db.prepare('SELECT * FROM paid_facts WHERE orderId=? ORDER BY occurredAt DESC,id DESC LIMIT 100').all(id),attempts:db.prepare('SELECT * FROM paid_attempts WHERE orderId=? ORDER BY createdAt DESC,id DESC LIMIT 100').all(id),refunds:db.prepare('SELECT id FROM paid_refunds WHERE orderId=? ORDER BY createdAt DESC,id DESC LIMIT 100').all(id).map(r=>this.payments.refundProjection(String(r.id))),limit:100};
  if(kind==='subscriptions')return {subscription:this.payments.subscription(id),orders:db.prepare('SELECT id FROM paid_orders WHERE subscriptionId=? ORDER BY createdAt DESC,id DESC LIMIT 100').all(id).map(o=>this.payments.orderProjection(String(o.id))),facts:this.payments.facts(id).slice(-100),limit:100};
  if(kind==='refunds'){const refund=this.payments.refundProjection(id);return {refund,order:this.payments.orderProjection(String(refund.orderId)),results:db.prepare('SELECT * FROM paid_refund_results WHERE refundId=? ORDER BY rowid DESC LIMIT 100').all(id),limit:100};}
  if(kind==='differences'){const difference=db.prepare('SELECT * FROM paid_differences WHERE id=?').get(id);if(!difference)throw invalid('差异不存在');return {difference:{...difference,currency:db.prepare('SELECT currency FROM paid_reconciliations WHERE id=?').get(String(difference.reconciliationId))!.currency,actionCount:db.prepare('SELECT count(*) n FROM paid_difference_actions WHERE differenceId=?').get(id)!.n},reconciliation:db.prepare('SELECT * FROM paid_reconciliations WHERE id=?').get(String(difference.reconciliationId)),actions:this.actions(id,new URLSearchParams())};}
  if(kind==='reconciliations'){const reconciliation=db.prepare('SELECT * FROM paid_reconciliations WHERE id=?').get(id);if(!reconciliation)throw invalid('对账记录不存在');return {reconciliation,summary:this.totals(new URLSearchParams({reconciliationId:id})),records:db.prepare('SELECT * FROM paid_provider_records WHERE reconciliationId=? ORDER BY id LIMIT 100').all(id),differences:db.prepare('SELECT * FROM paid_differences WHERE reconciliationId=? ORDER BY id LIMIT 100').all(id),limit:100};}
  throw invalid('不支持该详情');
 }
 actions(id:string,params:URLSearchParams){query(params,[]);if(!this.admin.db.prepare('SELECT 1 FROM paid_differences WHERE id=?').get(id))throw invalid('差异不存在');return page(this.admin,params,'payment-difference:'+id,'SELECT * FROM paid_difference_actions WHERE differenceId=?',[id],['createdAt','id']);}
 refund(c:AdminCommand){return this.admin.command(c,['id','amount','currency'],['id','state'],()=>{const r=this.payments.refundInTransaction(c.targetId,(typeof c.input.amount==='number'?c.input.amount:NaN),'admin_'+c.actor.id+'_'+c.idempotencyKey);return {before:null,after:{id:String(r.id),amount:Number(r.amount),currency:String(r.currency)},result:{id:String(r.id),state:'pending'}};});}
 annotate(c:AdminCommand){return this.admin.command(c,['id','note'],['updated'],()=>{if(!this.admin.db.prepare('SELECT 1 FROM paid_differences WHERE id=?').get(c.targetId))throw invalid('差异不存在');const note=adminText(c.input.note,'处理记录',1000),id=randomUUID();this.admin.db.prepare('INSERT INTO paid_difference_actions VALUES(?,?,?,?,?)').run(id,c.targetId,c.actor.id,note,this.admin.accounts.now());return {before:null,after:{id,note},result:{updated:true}};});}
 totals(params:URLSearchParams){
  for(const k of params.keys())if(!['currency','from','to','reconciliationId'].includes(k)||params.getAll(k).length!==1)throw invalid('查询参数无效');
  const db=this.admin.db;let currency=params.get('currency')??'USD',from=timestamp(params.get('from')??new Date(this.admin.accounts.now()-28*86400000).toISOString()),to=timestamp(params.get('to')??new Date(this.admin.accounts.now()).toISOString()),reconciliation:Record<string,unknown>|undefined;
  if(params.has('reconciliationId')){if(params.size!==1)throw invalid('对账快照与时间/币种不能混用');reconciliation=db.prepare('SELECT * FROM paid_reconciliations WHERE id=?').get(params.get('reconciliationId')!);if(!reconciliation)throw invalid('对账记录不存在');currency=String(reconciliation.currency);from=Number(reconciliation.starts);to=Number(reconciliation.ends);}
  if(!/^[A-Z]{3}$/.test(currency)||from>=to||to-from>366*86400000)throw invalid('币种或时间范围无效');
  const sum=(kind:string)=>checkedMinorTotal(Number(db.prepare('SELECT coalesce(sum(amount),0) n FROM paid_facts WHERE kind=? AND currency=? AND occurredAt>=? AND occurredAt<?').get(kind,currency,from,to)!.n));
  const provider=(kind:string)=>{if(!reconciliation)return null;const rows=db.prepare('SELECT amount FROM paid_provider_records WHERE reconciliationId=? AND kind=?').all(String(reconciliation.id),kind);return rows.length?rows.reduce((n,r)=>checkedMinorTotal(n+Number(r.amount)),0):null;};
  const orders=db.prepare('SELECT count(*) n,coalesce(sum(amount),0) gross FROM paid_orders WHERE currency=? AND createdAt>=? AND createdAt<?').get(currency,from,to)!;
  return {currency,from,to,orderCount:Number(orders.n),orderGross:checkedMinorTotal(Number(orders.gross)),successfulPaymentCount:Number(db.prepare("SELECT count(*) n FROM paid_facts WHERE kind='paid' AND currency=? AND occurredAt>=? AND occurredAt<?").get(currency,from,to)!.n),revenue:sum('paid'),refunds:sum('refund'),fees:provider('fee'),settlement:provider('settlement'),providerRevenue:provider('paid'),providerRefunds:provider('refund'),settlementAvailability:provider('settlement')===null?'unknown':'recorded',source:reconciliation?String(reconciliation.source):'internal_verified_facts',reconciliationId:reconciliation?.id??null};
 }
}
