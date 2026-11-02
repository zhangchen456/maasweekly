export interface DigestEvidence {id:string;url:string;observedDate:string;quote?:string;mentionedDates?:string[]}
export interface DigestSource {platform:string;date:string;url?:string;sourceUrl?:string;permalink?:string;status?:string}
export interface RelatedSource {url:string;recordUrl?:string;host:string}
export interface EvidenceItem {text:string;type:string;evidenceVersion?:number;evidence?:DigestEvidence[];relatedSources?:RelatedSource[]}
export interface DigestContext {platform:string;date:string;sources:DigestSource[]}

function sourceUrl(value:unknown):URL|null {
 if(typeof value!=='string')return null;
 try {const url=new URL(value);return url.protocol==='https:'&&!url.username&&!url.password ? url : null;}catch{return null;}
}
export function evidenceLinks(item:EvidenceItem) {
 return item.evidenceVersion===1 ? (item.evidence??[]).filter(e=>sourceUrl(e.url)&&/^de_[a-f0-9]{64}$/.test(e.id)&&/^\d{4}-\d{2}-\d{2}$/.test(e.observedDate)) : [];
}
/** Day/platform context is useful provenance, never proof of a specific summary claim. */
export function relatedSourceLinks(context?:DigestContext):RelatedSource[] {
 if(!context)return [];
 const found=new Map<string,RelatedSource>();
 for(const source of context.sources) {
  if(source.platform!==context.platform||source.date!==context.date||source.status==='withdrawn')continue;
  const url=sourceUrl(source.url??source.sourceUrl);
  const recordUrl=/^\/item\/obs_[a-f0-9]{64}\/$/.test(source.permalink??'') ? source.permalink : undefined;
  if(!url&&!recordUrl)continue;
  const key=url?.href??recordUrl!;
  const existing=found.get(key);
  if(!existing||(!existing.recordUrl&&url&&recordUrl))found.set(key,{url:key,host:url?.hostname??'',recordUrl:url?recordUrl:undefined});
 }
 // The archive index may repeat a record already linked beside its source page.
 for(const source of found.values())if(source.recordUrl)found.delete(source.recordUrl);
 return [...found.values()];
}
export function displayItem<T extends EvidenceItem>(item:T, _locale='zh', context?:DigestContext):T {
 if(evidenceLinks(item).length)return item;
 return {...item,type:'other',relatedSources:relatedSourceLinks(context)};
}
