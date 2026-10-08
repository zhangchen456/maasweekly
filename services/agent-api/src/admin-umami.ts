import type { AdminStore } from './admin-store.js';
import type { AnalyticsRange } from './admin-analytics.js';
interface UmamiConfig {endpoint:string;websiteId:string;token:string;version:'v2'|'v3'}
export function umamiConfig():UmamiConfig|null {
  const token=process.env.MAAS_UMAMI_TOKEN;if(!token)return null;
  const endpoint=process.env.MAAS_UMAMI_ENDPOINT??'https://api.umami.is/v1/us',websiteId=process.env.MAAS_UMAMI_WEBSITE_ID??'4f0172a2-5aea-48cf-bb38-22eb86368fea',version=process.env.MAAS_UMAMI_VERSION??'v3';
  const url=new URL(endpoint);if((url.protocol!=='https:'&&!(url.protocol==='http:'&&['localhost','127.0.0.1'].includes(url.hostname)))||url.username||url.password||url.search||url.hash||!/^[-a-zA-Z0-9]{1,100}$/.test(websiteId)||!['v2','v3'].includes(version))throw Error('invalid Umami configuration');
  return {endpoint:endpoint.replace(/\/$/,''),websiteId,token,version:version as 'v2'|'v3'};
}
function number(v:unknown) {if(typeof v!=='number'||!Number.isSafeInteger(v)||v<0)throw Error('invalid stats');return v;}
function label(v:unknown) {if(v===null||v==='')return 'Direct / 未识别来源';if(typeof v!=='string'||v.length>4096)throw Error('invalid metric');try{const url=new URL(v);return (url.hostname+url.pathname).slice(0,300);}catch{return v.split(/[?#]/)[0]!.slice(0,300);}}
export class AdminUmami {
  private starts:number[]=[];
  private pending=new Map<string,Promise<unknown>>();
  constructor(private admin:AdminStore,private config:UmamiConfig|null=umamiConfig(),private fetcher:typeof fetch=fetch) {}
  async query(r:AnalyticsRange) {
    const key=JSON.stringify([this.config?.endpoint,this.config?.websiteId,this.config?.version,r.start,r.end]);
    // Current-day queries normalize end to a minute for cache/single-flight purposes.
    const cacheKey=JSON.stringify([this.config?.endpoint,this.config?.websiteId,this.config?.version,r.start,Math.floor(r.end/60000)]);
    const cached=this.admin.db.prepare('SELECT value,updated FROM analytics_umami_cache WHERE key=?').get(cacheKey);
    if(cached&&this.admin.accounts.now()-Number(cached.updated)<60000)return JSON.parse(String(cached.value));
    const existing=this.pending.get(cacheKey);if(existing)return existing;
    // Bound concurrent external ranges; admin rate limit alone allows bursts.
    const now=this.admin.accounts.now();this.starts=this.starts.filter(t=>t>now-15000);
    if(this.pending.size>=4||this.starts.length>=10)return this.unavailable('busy');
    this.starts.push(now);
    const promise=this.load(r,cacheKey);this.pending.set(cacheKey,promise);
    try{return await promise;}finally{this.pending.delete(cacheKey);}
  }
  private unavailable(reason:string) {const success=this.admin.db.prepare("SELECT updated FROM analytics_health WHERE key='umami_success'").get();return {availability:'unavailable',reason,lastSuccessAt:success?new Date(Number(success.updated)).toISOString():null,stats:null,pages:null,sources:null};}
  private async load(r:AnalyticsRange,key:string) {
    if(!this.config)return this.unavailable('not_configured');
    try {
      const c=this.config;
      const get=async(route:string)=>{const url=new URL(`${c.endpoint}/websites/${c.websiteId}/${route}`);url.searchParams.set('startAt',String(r.start));url.searchParams.set('endAt',String(r.end-1));url.searchParams.set('timezone','Asia/Shanghai');
        const response=await this.fetcher(url,{headers:{Authorization:'Bearer '+c.token,Accept:'application/json'},signal:AbortSignal.timeout(4000),redirect:'error'});
        if(!response.ok)throw Error('external unavailable');const reader=response.body?.getReader();if(!reader)throw Error();let size=0;const chunks:Uint8Array[]=[];try{for(;;){const {done,value}=await reader.read();if(done)break;size+=value.length;if(size>131072)throw Error('oversize');chunks.push(value);}}finally{await reader.cancel();}return JSON.parse(Buffer.concat(chunks).toString());};
      const results=await Promise.allSettled([get('stats'),get('metrics?type='+(c.version==='v3'?'path':'url')+'&limit=20'),get('metrics?type=referrer&limit=20')]);
      if(results.some(r=>r.status==='rejected'))throw Error('external unavailable');
      const [stats,pages,sources]=results.map(r=>r.status==='fulfilled'?r.value:null);
      const rows=(raw:unknown)=>{if(!Array.isArray(raw)||raw.length>20)throw Error('invalid metrics');return raw.map(row=>({label:label(row.x),count:number(row.y)}));};
      const now=this.admin.accounts.now(),value={availability:'available',lastSuccessAt:new Date(now).toISOString(),asOf:new Date(now).toISOString(),rankingUnit:c.version==='v3'?'views':'visitors',stats:{pageviews:number(stats?.pageviews?.value),visitors:number(stats?.visitors?.value),visits:number(stats?.visits?.value)},pages:rows(pages),sources:rows(sources),limit:20};
      this.admin.accounts.transaction(()=>{this.admin.db.prepare("INSERT INTO analytics_health VALUES('umami_success',?,0) ON CONFLICT(key) DO UPDATE SET updated=excluded.updated").run(now);this.admin.db.prepare('INSERT OR REPLACE INTO analytics_umami_cache VALUES(?,?,?)').run(key,JSON.stringify(value),now);this.admin.db.exec('DELETE FROM analytics_umami_cache WHERE key NOT IN (SELECT key FROM analytics_umami_cache ORDER BY updated DESC LIMIT 32)');});return value;
    }catch{return this.unavailable('query_failed');}
  }
}
