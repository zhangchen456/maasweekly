import fs from 'node:fs';
import publicCatalog from '../data/ui-translations-en.json' with { type: 'json' };
import {createUiTranslator,englishHtml} from './ui-translation';
let privateTexts:Record<string,string>|undefined;
/** Paid-report translations are server data, never public code or assets. */
export function privateTranslations() {
  if(!privateTexts){
    try {
      const value=JSON.parse(fs.readFileSync(process.env.MAAS_PRIVATE_EN_TRANSLATIONS ?? '/srv/maasweekly/shared/translations/ui-en.json','utf8'));
      if(value.schemaVersion!==1||!value.texts||typeof value.texts!=='object')throw new Error('Invalid private translation catalog');
      privateTexts=value.texts;
    } catch(error){if((error as NodeJS.ErrnoException).code!=='ENOENT')throw error;privateTexts={};}
  }
  return privateTexts!;
}
export const englishServerUi=createUiTranslator({...publicCatalog.texts,...privateTranslations()});
export const englishServerHtml=(html:string)=>englishHtml(html,englishServerUi);
