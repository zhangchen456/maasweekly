import type { AdminStore } from './admin-store.js';
import type { Dataset } from './dataset.js';
import { hash } from './account-store.js';
import type { Issue } from './editorial-store.js';
/** Read-only T05 association. Never use current global source health for historical issues. */
export function editorialCoverage(admin:AdminStore,issue:Pick<Issue,'windowFrom'|'windowTo'>,ds:Dataset){
 const from=Date.parse(issue.windowFrom),to=Date.parse(issue.windowTo);
 const sourceIds=[...new Set(ds.changes.filter(c=>c.status==='active'&&c.observationDate>=issue.windowFrom.slice(0,10)&&c.observationDate<issue.windowTo.slice(0,10)).map(c=>c.sourceId))].sort();
 const exists=Boolean(admin.db.prepare("SELECT 1 FROM sqlite_master WHERE name='monitor_observations'").get());
 const items:Record<string,unknown>[]=[];
 for(const sourceId of sourceIds){
  if(!exists)continue;
  const rows=admin.db.prepare(`SELECT o.*,r.observedAt,r.inputVersion,r.outputVersion,r.payloadHash FROM monitor_observations o JOIN monitor_runs r ON r.id=o.runId WHERE o.sourceId=? AND o.attemptAt>=? AND o.attemptAt<? AND o.outcome!='not_run' AND (r.inputVersion=? OR r.outputVersion=? OR (coalesce(substr(r.inputVersion,1,3),'')!='ds_' AND coalesce(substr(r.outputVersion,1,3),'')!='ds_')) ORDER BY o.attemptAt DESC,r.observedAt DESC,r.id DESC LIMIT 1`).all(sourceId,from,to,ds.version,ds.version);
  // Explicit public dataset versions must match. Journal/unknown namespaces cannot prove non-relevance.
  const r=rows.find(r=>{const versions=[r.inputVersion,r.outputVersion].filter((v):v is string=>typeof v==='string'&&v.startsWith('ds_'));return !versions.length||versions.includes(ds.version);});
  if(!r)continue;
  const projection=ds.status.sourceStreams.find(s=>s.sourceId===sourceId&&(s.lastAttemptDate===null||s.lastAttemptDate>=issue.windowFrom.slice(0,10)&&s.lastAttemptDate<issue.windowTo.slice(0,10)));
  const limited=['failed','fetch_failed','parse_failed'].includes(String(r.outcome))||['partial','missing'].includes(String(r.coverage));
  items.push({sourceId,runId:r.runId,attemptAt:r.attemptAt,observedAt:r.observedAt,successAt:r.successAt,dataThrough:r.dataThrough,outcome:r.outcome,coverage:r.coverage,errorCode:r.errorCode,inputVersion:r.inputVersion,outputVersion:r.outputVersion,versionRelation:[r.inputVersion,r.outputVersion].includes(ds.version)?'matched':'unknown',projectionState:projection?.state??'absent',projectionConflict:limited&&(!projection||projection.state!=='failing'),limited,payloadHash:r.payloadHash});
 }
 const publicSources=ds.status.sourceStreams.filter(s=>sourceIds.includes(s.sourceId)&&s.lastAttemptDate!==null&&s.lastAttemptDate>=issue.windowFrom.slice(0,10)&&s.lastAttemptDate<issue.windowTo.slice(0,10)).map(s=>({...s})).sort((a,b)=>a.sourceId.localeCompare(b.sourceId));
 const basis={publicSources,datasetVersion:ds.version,windowFrom:issue.windowFrom,windowTo:issue.windowTo,sourceIds,monitorAvailable:exists,items};
 // Table availability alone must not invalidate an issue when no related observation was added.
 const basisHash=hash(JSON.stringify({...basis,monitorAvailable:undefined}));
 return {...basis,basisHash,limited:items.some(i=>i.limited)};
}
