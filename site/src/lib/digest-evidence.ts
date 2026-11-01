export interface DigestEvidence {id:string;url:string;observedDate:string;quote?:string;effectiveDates?:string[]}
export interface EvidenceItem {text:string;type:string;evidenceVersion?:number;evidence?:DigestEvidence[]}
export function evidenceLinks(item:EvidenceItem) {
 return item.evidenceVersion===1 ? (item.evidence??[]).filter(e=>{
  try {const u=new URL(e.url);return u.protocol==='https:'&&!u.username&&!u.password&&/^de_[a-f0-9]{64}$/.test(e.id)&&/^\d{4}-\d{2}-\d{2}$/.test(e.observedDate);}catch{return false;}
 }) : [];
}
export function displayItem<T extends EvidenceItem>(item:T, locale='zh'):T {
 if(evidenceLinks(item).length)return item;
 return {...item,type:'other',text:(locale==='en'?'Historical summary (not individually verified): ':'历史摘要（未逐条核验）：')+item.text};
}
