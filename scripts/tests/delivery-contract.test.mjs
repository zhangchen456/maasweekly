import {test} from 'node:test';
import assert from 'node:assert/strict';
import {parse} from '../../site/node_modules/parse5/dist/index.js';
import {weeklyDelivery,publicWeekly} from '../delivery-contract.mjs';
const fragment=(locale,text)=>`<div data-weekly-locale="${locale}"><div class="report-body"><div class="headline-detail">${text}</div></div></div>`;
const zh=fragment('zh','这里是中文报告的真实正文');
const english='This is the complete English report with verified sources.';
test('200 response and summary completeness cannot substitute for translated private body',()=>{
 assert.throws(()=>weeklyDelivery(zh+fragment('en','PRIVATE_SENTINEL 仍然没有翻译'),parse),e=>e.message==='private weekly English incomplete'&&!e.message.includes('SENTINEL'));
 assert.throws(()=>weeklyDelivery(zh,parse),/locale missing/);
 assert.throws(()=>weeklyDelivery(zh+fragment('en',''),parse),/body incomplete/);
 assert.equal(weeklyDelivery(zh+fragment('en',english),parse).englishComplete,true);
});
test('original evidence remains unchanged; untranslated editorial accessibility text fails',()=>{
 assert.equal(weeklyDelivery(zh+fragment('en',english+'<blockquote data-original-language>原文保留</blockquote>'),parse).englishComplete,true);
 assert.throws(()=>weeklyDelivery(zh+fragment('en',english+'<a title="未翻译">source</a>'),parse),/English incomplete/);
 publicWeekly('<p>Public preview</p>');assert.throws(()=>publicWeekly(zh),/private weekly content/);
});
