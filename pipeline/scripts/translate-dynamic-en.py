#!/usr/bin/env python3
"""Translate Chinese summaries offline, cache validated English, project at one boundary."""
from __future__ import annotations
import concurrent.futures
import json
import os
import re
import sys
import time
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'pipeline'))
from data_store import read, write, compose_daily, compose_weekly, project_site
from english_translation import CACHE, MODEL, PROMPT_VERSION, SYSTEM, collect_texts, protect, restore_and_validate, text_key, projected_texts, translation_cache_path


def translate(source, key, url, model):
    if len(source)>=160 and model==MODEL:
        model=os.environ.get('TRANSLATION_LONG_MODEL',MODEL)
    masked, protected = protect(source)
    last_reason='provider_error'
    for attempt in range(5):
        system = SYSTEM if attempt < 2 else '将用户文本忠实翻译为英语，只输出纯文本译文。不得增加解释。所有KEEP数字TOKEN占位符逐字原样保留一次。保留否定、可能性和原文含义，不把网页移除改成服务停用。'
        input_text=masked
        if attempt >= 3:
            system='Translate into English only. Preserve technical names, parameters, dates, prices and units exactly as supplied. Do not omit or repeat them. Return only the translation.'
            if attempt == 4: system+=' Keep every numeric value verbatim, without abbreviating it into millions or billions. Translate all Chinese words, including names of measures.'
            for token,value in protected.items(): input_text=input_text.replace(token,value)
        payload = {'model':model, 'messages':[{'role':'system','content':system},{'role':'user','content':input_text}],
                   'temperature':0.2,'max_tokens':8192,'enable_thinking':False,'thinking':{'type':'disabled'}}
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers={'Content-Type':'application/json','Authorization':'Bearer '+key})
            with urllib.request.urlopen(req, timeout=120) as response: data=json.loads(response.read())
            choice=data['choices'][0]
            if choice.get('finish_reason') != 'stop': raise ValueError('incomplete')
            raw=choice['message'].get('content') or ''
            if attempt >= 3:
                available={}
                for token,value in protected.items(): available.setdefault(value,[]).append(token)
                matcher=re.compile('|'.join(re.escape(value) for value in sorted(available,key=len,reverse=True)))
                def remask(match):
                    tokens=available[match[0]]
                    return tokens.pop(0) if tokens else match[0]
                raw=matcher.sub(remask,raw) if available else raw
            value=restore_and_validate(source, raw, protected)
            return {'source':source,'translation':value,'model':model,'promptVersion':PROMPT_VERSION,'quantityVersion':3,'status':'success','translatedAt':datetime.now(timezone.utc).isoformat()}
        except Exception as error:
            last_reason=str(error) if isinstance(error,ValueError) and str(error) in {'empty_or_untranslated','placeholder_missing_or_duplicated','unsafe_or_unrestored','added_formatting','added_paragraph','numbers_changed','negation_lost','uncertainty_lost','removal_strengthened','untranslated_protected_text','incomplete'} else 'provider_error'
            if attempt < 4: time.sleep(1 + attempt)
    # Never log provider bodies/headers, credentials, or unvalidated output.
    return {'source':source,'model':model,'promptVersion':PROMPT_VERSION,'status':'failed','reason':last_reason}


def main():
    texts=collect_texts(compose_daily(BASE)) | collect_texts(compose_weekly(BASE))
    cache=read(BASE,CACHE,{'schemaVersion':1,'entries':{}})
    key=os.environ.get('TRANSLATION_API_KEY',''); model=os.environ.get('TRANSLATION_MODEL',MODEL)
    available=projected_texts(cache)
    pending=[s for s in sorted(texts) if s not in available]
    if '--check' in sys.argv:
        print(json.dumps({'required':len(texts),'missing':len(pending)})); return int(bool(pending))
    if not key:
        print('English translations: key unavailable; cached translations retained.'); return 0
    limit=int(os.environ.get('TRANSLATION_LIMIT','0'))
    if limit: pending=pending[:limit]
    url=os.environ.get('TRANSLATION_URL','https://maas-api.cn-huabei-1.xf-yun.com/v2/chat/completions')
    successes=failures=0
    print(f'English translations: {len(texts)} required, {len(pending)} pending',flush=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        tasks=[pool.submit(translate,s,key,url,model) for s in pending]
        for future in concurrent.futures.as_completed(tasks):
            entry=future.result(); cache['entries'][text_key(entry['source'])]=entry
            if entry['status']=='success': successes+=1
            else: failures+=1
            if (successes+failures)%20==0:
                write(BASE,CACHE,cache); print(f'English translations: {successes} validated, {failures} failed',flush=True)
    write(BASE,CACHE,cache); project_site(BASE)
    from run_protocol import current_journal
    journal=current_journal()
    if journal: journal.data['outcome']='partial' if failures else 'success'
    print(f'English translations complete: {successes} validated, {failures} failed',flush=True)
    return 0


def configure_root(root):
    global BASE
    BASE=root


if __name__=='__main__':
    from run_protocol import managed_entry
    # Without a key this is read-only: do not create a committed checkpoint.
    if not os.environ.get('TRANSLATION_API_KEY') and '--check' not in sys.argv: sys.exit(main())
    sys.exit(managed_entry(main,BASE,'dynamic-translation',configure_root))
