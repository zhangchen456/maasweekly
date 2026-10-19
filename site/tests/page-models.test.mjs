// Public page output parity against the former per-model scans, plus safe JSON hydration.
import assert from 'node:assert/strict';
import {priceFixture} from './fixtures/price.mjs';
import { build } from 'esbuild';
import { fileURLToPath } from 'node:url';
import { performance } from 'node:perf_hooks';
const site = fileURLToPath(new URL('../', import.meta.url));
process.chdir(site);
async function load(entry) {
  const result = await build({absWorkingDir:site,entryPoints:[entry],bundle:true,write:false,format:'esm',platform:'node'});
  return import('data:text/javascript;base64,'+Buffer.from(result.outputFiles[0].text).toString('base64'));
}
const pages=await load('src/lib/model-pages.ts');
const {safeJson}=await load('src/lib/page-data.ts');
const release=pages.modelRelease();
const catalog=release.modelIdentities.models;
const before=performance.now();
let prices=0, changes=0;
for (const model of catalog) {
  const page=pages.modelPage(model.modelId);
  const expectedPrices=release.prices.filter(p=>p.modelId===model.modelId);
  const expectedChanges=release.changes.filter(c=>c.modelId===model.modelId && c.status==='active'
    && c.observationDate>=page.from && c.observationDate<page.to).slice(0,10);
  assert.deepEqual(page.prices,expectedPrices);
  assert.deepEqual(page.changes,expectedChanges);
  assert.equal(page.datasetVersion,release.datasetVersion);
  prices+=page.prices.length;changes+=page.changes.length;
}
const parityMs=performance.now()-before;
const reuse=pages.modelIndex();
assert.equal(reuse,pages.modelIndex());
const dangerous={value:'</script><script>throw new Error("injection")</script>\u2028\u2029'};
const json=safeJson(dangerous);
assert.ok(!json.includes('</script>'));
assert.deepEqual(JSON.parse(json),dangerous);
const fixture={dataThrough:'2026-10-01',modelIdentities:{models:[{modelId:'test:one',modelName:'One'}],families:[]},prices:[],evidence:[],changes:[
 {modelId:'test:one',status:'active',observationDate:'2026-07-03',id:'outside'},
 {modelId:'test:one',status:'withdrawn',observationDate:'2026-10-01',id:'withdrawn'},
 {modelId:'test:one',status:'active',observationDate:'2026-10-02',id:'future'},
 ...Array.from({length:12},(_,i)=>({modelId:'test:one',status:'active',observationDate:'2026-10-01',id:String(i)}))]};
assert.deepEqual(pages.createModelIndex(fixture).changes.get('test:one').map(c=>c.id),Array.from({length:10},(_,i)=>String(i)));
console.log(JSON.stringify({models:catalog.length,prices,changes,allModelOutputParity:true,parityMs,sharedIndex:true,safeHydration:true}));

// Homepage selection stays visible without quotes; quote components must share a scenario.
const home=await load('src/lib/home-models.ts');
const groups=home.homeModelGroups();
const {HOME_MODEL_GROUPS} = await load('src/config/home-model-selection.ts');
assert.deepEqual(groups.map(g=>({id:g.id,picks:g.models.map(row=>row.pick)})), HOME_MODEL_GROUPS.map(g=>({id:g.id,picks:g.models})));
assert(!groups.filter(g=>['flagship','value'].includes(g.id)).flatMap(g=>g.models).some(row=>row.pick.modelId.includes('coder') || row.pick.modelId.endsWith('-code')), 'general-purpose selections exclude coding specialists');
for (const row of groups.flatMap(g=>g.models)) {
  assert(row.quoteStatus, `${row.pick.modelId}: quote or missing-evidence status required`);
  assert.equal(row.modelHref, catalog.some(m=>m.modelId===row.pick.modelId) ? `/model/${row.pick.modelId}/` : null);
  if (!row.input) { assert.equal(row.output,undefined); assert.equal(row.cache,undefined); }
}
for (const group of groups) for (const row of group.models) {
  assert(row.pick.source.startsWith('https://'));
  if(row.input) {
    assert.equal(row.input.quality.state,'fresh');assert.equal(row.input.evidenceStatus,'complete');
    for(const p of [row.output,row.cache].filter(Boolean))assert.equal(home.quoteScenario(p),home.quoteScenario(row.input));
  }
}
const base={...priceFixture};
const selected=home.selectHomeQuote([
 {...base,id:'cn-input',region:'cn',amount:'20'},
 {...base,id:'us-cheapest',region:'us',amount:'0.01'},
 {...base,id:'cn-output',region:'cn',component:'output',amount:'40'},
 {...base,id:'us-output',region:'us',component:'output',amount:'0.02'},
 {...base,id:'bad-cache',region:'cn',component:'cache_read',evidenceStatus:'partial'},
], 'alibaba');
assert.equal(selected.input.id,'cn-input');assert.equal(selected.output.id,'cn-output');assert.equal(selected.cache,undefined);
assert.equal(home.selectHomeQuote([{...base,evidenceStatus:'partial'}], 'alibaba').input,undefined);
assert.equal(home.selectHomeQuote([], 'alibaba').input,undefined);
const newer={...base,observedAt:'2026-10-02T12:00:00Z',timeCondition:{period:'promotional',tz:'UTC',schedule:'through December 31, 2026'}};
assert.equal(home.selectHomeQuote([{...base,id:'old',observedAt:'2026-10-01T12:00:00Z'}, {...newer,id:'new'}], 'alibaba').input.id,'new');
assert.equal(home.selectHomeQuote([{...base,observedAt:'2026-10-01T12:00:00Z'}, {...newer,evidenceStatus:'partial'}], 'alibaba').input,undefined);
console.log('Homepage groups: configured picks, missing quote states, partial-evidence exclusion and scenario matching passed');
