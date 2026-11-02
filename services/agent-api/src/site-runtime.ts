/** Same-process SSR bridge: one immutable Dataset per request, no second full load. */
import {getEvidence} from './query.js';
import {currentAccess,historyAllowed,historyCutoff} from './membership.js';
import { AsyncLocalStorage } from 'node:async_hooks';
import type { Dataset } from './dataset.js';
import type { SiteDataStore, PageInputs } from './site-data-store.js';
import { SiteDataError } from './site-data-store.js';

const KEY = Symbol.for('maas.site-data.v1');
export interface SiteRelease {
  datasetVersion:string; dataThrough:string; coverage:Dataset['coverage'];
  changes:Dataset['changes']; prices:Dataset['prices']; weekly:Dataset['weekly'];
  evidence:unknown[]; modelIdentities:Dataset['modelIdentities'];
}
interface Snapshot extends PageInputs { dataset:Dataset; release:SiteRelease }
export interface SiteBridge {
  version:1;
  membership():{tier:string;cutoff:string|null}|null;
  publicationKey():string;
  release():SiteRelease;
  json(name:string,optional?:boolean):unknown;
  projection(name:string):unknown;
  hasItem(id:string):boolean;
  record(id:string):Promise<unknown|null>;
  revisions(id:string):Promise<unknown[]>;
  evidence(id:string):Promise<unknown|null>;
  facts(id:string):Promise<unknown[]>;
  weekly(id:string):unknown|null;
  dailyWeek(id:string):unknown|null;
}
export function isoWeek(date:string) {
  const value=new Date(date+'T00:00:00Z');
  const day=value.getUTCDay()||7;
  value.setUTCDate(value.getUTCDate()+4-day);
  const start=new Date(Date.UTC(value.getUTCFullYear(),0,1));
  return `${value.getUTCFullYear()}-W${String(Math.ceil(((value.getTime()-start.getTime())/86400000+1)/7)).padStart(2,'0')}`;
}
export class SiteRuntime {
  private snapshots=new WeakMap<Dataset,Snapshot>();
  private preparing=new WeakMap<Dataset,Promise<void>>();
  private context=new AsyncLocalStorage<Snapshot>();
  readonly bridge:SiteBridge;
  constructor(private store:Pick<SiteDataStore,'prepare'|'document'|'revisions'|'factsForEvidence'>) {
    this.bridge={version:1,membership:()=>{const a=currentAccess();return a?{tier:a.tier,cutoff:historyCutoff(this.current().dataset.dataThrough,a.tier)}:null;},publicationKey:()=>{const s=this.current();return s.dataset.version+':'+s.inputVersion+':'+s.codeCommit;},release:()=>{const s=this.current();return currentAccess()?{...s.release,changes:s.release.changes.filter(c=>historyAllowed(c.observationDate,s.dataset.dataThrough))}:s.release;},
      json:(name,optional)=>this.json(name,optional),projection:name=>this.projection(name),
      hasItem:id=>this.current().dataset.itemsById.has(id),
      record:async id=>{
        const s=this.current();
        if(!/^(obs|price)_[0-9a-f]{64}$/.test(id)||!s.dataset.itemsById.has(id))return null;
        const value=await this.store.document(s.inputVersion,`data/${id.startsWith('price_')?'price-records':'records'}/${id}.json`);
        if(!value||typeof value!=='object'||(value as {id?:unknown}).id!==id)throw new SiteDataError();
        return value;
      },
      revisions:async id=>{
        const s=this.current();
        if(!s.dataset.itemsById.has(id))return [];
        const rows=await this.store.revisions(s.inputVersion,id,id.startsWith('price_'));
        if(!rows.length)throw new SiteDataError();
        return rows;
      },
      evidence:async id=>{
        const s=this.current();
        if(!/^ev_[0-9a-f]{64}$/.test(id)||!getEvidence(s.dataset,id))return null;
        const value=await this.store.document(s.inputVersion,`data/price-evidence/${id}.json`);
        if(!value||typeof value!=='object'||(value as {id?:unknown}).id!==id)throw new SiteDataError();
        return value;
      },
      facts:async id=>Boolean(getEvidence(this.current().dataset,id))
        ?(await this.store.factsForEvidence(this.current().inputVersion,id)).filter((f:any)=>!currentAccess()||currentAccess()?.tier==='plus'||this.current().dataset.prices.some(p=>p.id===f.version_id)):[],
      weekly:id=>this.current().dataset.weekly.find(row=>row.id===id)??null,
      dailyWeek:id=>this.dailyWeek(id)};
  }
  async prepare(dataset:Dataset) {
    if(this.snapshots.has(dataset))return;
    const existing=this.preparing.get(dataset);if(existing)return existing;
    const job=this.prepareSnapshot(dataset);this.preparing.set(dataset,job);
    try{await job;}finally{this.preparing.delete(dataset);}
  }
  private async prepareSnapshot(dataset:Dataset){
    const inputs=await this.store.prepare(dataset.manifest);
    const release:SiteRelease={datasetVersion:dataset.version,dataThrough:dataset.dataThrough,
      coverage:dataset.coverage,changes:dataset.changes,prices:dataset.prices,weekly:dataset.weekly,
      evidence:[...dataset.evidenceById.values()],modelIdentities:dataset.modelIdentities};
    this.snapshots.set(dataset,{...inputs,dataset,release});
  }
  run<T>(dataset:Dataset,action:()=>T):T {
    const snapshot=this.snapshots.get(dataset);
    if(!snapshot)throw new SiteDataError();
    return this.context.run(snapshot,action);
  }
  install() {
    const globals=globalThis as unknown as Record<symbol,unknown>;
    if(globals[KEY]&&globals[KEY]!==this.bridge)throw new Error('site bridge already installed');
    globals[KEY]=this.bridge;
  }
  uninstall(){const g=globalThis as unknown as Record<symbol,unknown>;if(g[KEY]===this.bridge)delete g[KEY];}
  private current(){const value=this.context.getStore();if(!value)throw new SiteDataError();return value;}
  private json(name:string,optional=false){
    const values=this.current().projections;
    if(values.has(name)){
      const value=values.get(name);if(!currentAccess())return value;
      const allowed=(date:string)=>historyAllowed(date,this.current().dataset.dataThrough);
      if(name.endsWith('/daily_changes.json')){const d=value as {days:{date:string}[]};return {...d,days:d.days.filter(day=>allowed(day.date))};}
      if(name.endsWith('/record-index.json')||name.endsWith('/price-record-index.json'))return (value as {date:string}[]).filter(row=>allowed(row.date));
      if(name.endsWith('/weekly-digest.json'))return (value as {start:string;end:string;week:string}[]).map(w=>allowed(w.start)?w:{week:w.week,start:w.start,end:w.end,days:{},highlights:[],totals:(w as any).totals,indexOnly:true,restricted:true});
      return value;
    }
    if(optional)return null;
    throw new SiteDataError();
  }
  private projection(name:string){
    if(name.startsWith('pricing/')||name.startsWith('leaderboards/'))return this.json('data/derived/'+name);
    if(name==='platform-logos.json')return this.json('data/normalized/platform-logos.json');
    return this.json('site/src/data/'+name);
  }
  private dailyWeek(id:string){
    if(!/^\d{4}-W\d{2}$/.test(id))return null;
    const weeks=this.projection('weekly-digest.json') as {week:string}[];
    const found=weeks.find(w=>w.week===id);if(found)return found;
    const records=this.current().projections.get('site/src/data/record-index.json') as {date:string}[];
    const prices=this.current().projections.get('site/src/data/price-record-index.json') as {date:string}[];
    const matching=records.filter(row=>isoWeek(row.date)===id);
    if(!matching.length&&!prices.some(row=>isoWeek(row.date)===id))return null;
    const [year,week]=id.split('-W');
    const jan4=new Date(Date.UTC(Number(year),0,4));
    const monday=new Date(jan4);monday.setUTCDate(jan4.getUTCDate()-((jan4.getUTCDay()+6)%7)+(Number(week)-1)*7);
    const sunday=new Date(monday);sunday.setUTCDate(monday.getUTCDate()+6);
    return {week:id,start:monday.toISOString().slice(0,10),end:sunday.toISOString().slice(0,10),
      days:{},highlights:[],indexOnly:true,restricted:!historyAllowed(sunday.toISOString().slice(0,10),this.current().dataset.dataThrough),recordCount:matching.length};
  }
}
