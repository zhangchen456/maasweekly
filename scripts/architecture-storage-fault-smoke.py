#!/usr/bin/env python3
"""Keep a sealed local release serving while isolated storage restore candidates fail."""
import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path
BASE=Path(__file__).resolve().parents[1];sys.path.insert(0,str(BASE/'pipeline'))
from blob_store import FilesystemBlobStore
from storage_migration import restore, verify_objects
from input_snapshot import assert_no_pending


def main():
    parser=argparse.ArgumentParser();parser.add_argument('release',type=Path);parser.add_argument('manifest',type=Path);parser.add_argument('blob_root',type=Path);parser.add_argument('output',type=Path);args=parser.parse_args()
    release=args.release.resolve();metadata=json.loads((release/'metadata/release-manifest.json').read_text());manifest=json.loads(args.manifest.read_text());store=FilesystemBlobStore(args.blob_root)
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    def query(path):
        with urllib.request.urlopen(f'http://127.0.0.1:{port}/api/v1/'+path,timeout=10) as response:return json.load(response)
    with tempfile.TemporaryDirectory(prefix='maas-storage-lkg-') as folder:
        root=Path(folder);env={**os.environ,'HOST':'127.0.0.1','PORT':str(port),'PUBLIC_DATA_ROOT':str(release/'data/public/v1'),'MAAS_RELEASE_DIR':str(release),'RELOAD_INTERVAL_MS':'0','CURSOR_SECRET':'isolated-storage-fault-fixture','DIAGNOSTICS':'0'}
        with (root/'runtime.txt').open('w') as log:
            child=subprocess.Popen(['node',str(release/'agent-api/dist/server.js')],cwd=root,env=env,stdout=log,stderr=subprocess.STDOUT)
            try:
                for attempt in range(100):
                    try:status=query('status');break
                    except OSError:
                        if child.poll() is not None:raise RuntimeError('sealed runtime exited')
                        time.sleep(.1)
                else:raise RuntimeError('sealed runtime not ready')
                assert status['datasetVersion']==metadata['datasetVersion']
                page=query('changes?limit=1');cursor=page['page']['nextCursor'];report={'releaseId':metadata['releaseId'],'datasetVersion':metadata['datasetVersion'],'scope':'Local sealed API process, isolated failing build inputs; no production activation','faults':[]}
                digest=next(iter(manifest['files'].values()))['rawSha256'];raw=store.get(digest)
                for kind in ('missing','corrupt','unreachable'):
                    if kind=='missing':store.path(digest).unlink()
                    elif kind=='corrupt':store.path(digest).write_bytes(b'corrupt test object')
                    class Offline:
                        def get(self,*args,**kwargs):raise OSError('unreachable test store')
                    target=root/kind
                    try:restore(target,manifest,Offline() if kind=='unreachable' else store)
                    except (OSError,ValueError):pass
                    else:raise AssertionError('candidate did not fail')
                    try:assert_no_pending(target)
                    except ValueError:pass
                    else:raise AssertionError('candidate not blocked')
                    continued=query('changes?cursor='+cursor);assert continued['datasetVersion']==metadata['datasetVersion'];assert child.poll() is None
                    report['faults'].append({'kind':kind,'candidateBlocked':True,'apiContinued':True,'fixedVersionCursorContinued':True})
                    if kind in ('missing','corrupt'):store.path(digest).unlink(missing_ok=True);store.putIfAbsent(digest,raw)
                assert not verify_objects(manifest,store)['failures']
                args.output.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
            finally:
                child.terminate()
                try:child.wait(timeout=5)
                except subprocess.TimeoutExpired:child.kill();child.wait()

if __name__=='__main__':main()
