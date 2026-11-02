import {test} from 'node:test';
import assert from 'node:assert/strict';
import {build} from 'esbuild';
import {createRequire} from 'node:module';
const bundle=await build({entryPoints:['src/lib/dynamic-translation.ts'],bundle:true,write:false,format:'cjs',platform:'node'});
const m={exports:{}};new Function('module','exports','require',bundle.outputFiles[0].text)(m,m.exports,createRequire(import.meta.url));
const bridge=Symbol.for('maas.site-data.v1');
test('source excerpts retain original facts, cached translations and explicit original-language guidance',()=>{
 const previous=globalThis[bridge];const source='原始页面全文。'.repeat(10000);const record={summary:source,summaryOrigin:'rule',diff:{addedLines:[source]}};const before=structuredClone(record);
 globalThis[bridge]={projection:()=>({texts:{}})};
 try{
  assert.equal(m.exports.localizeRecordSummary(record,'zh'),source);
  const en=m.exports.localizeRecordSummary(record,'en');assert.match(en,/original source excerpt/);assert.doesNotMatch(en,/translation pending/);assert(!en.includes(source));assert.deepEqual(record,before);
  for(const summaryOrigin of ['llm','manual',null])assert.match(m.exports.localizeRecordSummary({...record,summaryOrigin},'en'),/translation pending/,'Editorial gaps remain explicit');
  globalThis[bridge]={projection:()=>({texts:{[source]:'Previously validated source translation'}})};
  assert.equal(m.exports.localizeRecordSummary(record,'en'),'Previously validated source translation');
  assert.equal(m.exports.localizeRecordSummary({summary:'Input $12 per MTok',summaryOrigin:'rule'},'en'),'Input $12 per MTok');
 }finally{if(previous===undefined)delete globalThis[bridge];else globalThis[bridge]=previous;}
});
