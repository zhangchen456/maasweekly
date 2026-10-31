import fs from 'node:fs';
import publicCatalog from '../data/ui-translations-en.json' with { type: 'json' };
import {createUiTranslator,englishHtml} from './ui-translation';
let privateTexts:Record<string,string> = {};
let signature:string|undefined;
let translator=createUiTranslator(publicCatalog.texts);
/** Private catalogs are atomically replaced independently of code deployments. */
export function privateTranslations() {
  const path=process.env.MAAS_PRIVATE_EN_TRANSLATIONS ?? '/srv/maasweekly/shared/translations/ui-en.json';
  let next:string;
  try {
    const stat=fs.statSync(path,{bigint:true});
    next=`${path}:${stat.dev}:${stat.ino}:${stat.size}:${stat.mtimeNs}`;
  } catch(error) {
    if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;
    next=`${path}:missing`;
  }
  if(next!==signature){
    let texts:Record<string,string>={};
    if(!next.endsWith(':missing')){
      const value=JSON.parse(fs.readFileSync(path,'utf8'));
      if(value.schemaVersion!==1||!value.texts||Array.isArray(value.texts)||typeof value.texts!=='object'||Object.values(value.texts).some(v=>typeof v!=='string'))throw new Error('Invalid private translation catalog');
      texts=value.texts;
    }
    const refreshed=createUiTranslator({...publicCatalog.texts,...texts});
    privateTexts=texts;translator=refreshed;signature=next;
  }
  return privateTexts;
}
export function englishServerUi(text:string){privateTranslations();return translator(text);}
export function englishServerHtml(html:string){privateTranslations();return englishHtml(html,translator);}
