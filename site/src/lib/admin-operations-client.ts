import { adminApi, AdminApiError, type AdminPage } from './admin-client';
type Row=Record<string,any>;
const root=document.querySelector<HTMLElement>('[data-operations]');
if(root){
  const mode=root.dataset.operations!,kind=mode.split('-')[0],detail=mode.endsWith('-detail'),id=new URLSearchParams(location.search).get('id');
  const el=(name:string)=>document.getElementById('ops-'+name)!;let generation=0,authorized=false,version=0,cursor:string|null=null;
  const subCursors:Record<string,string|null>={},pending=new Map<HTMLFormElement,{body:string;key:string}>();
  const clear=()=>{generation++;authorized=false;cursor=null;pending.clear();el('items').replaceChildren();for(const name of ['images','notes','verifications'])el(name)?.replaceChildren();root.querySelectorAll<HTMLFormElement>('form[data-action]').forEach(f=>f.reset());for(const name of ['user-link','feedback-link'])el(name)?.removeAttribute('href');for(const name of Object.keys(subCursors))delete subCursors[name];el('credential')?.querySelector('select')?.replaceChildren();for(const name of ['next','notes-next','verifications-next'])if(el(name))el(name).hidden=true;el('status').textContent='';};
  const error=(e:unknown)=>{if(e instanceof AdminApiError&&(e.status===401||e.status===403)){document.dispatchEvent(new CustomEvent('maas:admin-cleared'));document.getElementById('admin-private')!.hidden=true;}el('status').textContent=e instanceof AdminApiError?(e.status===409?'对象已更新，请重新查询后确认再提交。':e.message)+`（请求 ${e.requestId}）`:'加载失败，请重试。';};
  const labels:Record<string,string>={id:'编号',email:'邮箱',displayName:'昵称',profileCreated:'资料建立时间',profile:'用户资料',effectiveEntitlement:'当前权益',watchCount:'关注数量',status:'状态',source:'生效来源',starts:'开始时间',ends:'结束时间',created:'创建时间',createdAt:'记录时间',updatedAt:'更新时间',checkedAt:'验证时间',expires:'到期时间',used:'最近使用时间',revoked:'撤销标记',enabled:'开启',emailEnabled:'邮件开启',since:'偏好开启时间',emailSince:'邮件开启时间',scope:'关注范围',event:'事件',count:'次数',version:'管理版本',stage:'内部阶段',priority:'优先级',operatorId:'最近处理人',resolutionType:'解决类型',relatedFeedbackId:'关联反馈',feedbackId:'反馈编号',actorId:'操作者',actorType:'操作来源',body:'内部备注',kind:'验证类型',artifactRef:'修复 / 更正 / 依据引用',releaseRef:'发布版本',result:'验证结果',note:'验证说明',name:'凭证名称',purpose:'用途',reason:'操作原因',action:'动作',before:'操作前',after:'操作后',requestId:'请求编号',targetType:'对象类型',targetId:'对象编号',providers:'厂商',models:'模型',families:'模型系列',topics:'主题'};
  function record(target:HTMLElement,data:Row){const dl=document.createElement('dl');dl.className='admin-summary';for(const [key,value]of Object.entries(data)){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=labels[key]??key;
    if(value===null||value===undefined)dd.textContent='未知 / 无';
    else if(Array.isArray(value)){if(!value.length)dd.textContent='无';else for(const item of value){if(item&&typeof item==='object')record(dd,item);else{const line=document.createElement('div');line.textContent=String(item);dd.append(line);}}}
    else if(typeof value==='object')record(dd,value);
    else dd.textContent=typeof value==='number'&&['starts','ends','created','createdAt','updatedAt','checkedAt','expires','used','since','emailSince','profileCreated'].includes(key)?value?new Date(value).toLocaleString('zh-CN'):'未记录':typeof value==='boolean'?value?'是':'否':String(value);
    dl.append(dt,dd);}target.append(dl);}
  function link(target:HTMLElement,text:string,href:string){const a=document.createElement('a');a.textContent=text;a.href=href;target.append(a);}
  function records(name:string,p:AdminPage<Row>,append=false){if(!append)el(name).replaceChildren();for(const row of p.items)record(el(name),row);subCursors[name]=p.nextCursor;el(name+'-next').hidden=!p.nextCursor;}
  function filters(){const params=new URLSearchParams();const form=el('filter') as HTMLFormElement|null;if(form)for(const [key,value]of new FormData(form)){let s=String(value).trim();if(s){if(key==='from'||key==='to')s=new Date(s).toISOString();params.set(key,s);}}return params;}
  async function load(next:string|null=null){if(!authorized)return;const stamp=++generation;el('status').textContent='正在读取…';try{
    if(detail){if(!id)throw Error('缺少对象ID');const row=await adminApi<Row>(`${kind}/${encodeURIComponent(id)}`);if(stamp!==generation)return;el('items').replaceChildren();version=kind==='users'?row.adminVersion:row.ops.version;
      if(kind==='users'){
        record(el('items'),{邮箱:row.email,用户ID:row.id,昵称:row.profile?.displayName??'',资料建立时间:row.profile?.profileCreated?new Date(row.profile.profileCreated).toISOString():null,有效权益:row.effectiveEntitlement,手工记录:row.manual,公测记录:row.beta,公测开放:row.betaAvailable,关注数量:row.watchCount,免费邮件偏好:{enabled:row.emailEnabled,since:row.emailSince},专业邮件偏好:row.professionalEmail,近30天专业事件:row.events,管理版本:version});
        const heading=document.createElement('h2');heading.textContent='管理员操作历史（最近25条）';el('items').append(heading);for(const audit of row.history.items)record(el('items'),audit);if(row.history.nextCursor)link(el('items'),'更多操作历史',`/admin/audit/?targetType=user&targetId=${encodeURIComponent(id)}`);
        el('feedback-link').setAttribute('href','/admin/feedback/?userId='+encodeURIComponent(id));const select=el('credential').querySelector('select')!;select.replaceChildren();for(const credential of row.credentials){record(el('items'),credential);const option=document.createElement('option');option.value=credential.id;option.textContent=`${credential.name} · ${credential.purpose} · ${credential.revoked?'已撤销':'未撤销'} · ${credential.id}`;select.append(option);}
      }else{
        record(el('items'),{标题:row.title,描述:row.description,页面:row.page,用户:row.email,用户ID:row.userId,用户摘要:row.userSummary,公开状态:row.status,公开回复:row.reply,内部处理:row.ops,创建时间:new Date(row.created).toISOString()});
        for(const problem of row.problems??[])link(el('items'),`关联问题：${problem.title} · ${problem.repairStage}`,`/admin/problems/?id=${encodeURIComponent(problem.id)}`);
        el('user-link').setAttribute('href','/admin/users/detail/?id='+encodeURIComponent(row.userId));const form=el('update') as HTMLFormElement;for(const key of ['stage','priority','resolutionType','relatedFeedbackId']){const field=form.elements.namedItem(key) as HTMLInputElement;field.value=row.ops[key]??'';} (form.elements.namedItem('publicReply') as HTMLTextAreaElement).value=row.reply;
        records('notes',row.notes);records('verifications',row.verifications);el('images').replaceChildren();for(let i=0;i<row.imageCount;i++){const image=document.createElement('img');image.src=`/api/admin/feedback/${encodeURIComponent(id)}/images/${i}`;image.alt=`私有截图 ${i+1}`;image.style.maxWidth='100%';el('images').append(image);}
      }
    }else{const params=filters();if(next)params.set('cursor',next);const data=await adminApi<AdminPage<Row>>(kind+'?'+params);if(stamp!==generation)return;el('items').replaceChildren();for(const row of data.items){const article=document.createElement('article');link(article,kind==='users'?row.email:row.title,`/admin/${kind}/detail/?id=${encodeURIComponent(row.id)}`);record(article,kind==='users'?{昵称:row.displayName,资料建立时间:row.profileCreated?new Date(row.profileCreated).toISOString():null,权益:row.effectiveEntitlement,关注数量:row.watchCount}:{用户:row.email,公开状态:row.status,内部阶段:row.stage,优先级:row.priority,更新时间:new Date(row.updatedAt).toISOString()});el('items').append(article);}cursor=data.nextCursor;el('next').hidden=!cursor;}
    el('status').textContent=el('items').children.length?`已加载${detail?' · 管理版本 '+version:''}`:'没有符合条件的结果';
  }catch(e){if(stamp===generation)error(e);}}
  document.addEventListener('maas:admin-cleared',clear);
  document.addEventListener('maas:admin-ready',()=>{authorized=true;void load();});
  const filter=el('filter') as HTMLFormElement|null;if(filter){const params=new URLSearchParams(location.search);for(const [k,v]of params){const field=filter.elements.namedItem(k) as HTMLInputElement|null;if(field)field.value=v;}filter.addEventListener('submit',e=>{e.preventDefault();void load();});}
  el('next')?.addEventListener('click',()=>void load(cursor));
  for(const name of ['notes','verifications'])el(name+'-next')?.addEventListener('click',async()=>{const stamp=generation;try{const p=await adminApi<AdminPage<Row>>(`feedback/${encodeURIComponent(id!)}/${name}?cursor=${encodeURIComponent(subCursors[name]!)}`);if(authorized&&stamp===generation)records(name,p,true);}catch(e){if(stamp===generation)error(e);}});
  root.querySelectorAll<HTMLFormElement>('form[data-action]').forEach(form=>form.addEventListener('submit',async event=>{
    event.preventDefault();if(!authorized||!id)return;const stamp=generation;const input:Row=Object.fromEntries(new FormData(form));let action=form.dataset.action!;
    if(action==='entitlement'&&input.operation==='revoke'){delete input.starts;delete input.ends;}
    if(action==='update'){if(!input.resolutionType)delete input.resolutionType;if(!input.relatedFeedbackId)input.relatedFeedbackId=null;}
    if(action==='credential'){action='tokens/'+encodeURIComponent(input.credentialId)+'/revoke';delete input.credentialId;}
    input.expectedVersion=version;const body=JSON.stringify(input),previous=pending.get(form),key=previous?.body===body?previous.key:crypto.randomUUID();pending.set(form,{body,key});
    const buttons=form.querySelectorAll<HTMLButtonElement>('button');buttons.forEach(b=>b.disabled=true);el('status').textContent='正在提交…';
    try{await adminApi(`${kind}/${encodeURIComponent(id)}/${action}`,input,key);if(stamp!==generation)return;pending.delete(form);await load();if(authorized)el('status').textContent+=' · 操作已提交，以上为服务端最新结果';}catch(e){if(stamp===generation){if(e instanceof AdminApiError&&e.status===409)pending.delete(form);error(e);}}finally{buttons.forEach(b=>b.disabled=false);}
  }));
}
