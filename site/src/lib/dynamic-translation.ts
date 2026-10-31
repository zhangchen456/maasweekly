import reviewed from '../data/editorial-translations-en.json' with { type: 'json' };
import { siteRuntime } from './runtime.ts';
import { readFileSync } from 'node:fs';
import path from 'node:path';
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
      return reviewed.texts[item as keyof typeof reviewed.texts] ?? texts[item] ?? 'English translation pending. Please see the Chinese version for the original.';
    }
    if (Array.isArray(item)) return item.map(child=>walk(child,field));
    if (item && typeof item === 'object') return Object.fromEntries(Object.entries(item).map(([key,child])=>[key,walk(child,key)]));
    return item;
  };
  return walk(value) as T;
}
