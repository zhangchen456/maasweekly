import { onAccountChange } from '../scripts/account-client';
export class AdminApiError extends Error {
  constructor(readonly status: number, readonly code: string, message: string, readonly requestId: string) {super(message);}
}
export async function adminApi<T>(route: string, input?: Record<string, unknown>, idempotencyKey?: string): Promise<T> {
  const response=await fetch('/api/admin/'+route,{credentials:'same-origin',cache:'no-store',...(input?{method:'POST',headers:{'Content-Type':'application/json','Idempotency-Key':idempotencyKey ?? crypto.randomUUID()},body:JSON.stringify(input)}:{})});
  let value;try{value=await response.json();}catch{throw new AdminApiError(response.status,'unavailable','后台服务暂不可用',response.headers.get('X-Request-ID') ?? '');}
  if(!response.ok) throw new AdminApiError(response.status,value.code,value.message,value.requestId ?? '');
  return value;
}
export interface AdminIdentity {id:string;displayName:string;role:string;capabilities:string[]}
export interface AdminSummary {value:unknown;asOf:string;availability:string}
export interface AdminPage<T> {items:T[];nextCursor:string|null}
export interface AdminAudit {id:string;createdAt:number;actorType:string;actorId:string;action:string;targetType:string;targetId:string;reason:string;requestId:string;before:unknown;after:unknown}
const root=document.querySelector('[data-admin-page]');
if(root) {
  const el=(id:string)=>document.getElementById(id)!;
  const privatePanel=el('admin-private'), status=el('admin-status');let generation=0, nextCursor:string|null=null;
  const clear=()=>{document.dispatchEvent(new CustomEvent('maas:admin-cleared'));privatePanel.hidden=true;el('admin-identity').textContent='';el('admin-overview')?.replaceChildren();el('admin-audit-items')?.replaceChildren();nextCursor=null;if(el('admin-next')) el('admin-next').hidden=true;};
  const error=(e:unknown)=>{clear();status.textContent=e instanceof AdminApiError?(e.status===401?'请使用页面顶部的登录入口登录。':e.status===403?'无后台访问权限':e.status===409?'数据已更新，请重新查询。':e.message)+(e.requestId?`（请求 ${e.requestId}）`:''):'加载失败，请重试。';};
  function filters(){const params=new URLSearchParams();const form=el('admin-audit-filter') as HTMLFormElement|null;if(form)for(const [key,raw] of new FormData(form)){const value=String(raw).trim();if(value)params.set(key,key==='from'||key==='to'?new Date(value).toISOString():value);}return params;}
  async function audit(cursor:string|null=null){const version=++generation;status.textContent='正在加载审计…';try{const params=filters();if(cursor)params.set('cursor',cursor);const page=await adminApi<AdminPage<AdminAudit>>('audit?'+params);if(version!==generation)return;
    const body=el('admin-audit-items');body.replaceChildren();for(const row of page.items){const tr=document.createElement('tr');for(const text of [new Date(row.createdAt).toLocaleString('zh-CN')+'\n'+row.requestId,row.actorType+': '+row.actorId,row.action+'\n'+row.targetType+': '+row.targetId,row.reason,JSON.stringify({before:row.before,after:row.after},null,2)]){const td=document.createElement('td');td.textContent=text;tr.append(td);}body.append(tr);}nextCursor=page.nextCursor;el('admin-next').hidden=!nextCursor;privatePanel.hidden=false;status.textContent=page.items.length?'审计已加载':'没有符合条件的操作记录';
  }catch(e){if(version===generation)error(e);}}
  async function load(){const version=++generation;clear();status.textContent='正在检查后台权限…';try{const me=await adminApi<AdminIdentity>('me');if(version!==generation)return;el('admin-identity').textContent=`${me.displayName} · 管理员`;if(el('admin-overview')){const summary=await adminApi<Record<string,AdminSummary>>('overview');if(version!==generation)return;const labels:Record<string,string>={apiTime:'API 当前时间',datasetVersion:'数据版本',dataThrough:'数据截至',database:'数据库',releaseVersion:'API 发布版本',pendingFeedback:'未完成反馈数量（当前内部阶段非resolved）'};for(const [key,item]of Object.entries(summary)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=labels[key] ?? key;dd.textContent=(item.availability==='not_provided'?'未提供':item.availability==='unavailable'?'暂不可用':item.value===true?'可用':String(item.value))+` · 检查于 ${item.asOf}`;el('admin-overview').append(dt,dd);}privatePanel.hidden=false;status.textContent='后台权限已确认';}else if(el('admin-audit-items')) await audit();else{privatePanel.hidden=false;status.textContent='后台权限已确认';}if(!privatePanel.hidden && (el('admin-audit-items')?version+1===generation:version===generation))document.dispatchEvent(new CustomEvent('maas:admin-ready',{detail:me}));}catch(e){if(version===generation)error(e);}}
  const initialFilters=new URLSearchParams(location.search);for(const key of ['action','targetType','targetId']){const field=document.querySelector<HTMLInputElement>(`#admin-audit-filter [name=${key}]`);if(field&&initialFilters.has(key))field.value=initialFilters.get(key)!;}
  el('admin-retry').addEventListener('click',()=>void load());
  el('admin-audit-filter')?.addEventListener('submit',event=>{event.preventDefault();void audit();});
  el('admin-next')?.addEventListener('click',()=>void audit(nextCursor));
  onAccountChange(()=>void load());
  window.addEventListener('pagehide',()=>{generation++;clear();});
}
