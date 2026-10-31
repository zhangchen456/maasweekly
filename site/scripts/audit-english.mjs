import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { parse, parseFragment, serialize } from 'parse5';
import { parse as parseJavaScript } from '@babel/parser';
import { build } from 'esbuild';
import { marked } from 'marked';

const site = path.resolve(process.env.MAAS_TRANSLATION_SITE ?? fileURLToPath(new URL('../', import.meta.url)));
import {displayTexts} from './english-audit-text.mjs';
export {displayTexts} from './english-audit-text.mjs';
const han = /[\u3400-\u9fff]/;
const attributes = ['title','placeholder','aria-label','aria-roledescription','alt'];
function files(root, extension) {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root,{withFileTypes:true}).flatMap(e => e.isDirectory() ? files(path.join(root,e.name),extension) : extension.test(e.name) ? [path.join(root,e.name)] : []);
}
async function translator() {
  const result = await build({entryPoints:[path.join(site,'src/lib/ui-translation.ts')],bundle:true,write:false,format:'cjs',platform:'node'});
  const module = {exports:{}};
  new Function('module','exports',result.outputFiles[0].text)(module,module.exports);
  return module.exports.englishUi;
}
export async function collectSources(dist) {
  const translate = await translator();
  const sources = new Set();
  const add = text => { const s=text.trim(); if (han.test(s) && han.test(translate(s)) && s !== '中文') sources.add(s); };
  for (const file of files(path.join(dist,'en'),/\.html$/)) {
    const original = path.join(dist,path.relative(path.join(dist,'en'),file));
    if (fs.existsSync(original)) for (const text of displayTexts(fs.readFileSync(original,'utf8'),{legacyEvidence:true})) add(text);
  }
  // Authenticated report bodies are collected separately on the server.
  // These are authored descriptions and reports, never the immutable evidence store.
  const dataFiles=[...files(path.join(site,'src/content/platforms'),/\.json$/),...files(path.join(site,'src/data/leaderboards'),/\.json$/),path.join(site,'src/data/industry_sources.json')];
  for (const file of dataFiles) if(fs.existsSync(file)) {
    const visit=value=>{
      if(typeof value==='string' && han.test(value)) add(value);
      else if(Array.isArray(value))value.forEach(visit);
      else if(value&&typeof value==='object')Object.values(value).forEach(visit);
    };visit(JSON.parse(fs.readFileSync(file,'utf8')));
  }
  const serviceFiles=['account-http.ts','account-store.ts','account-state.ts','pro-http.ts','pro-store.ts','payment-http.ts','payment-store.ts'].map(name=>path.resolve(site,'../services/agent-api/src',name)).filter(file=>fs.existsSync(file));
  for (const file of [...files(path.join(site,'src'),/\.(ts|astro)$/),...files(path.join(site,'public'),/\.js$/),...serviceFiles]) {
    if (file.includes('/lib/ui-') || file.includes('/admin/') || file.includes('/scripts/style-lab')) continue;
    const raw=fs.readFileSync(file,'utf8');
    const scripts=file.endsWith('.astro') ? [...raw.matchAll(/<script\b[^>]*>([\s\S]*?)<\/script>/g)].map(m=>m[1]) : [raw];
    for (const script of scripts) {
      let ast; try { ast=parseJavaScript(script,{sourceType:'unambiguous',plugins:['typescript']}); } catch { continue; }
      const visit=node=>{
        if (!node || typeof node!=='object') return;
        if (node.type==='StringLiteral' || node.type==='TemplateElement') {
          const value=node.type==='StringLiteral' ? node.value : node.value.cooked;
          if (value && han.test(value)) {
            if (value.includes('<')) {
              // HTML literals contain labels as well as markup; translate the labels only.
              const fragment=parseFragment(value); const walk=n=>{if(n.nodeName==='#text')add(n.value);for(const a of n.attrs??[])if(attributes.includes(a.name))add(a.value);for(const c of n.childNodes??[])walk(c);};walk(fragment);
            } else add(value);
          }
        }
        for (const [key,value] of Object.entries(node)) if (!['loc','start','end','extra','comments','tokens'].includes(key)) {if(Array.isArray(value))value.forEach(visit);else if(value&&typeof value==='object')visit(value);}
      };visit(ast);
    }
  }
  return [...sources].sort();
}
export function auditEnglish(dist) {
  const failures=[];let pages=0,protectedBlocks=0;
  const originals=html=>{
    const result=[];
    const walk=node=>{
      if((node.attrs??[]).some(a=>a.name==='data-original-language') || node.tagName==='blockquote') {result.push(serialize(node));return;}
      for(const child of node.childNodes??[])walk(child);
    };walk(parse(html));return result;
  };
  for(const file of files(path.join(dist,'en'),/\.html$/)) {
    pages++;
    const html=fs.readFileSync(file,'utf8');
    const texts=displayTexts(html);
    const originalFile=path.join(dist,path.relative(path.join(dist,'en'),file));
    const evidence=originals(html);protectedBlocks+=evidence.length;
    if(fs.existsSync(originalFile) && JSON.stringify(evidence)!==JSON.stringify(originals(fs.readFileSync(originalFile,'utf8')))) texts.push('[Original evidence differs from the Chinese page]');
    if(texts.length)failures.push({page:path.relative(dist,file),texts:[...new Set(texts)]});
  }
  return {pages,protectedBlocks,failedPages:failures.length,failures};
}
if (process.argv[1] && path.resolve(process.argv[1])===fileURLToPath(import.meta.url)) {
  const dist=path.resolve(site,process.env.MAAS_AUDIT_DIST ?? 'dist');
  if(process.argv.includes('--collect')) {
    const sources=await collectSources(dist);
    const output=process.argv.includes('--output') ? process.argv[process.argv.indexOf('--output')+1] : path.join(site,'src/data/ui-translation-sources.json');
    if(process.argv.includes('--merge') && fs.existsSync(output)) { const previous=JSON.parse(fs.readFileSync(output,'utf8')); if(previous.scope!=='public')throw new Error('Only explicitly public sources may be merged');sources.push(...previous.texts); }
    fs.writeFileSync(output,JSON.stringify({schemaVersion:1,scope:'public',texts:[...new Set(sources)].sort()},null,2)+'\n');
    console.log(JSON.stringify({required:new Set(sources).size,output}));
  } else {
    const report=auditEnglish(dist);
    const output=process.argv.includes('--output') ? process.argv[process.argv.indexOf('--output')+1] : null;
    if(output)fs.writeFileSync(output,JSON.stringify(report,null,2)+'\n');
    console.log(JSON.stringify({pages:report.pages,protectedBlocks:report.protectedBlocks,failedPages:report.failedPages,examples:report.failures.slice(0,5)}));
    process.exitCode=report.pages && !report.failedPages ? 0 : 1;
  }
}
