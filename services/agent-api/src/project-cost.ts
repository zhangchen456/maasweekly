/** Deterministic token-cost calculations. Persist decimal strings, never floating-point money. */
import {createHash} from 'node:crypto';
import {AccountError} from './account-store.js';
import type {Dataset,PriceEntity} from './dataset.js';
export const SCALE=10n**12n;
export const canonical=(v:unknown):string=>JSON.stringify(v&&typeof v==='object'?Array.isArray(v)?v.map(x=>JSON.parse(canonical(x))):Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b)).map(([k,x])=>[k,JSON.parse(canonical(x))])):v??null);
export const digest=(v:unknown)=>createHash('sha256').update(canonical(v)).digest('hex');
export function decimal(value:unknown,places=12,max=1000000000000n){
 if(typeof value!=='string'||!new RegExp(`^(0|[1-9][0-9]{0,30})(\\.[0-9]{1,${places}})?$`).test(value))throw new AccountError(400,'invalid_decimal','请输入有效的非负数，月用量最多6位小数');
 const [a,b='']=value.split('.');const result=BigInt(a!)*10n**BigInt(places)+BigInt(b.padEnd(places,'0'));
 if(result>max*10n**BigInt(places))throw new AccountError(400,'invalid_decimal','输入数值超出范围');return result;
}
export const money=(v:bigint)=>`${v<0n?'-':''}${(v<0n?-v:v)/SCALE}.${String((v<0n?-v:v)%SCALE).padStart(12,'0')}`;
const value=(v:string)=>decimal(v,12,10n**30n);
const round=(n:bigint,d:bigint)=>(n+d/2n)/d;
export interface ProjectLineInput {label:string;inputPriceId:string|null;outputPriceId:string|null;inputMillions:string;outputMillions:string}
export interface ProjectInput {name:string;usageNote:string;currency:'USD'|'CNY';fx:string;lines:ProjectLineInput[]}
export interface BoundQuote {identity:Record<string,unknown>;id:string;factKey:string;amount:string;currency:string;unitQuantity:number;observedAt:string;evidenceId:string|null;sourceUrl:string|null}
export interface BaselineLine extends ProjectLineInput {modelId:string;modelName:string;platform:string;input:BoundQuote|null;output:BoundQuote|null}
export interface Baseline {name:string;usageNote:string;currency:'USD'|'CNY';fx:string;lines:BaselineLine[];datasetVersion:string;dataThrough:string;savedAt:number;cost:string}
export interface CostLine {label:string;modelId:string;modelName:string;platform:string;state:'ok'|'stale'|'unmatched'|'ambiguous'|'unsupported';cost:string|null;input:BoundQuote|null;output:BoundQuote|null}
export interface CostSnapshot {datasetVersion:string;dataThrough:string;checkedAt:number;complete:boolean;cost:string;lines:CostLine[];baselineDelta:string|null;previousDelta:string|null;fingerprint:string}
const fields=['providerId','sourceId','platformId','upstreamModelId','availabilityId','modelKey','modelId','component','currency','unitQuantity','unitName','region','billingMode','serviceTier','contextBand','timeCondition'] as const;
export function identity(p:PriceEntity){return Object.fromEntries(fields.map(k=>[k,p[k]??null]));}
export function quote(p:PriceEntity,ds:Dataset):BoundQuote {
 const ev=p.evidenceId?ds.evidenceById.get(p.evidenceId):null;const url=ev?.subpageUrl??ev?.sourceUrl??null;
 return {identity:identity(p),id:p.id,factKey:p.factKey,amount:p.amount,currency:p.currency,unitQuantity:p.unitQuantity,observedAt:p.observedAt,evidenceId:p.evidenceId,sourceUrl:url&&/^https?:\/\//.test(url)?url:null};
}
export function priceState(p:PriceEntity,now:number):CostLine['state'] {
 if(!p.modelId||!['token','tokens'].includes(p.unitName)||!['USD','CNY'].includes(p.currency)||!Number.isSafeInteger(p.unitQuantity)||p.unitQuantity<=0||!['input','output'].includes(p.component))return 'unsupported';
 const observed=Date.parse(p.quality.lastSuccessAt??p.observedAt);
 if(p.evidenceStatus!=='complete')return 'unsupported';
 if(p.quality.state!=='fresh'||!Number.isFinite(observed)||now-observed>72*3600000)return 'stale';
 try{decimal(p.amount);}catch{return 'unsupported';}return 'ok';
}
export function parseProject(value:unknown):ProjectInput {
 const x=value as ProjectInput;if(!x||typeof x!=='object'||Array.isArray(x)||Object.keys(x).some(k=>!['name','usageNote','currency','fx','lines'].includes(k)))throw new AccountError(400,'invalid_project','项目格式不正确');
 if(typeof x.name!=='string'||!x.name.trim()||x.name.length>80||typeof x.usageNote!=='string'||x.usageNote.length>300||!['USD','CNY'].includes(x.currency)||!Array.isArray(x.lines)||x.lines.length<1||x.lines.length>10)throw new AccountError(400,'invalid_project','项目需要名称及1至10条实际用量');
 if(decimal(x.fx,6,1000n)<10000n)throw new AccountError(400,'invalid_fx','汇率范围为0.01至1000');
 for(const line of x.lines){
  if(!line||typeof line!=='object'||Object.keys(line).some(k=>!['label','inputPriceId','outputPriceId','inputMillions','outputMillions'].includes(k))||typeof line.label!=='string'||line.label.length>80||![line.inputPriceId,line.outputPriceId].every(v=>v===null||typeof v==='string'&&v.length<=100))throw new AccountError(400,'invalid_line','用量条目格式不正确');
  const input=decimal(line.inputMillions,6,1000000n),output=decimal(line.outputMillions,6,1000000n);if(input+output===0n)throw new AccountError(400,'empty_usage','每条至少填写一种正数用量');
 }
 return {...x,name:x.name.trim(),lines:x.lines.map(l=>({...l,label:l.label.trim()}))};
}
function amount(q:BoundQuote,tokens:bigint,currency:string,fx:string){
 let cost=round(decimal(q.amount)*tokens,BigInt(q.unitQuantity));const rate=decimal(fx,6,1000n);
 if(q.currency!==currency)cost=q.currency==='USD'?round(cost*rate,1000000n):round(cost*1000000n,rate);return cost;
}
export function bindProject(input:ProjectInput,ds:Dataset,now:number):Baseline {
 const rows=input.lines.map(line=>{
  const read=(id:string|null,component:string,usage:string)=>{if(decimal(usage,6,1000000n)===0n)return null;const p=ds.prices.find(p=>p.id===id&&p.component===component);if(!p||priceState(p,now)!=='ok')throw new AccountError(409,'quote_unavailable','报价缺失、陈旧或不支持，请重新选择');if(ds.prices.filter(v=>canonical(identity(v))===canonical(identity(p))).length!==1)throw new AccountError(409,'ambiguous_quote','所选条件存在多条报价，请先核对');return p;};
  const a=read(line.inputPriceId,'input',line.inputMillions),b=read(line.outputPriceId,'output',line.outputMillions),p=a??b!;
  if(a&&b){const {component:_,...ai}=identity(a),{component:__,...bi}=identity(b);if(canonical(ai)!==canonical(bi))throw new AccountError(400,'incompatible_quote','输入和输出必须使用同一模型、平台及完整计费条件');}
  return {...line,modelId:p.modelId!,modelName:p.modelName??p.modelKey,platform:p.platformId??p.providerId,input:a?quote(a,ds):null,output:b?quote(b,ds):null};
 });
 const baseline:Baseline={...input,lines:rows,datasetVersion:ds.version,dataThrough:ds.dataThrough,savedAt:now,cost:'0.000000000000'};
 baseline.cost=recalculate(baseline,ds,now).cost;return baseline;
}
const priceIndexes=new WeakMap<Dataset,Map<string,PriceEntity[]>>();
export function recalculate(b:Baseline,ds:Dataset,now:number,previous?:CostSnapshot):CostSnapshot {
 let index=priceIndexes.get(ds);if(!index){index=new Map<string,PriceEntity[]>();for(const p of ds.prices){const key=canonical(identity(p));const rows=index.get(key)??[];rows.push(p);index.set(key,rows);}priceIndexes.set(ds,index);}
 const lines=b.lines.map((line:BaselineLine)=>{let state:CostLine['state']='ok';
  const resolve=(bound:BoundQuote|null)=>{if(!bound)return null;const matches=index.get(canonical(bound.identity))??[];if(matches.length!==1){state=matches.length?'ambiguous':'unmatched';return null;}const p=matches[0]!;const next=priceState(p,now);if(next!=='ok')state=next;return quote(p,ds);};
  const a=resolve(line.input),o=resolve(line.output);
  const cost=state==='ok'?money((a?amount(a,decimal(line.inputMillions,6,1000000n),b.currency,b.fx):0n)+(o?amount(o,decimal(line.outputMillions,6,1000000n),b.currency,b.fx):0n)):null;
  return {label:line.label,modelId:line.modelId,modelName:line.modelName,platform:line.platform,state,cost,input:a,output:o} as CostLine;
 });
 const sum=lines.reduce((n,l)=>n+(l.cost?value(l.cost):0n),0n),complete=lines.every(l=>l.state==='ok');
 return {datasetVersion:ds.version,dataThrough:ds.dataThrough,checkedAt:now,complete,cost:money(sum),lines,baselineDelta:complete?money(sum-value(b.cost)):null,previousDelta:complete&&previous?.complete?money(sum-value(previous.cost)):null,
 fingerprint:digest(lines.map(l=>({state:l.state,cost:l.cost,input:l.input?.amount??null,output:l.output?.amount??null})))};
}

export function projectQuotes(ds:Dataset,now:number){
 const groups=new Map<string,PriceEntity[]>();for(const p of ds.prices){if(!p.modelId||!['input','output'].includes(p.component))continue;const {component:_,...condition}=identity(p);const key=canonical(condition);const rows=groups.get(key)??[];rows.push(p);groups.set(key,rows);}
 return [...groups.entries()].map(([key,rows])=>{const p=rows[0]!,a=rows.filter(p=>p.component==='input'),b=rows.filter(p=>p.component==='output');
  const stable=(v:unknown)=>v&&typeof v==='object'?JSON.stringify(Object.fromEntries(Object.entries(v).sort(([a],[b])=>a.localeCompare(b)))):String(v||'');
  return {key:digest(key),modelId:p.modelId,modelName:p.modelName??p.modelKey,provider:p.providerId,platform:p.platformId??p.providerId,modelKey:p.modelKey,
   region:p.region,billingMode:p.billingMode,serviceTier:p.serviceTier,contextBand:p.contextBand,timeCondition:p.timeCondition,currency:p.currency,
   variantKey:JSON.stringify([p.region,p.billingMode,p.serviceTier,stable(p.contextBand),stable(p.timeCondition)]),
   inputPriceId:a.length===1?a[0]!.id:null,outputPriceId:b.length===1?b[0]!.id:null,
   inputAmount:a.length===1?a[0]!.amount:null,outputAmount:b.length===1?b[0]!.amount:null,unitQuantity:p.unitQuantity,
   state:a.length>1||b.length>1?'ambiguous':rows.some(p=>priceState(p,now)!=='ok')?'unavailable':'ok'};
 }).sort((a,b)=>a.modelName.localeCompare(b.modelName)||a.platform.localeCompare(b.platform));
}
