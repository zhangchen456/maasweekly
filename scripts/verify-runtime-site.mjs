#!/usr/bin/env node
/** Read-only SSR acceptance against a fixed public cache and PostgreSQL. */
import {pathToFileURL} from 'node:url';
import path from 'node:path';
import assert from 'node:assert/strict';
import {writeFile} from 'node:fs/promises';
const args=Object.fromEntries(process.argv.slice(2).reduce((rows,v,i,all)=>i%2?rows:[...rows,[v,all[i+1]]],[]));
const root=path.resolve(args['--package-root']??'.');
const data=path.resolve(args['--data-root']??'data/public/v1');
const load=p=>import(pathToFileURL(path.join(root,p)).href);
const {DatasetHolder}=await load('agent-api/dist/dataset.js');
const {SiteDataStore}=await load('agent-api/dist/site-data-store.js');
const {SiteRuntime}=await load('agent-api/dist/site-runtime.js');
const {capturePage}=await load('agent-api/dist/site-http.js');
const store=new SiteDataStore({connectionString:process.env.MAAS_SITE_DATABASE_URL}),runtime=new SiteRuntime(store);
const holder=new DatasetHolder(data,{publicationFile:'publication.json',prepare:ds=>runtime.prepare(ds)});
try{
 assert.equal(await holder.reloadAsync(),'changed',holder.lastReloadError??'');
 const dataset=holder.current;runtime.install();
 const {handler}=await runtime.run(dataset,()=>load('site/dist/server/entry.mjs'));
 const render=(url,internal=false)=>runtime.run(dataset,()=>capturePage(handler,url,'http://localhost',internal));
 const records=[dataset.changes.find(c=>c.recordType==='source_observation'),dataset.changes.find(c=>c.recordType==='price_change')].filter(Boolean);
 const weekly=dataset.weekly.filter(w=>w.id!=='2026-05-03').at(-1);
 const paths=['/','/en/','/models/','/pricing/','/compare/','/leaderboards/','/sources/','/weekly/','/feed.xml','/feed/weekly.xml','/sitemap.xml','/sitemaps/0.xml',...records.flatMap(r=>['/item/'+r.id+'/','/en/item/'+r.id+'/'])];
 const evidence=dataset.evidenceById.keys().next().value;if(evidence)paths.push('/evidence/'+evidence+'/');
 const results=[];
 for(const url of paths){const start=performance.now(),result=await render(url);assert.equal(result.status,200,url);assert.ok(!result.body.includes('data-private-weekly'),url);results.push({url,status:result.status,bytes:result.body.length,elapsedMs:Math.round(performance.now()-start)});}
 if(weekly){
   const result=await render('/weekly/'+weekly.id+'/');assert.equal(result.status,200);assert.ok(!result.body.includes('class="report-body"'));assert.ok(!result.body.includes('data-private-weekly'));
   const denied=await render('/_internal/weekly-body/'+weekly.id+'/');assert.equal(denied.status,404);
   const full=await render('/_internal/weekly-body/'+weekly.id+'/',true);assert.equal(full.status,200);assert.ok(full.body.includes('class="report-body"'));assert.ok(full.body.includes('headline-detail'));
   results.push({url:'/weekly/'+weekly.id+'/',status:200,privateBodyProtected:true,privateBytes:full.body.length});
 }
 for(const url of ['/item/obs_'+'f'.repeat(64)+'/','/model/notreal:missing/'])assert.equal((await render(url)).status,404);
 const report={status:'passed',activated:false,datasetVersion:dataset.version,site:dataset.manifest.site,pages:results,memory:process.memoryUsage()};
 if(args['--report'])await writeFile(args['--report'],JSON.stringify(report,null,2)+'\n');
 console.log(JSON.stringify({status:report.status,pages:results.length,datasetVersion:dataset.version,rssBytes:report.memory.rss}));
}finally{holder.close();runtime.uninstall();await store.close();}
