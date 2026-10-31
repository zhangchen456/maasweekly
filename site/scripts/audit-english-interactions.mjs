import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { JSDOM } from 'jsdom';
import { build } from 'esbuild';
import { displayTexts } from './audit-english.mjs';

const site=fileURLToPath(new URL('../',import.meta.url));
const failures=[];
async function script(entry){const result=await build({entryPoints:[path.join(site,entry)],bundle:true,write:false,format:'iife',platform:'browser'});return result.outputFiles[0].text;}
const observer=await script('src/scripts/ui-translation.ts');
const pause=()=>new Promise(resolve=>setTimeout(resolve,0));
function page(route){
  const dom=new JSDOM(fs.readFileSync(path.join(site,'dist/en',route,'index.html'),'utf8'),{url:'https://daily.maas.click/en/'+route+'/',runScripts:'outside-only',pretendToBeVisual:true});
  dom.window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}});
  dom.window.fetch=async()=>({ok:false,status:401,json:async()=>({message:'请先登录'})});
  dom.window.HTMLElement.prototype.scrollIntoView=function(){};
  dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true;};
  dom.window.HTMLDialogElement.prototype.close=function(){this.open=false;};
  dom.window.eval(observer);return dom;
}
function check(dom,step){const texts=displayTexts(dom.window.document.documentElement.outerHTML);if(texts.length)failures.push({step,texts:[...new Set(texts)]});}

const pricing=page('pricing');const pd=pricing.window.document;
const ledger=pd.querySelector('#goal-data').textContent;
pricing.window.eval(await script('src/scripts/price-workspace.ts'));await pause();check(pricing,'pricing: initial workspace');
for(const button of [...pd.querySelectorAll('#providers button')]){button.click();await pause();check(pricing,'pricing: provider '+button.textContent.trim());}
const search=pd.querySelector('#search');search.value='no-such-model';search.dispatchEvent(new pricing.window.Event('input',{bubbles:true}));await pause();check(pricing,'pricing: empty search');
search.value='';search.dispatchEvent(new pricing.window.Event('input',{bubbles:true}));await pause();
pd.querySelector('#clear')?.click();await pause();check(pricing,'pricing: clear comparison');
if(pd.querySelector('#goal-data').textContent!==ledger)throw Error('Original pricing data changed during translation');
pricing.window.close();

const boards=page('leaderboards');const bd=boards.window.document;
boards.window.eval(await script('src/scripts/leaderboards.ts'));await pause();check(boards,'rankings: initial');
for(const button of bd.querySelectorAll('[data-board]')){button.click();await pause();check(boards,'rankings: switch '+button.dataset.board);}
for(const widget of bd.querySelectorAll('.rank-widget')){
  const input=widget.querySelector('input[type=search]');input.value='no-such-model';input.dispatchEvent(new boards.window.Event('input'));await pause();
  input.value='';input.dispatchEvent(new boards.window.Event('input'));widget.querySelector('[data-sort]')?.click();
  for(const box of [...widget.querySelectorAll('.compare-check')].slice(0,3)){box.click();await pause();}
  check(boards,'rankings: search, sort and compare');widget.querySelector('.clear-compare')?.click();
}
boards.window.close();
const output=process.argv.includes('--output')?process.argv[process.argv.indexOf('--output')+1]:null;
if(output)fs.writeFileSync(output,JSON.stringify({failures},null,2)+'\n');
console.log(JSON.stringify({checked:['pricing providers/search/comparison','ranking tabs/search/sort/comparison','original pricing payload'],failures:failures.length,examples:failures.slice(0,3)}));
process.exitCode=failures.length?1:0;
