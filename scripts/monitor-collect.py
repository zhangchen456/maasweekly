#!/usr/bin/env python3
"""Read fixed repository namespaces and sanitized stage receipts; emit bounded v1 inbox.
No network, secret access, arbitrary log paths, backfilling unknown timestamps or executions.
"""
import argparse
import hashlib
import json
import re
from datetime import datetime
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ID = re.compile(r'[a-zA-Z0-9:_-]{1,128}')
def safe_json(p, root):
    if p.is_symlink() or not p.resolve().is_relative_to(root.resolve()) or p.stat().st_size > 8*1024*1024: raise ValueError('unsafe monitor input')
    return json.loads(p.read_text())
def ms(value):
    if value is None: return None
    if isinstance(value, (float, int)): return int(value * 1000)
    try:
        d = datetime.fromisoformat(value.replace('Z', '+00:00'))
        return int(d.timestamp() * 1000) if d.tzinfo else None
    except (ValueError, TypeError): return None

def collect(root=ROOT, stages=None):
    registry = safe_json(root/'pipeline/config/source_registry.json',root)['sources']
    providers = safe_json(root/'pipeline/config/public_providers.json',root)
    sources = {s['source_id']: {'id': s['source_id'], 'name': s['display_name'] + ' / ' + s['type_label'], 'platform': providers['sourceToProvider'].get(s['source_id']) or 'unknown', 'kind': s['source_type'], 'budgetHours': 48} for s in registry}
    aliases = {('http_' + hashlib.sha256(u.encode()).hexdigest()[:24]): s['source_id'] for s in registry for u in [s.get('primary_url'),*s.get('url_aliases',[])] if u}
    aliases.update(providers['pricingSourceKeyToSourceId'])
    paths = []
    for namespace in ('pipeline-runs','price-runs'):
        paths.extend((root/'data'/namespace).glob('*/*.json'))
        paths.extend((root/'data'/namespace/'staging').glob('*/journal.json'))
    # Committed record wins over its staging journal. Never import mutable running journals.
    runs = {}; skipped = 0
    for p in sorted(paths, key=str):
        d = safe_json(p,root)
        if d.get('state') not in ('committed','interrupted','discarded'): skipped += 1; continue
        family = d.get('family') or ('prices' if 'price-runs' in p.parts else 'unknown')
        runid = d.get('runId') or d.get('run_id'); end = ms(d.get('completedAt') or d.get('committed_at')); start = ms(d.get('startedAt'))
        observed = end or ms(d.get('created_at')) or start
        if not runid or not ID.fullmatch(runid) or observed is None: skipped += 1; continue
        result = d.get('outcome','unknown'); state = 'failed' if result == 'failed' else 'needs_review' if d['state']=='interrupted' else 'cancelled' if d['state']=='discarded' else 'succeeded'
        observations = []
        raw_sources = d.get('sources') or {s['source_key']: s for s in d.get('source_states',[]) if 'source_key' in s}
        for key,s in raw_sources.items():
            sid = s.get('sourceId') or aliases.get(key,key)
            if not ID.fullmatch(sid): skipped += 1; continue
            if sid not in sources: sources[sid] = {'id':sid,'name':sid,'platform':sid.split(':')[0].split('-')[0],'kind':'unmapped','budgetHours':48}
            outcome = s.get('outcome') or {'ok':'success','failed':'failed','not_run':'not_run'}.get(s.get('status'),'unknown')
            # Offline replay proves parsing, never proves a new live fetch or new success time.
            if d.get('offline'): outcome = 'not_run'
            error = None
            if outcome == 'failed':
                error = 'parse_failed' if s.get('failurePhase')=='parse' or s.get('errorCode')=='schema_failed' else 'fetch_failed' if s.get('failurePhase')=='fetch' or s.get('errorCode')=='fetch_failed' else 'fetch_or_parse_failed'
                if error != 'fetch_or_parse_failed': outcome = error
            if outcome not in ('success','unchanged','failed','fetch_failed','parse_failed','not_run','unknown'): outcome = 'unknown'
            success = ms(s.get('lastSuccessAt') or s.get('last_success_at'))
            attempted = ms(s.get('latestAttemptAt') or s.get('latest_attempt_at'))
            if attempted is None and outcome not in ('not_run','unknown'):
                attempted = ms(s.get('snapshot',{}).get('fetched_at')) or (start if s.get('attemptId') else None)
            coverage = s.get('coverage') or ('full' if outcome in ('success','unchanged') else 'missing' if outcome in ('failed','fetch_failed','parse_failed') else 'unknown')
            coverage = {'failed':'missing'}.get(coverage,coverage)
            if s.get('validation')=='failed': coverage='partial'; error=error or 'validation_failed'
            if coverage not in ('full','partial','missing','unknown'): coverage='unknown'
            observations.append({'sourceId':sid,'attemptAt':attempted,'successAt':success,'dataThrough':ms(s.get('snapshot',{}).get('fetched_at')) if outcome in ('success','unchanged') else None,'outcome':outcome,'coverage':coverage,'errorCode':error})
        grouped = {}
        for observation in observations:
            sid = observation['sourceId']
            if sid not in grouped: grouped[sid] = observation; continue
            old = grouped[sid]
            for field in ('attemptAt', 'successAt', 'dataThrough'):
                old[field] = max((v for v in (old[field], observation[field]) if v is not None), default=None)
            # Registry aliases may share a logical source. Any failed endpoint remains visible.
            if observation['errorCode']:
                old.update(outcome=observation['outcome'], errorCode=observation['errorCode'])
            if old['coverage'] != observation['coverage']: old['coverage'] = 'partial'
        observations = list(grouped.values())
        record = {'id':runid,'kind':family,'trigger':{'schedule':'schedule','workflow_dispatch':'manual','workflow_call':'workflow','manual':'manual'}.get(d.get('trigger'),'unknown'),
                  'state':state,'stage':'archive-committed' if d['state']=='committed' else d['state'],'startedAt':start,'finishedAt':end,'observedAt':observed,
                  'inputVersion':d.get('baselinePointer',{}).get('inputVersion'),'outputVersion':d.get('inputVersion'),'result':result if result in ('success','partial','failed','unchanged','not_run','unknown') else 'unknown',
                  'validation':'failed' if any(s.get('validation')=='failed' for s in raw_sources.values()) else 'passed' if raw_sources and all(s.get('validation')=='passed' for s in raw_sources.values()) else 'unknown','publication':'not_run','errorCode':'interrupted' if state=='needs_review' else 'execution_failed' if state=='failed' else None,'runLink':d.get('runLink') if isinstance(d.get('runLink'),str) and re.fullmatch(r'https://github.com/[\w.-]+/[\w.-]+/actions/runs/\d+',d['runLink']) else None,'sources':sorted(observations,key=lambda x:x['sourceId'])}
        if d['state'] in ('interrupted', 'discarded'):
            # Immutable snapshots remain reviewable after the original journal is recovered.
            suffix = hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()[:12]
            runid = runid[:90] + '_' + d['state'] + '_' + suffix; record['id'] = runid
        if runid in runs and runs[runid] != record: raise ValueError('conflicting run receipts; inspect journal recovery')
        runs[runid]=record
    if stages:
        for p in sorted(stages.glob('stage_*.json')):
            d = safe_json(p, stages)
            if d.get('state') == 'running':
                d.update(state='needs_review',errorCode='interrupted')
                d['id'] += '_interrupted_' + hashlib.sha256(json.dumps(d,sort_keys=True).encode()).hexdigest()[:12]
            if d['id'] in runs and runs[d['id']] != d: raise ValueError('conflicting stage receipt')
            runs[d['id']] = d
    ordered = sorted(runs.values(), key=lambda r:(r['observedAt'],r['id']))
    # Split deterministic batches; no unreported truncation or renewed timestamp on reimport.
    batches=[]
    for offset in range(0,max(1,len(ordered)),100):
        payload={'sources':sorted(sources.values(),key=lambda s:s['id']),'runs':ordered[offset:offset+100]}
        h=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest()
        batches.append({'schemaVersion':1,'batchId':'batch_'+h,**payload})
    return batches,skipped

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input-root',type=Path,default=ROOT);ap.add_argument('--stages',type=Path);ap.add_argument('--output',type=Path,required=True);a=ap.parse_args()
    if not a.output.is_absolute() or a.output.is_symlink(): raise ValueError('private absolute output required')
    batches,skipped=collect(a.input_root,a.stages);a.output.mkdir(parents=True,exist_ok=True,mode=0o700)
    for b in batches:
        p=a.output/(b['batchId']+'.json');p.write_text(json.dumps(b,ensure_ascii=False,sort_keys=True)+'\n');p.chmod(0o600)
    print(json.dumps({'batches':len(batches),'runs':sum(len(b['runs']) for b in batches),'sources':len(batches[0]['sources']),'skippedWithoutReliableRecord':skipped}))
if __name__=='__main__':main()
