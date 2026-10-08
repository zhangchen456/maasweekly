import { type ContentPackage, type FrozenInput, type Issue, bad } from './editorial-store.js';
import type { Dataset } from './dataset.js';
import { validateEditorial } from './pro-editorial.js';
export const checklistKeys=['sources','conditions','conclusions','coverage','preview','attribution'] as const;
export function checkPackage(pack:ContentPackage,issue:Issue,inputs:FrozenInput[],ds?:Dataset) {
 const blocking:string[]=[],manual:string[]=['逐项核对关键结论与引用、正文与表格数值、前后比较口径；程序不能证明语义正确'];
 const known=new Map(inputs.map(e=>[e.id,e]));
 for(const c of pack.contents){
  if(c.sample)blocking.push(`${c.id}: 工作台内容不得作为公开样例`);
  if(c.period.from!==issue.windowFrom||c.period.to!==issue.windowTo)blocking.push(`${c.id}: 时间窗口不一致`);
  if(c.coverage!==issue.coverage||c.coverageNote!==issue.coverageNote||c.dataThrough!==issue.dataThrough)blocking.push(`${c.id}: 覆盖与数据截至不一致`);
  if(/<\/?[a-z!]|javascript\s*:|data\s*:/i.test(c.body+' '+c.preview))blocking.push(`${c.id}: 原始HTML或危险链接`);
  for(const e of c.evidence){const frozen=known.get(e.id);if(!frozen||frozen.url!==e.url||frozen.observedAt!==e.observedAt)blocking.push(`${c.id}: 引用不属于冻结快照 ${e.id}`);}
  if(c.models.some(m=>!inputs.some(e=>c.evidence.some(ref=>ref.id===e.id)&&e.modelId===m))||c.families.some(m=>!inputs.some(e=>c.evidence.some(ref=>ref.id===e.id)&&e.familyId===m)))blocking.push(`${c.id}: 模型/系列归属无依据`);
  if(c.providers.some(p=>!inputs.some(e=>c.evidence.some(ref=>ref.id===e.id)&&e.providerId===p)))blocking.push(`${c.id}: 厂商归属无依据`);
  for(const row of c.rows){
   if('amount' in row||'beforeAmount' in row||'afterAmount' in row){
    const e=known.get(row.evidenceId??'');const p=e?.price;
    if(!p)blocking.push(`${c.id}: 价格行缺少结构化证据`);
    else for(const k of ['amount','beforeAmount','afterAmount','currency','unitQuantity','unitName','region','billingMode','serviceTier','contextBand','timeCondition']){
     if((['currency','unitQuantity','unitName','region','billingMode','serviceTier'].includes(k)&&!(k in row))||(k in row&&row[k]!==String(typeof p[k]==='object'?JSON.stringify(p[k]):p[k])))blocking.push(`${c.id}: 价格口径/数值 ${k} 不一致`);
    }
   }
  }
  if(ds)try{validateEditorial(c,ds);for(const e of c.evidence){const current=ds.itemsById.get(e.id);const frozen=known.get(e.id)!;if(current&&current.revision!==frozen.revision)blocking.push(`${c.id}: 当前证据版本变化 ${e.id}`);}}catch{blocking.push(`${c.id}: 当前证据已撤回、缺失或归属不明`);}
 }
 if(!inputs.length)blocking.push('零证据仅能保存期次覆盖说明，不能出版正文');
 return {blocking:[...new Set(blocking)],manual};
}
export function requireChecks(checks:ReturnType<typeof checkPackage>){if(checks.blocking.length)throw bad(checks.blocking.join('；'),'publication_validation',409);}
