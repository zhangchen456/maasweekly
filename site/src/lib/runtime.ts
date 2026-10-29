import type { PublicRelease } from './release';
/** Installed by the API process. Reads are pinned by AsyncLocalStorage per request. */
export interface SiteBridge {
  version:1;
  release():PublicRelease;
  json(name:string,optional?:boolean):unknown;
  projection(name:string):unknown;
  hasItem(id:string):boolean;
  record(id:string):Promise<any|null>;
  revisions(id:string):Promise<any[]>;
  evidence(id:string):Promise<any|null>;
  facts(id:string):Promise<any[]>;
  weekly(id:string):any|null;
  dailyWeek(id:string):any|null;
}
export function siteRuntime():SiteBridge|undefined {
  return (globalThis as unknown as Record<symbol,SiteBridge>)[Symbol.for('maas.site-data.v1')];
}
export function runtimeReports() {
  const bridge=siteRuntime();
  if(!bridge)return undefined;
  const today=new Date().toISOString().slice(0,10);
  return (bridge.release().weekly??[]).filter(r=>r.date<=today)
    .map(r=>({id:r.id,data:{title:r.title,date:r.date,period:r.period}}))
    .sort((a,b)=>b.data.date.localeCompare(a.data.date));
}
