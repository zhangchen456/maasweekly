// Public page output parity against the former per-model scans, plus safe JSON hydration.
import assert from 'node:assert/strict';
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
const fixture={...release,modelIdentities:{models:[{modelId:'test:one',modelName:'One'}],families:[]},prices:[],evidence:[],changes:[
 {modelId:'test:one',status:'active',observationDate:'2026-07-03',id:'outside'},
 {modelId:'test:one',status:'withdrawn',observationDate:'2026-10-01',id:'withdrawn'},
 ...Array.from({length:12},(_,i)=>({modelId:'test:one',status:'active',observationDate:'2026-10-01',id:String(i)})),
 {modelId:'test:one',status:'active',observationDate:'2026-10-02',id:'future'}]};
assert.deepEqual(pages.createModelIndex(fixture).changes.get('test:one').map(c=>c.id),Array.from({length:10},(_,i)=>String(i)));
console.log(JSON.stringify({models:catalog.length,prices,changes,allModelOutputParity:true,parityMs,sharedIndex:true,safeHydration:true}));
