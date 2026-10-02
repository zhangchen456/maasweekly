#!/usr/bin/env python3
"""Local migration tooling. Explicit manifest/copy/verify/restore/cleanup-plan stages; no delete or remote enable."""
import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE/'pipeline'))
from blob_store import FilesystemBlobStore, CachedBlobReader
from storage_migration import build_manifest, validate_manifest, copy_objects, verify_objects, restore, cleanup_plan
from input_snapshot import atomic


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    create = commands.add_parser('manifest'); create.add_argument('--source-root',type=Path,default=BASE); create.add_argument('--commit',required=True); create.add_argument('--output',type=Path,required=True)
    for name in ('copy','verify','restore'):
        command = commands.add_parser(name); command.add_argument('--manifest',type=Path,required=True); command.add_argument('--blob-root',type=Path,required=True); command.add_argument('--report',type=Path,required=True)
        if name=='copy': command.add_argument('--source-root',type=Path,default=BASE); command.add_argument('--failed-report',type=Path); command.add_argument('--max-objects',type=int)
        if name=='restore': command.add_argument('--destination',type=Path,required=True); command.add_argument('--cache',type=Path,required=True); command.add_argument('--cache-mib',type=int,default=64); command.add_argument('--max-files',type=int)
    cleanup=commands.add_parser('cleanup-plan'); cleanup.add_argument('--manifest',type=Path,action='append',required=True); cleanup.add_argument('--blob-root',type=Path,required=True); cleanup.add_argument('--grace-days',type=int,default=14); cleanup.add_argument('--report',type=Path,required=True)
    args=parser.parse_args(); start=time.monotonic()
    if args.command=='manifest':
        root=args.source_root.resolve()
        actual=subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()
        if actual!=args.commit: raise ValueError('source HEAD differs from fixed commit')
        dirty=subprocess.check_output(['git','-C',str(root),'status','--porcelain','--','data/snapshots','data/price-snapshots','data/price-evidence','data/public/v1'],text=True)
        if dirty: raise ValueError('migration sources differ from fixed commit')
        result=build_manifest(root,args.commit)
        if subprocess.check_output(['git','-C',str(root),'status','--porcelain','--','data/snapshots','data/price-snapshots','data/price-evidence','data/public/v1'],text=True).strip(): raise ValueError('source changed during manifest capture')
        if subprocess.check_output(['git','-C',str(root),'rev-parse','HEAD'],text=True).strip()!=args.commit: raise ValueError('source commit changed during capture')
        output=args.output
    elif args.command=='cleanup-plan':
        result=cleanup_plan(args.blob_root,[json.loads(p.read_text()) for p in args.manifest],now=time.time(),grace_seconds=args.grace_days*86400);output=args.report
    else:
        manifest=validate_manifest(json.loads(args.manifest.read_text()));store=FilesystemBlobStore(args.blob_root)
        if args.command=='copy':
            only={row['sha256'] for row in json.loads(args.failed_report.read_text())['failures']} if args.failed_report else None
            result=copy_objects(args.source_root.resolve(),manifest,store,only=only,max_objects=args.max_objects)
        elif args.command=='verify': result=verify_objects(manifest,store)
        else:
            cache=CachedBlobReader(store,args.cache,args.cache_mib*1024*1024)
            result=restore(args.destination.resolve(),manifest,cache,max_files=args.max_files)
            result.update(cacheHits=cache.hits,cacheMisses=cache.misses,cacheBytes=cache.prune())
        output=args.report; result.update(migrationVersion=manifest['migrationVersion'],elapsedSeconds=time.monotonic()-start)
    atomic(output,(json.dumps(result,ensure_ascii=False,indent=2)+'\n').encode())
    print(json.dumps({'command':args.command,'report':str(output),'elapsedSeconds':time.monotonic()-start}))
    return 2 if result.get('failures') or result.get('complete') is False else 0

if __name__=='__main__':
    try: raise SystemExit(main())
    except (OSError,ValueError,KeyError) as error:
        print('storage operation failed: '+type(error).__name__,file=sys.stderr);raise SystemExit(2)
