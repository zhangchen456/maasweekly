import { test } from 'node:test';
import assert from 'node:assert/strict';
import { mkdtempSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { Dataset, DatasetHolder } from '../dataset.js';
import { ReleaseFixture } from './fixture.js';
import { normalizeQuery, listPrices } from '../query.js';
import { validateIdentityCatalog, validatePricePlatforms, DatasetError } from '../public-contract/validation.js';
import type { ModelIdentityCatalog, PriceEntity } from '../public-contract/entities.js';
import { createHandler } from '../http.js';
import http from 'node:http';

const mid='anthropic:claude-sonnet-5.5';
const evidence={url:'https://platform.claude.com/docs/en/models/overview',verifiedAt:'2026-10-02'};
const catalog:ModelIdentityCatalog={models:[{modelId:mid,modelName:'Claude Sonnet 5.5'}],families:[],
 developers:[{developerId:'anthropic',displayName:'Anthropic'}],
 platforms:[{platformId:'anthropic-api',displayName:'Anthropic API'},{platformId:'google-vertex-ai',displayName:'Google Cloud'}],
 upstreamModels:[{upstreamModelId:mid,modelId:mid,developerId:'anthropic',modelName:'Claude Sonnet 5.5',evidence}],
 availabilities:['anthropic-api','google-vertex-ai'].map(platformId=>({availabilityId:mid+'@'+platformId,platformId,modelId:mid,upstreamModelId:mid,apiModelIds:['claude-sonnet-5-5'],sourceId:platformId==='anthropic-api'?'anthropic-pricing':'google-vertex-pricing',evidence}))};
function fixture(){
 const fx=new ReleaseFixture(mkdtempSync(path.join(tmpdir(),'cross-platform-')));
 fx.writeRelease('ds_'+'d'.repeat(64),{modelIdentities:catalog,providers:[{providerId:"anthropic",displayName:"Anthropic",region:"overseas"}],prices:catalog.availabilities!.map((a,i)=>({factKey:'f'+i,modelId:mid,modelKey:'claude-sonnet-5.5',providerId:'anthropic',sourceId:a.sourceId,platformId:a.platformId,upstreamModelId:mid,availabilityId:a.availabilityId,component:'input'}))});
 return fx;
}
test('legacy catalogs remain valid; dangling/ambiguous relations are rejected',()=>{
 assert.doesNotThrow(()=>validateIdentityCatalog({models:catalog.models,families:[]}));
 assert.doesNotThrow(()=>validateIdentityCatalog(catalog));
 for(const mutate of [
  (c:ModelIdentityCatalog)=>{c.availabilities![0]!.upstreamModelId='anthropic:unverified';},
  (c:ModelIdentityCatalog)=>{c.upstreamModels![0]!.developerId='google';},
  (c:ModelIdentityCatalog)=>{c.availabilities!.push({...c.availabilities![0]!});},
  (c:ModelIdentityCatalog)=>{c.availabilities![0]!.evidence.url='javascript:alert(1)';},
 ]){const c=structuredClone(catalog);mutate(c);assert.throws(()=>validateIdentityCatalog(c),DatasetError);}
});
test('platform filter is exact and optional; provider/modelId continue across platforms',()=>{
 const fx=fixture();try{
 const ds=Dataset.load(fx.root);
 const all=normalizeQuery('prices',new URLSearchParams({modelId:mid,provider:'anthropic'}),ds);
 assert.equal(all.problems.length,0,JSON.stringify(all.problems));assert.equal(listPrices(ds,all.normalized!).items.length,2);
 const cloud=normalizeQuery('prices',new URLSearchParams({modelId:mid,platformId:'google-vertex-ai'}),ds);
 assert.equal(cloud.problems.length,0);assert.equal(listPrices(ds,cloud.normalized!).items.length,1);
 assert.equal(listPrices(ds,cloud.normalized!).items[0]!.sourceId,'google-vertex-pricing');
 assert.equal(normalizeQuery('prices',new URLSearchParams({platformId:'google'}),ds).problems[0]!.code,'invalid_platformId');
 const tampered={...ds.prices[0]!,availabilityId:mid+'@unverified'};
 assert.throws(()=>validatePricePlatforms(catalog,[tampered]),DatasetError);
 }finally{fx.cleanup();}
});
test('/models publishes frozen relation catalog with the same dataset envelope',async()=>{
 const fx=fixture();const holder=new DatasetHolder(fx.root);assert(holder.reload());
 const server=http.createServer(createHandler(holder,{rateLimit:{capacity:100,refillPerMinute:1000}}));await new Promise<void>(r=>server.listen(0,'127.0.0.1',r));
 try{const address=server.address() as {port:number};const response=await fetch(`http://127.0.0.1:${address.port}/api/v1/models`);assert.equal(response.status,200);const body=await response.json() as any;assert.equal(body.datasetVersion,holder.current!.version);assert.deepEqual(body.availabilities,catalog.availabilities);assert.equal(body.models[0].modelId,mid);}
 finally{await new Promise<void>(r=>server.close(()=>r()));fx.cleanup();}
});
