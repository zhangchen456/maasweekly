#!/usr/bin/env python3
"""Backfill complete display strings with Spark; never translate source evidence."""
from __future__ import annotations
import argparse
import concurrent.futures
import importlib.util
import json
import os
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'pipeline'))
from english_translation import MODEL, SYSTEM, protect, restore_and_validate, text_key


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
    parser.add_argument('--cache',type=Path,default=ROOT/'data/derived/translations/ui-en.json')
    parser.add_argument('--check',action='store_true')
    args=parser.parse_args()
    sources=json.loads(args.sources.read_text())['texts']
    existing=json.loads(args.output.read_text()) if args.output.exists() else {'schemaVersion':1,'model':MODEL,'texts':{}}
    texts=existing['texts']
    cache=json.loads(args.cache.read_text()) if args.cache.exists() else {'schemaVersion':1,'entries':{}}
    for source in sources:
        row=cache['entries'].get(text_key(source),{})
        if row.get('source')==source and row.get('status')=='success': texts[source]=row['translation']
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
    batches=[];batch=[];size=0
    for source in pending:
        if batch and (len(batch)>=16 or size+len(source)>3000): batches.append(batch);batch=[];size=0
        batch.append(source);size+=len(source)
    if batch:batches.append(batch)
    def save():
        args.output.parent.mkdir(parents=True,exist_ok=True);args.cache.parent.mkdir(parents=True,exist_ok=True)
        args.output.write_text(json.dumps({'schemaVersion':1,'model':model,'texts':texts},ensure_ascii=False,indent=2)+'\n')
        args.cache.write_text(json.dumps(cache,ensure_ascii=False,indent=2)+'\n')
    failed=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        tasks=[pool.submit(translate_batch,b,key,url,model) for b in batches]
        for index,future in enumerate(concurrent.futures.as_completed(tasks),1):
            good,missing=future.result();texts.update(good);failed.extend(missing)
            for source,value in good.items():cache['entries'][text_key(source)]={'source':source,'translation':value,'status':'success','model':model}
            save()
            if index%10==0: print(json.dumps({'batches':index,'validated':len(texts),'retry':len(failed)}),flush=True)
    print(json.dumps({'individualRetries':len(failed)}),flush=True)
    failures=0
    with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
        for entry in pool.map(lambda source:dynamic.translate(source,key,url,model),failed):
            cache['entries'][text_key(entry['source'])]=entry
            if entry['status']=='success':texts[entry['source']]=entry['translation']
            else:failures+=1
            save()
    print(json.dumps({'translated':len(texts),'failed':failures}),flush=True)
    return int(bool(failures))

if __name__=='__main__':sys.exit(main())
