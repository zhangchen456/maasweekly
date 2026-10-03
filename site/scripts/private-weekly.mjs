import {readdir,readFile,writeFile,mkdir} from 'node:fs/promises';
import {fileURLToPath} from 'node:url';
import path from 'node:path';
/** Final publication gate: protected bodies never enter the static web root. */
export default function privateWeekly(){return {name:'private-weekly',hooks:{'astro:build:done':async({dir})=>{
 const root=fileURLToPath(dir),privateRoot=path.resolve(root,'../../data/private-weekly');await mkdir(privateRoot,{recursive:true});
 for(const locale of ['', 'en/']){const base=path.join(root,locale,'weekly');for(const id of await readdir(base)){
  if(!/^\d{4}-\d{2}-\d{2}$/.test(id))continue;
  const file=path.join(base,id,'index.html'),html=await readFile(file,'utf8');
  const match=html.match(/<template data-private-weekly[^>]*>([\s\S]*?)<\/template>/);
  if(!match){if(id!=='2026-05-03')throw new Error('Missing private weekly payload: '+id);continue;}
  if(!locale)await writeFile(path.join(privateRoot,id+'.html'),match[1]);
  await writeFile(file,html.replace(match[0],''));
 }}
}}};}
