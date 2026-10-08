import type { IncomingMessage, ServerResponse } from 'node:http';
import { AccountError } from './account-store.js';
import type { AdminStore } from './admin-store.js';
const DAY=86400000, OFFSET=8*3600000;
export const beijingDay=(time:number)=>Math.floor((time+OFFSET)/DAY)*DAY-OFFSET;
const invalid=()=>new AccountError(400,'invalid_parameter','日期参数无效；使用北京时间日期，范围最多366天');
export interface AnalyticsRange {start:number;end:number;timezone:'Asia/Shanghai';from:string;to:string}
function date(raw:string) {if(!/^\d{4}-\d{2}-\d{2}$/.test(raw))throw invalid();const n=Date.parse(raw+'T00:00:00+08:00');if(!Number.isFinite(n)||new Date(n+OFFSET).toISOString().slice(0,10)!==raw)throw invalid();return n;}
export function analyticsRange(params:URLSearchParams,now:number):AnalyticsRange {
  for(const key of params.keys())if(!['preset','from','to'].includes(key)||params.getAll(key).length!==1)throw invalid();
  const preset=params.get('preset')??(params.has('from')||params.has('to')?'custom':'7');let start:number,end:number;
  if(preset==='custom'){if(!params.has('from')||!params.has('to'))throw invalid();start=date(params.get('from')!);end=date(params.get('to')!)+DAY;if(end-start>366*DAY||start>=end||start>=now)throw invalid();end=Math.min(end,now);}
  else{if(!['7','28'].includes(preset)||params.has('from')||params.has('to'))throw invalid();end=now;start=beijingDay(now)-(Number(preset)-1)*DAY;}
  return {start,end,timezone:'Asia/Shanghai',from:new Date(start+OFFSET).toISOString().slice(0,10),to:new Date(end-1+OFFSET).toISOString().slice(0,10)};
}
export function migrateAnalytics(admin:AdminStore) {
  admin.accounts.transaction(()=>{
    if(admin.db.prepare('SELECT 1 FROM admin_schema_migrations WHERE version=4').get())return;
    admin.db.exec(`CREATE TABLE account_registrations(userId TEXT PRIMARY KEY REFERENCES users(id),created INTEGER NOT NULL);
      CREATE TABLE analytics_requests(day INTEGER NOT NULL,channel TEXT NOT NULL,status INTEGER NOT NULL,count INTEGER NOT NULL,PRIMARY KEY(day,channel,status));
      CREATE TABLE analytics_health(key TEXT PRIMARY KEY,updated INTEGER NOT NULL,value INTEGER NOT NULL);
      CREATE TABLE analytics_umami_cache(key TEXT PRIMARY KEY,value TEXT NOT NULL,updated INTEGER NOT NULL);
      CREATE INDEX analytics_registration_created ON account_registrations(created);
      CREATE INDEX analytics_profile_created ON account_profiles(created);
      CREATE INDEX analytics_beta_created ON pro_beta_access(created);
      CREATE INDEX analytics_events_kind_time ON pro_events(event,created,userId,target);
      CREATE INDEX analytics_events_target_user ON pro_events(target,event,userId,created);`);
    admin.db.prepare('INSERT INTO analytics_health VALUES(?,?,0)').run('collection_start',admin.accounts.now());
    admin.db.prepare("INSERT INTO analytics_health VALUES('request_failures',?,0)").run(admin.accounts.now());
    admin.db.prepare('INSERT INTO admin_schema_migrations VALUES(4,?)').run(admin.accounts.now());
  });
}
// One finished HTTP request, fixed channel only. No identity, body, query or credential.
export function trackAnalyticsRequest(admin:AdminStore,req:IncomingMessage,res:ServerResponse) {
  const path=(req.url??'').split('?')[0];const channel=path==='/api/mcp'?'public_mcp':path==='/api/pro/mcp'?'pro_mcp':path?.startsWith('/api/v1/')?'public_api':path?.startsWith('/api/pro/')&&Boolean(req.headers.authorization)?'pro_api':null;
  if(!channel)return;
  res.once('finish',()=>{try {admin.db.prepare('INSERT INTO analytics_requests VALUES(?,?,?,1) ON CONFLICT(day,channel,status) DO UPDATE SET count=count+1').run(beijingDay(admin.accounts.now()),channel,res.statusCode);}
    catch{try{admin.db.prepare("UPDATE analytics_health SET value=value+1,updated=? WHERE key='request_failures'").run(admin.accounts.now());}catch{/* cannot report a failed database through itself */}}});
}
const EXPORTS="(event='report_export' OR (event='content_export' AND NOT EXISTS(SELECT 1 FROM pro_content c WHERE c.id=target AND json_extract(c.payload,'$.sample')=1)))";
const READS="('content_read','report_read','weekly_read')";
export function analyticsBusiness(admin:AdminStore,r:AnalyticsRange,now:number) {
  const db=admin.db,start=Number(db.prepare("SELECT updated FROM analytics_health WHERE key='collection_start'").get()!.updated);
  const count=(sql:string,...args:(string|number)[])=>Number(db.prepare(sql).get(...args)?.n??0);
  const coverage=(from:number)=>({availability:r.start>=from?'available':'partial',completeSince:new Date(from).toISOString()});
  const events=db.prepare(`SELECT event,count(*) AS count,count(DISTINCT userId) AS accounts FROM pro_events WHERE created>=? AND created<? AND event IN ('content_read','report_read','weekly_read','content_export','report_export','sample_read','agent_tool_success') AND (event!='content_export' OR NOT EXISTS(SELECT 1 FROM pro_content c WHERE c.id=target AND json_extract(c.payload,'$.sample')=1)) GROUP BY event ORDER BY event`).all(r.start,r.end);
  const weekly=db.prepare(`WITH targets AS (
    SELECT DISTINCT target AS id,CASE WHEN event='weekly_read' THEN 'legacy_weekly' ELSE 'briefing' END AS kind FROM pro_events WHERE created>=? AND created<? AND userId IS NOT NULL AND (event='weekly_read' OR (event='content_read' AND EXISTS(SELECT 1 FROM pro_content c WHERE c.id=target AND json_extract(c.payload,'$.kind')='briefing' AND json_extract(c.payload,'$.sample')=0)))
    UNION SELECT DISTINCT id,'briefing' FROM pro_content WHERE published>=? AND published<? AND json_extract(payload,'$.kind')='briefing' AND json_extract(payload,'$.sample')=0
  ) SELECT t.id,t.kind,count(e.userId) AS requests,count(DISTINCT e.userId) AS readers FROM targets t LEFT JOIN pro_events e ON e.target=t.id AND e.event=CASE WHEN t.kind='legacy_weekly' THEN 'weekly_read' ELSE 'content_read' END AND e.created>=? AND e.created<? AND e.userId IS NOT NULL GROUP BY t.id,t.kind ORDER BY readers DESC,t.id LIMIT 101`).all(r.start,r.end,r.start,r.end,r.start,r.end) as unknown as {id:string;kind:string;requests:number;readers:number}[];
  const weeklyItems=weekly.slice(0,100).map(row=>({...row,returningReaders:count(`SELECT count(*) AS n FROM (SELECT userId FROM pro_events WHERE target=? AND event=? AND userId IS NOT NULL AND created>=? AND created<? GROUP BY userId HAVING count(DISTINCT CAST((created+28800000)/86400000 AS INTEGER))>=2)`,String(row.id),row.kind==='legacy_weekly'?'weekly_read':'content_read',r.start,r.end)}));
  const rate=(numerator:number,denominator:number,immature:number)=>({numerator,denominator,immature,minimumSample:5,rate:denominator>=5?numerator/denominator:null,status:denominator===0?'no_denominator':denominator<5?'insufficient_sample':'available'});
  const matureEnd=Math.min(r.end,now-7*DAY+1);
  const registered=count('SELECT count(*) AS n FROM account_registrations WHERE created>=? AND created<?',r.start,r.end);
  const denominator=count('SELECT count(*) AS n FROM account_registrations WHERE created>=? AND created<?',r.start,matureEnd);
  const activated=count('SELECT count(*) AS n FROM account_registrations r JOIN pro_beta_access b ON b.userId=r.userId WHERE r.created>=? AND r.created<? AND b.created>=r.created AND b.created<r.created+?',r.start,matureEnd,7*DAY);
  const first=`WITH first AS (SELECT userId,min(created) AS firstAt FROM pro_events WHERE event IN ${READS} AND userId IS NOT NULL GROUP BY userId) `;
  const cohortStart=Math.max(r.start,start),retentionEnd=Math.min(r.end,now-28*DAY+1);
  const readers=count(first+'SELECT count(*) AS n FROM first WHERE firstAt>=? AND firstAt<?',cohortStart,r.end);
  const matured=count(first+'SELECT count(*) AS n FROM first WHERE firstAt>=? AND firstAt<?',cohortStart,retentionEnd);
  const returned=count(first+`SELECT count(*) AS n FROM first f WHERE firstAt>=? AND firstAt<? AND EXISTS(SELECT 1 FROM pro_events e WHERE e.userId=f.userId AND e.event IN ${READS} AND e.created>=f.firstAt+? AND e.created<f.firstAt+?)`,cohortStart,retentionEnd,21*DAY,28*DAY);
  return {asOf:new Date(now).toISOString(),coverage:coverage(start),profilesCreated:count('SELECT count(*) AS n FROM account_profiles WHERE created>=? AND created<?',r.start,r.end),registrations:{count:registered,...coverage(start),historicalUnknown:count('SELECT count(*) AS n FROM users WHERE id NOT IN (SELECT userId FROM account_registrations)')},betaActivated:count('SELECT count(*) AS n FROM pro_beta_access WHERE created>=? AND created<?',r.start,r.end),professionalReads:{requests:count(`SELECT count(*) AS n FROM pro_events WHERE event IN ${READS} AND created>=? AND created<?`,r.start,r.end),accounts:count(`SELECT count(DISTINCT userId) AS n FROM pro_events WHERE event IN ${READS} AND created>=? AND created<?`,r.start,r.end)},exports:{requests:count(`SELECT count(*) AS n FROM pro_events WHERE ${EXPORTS} AND created>=? AND created<?`,r.start,r.end),accounts:count(`SELECT count(DISTINCT userId) AS n FROM pro_events WHERE ${EXPORTS} AND created>=? AND created<?`,r.start,r.end)},events,weekly:{items:weeklyItems,truncated:weekly.length>100},agents:{...coverage(start),failures:Number(db.prepare("SELECT value FROM analytics_health WHERE key='request_failures'").get()?.value??0),items:db.prepare('SELECT channel,sum(count) AS requests,sum(CASE WHEN status>=200 AND status<300 THEN count ELSE 0 END) AS httpSuccess FROM analytics_requests WHERE day>=? AND day<? GROUP BY channel ORDER BY channel').all(r.start,r.end)},activation7d:{...rate(activated,denominator,registered-denominator),...coverage(start)},retentionWeek4:{...rate(returned,matured,readers-matured),...coverage(start)}};
}
