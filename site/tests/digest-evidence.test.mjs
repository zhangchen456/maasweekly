import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {transform} from 'esbuild';
const source=readFileSync(new URL('../src/lib/digest-evidence.ts',import.meta.url),'utf8');
const {code}=await transform(source,{loader:'ts',format:'esm'});
const {displayItem,evidenceLinks}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
test('unverified historical claims never retain high-risk labels',()=>{
 for(const type of ['sunset','pricing','release']){const item=displayItem({type,text:'old'},'en');assert.equal(item.type,'other');assert.match(item.text,/not individually verified/);}
});
test('only safe bound evidence links render',()=>{
 const item={text:'fact',type:'pricing',evidenceVersion:1,evidence:[{id:'de_'+'a'.repeat(64),url:'https://official.test/pricing',observedDate:'2026-11-01'}]};
 assert.deepEqual(displayItem(item),item);assert.equal(evidenceLinks(item).length,1);
 for(const url of ['javascript:alert(1)','https://x:y@official.test'])assert.equal(evidenceLinks({...item,evidence:[{...item.evidence[0],url}]}).length,0);
});
