import { currentAccount, onAccountChange, openAccountLogin } from './account-client';
const root = document.querySelector('[data-pro-page]');
if (root) {
  const el = <T extends HTMLElement>(id:string) => document.getElementById(id) as T;
  const text = (id:string,value:string) => { el(id).textContent=value; };
  let generation=0;
  async function api<T=any>(route:string, input?:unknown):Promise<T> {
    const owner=generation;
    const r=await fetch(`/api/pro/${route}`,{credentials:'same-origin',cache:'no-store',...(input===undefined ? {} : {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(input)})});
    let v; try {v=await r.json();} catch {throw new Error('服务暂不可用');} if(owner!==generation)throw new Error('账户状态已更新，请重试'); if (!r.ok) throw new Error(v.message ?? '请求失败'); return v;
  }
  const run=(fn:()=>Promise<void>)=>{void fn().catch(e=>text('pro-status',e.message));};
  function hideReader(){el('pro-catalog').hidden=false;el('pro-reader').hidden=true; el('pro-content').replaceChildren();el('pro-downloads').replaceChildren();}
  function clearSecret(){el('pro-secret').hidden=true;el<HTMLInputElement>('pro-secret-value').value='';}
  function downloads(route:string){el('pro-downloads').replaceChildren();for(const [format,label] of [['markdown','Markdown'],['csv','CSV']]){const a=document.createElement('a');a.href=`/api/pro/${route}?format=${format}`;a.textContent=label!;a.download='';el('pro-downloads').append(a);}}
  function node(tag:string,value:string){const element=document.createElement(tag);element.textContent=value;return element;}
  function table(rows:Record<string,string>[]){if(!rows.length)return;const container=document.createElement('div');container.className='pro-table';const table=document.createElement('table');const keys=[...new Set(rows.flatMap(r=>Object.keys(r)))];const head=document.createElement('tr');for(const key of keys)head.append(node('th',key));table.append(head);for(const row of rows){const tr=document.createElement('tr');for(const key of keys)tr.append(node('td',row[key]??''));table.append(tr);}container.append(table);el('pro-content').append(container);}
  function sources(evidence:any[]){el('pro-content').append(node('h3','证据来源'));for(const e of evidence){const p=document.createElement('p');const a=document.createElement('a');a.href=e.url;a.textContent=`官方来源 · ${new URL(e.url).hostname}`;a.target='_blank';a.rel='noopener noreferrer';p.append(a,node('small',` · ${e.observedAt} · ${e.note}`));if(/^(obs_|ev_)/.test(e.id)){const archive=document.createElement('a');archive.href=`/${e.id.startsWith('obs_')?'item':'evidence'}/${encodeURIComponent(e.id)}/`;archive.textContent=' 查看平台归档';p.append(archive);}el('pro-content').append(p);}}
  function reveal(){el('pro-catalog').hidden=true;el('pro-reader').hidden=false;el('pro-reader').focus();}
  async function readContent(id:string) {
    const version=generation,c=await api(`content/${encodeURIComponent(id)}`);if(version!==generation)return;
    el('pro-content').replaceChildren(node('h1',c.title),node('p',`版本 ${c.version} · 统计 ${c.period.from} — ${c.period.to}`),node('p',`数据截至 ${c.dataThrough} · 覆盖：${c.coverage} · ${c.coverageNote}`));
    for(const paragraph of c.body.split('\n\n'))el('pro-content').append(node('p',paragraph));
    table(c.rows);el('pro-content').append(node('h3','适用条件'),node('p',c.conditions),node('h3','局限'),node('p',c.limitations));sources(c.evidence);if(c.correction)el('pro-content').append(node('h3','更正'),node('p',c.correction));
    downloads(`content/${encodeURIComponent(id)}`);reveal();
  }
  async function readReport(id:string){
    const version=generation,r=await api(`report/${id}`);if(version!==generation)return;
    const topics:Record<string,string>={price:'价格',billing:'计费条件',lifecycle:'生命周期',capability:'服务能力'};
    el('pro-content').replaceChildren(node('h1',`个人简报 ${r.period}`),node('p',`范围快照：${[...r.scope.providers,...r.scope.models,...r.scope.families].join('、')} · ${r.scope.topics.map((t:string)=>topics[t]).join('、')}`),node('p',`覆盖：${r.coverage}`));
    if(!r.items.length)el('pro-content').append(node('p',r.coverage==='normal'?'本期没有匹配的重要变化。':'本期覆盖异常，无法确认是否有变化。'));
    for(const c of r.items){if(c.withdrawn){el('pro-content').append(node('p',`${c.id} 已撤回`));continue;}
      el('pro-content').append(node('h2',c.title),node('p',`版本 ${c.version}${c.selectedVersion!==c.version?'（较本期首次发布已更正）':''}`),node('p',c.preview),node('p',`适用条件：${c.conditions}`),node('p',`局限：${c.limitations}`));
      if(c.correction)el('pro-content').append(node('p','更正：'+c.correction));sources(c.evidence);
      const b=document.createElement('button');b.textContent='阅读完整分析 →';b.onclick=()=>run(()=>readContent(c.id));el('pro-content').append(b);
    }
    downloads(`report/${id}`);reveal();
  }
  async function catalog(){const v=generation,c=await api('catalog');if(v!==generation)return;el('pro-catalog').replaceChildren();if(!c.items.length)text('pro-catalog','首批内容正在审核，发布后会出现在这里。');for(const item of c.items){const div=document.createElement('div');div.className='pro-entry';const small=document.createElement('small');small.textContent=`${({explainer:'变化详解',comparison:'对比专题',briefing:'专业简报'} as Record<string,string>)[item.kind]} · v${item.version}${item.sample ? ' · 完整公开样例' : ''}`;const h=document.createElement('h3');h.textContent=item.title;const p=document.createElement('p');p.textContent=item.preview;const b=document.createElement('button');b.textContent=item.sample?'阅读样例 →':'阅读全文 →';b.onclick=()=>run(()=>readContent(item.id));div.append(small,h,p,b);el('pro-catalog').append(div);}}
  const values=(id:string)=>Array.from(el<HTMLSelectElement>(id).selectedOptions).map(o=>o.value);
  const select=(id:string,values:string[])=>{for(const o of el<HTMLSelectElement>(id).options)o.selected=values.includes(o.value);};
  async function tokenList(){const v=generation,r=await api('tokens');if(v!==generation)return;el('pro-tokens').replaceChildren();for(const t of r.items){const div=document.createElement('div');div.className='pro-token-row';const active=!t.revoked&&t.expires>Date.now();div.textContent=`${t.name} · ${t.purpose} · ${active?'有效':'已失效'}\n到期 ${new Date(t.expires).toLocaleString()}${t.used?' · 最近使用 '+new Date(t.used).toLocaleString():''}`;if(active){const b=document.createElement('button');b.textContent='撤销';b.onclick=()=>run(async()=>{await api('revoke-token',{id:t.id});clearSecret();await tokenList();text('pro-status','凭证已撤销');});div.append(b);}el('pro-tokens').append(div);}}
  onAccountChange(user=>{generation++;hideReader();clearSecret();for(const id of ['pro-settings-panel','pro-token-panel','pro-reports-panel','pro-apply'])el(id).hidden=true;el('pro-login').hidden=Boolean(user);el('pro-reports').replaceChildren();el('pro-tokens').replaceChildren();text('pro-entitlement',user?'正在查询权益…':'登录后查看权益');run(async()=>{await catalog();if(!user)return;const version=generation,p=await api('me');if(version!==generation)return;const active=p.entitlement.status==='active';text('pro-entitlement',p.entitlement.source==='beta'?'Plus 公测免费体验中':`${({active:'专业服务生效中',pending:'等待试点开通',expired:'专业服务已到期',revoked:'专业服务已撤销'} as Record<string,string>)[p.entitlement.status]}${p.entitlement.ends?' · 截至 '+new Date(p.entitlement.ends).toLocaleString():''}`);el('pro-apply').hidden=active||!p.betaAvailable||p.entitlement.status==='revoked';if(p.applied)text('pro-status','试点申请已记录');else text('pro-status',active?'已连接专业服务':'可先阅读公开样例，或免费开启 Plus 公测');el('pro-reports-panel').hidden=false;for(const r of p.reports){const b=document.createElement('button');b.textContent=`${r.period} · ${r.coverage}`;b.onclick=()=>run(()=>readReport(r.id));el('pro-reports').append(b);}if(!p.reports.length)text('pro-reports','尚无已组合的个人简报');if(!active)return;
    const [catalogResponse,statusResponse]=await Promise.all([fetch('/api/v1/models').then(r=>r.json()),fetch('/api/v1/status').then(r=>r.json())]);if(version!==generation)return;
    for(const [id,items,key,label] of [['pro-models',catalogResponse.models,'modelId','modelName'],['pro-families',catalogResponse.families,'familyId','displayName'],['pro-providers',statusResponse.status.providers,'providerId','displayName']] as const){el(id).replaceChildren();for(const item of items??[]){const option=document.createElement('option');option.value=item[key];option.textContent=item[label]??item[key];el(id).append(option);}}
    const s=p.settings?.scope??{providers:[],models:[],families:[],topics:['price','billing']};select('pro-providers',s.providers);select('pro-models',s.models);select('pro-families',s.families);for(const t of document.querySelectorAll<HTMLInputElement>('[name=topic]'))t.checked=s.topics.includes(t.value);el<HTMLInputElement>('pro-email').checked=p.settings?.emailEnabled??false;el<HTMLInputElement>('pro-email').disabled=!p.mailAvailable;el('pro-settings-panel').hidden=false;el('pro-token-panel').hidden=false;await tokenList();const params=new URLSearchParams(location.search);if(params.has('content'))await readContent(params.get('content')!);else if(params.has('report'))await readReport(params.get('report')!);
  });});
  el('pro-login').onclick=openAccountLogin;el('pro-close').onclick=hideReader;el('pro-secret-clear').onclick=clearSecret;
  el('pro-import').onclick=()=>{select('pro-models',currentAccount()?.watches.map(w=>w.modelId)??[]);text('pro-status','已填入关注模型，请检查后保存。邮件设置保持当前选择。');};
  el('pro-apply').onsubmit=e=>{e.preventDefault();run(async()=>{await api('beta',{});location.reload();});};
  el('pro-settings').onsubmit=e=>{e.preventDefault();run(async()=>{const r=await api('settings',{scope:{providers:values('pro-providers'),models:values('pro-models'),families:values('pro-families'),topics:Array.from(document.querySelectorAll<HTMLInputElement>('[name=topic]:checked')).map(t=>t.value)},emailEnabled:el<HTMLInputElement>('pro-email').checked});text('pro-match',`当前已发布内容中匹配 ${r.matching.length} 项`);text('pro-status','范围与专业邮件设置已保存。');});};
  el('pro-token-form').onsubmit=e=>{e.preventDefault();run(async()=>{const purpose=el<HTMLSelectElement>('pro-token-purpose').value,r=await api('token',{name:el<HTMLInputElement>('pro-token-name').value,purpose});el<HTMLInputElement>('pro-secret-value').value=purpose==='rss'?`${location.origin}/api/pro/feed?token=${encodeURIComponent(r.token)}`:r.token;el('pro-secret').hidden=false;await tokenList();text('pro-status',purpose==='rss'?'RSS旧地址已失效，请更新阅读器订阅。':'通用凭证只显示这一次。');});};
  el('pro-rss-copy').onclick=()=>run(async()=>{const r=await api('rss-address');if(!r.url)throw new Error('请先生成私有RSS凭证');el<HTMLInputElement>('pro-secret-value').value=r.url;el('pro-secret').hidden=false;});
  window.addEventListener('pagehide',()=>{hideReader();clearSecret();});
}
