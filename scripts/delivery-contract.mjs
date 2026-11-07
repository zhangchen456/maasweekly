import {parse} from '../site/node_modules/parse5/dist/index.js';
export {parse};
/** Assert delivered content, without emitting private text in failures or receipts. */
export function weeklyDelivery(html, parse) {
 const locales={};
 const find=n=>{const a=Object.fromEntries((n.attrs??[]).map(x=>[x.name,x.value]));if(a['data-weekly-locale']){if(locales[a['data-weekly-locale']])throw Error('duplicate weekly locale');locales[a['data-weekly-locale']]=n;}for(const c of n.childNodes??[])find(c);};find(parse(html));
 if(!locales.zh||!locales.en)throw Error('private weekly locale missing');
 const scan=root=>{let characters=0,han=0,headlines=0,body=false;
  const walk=(n,protectedParent=false)=>{const a=Object.fromEntries((n.attrs??[]).map(x=>[x.name,x.value]));const protectedNode=protectedParent||['script','style','pre','code','blockquote'].includes(n.tagName)||'data-original-language'in a;
   if((a.class??'').split(/\s+/).includes('report-body'))body=true;
   if((a.class??'').split(/\s+/).includes('headline-detail'))headlines++;
   if(n.nodeName==='#text'&&!protectedNode){characters+=n.value.trim().length;if(/[\u3400-\u9fff]/u.test(n.value))han++;}
   if(!protectedNode)for(const k of ['title','alt','aria-label'])if(/[\u3400-\u9fff]/u.test(a[k]??''))han++;
   for(const c of n.childNodes??[])walk(c,protectedNode);
  };walk(root);return {characters,han,headlines,body};};
 const zh=scan(locales.zh),en=scan(locales.en);
 if(!zh.body||!en.body||!zh.headlines||zh.headlines!==en.headlines||en.characters<20)throw Error('private weekly body incomplete');
 if(en.han||html.includes('English translation pending.'))throw Error('private weekly English incomplete');
 return {englishCharacters:en.characters,headlines:en.headlines,englishComplete:true};
}
export function publicWeekly(html) {
 if(/data-weekly-locale|data-private-weekly|class="report-body"/.test(html))throw Error('private weekly content in public preview');
}
