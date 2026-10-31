/** Bundle with esbuild before running against an installed runtime. Read-only. */
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL} from 'node:url';
import {parse, serialize} from '../site/node_modules/parse5/dist/index.js';
import {displayTexts} from '../site/scripts/english-audit-text.mjs';
import {englishHtml} from '../site/src/lib/ui-translation.ts';

const args=Object.fromEntries(process.argv.slice(2).reduce((rows,v,i,a)=>i%2?rows:[...rows,[v,a[i+1]]],[]));
const root=path.resolve(args['--package-root']);
const load=p=>import(pathToFileURL(path.join(root,p)).href);
const {DatasetHolder}=await load('agent-api/dist/dataset.js');
const {SiteDataStore}=await load('agent-api/dist/site-data-store.js');
const {SiteRuntime}=await load('agent-api/dist/site-runtime.js');
const {capturePage}=await load('agent-api/dist/site-http.js');
const store=new SiteDataStore({connectionString:process.env.MAAS_SITE_DATABASE_URL}),runtime=new SiteRuntime(store);
// Build one read-only index for the pinned snapshot instead of repeating a
// history-wide evidence query for every page. This only affects the audit.
const prepare=store.prepare.bind(store);
store.prepare=async manifest=>{
  const inputs=await prepare(manifest);
  await store.pool.query('SET statement_timeout=30000');
  const result=await store.pool.query(`WITH RECURSIVE chain AS (
    SELECT version,parent_version,0 AS depth FROM maas_data.input_versions WHERE version=$1
    UNION ALL SELECT v.version,v.parent_version,c.depth+1 FROM maas_data.input_versions v JOIN chain c ON v.version=c.parent_version
  ), selected AS (
    SELECT DISTINCT ON(x.logical_path) x.logical_path,x.sha256 FROM maas_data.input_deltas x JOIN chain c ON c.version=x.input_version
    WHERE x.logical_path LIKE 'data/price-facts/versions/%' ORDER BY x.logical_path,c.depth
  ) SELECT d.payload_json FROM selected s JOIN maas_data.documents d ON d.sha256=s.sha256 ORDER BY d.entity_id`,[inputs.inputVersion]);
  const facts=new Map();
  for(const row of result.rows){const value=JSON.parse(row.payload_json);const key=value.evidence_id;if(!facts.has(key))facts.set(key,[]);facts.get(key).push(value);}
  store.factsForEvidence=async(_version,id)=>facts.get(id)??[];
  return inputs;
};
for(const method of ['document','revisions']){
  const original=store[method].bind(store),cache=new Map();
  store[method]=async(...args)=>{const key=JSON.stringify(args);if(cache.has(key))return cache.get(key);const result=await original(...args);if(cache.size>8)cache.delete(cache.keys().next().value);cache.set(key,result);return result;};
}
const holder=new DatasetHolder(path.resolve(args['--data-root']),{publicationFile:'publication.json',prepare:ds=>runtime.prepare(ds)});
const report={codeCommit:JSON.parse(fs.readFileSync(path.join(root,'metadata/runtime-manifest.json'),'utf8')).codeCommit,pages:0,protectedBlocks:0,privateReports:0,failures:[],elapsedSeconds:0};
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
  const paths=new Set(['/en/','/en/models/','/en/pricing/','/en/compare/','/en/guides/','/en/leaderboards/','/en/changes/','/en/sources/','/en/weekly/','/en/agent/','/en/method/','/en/about/','/en/aup/','/en/terms/','/en/privacy/','/en/changelog/','/en/account/','/en/account/unsubscribe/','/en/subscription/','/en/subscription/payments/','/en/subscription/sandbox/','/en/pro/','/en/pro/weekly/','/en/pro/unsubscribe/','/en/feedback/']);
  const index=(await render('/sitemap.xml')).body.toString();
  for(const match of index.matchAll(/<loc>([^<]+)<\/loc>/g)){
    const shard=(await render(new URL(match[1]).pathname)).body.toString();
    for(const url of shard.matchAll(/<loc>([^<]+)<\/loc>/g)){const p=new URL(url[1]).pathname;if(p.startsWith('/en/'))paths.add(p);}
  }
  for(const id of dataset.itemsById.keys())paths.add('/en/item/'+id+'/');
  for(const id of dataset.evidenceById.keys())paths.add('/en/evidence/'+id+'/');
  const queue=args['--paths-report'] ? [...new Set(JSON.parse(fs.readFileSync(args['--paths-report'],'utf8')).failures.map(f=>f.url).filter(p=>p.startsWith('/en/')))] : [...paths];report.total=queue.length;
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
    if(report.pages%250===0){fs.writeFileSync(args['--report'],JSON.stringify(report,null,2)+'\n');console.log(JSON.stringify({pages:report.pages,total:report.total,failures:report.failures.length,seconds:Math.round((Date.now()-start)/1000)}));}
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
