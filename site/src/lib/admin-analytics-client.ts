import {analyticsCsv} from './admin-analytics-export';
import {adminApi,AdminApiError} from './admin-client';
interface Rate {numerator:number;denominator:number;immature:number;rate:number|null;status:string;availability:string}
interface Coverage {availability:string;completeSince:string}
export interface Result {
 range:{from:string;to:string;timezone:string;end:number};
 website:{availability:string;lastSuccessAt:string|null;reason?:string;stats:{pageviews:number;visitors:number;visits:number}|null;pages:{label:string;count:number}[]|null;sources:{label:string;count:number}[]|null;rankingUnit:string;asOf?:string};
 business:{growth?:Coverage&{firstActions:{event:string;accounts:number}[];retentionDay7:{numerator:number;denominator:number;immature:number;rate:number|null};campaigns:{firstCampaign:string;lastCampaign:string;registered:number;mature:number;used:number;returned:number;eligible:number;retained:number;useRate:number|null;returnRate:number|null;day7Rate:number|null}[]};dataHealth:{asOf:string;requestCollection:{lastSuccessAt:string|null;failures:number;lastFailureAt:string|null};lastRecorded:{registration:string|null;accountAction:string|null;coreUsage:string|null};requestDays:{day:number;requests:number}[]};freeFunnel:Coverage&{windowDays:number;weekly:{weekStart:string;registered:number;mature:number;immature:number;used:number;returned:number;useRate:number|null;returnRate:number|null}[];items:{firstSource:string;lastSource:string;registered:number;mature:number;immature:number;used:number;returned:number;useRate:number|null;returnRate:number|null}[]};accountActions:Coverage&{items:{event:string;requests:number;accounts:number}[]};asOf:string;coverage:Coverage;profilesCreated:number;registrations:Coverage&{count:number;historicalUnknown:number};betaActivated:number;professionalReads:{requests:number;accounts:number};exports:{requests:number;accounts:number};events:{event:string;count:number;accounts:number}[];weekly:{items:{id:string;kind:string;requests:number;readers:number;returningReaders:number}[];truncated:boolean};agents:Coverage&{failures:number;items:{channel:string;requests:number;httpSuccess:number}[]};valueActivation7d:Rate;valueUsage:{activeAccounts:number;returningAccounts:number};activation7d:Rate;retentionWeek4:Rate};
}
const form=document.getElementById('analytics-filter') as HTMLFormElement|null;
if(form){
 const exportButton=document.getElementById('analytics-export') as HTMLButtonElement;
 let exportParams:string|null=null;
 const invalidateExport=()=>{exportParams=null;exportButton.disabled=true;};
 const el=(id:string)=>document.getElementById('analytics-'+id)!;let generation=0,ready=false;
 const time=(s:string|number)=>new Date(s).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai',hour12:false});
 const clear=()=>{generation++;ready=false;invalidateExport();for(const id of ['status','health','website-state','website','pages','sources','coverage','business','weekly','agents','cohorts'])el(id).replaceChildren();};
 const text=(id:string,value:string)=>{el(id).textContent=value;};
 const summary=(id:string,items:[string,string|number][])=>{const list=el(id);list.replaceChildren();for(const [key,value] of items){const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=key;dd.textContent=String(value);list.append(dt,dd);}};
 const table=(id:string,headers:string[],rows:(string|number)[][])=>{const host=el(id);host.replaceChildren();if(!rows.length){host.textContent='该范围内没有记录';return;}const wrap=document.createElement('div');wrap.className='admin-table-wrap';const t=document.createElement('table'),head=document.createElement('thead'),tr=document.createElement('tr');for(const h of headers){const th=document.createElement('th');th.textContent=h;tr.append(th);}head.append(tr);t.append(head);const body=document.createElement('tbody');for(const row of rows){const tr=document.createElement('tr');for(const value of row){const td=document.createElement('td');td.textContent=String(value);tr.append(td);}body.append(tr);}t.append(body);wrap.append(t);host.append(wrap);};
 async function load(){if(!ready)return;const current=++generation;invalidateExport();text('status','正在查询…');try{const data=new FormData(form!),preset=String(data.get('preset')),params=new URLSearchParams({preset});if(preset==='custom'){params.set('from',String(data.get('from')));params.set('to',String(data.get('to')));}const result=await adminApi<Result>('analytics?'+params);if(current!==generation)return;
   const {business:b,website:w,range:r}=result;text('status',`${r.from} 至 ${r.to} · 北京时间 · 数据截至 ${time(r.end)}`);
   text('website-state',w.availability==='available'?`查询成功于 ${time(w.asOf!)} · 排行单位：${w.rankingUnit==='views'?'浏览量':'访客'}`:`不可用（${w.reason==='not_configured'?'未配置服务端统计凭据':w.reason==='busy'?'查询繁忙':'统计查询失败或配置无效'}）· 最近成功：${w.lastSuccessAt?time(w.lastSuccessAt):'尚无成功记录'}`);
   if(w.stats){summary('website',[['浏览量',w.stats.pageviews],['访客（Umami去重口径）',w.stats.visitors],['访问次数（会话）',w.stats.visits]]);table('pages',['页面',w.rankingUnit==='views'?'浏览量':'访客'],w.pages!.map(x=>[x.label,x.count]));table('sources',['来源',w.rankingUnit==='views'?'浏览量':'访客'],w.sources!.map(x=>[x.label,x.count]));}else{for(const id of ['website','pages','sources'])el(id).replaceChildren();}
   el('health').replaceChildren();
   const h=b.dataHealth;
   const healthRows:[string,string|number][]=[['API请求统计最近成功写入',h.requestCollection.lastSuccessAt?time(h.requestCollection.lastSuccessAt):'尚无精确时间记录（新版本起记录）'],['请求统计累计写入失败',h.requestCollection.failures],['最近可记录的写入失败',h.requestCollection.lastFailureAt?time(h.requestCollection.lastFailureAt):'尚无记录'],['最近新注册',h.lastRecorded.registration?time(h.lastRecorded.registration):'尚无记录'],['最近账号行为事件',h.lastRecorded.accountAction?time(h.lastRecorded.accountAction):'尚无记录'],['最近核心使用事件',h.lastRecorded.coreUsage?time(h.lastRecorded.coreUsage):'尚无记录']];
   for(const [label,value] of healthRows){const p=document.createElement('p');p.textContent=label+'：'+value;el('health').append(p);}
   if(h.requestCollection.failures>0){const warning=document.createElement('p');warning.textContent='存在历史采集失败，相关请求汇总可能偏低；后续写入恢复不会清除累计失败记录。';el('health').append(warning);}
   const days=document.createElement('p');days.textContent=h.requestDays.length?`筛选范围内有请求记录的日期：${h.requestDays.map(d=>new Date(d.day+8*3600000).toISOString().slice(0,10)+'（'+d.requests+'次）').join('、')}`:'筛选范围内尚无 API 请求汇总；不能据此推断网站无人访问。';el('health').append(days);
   text('coverage',`${b.coverage.availability==='partial'?'所选范围含历史缺失；下列数字仅为已记录结果。':'完整采集范围内的已记录结果。'} 完整采集开始：${time(b.coverage.completeSince)} · 查询于 ${time(b.asOf)}`);
   summary('business',[['核心使用账号',b.valueUsage.activeAccounts],['核心使用跨日回访账号',b.valueUsage.returningAccounts],['资料建立（非注册）',b.profilesCreated],['已知时间的新注册',b.registrations.count],['历史注册时间未知的账号（当前存量）',b.registrations.historicalUnknown],['公测激活账号',b.betaActivated],['专业内容成功读取次数',b.professionalReads.requests],['专业内容去重读取账号',b.professionalReads.accounts],['专业导出次数',b.exports.requests],['专业导出去重账号',b.exports.accounts],['专业Agent工具成功次数',b.events.find(e=>e.event==='agent_tool_success')?.count??0]]);
   for (const action of b.accountActions.items) { const dt=document.createElement('dt'),dd=document.createElement('dd');dt.textContent=({model_followed:'成功关注模型账号',reminder_enabled:'成功开启提醒账号',comparison_completed:'完成价格对比账号（浏览器报告）',cost_estimate_completed:'完成成本估算账号（浏览器报告）'} as Record<string,string>)[action.event]??action.event;dd.textContent=String(action.accounts);el('business').append(dt,dd); }
   const actionNote=document.createElement('p');actionNote.textContent=`账号行为事件自 ${time(b.accountActions.completeSince)} 开始记录，覆盖：${b.accountActions.availability==='available'?'所选时段':'部分时段'}；关注/提醒重复提交不重复记录；对比/估算为浏览器报告，按账号、事件和北京时间日期去重。`;el('business').append(actionNote);
   table('weekly',['期次 / 内容ID','入口','读取次数','去重读者','跨日回访读者'],b.weekly.items.map(x=>[x.id,x.kind==='briefing'?'正式专业周报':'历史日期周报',x.requests,x.readers,x.returningReaders]));if(b.weekly.truncated){const p=document.createElement('p');p.textContent='仅显示前100项，请缩短日期范围。';el('weekly').append(p);}
   table('agents',['渠道','完成请求','HTTP 2xx'],b.agents.items.map(x=>[({public_api:'公共API',public_mcp:'公共MCP',pro_api:'专业Bearer API',pro_mcp:'专业MCP'} as Record<string,string>)[x.channel]??x.channel,x.requests,x.httpSuccess]));if(b.agents.failures){const p=document.createElement('p');p.textContent=`采集写入失败累计 ${b.agents.failures} 次；请求汇总可能不完整。`;el('agents').append(p);}
   table('cohorts',['队列','分子','成熟分母','未成熟','比例 / 状态'],[['注册后7天核心使用',b.valueActivation7d],['注册后7天公测激活',b.activation7d],['首次已记录专业读取后第4周回访',b.retentionWeek4]].map(([label,raw])=>{const rate=raw as Rate;return [String(label),rate.numerator,rate.denominator,rate.immature,rate.rate===null?(rate.status==='no_denominator'?'分母为0':'样本不足'):(rate.rate*100).toFixed(1)+'%'];}));
   const channels:Record<string,string>={search:'搜索',social:'社交',ai:'AI 助手',referral:'其他外站',campaign:'其他活动',unknown:'直接或未知'};
   const heading=document.createElement('h3');heading.textContent='新注册账号：7天免费使用漏斗';el('cohorts').append(heading);
   const note=document.createElement('p');note.textContent=`自 ${time(b.freeFunnel.completeSince)} 起的新注册账号；首次→最近来源仅为注册时的标签页会话渠道，由客户端提供。使用含关注、提醒开启、正式内容读取/导出和工具成功；回访指7天内至少两个北京时间日期有使用。观察期不足单列，少于5个账号不显示转化率，不含匿名访客和历史来源推测。`;el('cohorts').append(note);
   const weeklyHeading=document.createElement('h3');weeklyHeading.textContent='按注册周比较（北京时间，周一开始）';el('cohorts').append(weeklyHeading);
   const weeklyNote=document.createElement('p');weeklyNote.textContent='每行仅包含筛选日期内注册的账号，首尾周可能不完整；每个账号观察注册后的7天，观察中账号不计入使用率分母。';el('cohorts').append(weeklyNote);
   for(const row of b.freeFunnel.weekly??[]){const p=document.createElement('p');p.textContent=`${row.weekStart} 当周：注册 ${row.registered}，成熟 ${row.mature}，观察中 ${row.immature}；已使用 ${row.used}，跨日回访 ${row.returned}；使用率 ${row.useRate===null?'样本不足':(row.useRate*100).toFixed(1)+'%'}，使用后回访率 ${row.returnRate===null?'样本不足':(row.returnRate*100).toFixed(1)+'%'}`;el('cohorts').append(p);}
   const sourceHeading=document.createElement('h3');sourceHeading.textContent='按注册来源比较';el('cohorts').append(sourceHeading);
   const rows=b.freeFunnel.items;
   if(!rows.length){const empty=document.createElement('p');empty.textContent='尚无新队列记录';el('cohorts').append(empty);}
   for(const row of rows){const p=document.createElement('p');p.textContent=`${channels[row.firstSource]??'未知'} → ${channels[row.lastSource]??'未知'}：注册 ${row.registered}，成熟 ${row.mature}，观察中 ${row.immature}；已使用 ${row.used}，跨日回访 ${row.returned}；使用率 ${row.useRate===null?'样本不足':(row.useRate*100).toFixed(1)+'%'}，使用后回访率 ${row.returnRate===null?'样本不足':(row.returnRate*100).toFixed(1)+'%'}`;el('cohorts').append(p);}
   if(b.growth){
    const g=b.growth,labels:Record<string,string>={model_followed:'关注模型',reminder_enabled:'开启提醒',comparison_completed:'完成价格对比（浏览器报告）',cost_estimate_completed:'完成成本估算（浏览器报告）',content_read:'专业内容读取',report_read:'报告读取',weekly_read:'周报读取',content_export:'内容导出',report_export:'报告导出',agent_tool_success:'Agent工具成功',no_recorded_action:'尚无有效行为记录'};
    const append=(value:string)=>{const p=document.createElement('p');p.textContent=value;el('cohorts').append(p);};
    const heading=document.createElement('h3');heading.textContent='新增增长指标：首次行为、推广活动与第7天留存';el('cohorts').append(heading);
    append(`采集起点：${time(g.completeSince)}；仅含此后新注册账号。首次行为取注册后7天内最早的已记录有效行为；同毫秒按事件名称排序。对比和估算为浏览器报告，账号内每日去重，匿名事件仅在Umami查看。`);
    for(const x of g.firstActions)append(`${labels[x.event]??x.event}：${x.accounts} 个账号`);
    const d=g.retentionDay7;append(`第7天留存：${d.numerator} / ${d.denominator}，${d.rate===null?'样本不足':(d.rate*100).toFixed(1)+'%'}；观察中 ${d.immature}。注册日为第0天，按北京时间第7天有有效行为计算，等待该日完整结束后纳入分母。`);
    for(const x of g.campaigns)append(`推广活动 ${x.firstCampaign} → ${x.lastCampaign}：注册 ${x.registered}，满7天 ${x.mature}，使用 ${x.used}，跨日回访 ${x.returned}；使用率 ${x.useRate===null?'样本不足':(x.useRate*100).toFixed(1)+'%'}；第7天回访 ${x.retained}/${x.eligible}（${x.day7Rate===null?'样本不足':(x.day7Rate*100).toFixed(1)+'%'}）。`);
   }
   exportParams=params.toString();exportButton.disabled=false;
 }catch(e){if(current!==generation)return;for(const id of ['health','website-state','website','pages','sources','coverage','business','weekly','agents','cohorts'])el(id).replaceChildren();if(e instanceof AdminApiError&&(e.status===401||e.status===403)){clear();document.dispatchEvent(new CustomEvent('maas:admin-cleared'));document.getElementById('admin-private')!.hidden=true;}text('status',e instanceof Error?e.message:'查询失败，请重试。');}}
 exportButton.addEventListener('click',async()=>{
  if(!ready||!exportParams)return;
  const params=exportParams,current=generation;exportButton.disabled=true;
  try{
   // Re-query through admin authorization; never download a cached snapshot after revocation.
   const result=await adminApi<Result>('analytics?'+params);
   if(!ready||current!==generation||params!==exportParams)return;
   const url=URL.createObjectURL(new Blob([analyticsCsv(result)],{type:'text/csv;charset=utf-8'}));
   const link=document.createElement('a');link.href=url;link.download=`maas-analytics-${result.range.from}-${result.range.to}.csv`;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
   text('status','已导出重新查询的统计结果；文件包含查询时间、范围及口径说明。');
  }catch(e){if(current!==generation)return;if(e instanceof AdminApiError&&(e.status===401||e.status===403)){clear();document.dispatchEvent(new CustomEvent('maas:admin-cleared'));document.getElementById('admin-private')!.hidden=true;}text('status',e instanceof Error?e.message:'导出失败，请重试。');}
  finally{if(current===generation&&ready&&exportParams)exportButton.disabled=false;}
 });
 form.addEventListener('input',()=>{generation++;invalidateExport();});
 form.addEventListener('submit',e=>{e.preventDefault();void load();});document.addEventListener('maas:admin-ready',()=>{ready=true;void load();});document.addEventListener('maas:admin-cleared',clear);window.addEventListener('pagehide',clear);
 const preset=form.elements.namedItem('preset') as HTMLSelectElement;const toggle=()=>{for(const name of ['from','to']){const input=form.elements.namedItem(name) as HTMLInputElement;input.disabled=preset.value!=='custom';input.required=preset.value==='custom';}};preset.addEventListener('change',toggle);toggle();
}
