import { siteRuntime } from './runtime.ts';
import { modelIndex, translatedModels } from './model-pages';
import { priceGuides } from './price-guides';
import { canonicalUrl } from './seo';
const SIZE=45000;
const xml=(s:string)=>s.replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;').replaceAll('"','&quot;');
export function sitemapUrls(){
  const runtime=siteRuntime();if(!runtime)throw new Error('runtime sitemap requires pinned inputs');
  const release=runtime.release();
  const routes=new Set<string>();
  const add=(route:string)=>{routes.add(canonicalUrl(route));routes.add(canonicalUrl('/en'+(route==='/'?'/':route)));};
  for(const route of ['/','/models/','/pricing/','/compare/','/guides/','/leaderboards/','/changes/','/weekly/','/agent/','/method/','/about/','/terms/','/privacy/','/aup/'])add(route);
  for(const guide of priceGuides)add('/guides/'+guide.slug+'/');
  for(const report of release.weekly??[])add('/weekly/'+report.id+'/');
  const weeks=new Set((runtime.projection('weekly-digest.json') as {week:string}[]).map(w=>w.week));
  const weekOf=(date:string)=>{
    const d=new Date(date+'T00:00:00Z');d.setUTCDate(d.getUTCDate()+4-(d.getUTCDay()||7));
    const year=d.getUTCFullYear();return year+'-W'+String(Math.ceil(((d.getTime()-Date.UTC(year,0,1))/86400000+1)/7)).padStart(2,'0');
  };
  for(const name of ['record-index.json','price-record-index.json'])for(const row of runtime.projection(name) as {date:string}[])weeks.add(weekOf(row.date));
  for(const week of weeks)if(week!=='2026-W35')add('/daily/'+week+'/');
  const index=modelIndex(),english=new Set(translatedModels().map(p=>p.model.modelId));
  for(const id of index.models.keys())if(index.prices.has(id)||index.changes.has(id)){
    routes.add(canonicalUrl('/model/'+id+'/'));
    if(english.has(id))routes.add(canonicalUrl('/en/model/'+id+'/'));
  }
  for(const item of release.changes??[])if(item.status!=='withdrawn'&&(item.recordType==='price_change'||(item.summary??'').trim().length>=80))add('/item/'+item.id+'/');
  return [...routes].sort();
}
export function sitemapResponse(shard?:string){
  const urls=sitemapUrls();let body:string;
  if(shard===undefined){
    const pages=Array.from({length:Math.ceil(urls.length/SIZE)},(_,i)=>`<sitemap><loc>${xml(new URL('/sitemaps/'+i+'.xml',canonicalUrl('/')).href)}</loc></sitemap>`).join('');
    body=`<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${pages}</sitemapindex>`;
  }else{
    if(!/^(0|[1-9][0-9]*)$/.test(shard)||Number(shard)*SIZE>=urls.length)return new Response('Not found',{status:404});
    body=`<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls.slice(Number(shard)*SIZE,(Number(shard)+1)*SIZE).map(u=>`<url><loc>${xml(u)}</loc></url>`).join('')}</urlset>`;
  }
  return new Response('<?xml version="1.0" encoding="UTF-8"?>'+body,{headers:{'Content-Type':'application/xml; charset=utf-8'}});
}
