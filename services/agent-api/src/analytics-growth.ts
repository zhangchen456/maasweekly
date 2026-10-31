import type {AdminStore} from './admin-store.js';
import type {AnalyticsRange} from './admin-analytics.js';
const DAY=86400000;
export function growthAnalytics(admin:AdminStore,r:AnalyticsRange,now:number,valueEvent:string) {
 const db=admin.db,start=Number(db.prepare("SELECT created FROM account_value_metadata WHERE key='growth_start'").get()!.created);
 const sql=`WITH activity AS (
  SELECT e.userId,e.created,e.event FROM pro_events e WHERE e.userId IS NOT NULL AND ${valueEvent}
  UNION ALL SELECT userId,created,event FROM account_value_events WHERE event IN ('model_followed','reminder_enabled','comparison_completed','cost_estimate_completed','cost_estimate_completed_v2')
 ), cohort AS (
  SELECT r.userId,r.created,coalesce(c.firstCampaign,'unknown') AS firstCampaign,coalesce(c.lastCampaign,'unknown') AS lastCampaign,
   CASE WHEN r.created+${7*DAY}<=? THEN 1 ELSE 0 END AS mature,
   CASE WHEN CAST((r.created+28800000)/${DAY} AS INTEGER)*${DAY}-28800000+${8*DAY}<=? THEN 1 ELSE 0 END AS day7Eligible,
   (SELECT count(DISTINCT CAST((a.created+28800000)/${DAY} AS INTEGER)) FROM activity a WHERE a.userId=r.userId AND a.created>=r.created AND a.created<r.created+${7*DAY} AND a.created<?) AS activeDays,
   (SELECT a.event FROM activity a WHERE a.userId=r.userId AND a.created>=r.created AND a.created<r.created+${7*DAY} AND a.created<? ORDER BY a.created,a.event LIMIT 1) AS firstEvent,
   CASE WHEN EXISTS(SELECT 1 FROM activity a WHERE a.userId=r.userId AND CAST((a.created+28800000)/${DAY} AS INTEGER)=CAST((r.created+28800000)/${DAY} AS INTEGER)+7 AND a.created<?) THEN 1 ELSE 0 END AS day7Returned
  FROM account_registrations r LEFT JOIN account_registration_campaigns c ON c.userId=r.userId WHERE r.created>=? AND r.created<?
 ) `;
 const args=[now,now,now,now,now,Math.max(start,r.start),r.end];
 const sums=`count(*) AS registered,sum(mature) AS mature,sum(CASE WHEN mature=1 AND activeDays>0 THEN 1 ELSE 0 END) AS used,sum(CASE WHEN mature=1 AND activeDays>=2 THEN 1 ELSE 0 END) AS returned,sum(day7Eligible) AS eligible,sum(CASE WHEN day7Eligible=1 AND day7Returned=1 THEN 1 ELSE 0 END) AS retained`;
 type Counts={registered:number;mature:number;used:number;returned:number;eligible:number;retained:number};
 const total=db.prepare(sql+`SELECT ${sums} FROM cohort`).get(...args) as unknown as Counts;
 const rate=(n:number,d:number)=>d>=5?n/d:null;
 const campaigns=db.prepare(sql+`SELECT firstCampaign,lastCampaign,${sums} FROM cohort GROUP BY firstCampaign,lastCampaign ORDER BY registered DESC,firstCampaign,lastCampaign`).all(...args) as unknown as (Counts&{firstCampaign:string;lastCampaign:string})[];
 const firstActions=db.prepare(sql+`SELECT coalesce(firstEvent,'no_recorded_action') AS event,count(*) AS accounts FROM cohort GROUP BY firstEvent ORDER BY accounts DESC,event`).all(...args) as unknown as {event:string;accounts:number}[];
 return {availability:r.start>=start?'available':'partial',completeSince:new Date(start).toISOString(),firstActions,
  retentionDay7:{numerator:total.retained??0,denominator:total.eligible??0,immature:total.registered-(total.eligible??0),rate:rate(total.retained??0,total.eligible??0)},
  campaigns:campaigns.map(x=>({...x,useRate:rate(x.used,x.mature),returnRate:rate(x.returned,x.used),day7Rate:rate(x.retained,x.eligible)}))};
}
