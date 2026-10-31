/** Bundle with esbuild before running against an installed runtime. Read-only. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {parse, serialize} from '../site/node_modules/parse5/dist/index.js';
import {displayTexts} from '../site/scripts/audit-english.mjs';
import {englishHtml} from '../site/src/lib/ui-translation.ts';

const args=Object.fromEntries(process.argv.slice(2).reduce((rows,v,i,a)=>i%2?rows:[...rows,[v,a[i+1]]],[]));
const root=path.resolve(args['--package-root']);
const load=p=>import(pathToFileURL(path.join(root,p)).href);
const {DatasetHolder}=await load('agent-api/dist/dataset.js');
const {SiteDataStore}=await load('agent-api/dist/site-data-store.js');
const {SiteRuntime}=await load('agent-api/dist/site-runtime.js');
const {capturePage}=await load('agent-api/dist/site-http.js');
const store=new SiteDataStore({connectionString:process.env.MAAS_SITE_DATABASE_URL}),runtime=new SiteRuntime(store);
const holder=new DatasetHolder(path.resolve(args['--data-root']),{publicationFile:'publication.json',prepare:ds=>runtime.prepare(ds)});
const report={pages:0,protectedBlocks:0,privateReports:0,failures:[],elapsedSeconds:0};
const start=Date.now();
function originals(html){
  const rows=[];
  const walk=n=>{if(n.attrs?.some(a=>a.name==='data-original-language')){rows.push(serialize(n));return;}for(const child of n.childNodes??[])walk(child);};
  walk(parse(html));return rows;
}
try {
  if(await holder.reloadAsync()!=='changed')throw Error(holder.lastReloadError??'Dataset unavailable');
  const dataset=holder.current;runtime.install();
  report.datasetVersion=dataset.version;
  const {handler}=await runtime.run(dataset,()=>load('site/dist/server/entry.mjs'));
  const render=(url,internal=false)=>runtime.run(dataset,()=>capturePage(handler,url,'https://daily.maas.click',internal));
  const paths=new Set(['/en/','/en/models/','/en/pricing/','/en/compare/','/en/guides/','/en/leaderboards/','/en/changes/','/en/sources/','/en/weekly/','/en/agent/','/en/method/','/en/about/','/en/changelog/','/en/account/','/en/account/unsubscribe/','/en/subscription/','/en/subscription/payments/','/en/subscription/sandbox/','/en/pro/','/en/pro/weekly/','/en/pro/unsubscribe/','/en/feedback/']);
  const index=(await render('/sitemap.xml')).body.toString();
  for(const match of index.matchAll(/<loc>([^<]+)<\/loc>/g)){
    const shard=(await render(new URL(match[1]).pathname)).body.toString();
    for(const url of shard.matchAll(/<loc>([^<]+)<\/loc>/g)){const p=new URL(url[1]).pathname;if(p.startsWith('/en/'))paths.add(p);}
  }
  for(const id of dataset.itemsById.keys())paths.add('/en/item/'+id+'/');
  for(const id of dataset.evidenceById.keys())paths.add('/en/evidence/'+id+'/');
  const queue=[...paths];report.total=queue.length;
  if(args['--html-dir'])fs.mkdirSync(args['--html-dir'],{recursive:true});
  // One renderer avoids competing with public requests for database connections.
  for(const url of queue){
    const result=await render(url),html=result.body.toString();
    const texts=[...new Set(displayTexts(html))];
    if(result.status!==200||texts.length||html.includes('English translation pending.'))report.failures.push({url,status:result.status,texts,pending:html.includes('English translation pending.')});
    const blocks=originals(html);report.protectedBlocks+=blocks.length;
    if(blocks.length){const zh=originals((await render(url.replace(/^\/en/,''))).body.toString());if(JSON.stringify(blocks)!==JSON.stringify(zh))report.failures.push({url,originalEvidenceChanged:true});}
    if(args['--html-dir']&&/^\/en\/(pricing|leaderboards)\/$/.test(url)){const out=path.join(args['--html-dir'],url);fs.mkdirSync(out,{recursive:true});fs.writeFileSync(path.join(out,'index.html'),html);}
    report.pages++;
    if(report.pages%250===0)console.log(JSON.stringify({pages:report.pages,total:report.total,failures:report.failures.length,seconds:Math.round((Date.now()-start)/1000)}));
    if(args['--limit']&&report.pages>=Number(args['--limit']))break;
  }
  for(const row of dataset.weekly){
    const result=await render('/_internal/weekly-body/'+row.id+'/',true);
    if(result.status===404)continue;
    const texts=displayTexts(englishHtml(result.body.toString()));
    if(result.status!==200||texts.length)report.failures.push({url:'private-weekly/'+row.id,status:result.status,texts:[...new Set(texts)]});
    report.privateReports++;
  }
}finally{holder.close();runtime.uninstall();await store.close();}
report.elapsedSeconds=Math.round((Date.now()-start)/1000);
fs.writeFileSync(args['--report'],JSON.stringify(report,null,2)+'\n');
console.log(JSON.stringify({...report,failures:report.failures.slice(0,5)}));
process.exitCode=report.failures.length?1:0;
