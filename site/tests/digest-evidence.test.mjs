import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {transform} from 'esbuild';
const source=readFileSync(new URL('../src/lib/digest-evidence.ts',import.meta.url),'utf8');
const {code}=await transform(source,{loader:'ts',format:'esm'});
const {displayItem,evidenceLinks,relatedSourceLinks}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('unverified historical claims never retain high-risk labels',()=>{
 for(const type of ['sunset','pricing','release']){const item=displayItem({type,text:'old'},'en');assert.equal(item.type,'other');assert.equal(item.text,'old');assert.deepEqual(item.relatedSources,[]);assert.equal(item.evidenceVersion,undefined);}
});
test('only safe bound evidence links render',()=>{
 const item={text:'fact',type:'pricing',evidenceVersion:1,evidence:[{id:'de_'+'a'.repeat(64),url:'https://official.test/pricing',observedDate:'2026-11-01'}]};
 assert.deepEqual(displayItem(item),item);assert.equal(evidenceLinks(item).length,1);
 for(const url of ['javascript:alert(1)','https://x:y@official.test'])assert.equal(evidenceLinks({...item,evidence:[{...item.evidence[0],url}]}).length,0);
});

const permalink='/item/obs_'+'a'.repeat(64)+'/';
const context={platform:'OpenAI',date:'2026-10-31',sources:[{platform:'OpenAI',date:'2026-10-31',url:'https://platform.openai.com/docs/models',permalink}]};
test('legacy summaries recover contextual sources without becoming bound evidence',()=>{
 const original={text:'Original AI summary',type:'release'};
 const item=displayItem(original,'zh',context);
 assert.equal(item.text,original.text);assert.equal(item.type,'other');assert.equal(evidenceLinks(item).length,0);
 assert.deepEqual(item.relatedSources,[{url:'https://platform.openai.com/docs/models',host:'platform.openai.com',recordUrl:permalink}]);
 assert.deepEqual(original,{text:'Original AI summary',type:'release'});
});
test('source context never crosses a date or platform and withdrawn records are omitted',()=>{
 const source=context.sources[0];
 for(const extra of [{date:'2026-10-30'},{platform:'Other'},{status:'withdrawn'}])
  assert.deepEqual(relatedSourceLinks({...context,sources:[{...source,...extra}]}),[]);
});
test('context rejects unsafe URLs and arbitrary internal paths',()=>{
 for(const url of ['javascript:alert(1)','https://x:y@official.test','//other.test','/api/account/'])
  assert.deepEqual(relatedSourceLinks({...context,sources:[{platform:context.platform,date:context.date,url,permalink:'/api/account/'}]}),[]);
});
test('duplicate sources retain the available archived change link',()=>{
 const source=context.sources[0];
 const links=relatedSourceLinks({...context,sources:[{...source,permalink:undefined},source,source]});
 assert.equal(links.length,1);assert.equal(links[0].recordUrl,permalink);
});
test('old archive index can link its actual record without inventing an external source',()=>{
 const source={platform:context.platform,date:context.date,permalink};
 const item=displayItem({text:'old archive',type:'pricing'},'en',{...context,sources:[source]});
 assert.deepEqual(item.relatedSources,[{url:permalink,host:'',recordUrl:undefined}]);assert.equal(evidenceLinks(item).length,0);
});
test('context cannot upgrade a malformed evidence reference to a verified label',()=>{
 const item=displayItem({text:'old',type:'sunset',evidenceVersion:1,evidence:[{id:'bad',url:'https://official.test',observedDate:context.date}]},'en',context);
 assert.equal(item.type,'other');assert.equal(evidenceLinks(item).length,0);assert.equal(item.relatedSources.length,1);
});

test('archive fallback never repeats a record already attached to its source page',()=>{
 const source=context.sources[0];
 const links=relatedSourceLinks({...context,sources:[source,{platform:context.platform,date:context.date,permalink}]});
 assert.equal(links.length,1);assert.equal(links[0].recordUrl,permalink);
});
