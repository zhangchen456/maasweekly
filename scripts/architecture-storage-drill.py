#!/usr/bin/env python3
"""Blank-environment local blob restore and build proof; fixed Git code+metadata, no production writes."""
import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'pipeline'))
from blob_store import FilesystemBlobStore, CachedBlobReader, checksum, safe_path
from storage_migration import build_manifest, copy_objects, verify_objects, restore, cleanup_plan
from snapshot_reader import SnapshotReader
from input_snapshot import assert_no_pending


def run(argv,cwd,output):
    start=time.monotonic()
    with output.open('w') as stream: result=subprocess.run(argv,cwd=cwd,stdout=stream,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'drill stage failed ({result.returncode}): {output.name}')
    return {'command':argv,'exitCode':result.returncode,'elapsedSeconds':time.monotonic()-start,'log':output.name,'logSha256':checksum(output.read_bytes())}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--source',type=Path,default=BASE);parser.add_argument('--commit',required=True);parser.add_argument('--workspace',type=Path,required=True);parser.add_argument('--evidence',type=Path,required=True);args=parser.parse_args()
    source=args.source.resolve();workspace=args.workspace.resolve();evidence=args.evidence.resolve();workspace.mkdir(parents=True,exist_ok=True);evidence.mkdir(parents=True,exist_ok=True)
    head=subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()
    if head!=args.commit:raise ValueError('source HEAD differs from pinned commit')
    if subprocess.check_output(['git','-C',str(source),'status','--porcelain','--','data'],text=True).strip():raise ValueError('source data differs from pinned commit')
    manifest=build_manifest(source,args.commit);(evidence/'migration-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n')
    store=FilesystemBlobStore(workspace/'blobs');report={'sourceCommit':args.commit,'migrationVersion':manifest['migrationVersion'],'datasetVersion':manifest['datasetVersion'],'scope':'Local filesystem only; original Git data and production releases untouched'}
    start=time.monotonic();partial=copy_objects(source,manifest,store,max_objects=7);assert not partial['complete'];report['partialCopy']=partial
    check=verify_objects(manifest,store);start_resume=time.monotonic();resume=copy_objects(source,manifest,store,only={x['sha256'] for x in check['failures']});assert resume['complete'];report['copyResume']={**resume,'elapsedSeconds':time.monotonic()-start_resume};report['copyTotalSeconds']=time.monotonic()-start
    check=verify_objects(manifest,store);assert not check['failures'];report['objectVerification']=check
    report['files']=len(manifest['files']);unique={x['rawSha256']:x['bytes'] for x in manifest['files'].values()};report['uniqueObjects']=len(unique);report['sourceBytes']=sum(x['bytes'] for x in manifest['files'].values());report['uniqueBytes']=sum(unique.values())
    report['legacyMissingRaw']=[{'snapshotId':sid,'contentHash':r['semanticContentHash'],'evidenceCount':len(r['evidenceIds'])} for sid,r in manifest['snapshots'].items() if r['rawState']=='legacy_raw_missing']
    # Keep all source archives/public retained versions in the metadata bundle; only raw snapshots move.
    destination=workspace/'restored'
    if destination.exists():raise ValueError('blank destination required')
    destination.mkdir();start=time.monotonic();metadata_bytes=metadata_files=0;skipped_links=[]
    process=subprocess.Popen(['git','-C',str(source),'archive','--format=tar',args.commit],stdout=subprocess.PIPE)
    with tarfile.open(fileobj=process.stdout,mode='r|') as archive:
        for member in archive:
            if member.name=='data/snapshots' or member.name.startswith('data/snapshots/'):continue
            if member.issym() or member.islnk():
                if member.name=='site/CLAUDE.md' and member.linkname=='AGENTS.md':
                    link=safe_path(destination,member.name);link.parent.mkdir(parents=True,exist_ok=True);link.symlink_to('AGENTS.md');continue
                if not member.name.startswith(('.claude/','.agents/')):raise ValueError('unexpected code symlink in recovery bundle')
                skipped_links.append(member.name);continue
            path=safe_path(destination,member.name)
            if member.isdir():path.mkdir(parents=True,exist_ok=True)
            elif member.isfile():
                path.parent.mkdir(parents=True,exist_ok=True)
                with archive.extractfile(member) as src,path.open('wb') as out:shutil.copyfileobj(src,out)
                path.chmod(member.mode);metadata_bytes+=member.size;metadata_files+=1
            else:raise ValueError('unexpected Git archive member')
    if process.wait():raise RuntimeError('Git code/metadata bundle failed')
    report['codeMetadataRecovery']={'files':metadata_files,'bytes':metadata_bytes,'elapsedSeconds':time.monotonic()-start,'skippedToolSymlinks':skipped_links}
    assert not (destination/'data/snapshots').exists()
    cache=CachedBlobReader(store,workspace/'cache',64*1024*1024);start=time.monotonic();partial_restore=restore(destination,manifest,cache,max_files=7);assert not partial_restore['complete'];report['partialRestore']=partial_restore
    try:assert_no_pending(destination)
    except ValueError:report['partialRestoreBuildBlocked']=True
    else:raise AssertionError('incomplete restore was buildable')
    resumed=restore(destination,manifest,cache);assert resumed['complete'];report['restore']={**resumed,'elapsedSeconds':time.monotonic()-start,'cacheHits':cache.hits,'cacheMisses':cache.misses,'cacheBytes':cache.prune()}
    # Both compatibility paths must yield the same exact bytes, not just display-equivalent HTML.
    legacy=SnapshotReader(source,manifest,cache);migrated=SnapshotReader(workspace/'no-legacy-files',manifest,cache)
    for logical in manifest['files']:assert legacy.get(logical)==migrated.get(logical)==(destination/logical).read_bytes()
    for ref in manifest['snapshots'].values():assert checksum((destination/ref['metadataPath']).read_bytes())==ref['metadataSha256']
    report['allRawAndMetadataBytesEqual']=True
    report['stages']=[]
    for label,argv in [('records',[sys.executable,'pipeline/scripts/validate-archive.py']),('prices',[sys.executable,'pipeline/scripts/validate-price-archive.py','--check']),('export',[sys.executable,'pipeline/scripts/export-public-data.py'])]:report['stages'].append(run(argv,destination,evidence/(label+'.txt')))
    original=json.loads((source/'data/public/v1/manifest.json').read_text());rebuilt=json.loads((destination/'data/public/v1/manifest.json').read_text());assert original['datasetVersion']==rebuilt['datasetVersion'];comparisons=[]
    for entry in original['files']:
        other=next(f for f in rebuilt['files'] if Path(f['path']).name==Path(entry['path']).name)
        assert (source/'data/public/v1'/entry['path']).read_bytes()==(destination/'data/public/v1'/other['path']).read_bytes()
        comparisons.append({'collection':Path(entry['path']).name,'sha256':entry['sha256'],'bytesEqual':True})
    report['publicCollections']=comparisons;report['retainedVersionPathsPreserved']=sorted(p.name for p in (source/'data/public/v1/releases').iterdir())==sorted(p.name for p in (destination/'data/public/v1/releases').iterdir())
    # Dependency cache is copied from the locked local environment; it is not recovered business input.
    shutil.copytree(source/'site/node_modules',destination/'site/node_modules',symlinks=True)
    report['stages'].append(run(['npm','run','build'],destination/'site',evidence/'site-build.txt'))
    report['builtHtmlFiles']=sum(1 for p in (destination/'site/dist').rglob('*.html'))
    # Missing/corrupt/unavailable object failures leave isolated candidates unbuildable.
    digest=next(iter(unique));original_blob=store.get(digest);faults=[]
    for kind in ('missing','corrupt','unreachable'):
        target=workspace/('fault-'+kind)
        if kind=='missing':store.path(digest).unlink()
        elif kind=='corrupt':store.path(digest).write_bytes(b'corrupt')
        class Unreachable:
            def get(self,*args,**kwargs):raise OSError('unreachable test store')
        try:restore(target,manifest,Unreachable() if kind=='unreachable' else store)
        except (OSError,ValueError):
            try:assert_no_pending(target)
            except ValueError:faults.append({'kind':kind,'candidateBlocked':True})
            else:raise AssertionError('fault candidate not blocked')
        else:raise AssertionError('fault did not fail')
        if kind in ('missing','corrupt'):
            store.path(digest).unlink(missing_ok=True);store.putIfAbsent(digest,original_blob)
    report['faults']=faults
    orphan=b'orphan only for cleanup dry run';orphan_hash=checksum(orphan);store.putIfAbsent(orphan_hash,orphan)
    cleanup=cleanup_plan(store.root,[manifest],now=time.time()+15*86400,grace_seconds=14*86400);assert [r['blobId'] for r in cleanup['candidates']]==['blob_'+orphan_hash];assert store.path(orphan_hash).exists();report['cleanupDryRun']=cleanup
    (evidence/'drill.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n');print(json.dumps({'files':report['files'],'uniqueBytes':report['uniqueBytes'],'builtHtmlFiles':report['builtHtmlFiles'],'evidence':str(evidence)}))

if __name__=='__main__':main()
