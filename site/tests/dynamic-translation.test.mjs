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
// A failed or unavailable translation must not leak Chinese editorial text
// into English pages or block publication of the original Chinese data.
const missing='新版本尚未翻译的测试内容';
const pending={text:missing,logo_summary:missing,theme:missing,title:missing,body:missing,story:missing,llm_summary:missing};
const pendingEn=localizeEditorial(pending,'en');
for(const text of Object.values(pendingEn)) {
 assert.match(text,/English translation pending/);
 assert.match(text,/Chinese version/);
 assert(!/[\u3400-\u9fff]/.test(text),'Pending translation notices remain English');
 assert(!text.includes(missing),'Untranslated source is not echoed into the notice');
}
assert.deepEqual(localizeEditorial(pending,'zh'),pending,'Chinese originals remain available');
assert.equal(pending.text,missing,'Fallback does not mutate the shared source');
for(const file of ['dist/en/index.html','dist/en/daily/2026-W41/index.html']) {
 const doc=new JSDOM(readFileSync(file,'utf8')).window.document;
 const summaries=doc.querySelectorAll('.highlight-summary,.highlight-title,.vendor-change-item p,.llm-summary,.story-sec-item p,.story-sec-item h3,.hl-text');
 assert(summaries.length,'Dynamic summary nodes rendered');
 for(const node of summaries) assert(!/[\u3400-\u9fff]/.test(node.textContent),`${file}: untranslated editorial text: ${node.textContent}`);
 if(file.includes('/daily/')) for(const node of doc.querySelectorAll('.back-link,.section-note,.day-stats,.pcx-fold summary,.footnote,.wr-title,.wr-note,.hero-aside')) {
  assert(!/[\u3400-\u9fff]/.test(node.textContent),`${file}: untranslated archive label: ${node.textContent}`);
 }
}
console.log('Dynamic English projection, source preservation and rendered summaries passed');
