import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {transform} from 'esbuild';
import {JSDOM} from 'jsdom';
const compiled=(await transform(readFileSync('src/scripts/explore.ts','utf8').replace(/^import .*;\n/,''),{loader:'ts',format:'iife'})).code;
function exercise(html) {
const dom=new JSDOM(html,{url:'https://daily.maas.click/',runScripts:'outside-only'});
const {window}=dom;
window.savedState=()=>()=>{};
window.currentAccount=()=>null;
window.eval(compiled);
const doc=window.document;
const click=selector=>doc.querySelector(selector).click();
const rows=()=>[...doc.querySelectorAll('.vendor-change-row')].filter(el=>!el.hidden);
const matching=row=>[...row.querySelectorAll('.vendor-change-item')].filter(el=>!el.hidden);
const input=value=>{doc.querySelector('#signal-search').value=value;doc.querySelector('#signal-search').dispatchEvent(new window.Event('input'));};
assert.equal(doc.querySelectorAll('#digest').length,1);
assert.equal(doc.querySelectorAll('.platform-card,.price-changes,.market-table').length,0);
assert.equal(doc.querySelectorAll('#signal-search').length,1);
const allPlatforms=rows().map(el=>el.dataset.platform);
if (!allPlatforms.length) {
  assert.equal(doc.querySelector('#digest').hidden,true);
  console.log('Homepage empty-state controls passed');
} else {
for(const row of rows()) assert(row.querySelector('.vendor-change-body > ul').children.length<=3);
click('[data-range=today]');
const expectedToday = [...doc.querySelectorAll('.vendor-change-row')].filter(row => [...row.querySelectorAll('.vendor-change-item')].some(item => item.dataset.date === doc.querySelector('[data-latest-date]').dataset.latestDate)).map(row => row.dataset.platform);
assert.deepEqual(rows().map(row => row.dataset.platform), expectedToday);
for(const row of rows()) for(const item of matching(row)) assert.equal(item.dataset.date,doc.querySelector('[data-latest-date]').dataset.latestDate);
click('[data-range=week]');
assert.deepEqual(rows().map(el=>el.dataset.platform),allPlatforms);
// Search terms and expected results come from this rendered dataset, not yesterday's news.
const searchTerms = [allPlatforms[0], matching(rows()[0])[0].textContent.trim()];
for (const term of searchTerms) {
 input('');
 const query = term.toLocaleLowerCase();
 const expectedSearch = rows().map(row => ({row, items: matching(row).filter(item => `${row.dataset.platform} ${item.textContent}`.toLocaleLowerCase().includes(query))})).filter(({items}) => items.length);
 assert(expectedSearch.length > 0, 'positive search sample exists');
 input(query);
 assert.deepEqual(rows(), expectedSearch.map(({row}) => row));
 for (const {row, items} of expectedSearch) assert.deepEqual(matching(row), items);
}
input('');click('[data-filter=sunset]');
for(const row of rows()) assert(matching(row).every(el=>el.dataset.type==='sunset'));
click('[data-filter=all]');
for(const row of rows()) {
  const order=matching(row).map(el=>Number(el.dataset.order));
  assert.deepEqual(order,[...order].sort((a,b)=>a-b),'filter reset preserves latest-first order');
}
input('no-matching-model-123');
assert.equal(rows().length,0);
assert.equal(doc.querySelector('#filter-empty').hidden,false);
click('#reset-filters');
assert.deepEqual(rows().map(el=>el.dataset.platform),allPlatforms);
const followed = allPlatforms[0];
const followButton = [...doc.querySelectorAll('[data-follow]')].find(button => button.dataset.follow === followed);
followButton.click();click('#following-filter');
assert.deepEqual(rows().map(el=>el.dataset.platform),[followed]);
click('#reset-filters');
assert.equal(followButton.getAttribute('aria-pressed'),'true');
console.log('Homepage: one change section, no price tables, range/search/type/follow/reset and chronological order passed');

}

}
// Fixed fixtures exercise news aging, all platforms active today, and an empty digest.
function fixture(empty=false, allToday=false) {
 const row=(platform,items)=>`<article class="vendor-change-row" data-platform="${platform}"><div class="vendor-change-identity"><p></p></div><button data-follow="${platform}"></button><div class="vendor-change-body"><ul>${items.map(([text,type,date],i)=>`<li class="vendor-change-item" data-type="${type}" data-date="${date}" data-order="${i}">${text}</li>`).join('')}</ul><details class="vendor-change-more"><summary></summary><ul></ul></details></div></article>`;
 return `<section data-latest-date="2035-01-08"><input id="signal-search"><select id="platform-filter"><option value=""></option></select><button id="following-filter"></button><button data-range="today"></button><button data-range="week"></button>${['all','release','pricing','sunset'].map(type=>`<button data-filter="${type}"></button>`).join('')}<p id="filter-status"></p><p id="change-range-note"></p><div id="filter-empty"><button id="reset-filters"></button></div><div id="digest">${empty?'':row('Fixture A',[['Orchid release','release','2035-01-08'],['Old sunset','sunset','2035-01-07'],['Price','pricing','2035-01-08'],['Extra','release','2035-01-07']])+row('Fixture B',[['Other news','release',allToday?'2035-01-08':'2035-01-07']])}</div><div id="signals"></div></section>`;
}
exercise(fixture());
exercise(fixture(false,true));
exercise(fixture(true));
exercise(readFileSync('dist/index.html','utf8'));
