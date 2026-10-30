import type {Result} from './admin-analytics-client';
// Quote every cell, retain measured zero, and neutralize spreadsheet formulas.
export function csvCell(value:unknown):string {
 let text=value===null||value===undefined?'':String(value);
 if(/^[\s\u0000-\u001f]*[=+@-]/u.test(text)||/^[\t\r\n]/.test(text))text="'"+text;
 return '"'+text.replace(/"/g,'""')+'"';
}
export function analyticsCsv(result:Result):string {
 const {business:b,website:w,range:r}=result;
 const rows:unknown[][]=[['开始日期','结束日期','时区','业务查询时间','分类','分组','指标','数值','单位','状态','口径说明']];
 const add=(section:string,group:string,metric:string,value:unknown,unit:string,status:string,note='')=>rows.push([r.from,r.to,r.timezone,b.asOf,section,group,metric,value,unit,status,note]);
 add('口径','','业务完整采集起点',b.coverage.completeSince,'ISO时间',b.coverage.availability,'历史不回填；日期范围可能包含未采集时段');
 add('口径','','免费漏斗采集起点',b.freeFunnel.completeSince,'ISO时间',b.freeFunnel.availability,'每个账号观察注册后7天；小于5个分母不显示率；首尾周可能不完整');
 const stats=[['浏览量',w.stats?.pageviews,'次'],['访客',w.stats?.visitors,'Umami去重访客'],['访问会话',w.stats?.visits,'会话']] as const;
 for(const [label,value,unit] of stats)add('网站流量','Umami',label,w.availability==='available'?value:null,unit,w.availability,w.reason??'Umami独立口径，不与站内账号拼接');
 add('网站流量','Umami','最近成功查询',w.lastSuccessAt,'ISO时间',w.availability);
 add('网站流量','Search Console','自动同步',null,'', 'not_configured','当前仅人工核对；本文件不含搜索展现或点击数据');
 for(const [metric,value] of [['新注册',b.registrations.count],['核心使用账号',b.valueUsage.activeAccounts],['核心使用跨日回访账号',b.valueUsage.returningAccounts],['免费公测激活',b.betaActivated],['专业读取次数',b.professionalReads.requests],['专业读取账号',b.professionalReads.accounts],['导出次数',b.exports.requests],['导出账号',b.exports.accounts]] as const)add('业务总览','',metric,value,metric.endsWith('次数')?'次':'账号',b.coverage.availability,'公测激活不是付费；核心使用不代表阅读完成');
 for(const action of b.accountActions.items)add('账号行为',action.event,'成功行为账号',action.accounts,'账号',b.accountActions.availability,'关注或开启提醒的服务端事实');
 const cohort=(group:string,items:Result['business']['freeFunnel']['weekly']|Result['business']['freeFunnel']['items'])=>{
  if(!items.length)add(group,'','队列记录',null,'', 'no_records','没有符合口径的队列，不代表网站没有访问');
  for(const row of items){const key='weekStart' in row?row.weekStart:row.firstSource+' → '+row.lastSource;
   for(const field of ['registered','mature','immature','used','returned'] as const)add(group,key,({registered:'注册',mature:'已满7天',immature:'观察中',used:'已使用',returned:'跨日回访'})[field],row[field],'账号',b.freeFunnel.availability);
   add(group,key,'7天使用率',row.useRate,'比例0至1',row.useRate===null?'insufficient_sample':b.freeFunnel.availability,'分子=已使用；分母=已满7天注册账号');
   add(group,key,'使用后跨日回访率',row.returnRate,'比例0至1',row.returnRate===null?'insufficient_sample':b.freeFunnel.availability,'分子=跨日回访；分母=已使用账号');
  }
 };
 cohort('注册周',b.freeFunnel.weekly);cohort('首次→最近来源',b.freeFunnel.items);
 if(b.growth){
  const g=b.growth;
  add('新增增长指标','','采集起点',g.completeSince,'ISO时间',g.availability,'仅此后新注册账号；首次行为观察注册后7天；对比/估算为浏览器报告，非服务端核验计算');
  for(const x of g.firstActions)add('首次有效行为',x.event,'账号',x.accounts,'账号',g.availability,'相同时刻按事件名排序；无记录不等于未使用');
  const d=g.retentionDay7;
  for(const [key,value] of Object.entries(d))add('第7天留存','',key,value,key==='rate'?'比例0至1':'账号',value===null?'insufficient_sample':g.availability,'注册日为第0天；北京时间第7天使用，整日结束才进入分母；至少5个成熟账号展示比例');
  for(const x of g.campaigns)for(const [key,value] of Object.entries(x))if(!['firstCampaign','lastCampaign'].includes(key))add('推广活动',x.firstCampaign+' → '+x.lastCampaign,key,value,key.endsWith('Rate')?'比例0至1':'账号',value===null?'insufficient_sample':g.availability,'7天使用和第7天留存采用各自成熟分母；unknown含缺失或未配置活动');
 }
 for(const row of b.agents.items){add('API请求',row.channel,'完成请求',row.requests,'请求',b.agents.availability,'不是用户数');add('API请求',row.channel,'HTTP 2xx',row.httpSuccess,'请求',b.agents.availability,'HTTP成功不等于工具业务成功');}
 const h=b.dataHealth.requestCollection;
 add('采集健康','','最近成功写入',h.lastSuccessAt,'ISO时间',h.lastSuccessAt?'observed':'unknown','全部历史记录，不受筛选范围限制');
 add('采集健康','','累计可记录写入失败',h.failures,'次',h.failures?'known_failures':'no_recorded_failures','0不保证绝对完整；数据库不可用时可能无法记录失败');
 add('采集健康','','最近写入失败',h.lastFailureAt,'ISO时间',h.lastFailureAt?'observed':'unknown');
 for(const [key,value] of Object.entries(b.dataHealth.lastRecorded))add('采集健康',key,'最近事件',value,'ISO时间',value?'observed':'unknown','全部历史记录，不受筛选范围限制');
 for(const day of b.dataHealth.requestDays)add('每日请求',new Date(day.day+8*3600000).toISOString().slice(0,10),'完成请求',day.requests,'请求','observed','北京时间整日；只列有记录的日期，不能推断缺失区间');
 return '\ufeff'+rows.map(row=>row.map(csvCell).join(',')).join('\r\n')+'\r\n';
}
