#!/usr/bin/env python3
"""Backfill complete display strings with Spark; never translate source evidence."""
from __future__ import annotations
import argparse
import concurrent.futures
import importlib.util
import json
import os
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipeline'))
from english_translation import MODEL, SYSTEM, PROMPT_VERSION, HAN, protect, restore_and_validate, text_key, projected_texts, normalize_terms


def editorial_parts(source):
    if len(source)<64:return [source]
    return re.findall(r'[^，、（）；。！？\n]+|[，、（）；。！？\n]+',source) or [source]


def remask(text, protected):
    available={}
    for token,value in protected.items():available.setdefault(value,[]).append(token)
    if not available:return text
    pattern=re.compile('|'.join(re.escape(value) for value in sorted(available,key=len,reverse=True)))
    def replace(match):
        tokens=available[match[0]]
        return tokens.pop(0) if tokens else match[0]
    return pattern.sub(replace,text)


def translate_source(source, key, url, model, dynamic):
    parts=editorial_parts(source)
    if len(parts)==1:return dynamic.translate(source,key,url,model)
    translated=[]
    for part in parts:
        if not HAN.search(part):translated.append(part.translate(str.maketrans({'，':',','、':',','（':'(', '）':')','；':';','。':'.','！':'!','？':'?'})));continue
        entry=dynamic.translate(part,key,url,model)
        if entry['status']!='success':return {**entry,'source':source}
        translated.append(entry['translation'])
    _,protected=protect(source)
    try:
        value=restore_and_validate(source,remask(' '.join(translated),protected),protected)
        return {'source':source,'translation':value,'status':'success','model':model,'promptVersion':PROMPT_VERSION,'quantityVersion':2}
    except ValueError as error:
        return {'source':source,'status':'failed','model':model,'reason':str(error)}


def translate_batch(sources, key, url, model):
    prepared = [protect(s) for s in sources]
    messages = [{'id': str(i), 'text': pair[0]} for i, pair in enumerate(prepared)]
    prompt = SYSTEM + '\nThe input is a JSON array of independent translation requests. Return a JSON object mapping each id to its English translation. Preserve placeholders within each item. No Markdown fences.'
    payload = {'model': model, 'messages': [{'role':'system','content':prompt}, {'role':'user','content':json.dumps(messages,ensure_ascii=False)}], 'temperature':0.1, 'max_tokens':8192, 'enable_thinking':False, 'thinking':{'type':'disabled'}}
    translated = {}
    try:
        request = urllib.request.Request(url,data=json.dumps(payload).encode(),headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
        with urllib.request.urlopen(request,timeout=120) as response:
            choice=json.load(response)['choices'][0]
        if choice.get('finish_reason')!='stop': raise ValueError('incomplete')
        raw=choice['message']['content'].strip()
        if raw.startswith('```'): raw=raw.split('\n',1)[1].rsplit('```',1)[0]
        values=json.loads(raw)
        for i,source in enumerate(sources):
            try: translated[source]=restore_and_validate(source,values[str(i)],prepared[i][1])
            except (ValueError,KeyError,TypeError): pass
    except Exception:
        # Provider bodies, credentials and unvalidated responses are never logged.
        pass
    missing=[s for s in sources if s not in translated]
    return translated,missing


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--sources',type=Path,default=ROOT/'site/src/data/ui-translation-sources.json')
    parser.add_argument('--output',type=Path,default=ROOT/'site/src/data/ui-translations-en.json')
    parser.add_argument('--cache',type=Path)
    parser.add_argument('--check',action='store_true')
    parser.add_argument('--batch-only',action='store_true')
    parser.add_argument('--retry-only',action='store_true')
    args=parser.parse_args()
    if args.cache is None:
        from data_location import data_path
        args.cache=data_path(ROOT,'data/derived/translations/ui-en.json')
    sources=json.loads(args.sources.read_text())['texts']
    existing=json.loads(args.output.read_text()) if args.output.exists() else {'schemaVersion':1,'model':MODEL,'texts':{}}
    texts=existing['texts']
    cache=json.loads(args.cache.read_text()) if args.cache.exists() else {'schemaVersion':1,'entries':{}}
    validated=projected_texts(cache)
    texts={s:t for s,t in texts.items() if '万亿' not in s or s in validated}
    texts.update(validated)
    pending=[s for s in sources if s not in texts]
    print(json.dumps({'required':len(sources),'pending':len(pending),'model':MODEL}),flush=True)
    if args.check: return int(bool(pending))
    key=os.environ.get('TRANSLATION_API_KEY','')
    if not key: raise SystemExit('TRANSLATION_API_KEY is required; no source text was replaced.')
    model=os.environ.get('TRANSLATION_MODEL',MODEL)
    if not model.startswith('spark-'): raise SystemExit('This backfill requires the Spark model.')
    url=os.environ.get('TRANSLATION_URL','https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions')
    spec=importlib.util.spec_from_file_location('translate_dynamic',ROOT/'pipeline/scripts/translate-dynamic-en.py')
    dynamic=importlib.util.module_from_spec(spec);spec.loader.exec_module(dynamic)
    failed=[s for s in pending if len(s)>160]
    batch_sources=[s for s in pending if len(s)<=160]
    if args.retry_only:failed=pending;batch_sources=[]
    batches=[];batch=[];size=0
    for source in batch_sources:
        if batch and (len(batch)>=16 or size+len(source)>3000): batches.append(batch);batch=[];size=0
        batch.append(source);size+=len(source)
    if batch:batches.append(batch)
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True);args.cache.parent.mkdir(parents=True,exist_ok=True)
        for file,value in [(args.output,{'schemaVersion':1,'model':model,'texts':texts}),(args.cache,cache)]:
            temporary=file.with_name(file.name+'.tmp')
            temporary.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n');os.replace(temporary,file)
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tasks=[pool.submit(translate_batch,b,key,url,model) for b in batches]
        for index,future in enumerate(concurrent.futures.as_completed(tasks),1):
            good,missing=future.result();texts.update({source:normalize_terms(source,value) for source,value in good.items()});failed.extend(missing)
            for source,value in good.items():cache['entries'][text_key(source)]={'source':source,'translation':value,'status':'success','model':model,'promptVersion':PROMPT_VERSION,'quantityVersion':2}
            save()
            if index%10==0: print(json.dumps({'batches':index,'validated':len(texts),'retry':len(failed)}),flush=True)
    print(json.dumps({'individualRetries':len(failed)}),flush=True)
    if args.batch_only:
        save();return 0
    failures=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tasks=[pool.submit(translate_source,source,key,url,model,dynamic) for source in failed]
        for index,future in enumerate(concurrent.futures.as_completed(tasks),1):
            entry=future.result()
            cache['entries'][text_key(entry['source'])]=entry
            if entry['status']=='success':texts[entry['source']]=normalize_terms(entry['source'],entry['translation'])
            else:failures+=1
            if index%10==0:
                save();print(json.dumps({'retriesCompleted':index,'remaining':len(failed)-index,'failed':failures}),flush=True)
        save()
    print(json.dumps({'translated':len(texts),'failed':failures}),flush=True)
    return int(bool(failures))

if __name__=='__main__':sys.exit(main())
