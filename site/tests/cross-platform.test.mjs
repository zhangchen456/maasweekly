import assert from 'node:assert/strict';
import { build } from 'esbuild';
import { readFileSync } from 'node:fs';
process.chdir(new URL('../',import.meta.url).pathname);
async function load(file){const b=await build({absWorkingDir:process.cwd(),entryPoints:[file],bundle:true,write:false,format:'esm',platform:'node'});return import('data:text/javascript;base64,'+Buffer.from(b.outputFiles[0].text).toString('base64'));}
const {crossPlatformGroups}=await load('src/lib/cross-platform.ts');
const {modelRelease}=await load('src/lib/model-pages.ts');
const {selectHomeQuote}=await load('src/lib/home-models.ts');
const release=modelRelease(),groups=crossPlatformGroups(release);
assert.equal(groups.length,3);
for(const g of groups){
 assert.equal(new Set(g.rows.map(r=>r.availability.platformId)).size,2);
 for(const row of g.rows){
  // The product contract permits unavailable current quotes; never substitute stale evidence.
  if (!row.input) {
   assert.equal(row.output,undefined);
   assert.equal(row.cache,undefined);
   const prices=release.prices.filter(p=>p.availabilityId===row.availability.availabilityId);
   const latest=Math.max(...prices.map(p=>Date.parse(p.observedAt)));
   assert(!prices.some(p=>Date.parse(p.observedAt)===latest && p.quality.state==='fresh'
     && p.evidenceStatus==='complete' && p.billingMode==='realtime' && p.serviceTier==='standard' && p.component==='input'),
     `${g.model.modelId}/${row.availability.platformId}: an eligible current quote must not be hidden`);
   continue;
  }
  assert.equal(row.input.quality.state,'fresh');
  assert.equal(row.input.evidenceStatus,'complete');
  assert.equal(row.input.platformId,row.availability.platformId);
  if(!row.output) continue;
  assert.equal(row.output.platformId,row.availability.platformId);
  assert.equal(row.output.observedAt,row.input.observedAt);
  assert.deepEqual(row.output.contextBand,row.input.contextBand);
  assert.deepEqual(row.output.timeCondition,row.input.timeCondition);
 }
}
const gemini=release.prices.filter(p=>p.modelId==='google:gemini-3.8-flash');
assert.equal(selectHomeQuote(gemini,'google').input.sourceId,'google-gemini-pricing');
const cloud=gemini.find(p=>p.platformId==='google-vertex-ai' && p.component==='input');
assert(cloud);
assert.equal(selectHomeQuote([...gemini,{...cloud,observedAt:'2030-01-01T00:00:00Z'}],'google').input.sourceId,'google-gemini-pricing');
const old=groups.flatMap(g=>g.rows).find(r=>r.input)?.input;
assert(old,'at least one valid current quote is required for pairing fixtures');
const a=release.modelIdentities.availabilities[0];
const base={...old,modelId:a.modelId,upstreamModelId:a.upstreamModelId,availabilityId:a.availabilityId,platformId:a.platformId,component:'input',observedAt:'2026-10-01T00:00:00Z'};
const bad={...base,id:'new-partial',observedAt:'2026-10-02T00:00:00Z',evidenceStatus:'partial'};
const partial=crossPlatformGroups({...release,prices:[base,bad]});
assert.equal(partial.find(g=>g.model.modelId===a.modelId).rows.find(r=>r.availability.availabilityId===a.availabilityId).input,undefined);
assert.equal(crossPlatformGroups({...release,modelIdentities:{models:[],families:[]}}).length,0);
const html=readFileSync('dist/compare/index.html','utf8');
assert(html.includes('同一模型，不同平台怎么收费？'));
for(const id of ['google-gemini-api','google-vertex-ai','anthropic-api'])assert(html.includes(`data-platform-id="${id}"`));
assert(!html.includes('undefined'));
if(groups.some(g=>g.rows.some(r=>!r.input))) assert(html.includes('等待完整、最新的价格证据'));

console.log(JSON.stringify({models:groups.length,rows:groups.reduce((n,g)=>n+g.rows.length,0),exactPlatforms:true,scenarioParity:true,defaultSourceStable:true,missingQuoteExclusion:true,rendered:true}));
