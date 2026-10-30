import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import {transform} from 'esbuild';
import {JSDOM} from 'jsdom';
const campaigns=JSON.parse(fs.readFileSync(new URL('../../packages/analytics/campaigns.json',import.meta.url),'utf8'));
const source=fs.readFileSync(new URL('../src/scripts/source-attribution.ts',import.meta.url),'utf8');
const code=(await transform(source.replace(/^import[^\n]+\n/,'const campaigns='+JSON.stringify(campaigns)+';\n').replace(/export /g,''),{loader:'ts'})).code;
function page(url,referrer){const dom=new JSDOM('',{url,referrer,runScripts:'outside-only'});dom.window.eval(code);return dom;}
test('source session retains first and latest channel without URLs, terms or identity',()=>{
 const d=page('https://daily.maas.click/?utm_source=google&q=secret','https://google.com/search?q=private');
 assert.deepEqual(JSON.parse(JSON.stringify(d.window.registrationSource())),{first:'search',last:'search'});
 d.window.history.replaceState({},'', '/subscription/?utm_source=chatgpt');
 assert.equal(d.window.registrationSource().last,'ai');
 const stored=d.window.sessionStorage.getItem('maas-source-session-v1');assert.ok(!/private|secret|google|chatgpt|https/.test(stored));
 d.window.localStorage.setItem('umami.disabled','1');assert.equal(d.window.registrationSource(),undefined);assert.equal(d.window.sessionStorage.length,0);d.window.close();
});
test('internal UTM cannot overwrite source, expired sessions reset and DNT disables attribution',()=>{
 const d=page('https://daily.maas.click/subscription/?utm_source=google','https://daily.maas.click/models/');
 d.window.sessionStorage.setItem('maas-source-session-v1',JSON.stringify({first:'ai',last:'ai',started:Date.now()}));
 assert.equal(d.window.registrationSource().last,'ai');
 d.window.sessionStorage.setItem('maas-source-session-v1',JSON.stringify({first:'ai',last:'ai',started:Date.now()-31*60000}));
 assert.equal(d.window.registrationSource().first,'unknown');
 Object.defineProperty(d.window.navigator,'doNotTrack',{value:'1'});assert.equal(d.window.registrationSource(),undefined);d.window.close();
});
test('blocked storage never breaks registration',()=>{
 const d=page('https://daily.maas.click/');Object.defineProperty(d.window,'sessionStorage',{get(){throw Error('blocked');}});
 assert.equal(d.window.registrationSource(),undefined);d.window.close();
});
test('Google AI referrals are distinct from search',()=>{
 const d=page('https://daily.maas.click/','https://gemini.google.com/app/private-chat');
 assert.equal(d.window.registrationSource().first,'ai');d.window.close();
});
test('account verification includes only source channels and password login is unchanged',async()=>{
 const d=page('https://daily.maas.click/?utm_source=google','https://google.com/search?q=private');
 const requests=[];d.window.fetch=async(url,init)=>{requests.push({url,init});return {ok:!url.endsWith('/me'),status:url.endsWith('/me')?401:200,json:async()=>({})};};
 const client=fs.readFileSync(new URL('../src/scripts/account-client.ts',import.meta.url),'utf8').replace(/^import[^\n]+\n/,'').replace(/export /g,'');
 d.window.eval((await transform(client,{loader:'ts'})).code);
 await d.window.accountApi('verify',{email:'test@example.test',code:'123456'});
 const body=JSON.parse(requests.find(r=>r.url.endsWith('/verify')).init.body);
 assert.deepEqual(body.attribution,{first:'search',last:'search'});
 await d.window.accountApi('login',{email:'test@example.test',password:'secret'});
 assert.equal(JSON.parse(requests.find(r=>r.url.endsWith('/login')).init.body).attribution,undefined);
 d.window.close();
});

test('only registered campaign IDs persist across internal navigation; arbitrary text is discarded',()=>{
 const d=page('https://daily.maas.click/?utm_source=wechat&utm_campaign=weekly-wechat-v1','https://weixin.qq.com/');
 assert.equal(d.window.registrationSource().firstCampaign,'weekly-wechat-v1');
 d.window.history.replaceState({},'', '/subscription/?utm_campaign=private@example.test');
 assert.equal(d.window.registrationSource().lastCampaign,'weekly-wechat-v1');
 assert.ok(!d.window.sessionStorage.getItem('maas-source-session-v1').includes('private'));
 d.window.localStorage.setItem('umami.disabled','1');assert.equal(d.window.registrationSource(),undefined);d.window.close();
});
test('server campaign allowlist matches canonical public config',()=>{
 const server=fs.readFileSync(new URL('../../services/agent-api/src/analytics-campaigns.ts',import.meta.url),'utf8');
 assert.deepEqual(JSON.parse(server.match(/= (\[.*\]);/)[1]),campaigns);
});
