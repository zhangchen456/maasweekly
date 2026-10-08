import { onAccountChange } from './account-client';
const root=document.querySelector('[data-pro-weekly]');
if(root){let generation=0;const body=document.getElementById('weekly-reader-body')!,list=document.getElementById('weekly-reader-list')!,status=document.getElementById('weekly-reader-status')!;
 async function load(){const g=++generation;body.replaceChildren();list.replaceChildren();try{const r=await fetch('/api/pro/catalog',{credentials:'same-origin',cache:'no-store'});if(!r.ok)throw new Error('情报目录暂不可用');const data=await r.json();if(g!==generation)return;const id=new URLSearchParams(location.search).get('id');const items=data.items.filter((c:any)=>c.kind==='briefing');for(const c of items){const p=document.createElement('p'),a=document.createElement('a');a.href='/pro/weekly/?id='+encodeURIComponent(c.id);a.textContent=c.title+' · '+c.coverage;p.append(a);const preview=document.createElement('p');preview.textContent=c.preview;list.append(p,preview);}
 if(!id){status.textContent=items.length?'选择一期周报':'尚无已出版统一周报';return;}const entry=items.find((c:any)=>c.id===id);if(!entry){status.textContent='周报不存在或已撤回';return;}
 const full=await fetch('/api/pro/content/'+encodeURIComponent(id),{credentials:'same-origin',cache:'no-store'});if(g!==generation)return;if(full.status===401||full.status===403){status.textContent='公共预览如上；请登录并开启有效 Plus 权益阅读全文。';return;}if(!full.ok)throw new Error('全文暂不可用');const c=await full.json();if(g!==generation)return;
 // Text rendering intentionally disables raw HTML and links, including malicious Markdown URLs.
 body.textContent=`${c.title}\n版本 ${c.version} · ${c.period.from} — ${c.period.to}\n截至 ${c.dataThrough} · ${c.coverage} ${c.coverageNote}\n\n${c.body}\n\n适用条件\n${c.conditions}\n\n局限\n${c.limitations}\n\n表格\n${JSON.stringify(c.rows,null,2)}\n\n来源\n${c.evidence.map((e:any)=>`${e.id} ${e.url} (${e.observedAt}) ${e.note}`).join('\n')}\n${c.correction?'更正：'+c.correction:''}`;status.textContent='Plus 全文 · 当前已出版版本';
 }catch(e){if(g===generation)status.textContent=e instanceof Error?e.message:'加载失败';}}
 onAccountChange(()=>void load());window.addEventListener('pagehide',()=>{generation++;body.replaceChildren();list.replaceChildren();});
}
