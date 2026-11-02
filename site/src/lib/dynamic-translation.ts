import {privateTranslations} from './translation-server';
import uiCatalog from '../data/ui-translations-en.json' with { type: 'json' };
import reviewed from '../data/editorial-translations-en.json' with { type: 'json' };
import { siteRuntime } from './runtime.ts';
import { readFileSync } from 'node:fs';
import path from 'node:path';
const pendingTranslation = 'English translation pending. Please see the Chinese version for the original.';
// Offline translations are loaded once per immutable build.
const editorialFields = new Set(['text','logo_summary','theme','title','body','story','llm_summary']);
let translations: Record<string,string> | undefined;
function dictionary() {
  if(siteRuntime())return (siteRuntime()!.projection('translations-en.json') as {texts:Record<string,string>}).texts;
  if (!translations) {
    try {
      const value = JSON.parse(readFileSync(path.resolve(process.cwd(),'src/data/translations-en.json'),'utf8'));
      if (value.schemaVersion !== 1 || !value.texts || typeof value.texts !== 'object') throw new Error('Malformed English translation projection');
      translations = value.texts;
    } catch (error) {
      if ((error as NodeJS.ErrnoException).code !== 'ENOENT') throw error;
      translations = {};
    }
  }
  return translations!;
}
/** Translate complete editorial fields before markup splits model names into code spans. */
export function localizeEditorial<T>(value:T, locale:'zh'|'en'):T {
  if (locale !== 'en') return value;
  const texts = dictionary();
  const walk = (item:unknown, field=''):unknown => {
    if (typeof item === 'string') {
      if (!editorialFields.has(field) || !/[\u3400-\u9fff]/.test(item)) return item;
      const translated=reviewed.texts[item as keyof typeof reviewed.texts] ?? texts[item] ?? privateTranslations()[item] ?? uiCatalog.texts[item as keyof typeof uiCatalog.texts] ?? pendingTranslation;
      return /[\u3400-\u9fff]/.test(translated) ? pendingTranslation : translated;
    }
    if (Array.isArray(item)) return item.map(child=>walk(child,field));
    if (item && typeof item === 'object') return Object.fromEntries(Object.entries(item).map(([key,child])=>[key,walk(child,key)]));
    return item;
  };
  return walk(value) as T;
}

/** Rule summaries quote source evidence; missing editorial translation is not an error for them. */
export function localizeRecordSummary(record:{summary?:string|null;summaryOrigin?:string|null},locale:'zh'|'en'):string {
  const source=record.summary??'';
  const text=localizeEditorial({text:source},locale).text;
  if(locale==='en'&&record.summaryOrigin==='rule'&&text===pendingTranslation)
    return 'This is an original source excerpt. Review the source evidence or open the official source in its original language.';
  return text;
}
