import { readFileSync } from 'node:fs';
import path from 'node:path';
import { modelRelease } from './model-pages';
import type { WorkspaceData } from './pricing-workspace';

/** Single server-side boundary. Missing optional snapshots differ from malformed inputs. */
export function readPageJson<T>(relative: string, optional = false): T | null {
  const file = path.resolve(process.cwd(), '..', 'data', relative);
  try { return JSON.parse(readFileSync(file, 'utf8')) as T; }
  catch (error) { if (optional && (error as NodeJS.ErrnoException).code === 'ENOENT') return null; throw error; }
}
export function safeJson(value: unknown): string {
  return JSON.stringify(value).replace(/<\//g, '<\\/').replace(/\u2028/g, '\\u2028').replace(/\u2029/g, '\\u2029');
}
interface Logo {id:string;name:string;aliases:string[];file:string}
interface Gpu {gpu:string;hourly_cny:string;monthly_cny:string;use:string;source:string}
interface Chip {vendor:string;metric:string;value:string;note:string;source:string}
const normalize = (name:string) => name.normalize('NFKC').toLocaleLowerCase('en-US').replace(/[\s._/()（）-]+/g, '');
export function pricingPage() {
  const ledger = readPageJson<WorkspaceData>('derived/pricing/ledger.json', true);
  const gpu = readPageJson<{snapshot_date:string;gpu_list:Gpu[]}>('derived/pricing/gpu.json', true);
  const chips = readPageJson<{snapshot_date:string;note:string;chips:Chip[]}>('derived/pricing/chips.json', true);
  const logos = readPageJson<Logo[]>('normalized/platform-logos.json')!;
  const lookup = new Map(logos.flatMap(p => [p.id,p.name,...p.aliases].map(name => [normalize(name),p.file] as const)));
  const data = ledger ? {...ledger, modelIdentities:modelRelease().modelIdentities,
    provider_logos:Object.fromEntries((ledger.providers ?? [...new Set(ledger.prices.map(p=>p.provider))]).flatMap(p=>{
      const file=lookup.get(normalize(p)); return file?[[p,file]]:[];
    }))} : null;
  const ledgerDate = ledger?.meta?.published_at
    ? new Date(ledger.meta.published_at*1000).toLocaleDateString('zh-CN',{month:'2-digit',day:'2-digit'}).replace(/\//g,'.') : '—';
  const modelCount = new Set(ledger?.prices.map(p=>`${p.provider}/${p.model}`)??[]).size;
  const providerCount = ledger?.providers?.length ?? 0;
  const range=(value:string)=> { const numbers=String(value).match(/[\d.]+/g)?.map(Number).filter(Number.isFinite)??[];return {low:numbers[0]??0,high:numbers.at(-1)??numbers[0]??0}; };
  const maxMonthly = Math.max(...(gpu?.gpu_list??[]).map(p=>range(p.monthly_cny).high),1);
  const gpuRows=(gpu?.gpu_list??[]).map(p=>{const r=range(p.monthly_cny);const start=r.low?Math.sqrt(r.low/maxMonthly)*100:0;const end=r.high?Math.sqrt(r.high/maxMonthly)*100:0;return {...p,start,width:Math.max(end-start,r.high?2.2:0)};});
  const groups=new Map<string,{vendor:string;entries:Chip[]}>();
  for (const chip of chips?.chips??[]) { const group=groups.get(chip.vendor)??{vendor:chip.vendor,entries:[]};group.entries.push(chip);groups.set(chip.vendor,group); }
  return {ledger:data,gpu,chips,ledgerDate,modelCount,providerCount,gpuRows,chipGroups:[...groups.values()]};
}

/** Projection is built by AR-03's sole projector before Astro; no independent business writer. */
export function readPageProjection<T>(relative: string): T {
  return JSON.parse(readFileSync(path.resolve(process.cwd(),'src','data',relative),'utf8')) as T;
}
