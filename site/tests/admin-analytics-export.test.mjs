import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {transform} from 'esbuild';
import {JSDOM} from 'jsdom';
const source=fs.readFileSync(new URL('../src/lib/admin-analytics-export.ts',import.meta.url),'utf8');
const code=(await transform(source,{loader:'ts',format:'esm'})).code;
const {csvCell,analyticsCsv}=await import('data:text/javascript;base64,'+Buffer.from(code).toString('base64'));
const coverage={availability:'partial',completeSince:'2026-10-30T12:00:00Z'};
const rate={numerator:0,denominator:0,immature:1,rate:null,status:'no_denominator'};
function fixture(){return {range:{from:'2026-10-25',to:'2026-10-31',timezone:'Asia/Shanghai',end:1793400000000},website:{availability:'unavailable',reason:'not_configured',stats:null,lastSuccessAt:null},business:{asOf:'2026-10-31T00:00:00Z',coverage,registrations:{count:0},profilesCreated:0,betaActivated:0,professionalReads:{requests:0,accounts:0},exports:{requests:0,accounts:0},events:[],weekly:{items:[],truncated:false},valueActivation7d:rate,activation7d:rate,retentionWeek4:rate,valueUsage:{activeAccounts:0,returningAccounts:0},accountActions:{...coverage,items:[]},freeFunnel:{...coverage,windowDays:7,weekly:[{weekStart:'2026-10-26',registered:1,mature:0,immature:1,used:0,returned:0,useRate:null,returnRate:null}],items:[]},agents:{...coverage,failures:0,items:[]},dataHealth:{requestCollection:{lastSuccessAt:null,failures:0,lastFailureAt:null},lastRecorded:{registration:null,accountAction:null,coreUsage:null},requestDays:[]}}};}
test('CSV preserves unknown vs zero, cohort denominators and coverage without raw identities',()=>{
 const data=fixture();data.privateEmail='never-export@example.test';
 const csv=analyticsCsv(data);assert.ok(csv.startsWith('\ufeff'));assert.ok(csv.includes('"浏览量","","次","unavailable"'));assert.ok(csv.includes('"新注册","0","账号","partial"'));assert.ok(csv.includes('"7天使用率","","比例0至1","insufficient_sample"'));assert.ok(csv.includes('分母=已满7天注册账号'));assert.ok(csv.includes('Search Console'));assert.ok(!csv.includes(data.privateEmail));
});
test('CSV protects formula prefixes, quotes, commas and multiline labels',()=>{
 for(const text of ['=HYPERLINK("x")',' +1','\t@SUM(1)','-cmd','\n=1'])assert.ok(csvCell(text).startsWith('"\''));
 assert.equal(csvCell('a,"b"\nc'),'"a,""b""\nc"');assert.equal(csvCell(0),'"0"');assert.equal(csvCell(null),'""');
});
test('export reauthorizes and cannot download after role revocation',async()=>{
 const ids=['status','health','website-state','website','pages','sources','coverage','business','weekly','agents','cohorts'];
 const d=new JSDOM(`<div id="admin-private"></div><form id="analytics-filter"><select name="preset"><option value="7">7</option></select><input name="from"><input name="to"><button id="analytics-export" type="button" disabled>Export</button></form>${ids.map(id=>`<div id="analytics-${id}"></div>`).join('')}`,{url:'https://daily.maas.click/admin/analytics/',runScripts:'outside-only'});
 const win=d.window;let calls=0,downloads=0;
 win.adminApi=async()=>{calls++;if(calls>1)throw new win.AdminApiError('revoked',403);return fixture();};
 win.AdminApiError=class extends Error{constructor(message,status){super(message);this.status=status;}};win.analyticsCsv=analyticsCsv;
 win.URL.createObjectURL=()=>{downloads++;return 'blob:test';};
 const client=fs.readFileSync(new URL('../src/lib/admin-analytics-client.ts',import.meta.url),'utf8').replace(/^import .*;\n/gm,'');
 win.eval((await transform(client,{loader:'ts',format:'iife'})).code);
 win.document.dispatchEvent(new win.CustomEvent('maas:admin-ready'));await new Promise(r=>setTimeout(r,10));
 const button=win.document.getElementById('analytics-export');assert.equal(button.disabled,false);button.click();await new Promise(r=>setTimeout(r,10));
 assert.equal(calls,2);assert.equal(downloads,0);assert.equal(button.disabled,true);assert.equal(win.document.getElementById('admin-private').hidden,true);d.window.close();
});
