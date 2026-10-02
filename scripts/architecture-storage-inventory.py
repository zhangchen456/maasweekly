#!/usr/bin/env python3
"""Read-only logical/allocated byte inventory and dated raw-snapshot observations."""
import argparse
import json
import re
import statistics
import subprocess
from datetime import datetime,timezone
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]


def measure(root,paths):
    files=set()
    for name in paths:
        folder=root/name
        if folder.is_file():files.add(folder)
        elif folder.is_dir():files.update(p for p in folder.rglob('*') if p.is_file() and not p.is_symlink())
    return {'files':len(files),'bytes':sum(p.stat().st_size for p in files),'allocatedBytes':sum(p.stat().st_blocks*512 for p in files)}


def main():
    parser=argparse.ArgumentParser();parser.add_argument('output',type=Path);parser.add_argument('--root',type=Path,default=BASE);args=parser.parse_args();root=args.root.resolve()
    categories={
      'rawSnapshots':['data/snapshots'],
      'priceFactsAndEvents':['data/price-facts','data/price-records','data/price-record-revisions'],
      'sourceFactsAndRevisions':['data/records','data/record-revisions'],
      'evidenceAndSnapshotMetadata':['data/price-evidence','data/price-snapshots'],
      'retainedPublicReleases':['data/public/v1'],
      'standardInputs':['data/normalized','data/derived','data/editorial'],
      'siteCompatibilityProjection':['site/src/data'],
      'localReleasePackages':['dist-release'],
      'runtimeInputCheckpointCache':['data/input-manifests','data/input-objects']}
    report={'sampledAt':datetime.now(timezone.utc).isoformat(),'scope':'Read-only; logical bytes differ from filesystem allocation and Git history','categories':{k:measure(root,v) for k,v in categories.items()}}
    dates=[]
    for p in sorted((root/'data/snapshots').iterdir()):
        if p.is_dir() and re.fullmatch(r'\d{4}-\d{2}-\d{2}',p.name):dates.append({'date':p.name,**measure(root,[p.relative_to(root)])})
    report['datedSnapshots']=dates
    recent=dates[-14:];values=[p['bytes'] for p in recent]
    report['recentStoredRawBytesPerObservedDay']={'sampleCount':len(recent),'from':recent[0]['date'],'to':recent[-1]['date'],'median':statistics.median(values),'mean':statistics.mean(values),'min':min(values),'max':max(values),'interpretation':'Stored per-day raw bytes, not incremental Git pack size or future growth guarantee'}
    report['gitObjectStats']=subprocess.check_output(['git','-C',str(root),'count-objects','-vH'],text=True).strip()
    report['noHistoryRewrite']=True
    args.output.parent.mkdir(parents=True,exist_ok=True);args.output.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'categories':len(categories),'report':str(args.output)}))

if __name__=='__main__':main()
