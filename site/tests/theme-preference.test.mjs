import fs from 'node:fs';
import vm from 'node:vm';
import assert from 'node:assert/strict';
const layout=fs.readFileSync('src/layouts/Layout.astro','utf8');
const script=layout.match(/<script is:inline>\s*(\(function[\s\S]*?)<\/script>/)[1];
for(const saved of [null,'system','light','dark','invalid']) for(const dark of [false,true]) {
 const root={dataset:{},style:{}};const select={value:''};const handlers={};
 const system={matches:dark,addEventListener:(_,fn)=>handlers.system=fn};let stored=saved;
 vm.runInNewContext(script,{document:{documentElement:root,querySelector:()=>select,addEventListener:(name,fn)=>handlers[name]=fn},window:{matchMedia:()=>system},localStorage:{getItem:()=>stored,setItem:(_,v)=>stored=v}});
 const pref=['light','dark'].includes(saved)?saved:'system';
 assert.equal(root.dataset.theme,pref==='system'?(dark?'dark':'light'):pref);
 system.matches=!dark;handlers.system();
 assert.equal(root.dataset.theme,pref==='system'?(!dark?'dark':'light'):pref);
 handlers['maas:appearance-restored']({detail:'system'});assert.equal(select.value,'system');assert.equal(stored,'system');
 handlers['maas:appearance-restored']({detail:'light'});system.matches=true;handlers.system();assert.equal(root.dataset.theme,'light');
}
console.log('Theme preference persistence, account restoration and live system changes passed');
