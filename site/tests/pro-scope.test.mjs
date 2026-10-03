import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import { JSDOM } from 'jsdom';
import { transform } from 'esbuild';

test('scope checkboxes retain multiple choices, search preserves selection, import and save use all selected IDs', async () => {
  const source=fs.readFileSync(new URL('../src/pages/pro.astro',import.meta.url),'utf8');
  const dom=new JSDOM(source.split('---')[2].split('<script>')[0],{url:'http://localhost/pro/',runScripts:'outside-only'});
  const win=dom.window, doc=win.document, calls=[];
  let onChange;
  win.currentAccount=()=>({watches:[{modelId:'model-b'}]}); win.openAccountLogin=()=>{}; win.onAccountChange=fn=>{onChange=fn;};
  const models={models:[{modelId:'model-a',modelName:'Model A'},{modelId:'model-b',modelName:'Model B'}],families:[{familyId:'family-a',displayName:'Family A'}]};
  const settings={scope:{providers:['a'],models:[],families:[],topics:['price']},emailEnabled:false};
  win.fetch=async (url,options)=>{
    calls.push({url,body:options?.body?JSON.parse(options.body):null});
    const data=url==='/api/v1/models'?models:url==='/api/v1/status'?{status:{providers:[{providerId:'a',displayName:'Alpha'},{providerId:'b',displayName:'Beta'}]}}:url==='/api/pro/me'?{entitlement:{status:'active',source:'beta'},reports:[],settings,mailAvailable:true}:url==='/api/pro/settings'?{matching:[]}:{items:[]};
    return {ok:true,json:async()=>data};
  };
  const script=fs.readFileSync(new URL('../src/scripts/pro.ts',import.meta.url),'utf8').replace(/^import .*;\n/,'');
  win.eval((await transform(script,{loader:'ts'})).code);
  const settle=()=>new Promise(resolve=>setImmediate(resolve));
  try {
    onChange({});await settle();
    const check=(id,value)=>doc.querySelector(`#${id} input[value="${value}"]`);
    assert.equal(check('pro-providers','a').checked,true);
    check('pro-providers','b').click();assert.equal(check('pro-providers','a').checked,true);
    assert.equal(doc.getElementById('pro-providers-count').textContent,'已选 2 项');
    const search=doc.getElementById('pro-providers-search');search.value='Beta';search.dispatchEvent(new win.Event('input'));
    assert.equal(check('pro-providers','a').parentElement.hidden,true);assert.equal(check('pro-providers','a').checked,true);
    search.value='missing';search.dispatchEvent(new win.Event('input'));assert.equal(doc.getElementById('pro-providers-empty').hidden,false);
    doc.getElementById('pro-import').click();assert.equal(check('pro-models','model-b').checked,true);
    check('pro-models','model-a').click();
    doc.getElementById('pro-settings').dispatchEvent(new win.Event('submit',{cancelable:true}));await settle();
    const saved=calls.find(c=>c.url==='/api/pro/settings').body;
    assert.deepEqual(saved.scope.providers,['a','b']);assert.deepEqual(saved.scope.models,['model-a','model-b']);assert.equal(saved.emailEnabled,false);
    check('pro-providers','b').click();assert.equal(check('pro-providers','a').checked,true);assert.equal(doc.getElementById('pro-providers-count').textContent,'已选 1 项');
    onChange(null);assert.equal(doc.getElementById('pro-settings-panel').hidden,true);
  } finally {win.close();}
});
