import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { JSDOM } from 'jsdom';
import { localizeEditorial } from '../src/lib/dynamic-translation.ts';
const cache=JSON.parse(readFileSync('src/data/translations-en.json','utf8'));
const source=Object.keys(cache.texts).find(text=>text.length>20);
assert(source,'Backfilled English content exists');
const input={highlights:[{platform:'百度千帆',logo_summary:source,items:[{text:source,type:'other'}]}],changed:[{llm_summary:source,signal_preview:source,added_lines:[source]}]};
const en=localizeEditorial(input,'en');
assert.equal(en.highlights[0].items[0].text,cache.texts[source]);
assert.equal(en.changed[0].llm_summary,cache.texts[source]);
assert.equal(en.changed[0].signal_preview,source,'Original evidence remains unchanged');
assert.equal(en.changed[0].added_lines[0],source);
assert.equal(en.highlights[0].platform,'百度千帆','Provider identity is unchanged');
assert.deepEqual(localizeEditorial(input,'zh'),input);
assert.equal(input.highlights[0].items[0].text,source,'No shared Chinese data mutation');
assert.match(localizeEditorial({text:'新版本尚未翻译的测试内容'},'en').text,/English translation pending/);
for(const file of ['dist/en/index.html','dist/en/daily/2026-W41/index.html']) {
 const doc=new JSDOM(readFileSync(file,'utf8')).window.document;
 const summaries=doc.querySelectorAll('.highlight-summary,.highlight-title,.vendor-change-item p,.llm-summary,.story-sec-item p,.story-sec-item h3,.hl-text');
 assert(summaries.length,'Dynamic summary nodes rendered');
 for(const node of summaries) assert(!/[\u3400-\u9fff]/.test(node.textContent),`${file}: untranslated editorial text: ${node.textContent}`);
}
console.log('Dynamic English projection, source preservation and rendered summaries passed');
