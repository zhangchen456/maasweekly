import hashlib
import fcntl
import json
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(BASE/'pipeline'))
from blob_store import FilesystemBlobStore, CachedBlobReader, BlobIntegrityError
from storage_migration import build_manifest, copy_objects, verify_objects, restore, cleanup_plan, validate_manifest, RESTORE_PENDING
from snapshot_reader import SnapshotReader
from input_snapshot import assert_no_pending
from run_protocol import RunJournal


class BlobStorageTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.source=self.root/'source';self.store=FilesystemBlobStore(self.root/'blobs')
        for name,raw in [('old.md',b'old input'),('new.html',b'<html>new</html>'),('duplicate.md',b'old input')]:
            p=self.source/'data/snapshots/2026-10-01'/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(raw)
        self.manifest=build_manifest(self.source,'1'*40)
    def tearDown(self): self.temp.cleanup()

    def test_atomic_concurrent_upload_and_corruption_refuses_overwrite(self):
        raw=b'concurrent same bytes';sha=hashlib.sha256(raw).hexdigest()
        with ThreadPoolExecutor(max_workers=4) as pool: result=list(pool.map(lambda _:self.store.putIfAbsent(sha,raw),range(8)))
        self.assertEqual(result.count(True),1);self.assertEqual(self.store.get(sha),raw)
        self.store.path(sha).write_bytes(b'bad')
        with self.assertRaises(BlobIntegrityError): self.store.putIfAbsent(sha,raw)
        with self.assertRaises(BlobIntegrityError): self.store.get(sha)
        with self.assertRaises(BlobIntegrityError): self.store.putIfAbsent('0'*64,raw)
        self.assertFalse(list(self.store.root.rglob('.upload-*')))

    def test_partial_copy_verify_failed_only_resume(self):
        first=copy_objects(self.source,self.manifest,self.store,max_objects=1);self.assertFalse(first['complete'])
        check=verify_objects(self.manifest,self.store);self.assertEqual(len(check['failures']),1)
        retry=copy_objects(self.source,self.manifest,self.store,only={x['sha256'] for x in check['failures']});self.assertTrue(retry['complete']);self.assertEqual(retry['copiedObjects'],1)
        repeat=copy_objects(self.source,self.manifest,self.store);self.assertEqual(repeat['copiedObjects'],0);self.assertEqual(repeat['existingObjects'],2)
        logical=next(iter(self.manifest['files']));(self.source/logical).write_bytes(b'changed after manifest')
        self.assertFalse(copy_objects(self.source,self.manifest,self.store)['complete'])

    def test_restore_interrupt_blocks_build_and_resumes_exact_bytes(self):
        copy_objects(self.source,self.manifest,self.store);destination=self.root/'restored'
        result=restore(destination,self.manifest,self.store,max_files=1);self.assertFalse(result['complete'])
        with self.assertRaisesRegex(ValueError,'storage restore pending'): assert_no_pending(destination)
        with self.assertRaisesRegex(ValueError,'storage restore pending'):
            with RunJournal(destination,'sources','blocked_writer'):pass
        done=restore(destination,self.manifest,self.store);self.assertTrue(done['complete']);self.assertEqual(done['existingFiles'],1)
        assert_no_pending(destination)
        for logical in self.manifest['files']: self.assertEqual((destination/logical).read_bytes(),(self.source/logical).read_bytes())

    def test_missing_bad_hash_unreachable_keep_pending(self):
        for name,kind in [('missing',0),('corrupt',1),('unreachable',2)]:
            copy_objects(self.source,self.manifest,self.store)
            digest=next(iter(self.manifest['files'].values()))['rawSha256'];p=self.store.path(digest)
            if kind==0:p.unlink()
            elif kind==1:p.write_bytes(b'corrupt')
            class Unreachable:
                def get(self,*args,**kwargs):raise OSError('offline store')
            reader=Unreachable() if kind==2 else self.store
            target=self.root/name
            with self.assertRaises((OSError,ValueError)):restore(target,self.manifest,reader)
            self.assertTrue((target/RESTORE_PENDING).exists())
            if p.exists() and p.read_bytes()==b'corrupt':p.unlink()

    def test_bounded_cache_hit_evict_and_repair(self):
        copy_objects(self.source,self.manifest,self.store);cache=CachedBlobReader(self.store,self.root/'cache',max_bytes=16)
        hashes=list({p['rawSha256'] for p in self.manifest['files'].values()})
        for h in hashes:cache.get(h)
        self.assertLessEqual(cache.prune(),16)
        h=hashes[-1];cache.get(h);self.assertGreater(cache.hits,0)
        cache.cache.path(h).write_bytes(b'bad cache');self.assertEqual(cache.get(h),self.store.get(h))
        self.assertLessEqual(cache.prune(),16)

    def test_legacy_and_blob_reader_are_equal_no_silent_corrupt_fallback(self):
        copy_objects(self.source,self.manifest,self.store);legacy=SnapshotReader(self.source,self.manifest,self.store);migrated=SnapshotReader(self.root/'blank',self.manifest,self.store)
        for logical in self.manifest['files']:self.assertEqual(legacy.get(logical),migrated.get(logical))
        logical=next(iter(self.manifest['files']));(self.source/logical).write_bytes(b'wrong')
        with self.assertRaises(BlobIntegrityError):legacy.get(logical)
        with self.assertRaises(FileNotFoundError):migrated.get('data/snapshots/unknown.md')

    def test_path_manifest_and_cache_symlinks_fail_closed(self):
        with self.assertRaises(BlobIntegrityError):self.store.get('../escape')
        bad=json.loads(json.dumps(self.manifest));bad['files']['data/snapshots/escape.md']=bad['files'].pop(next(iter(bad['files'])))
        with self.assertRaises(BlobIntegrityError):validate_manifest(bad)
        cache=self.root/'cache-link';cache.symlink_to(self.source,target_is_directory=True)
        with self.assertRaises(BlobIntegrityError):CachedBlobReader(self.store,cache)
        outside=self.root/'outside';outside.mkdir();(self.store.root/'sha256').mkdir(parents=True)
        digest=next(iter(self.manifest['files'].values()))['rawSha256'];(self.store.root/'sha256'/digest[:2]).symlink_to(outside,target_is_directory=True)
        with self.assertRaises(BlobIntegrityError):self.store.putIfAbsent(digest,b'old input')

    def test_cleanup_dry_run_marks_all_supplied_history_refs(self):
        copy_objects(self.source,self.manifest,self.store);raw=b'unreferenced';sha=hashlib.sha256(raw).hexdigest();self.store.putIfAbsent(sha,raw)
        result=cleanup_plan(self.store.root,[self.manifest],now=time.time()+86400*15,grace_seconds=86400*14)
        self.assertEqual([r['blobId'] for r in result['candidates']],['blob_'+sha]);self.assertTrue(self.store.path(sha).exists());self.assertTrue(result['dryRun'])
        with self.assertRaises(ValueError):cleanup_plan(self.store.root,[],now=time.time(),grace_seconds=0)

    def test_restore_shares_writer_lock_and_refuses_pipeline_pending(self):
        target=self.root/'locked';(target/'data').mkdir(parents=True)
        with (target/'data/.pipeline.lock').open('a+b') as stream:
            fcntl.flock(stream.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
            with self.assertRaisesRegex(ValueError,'writer is active'):restore(target,self.manifest,self.store)
        (target/'data/pipeline-pending.json').write_text('{}')
        with self.assertRaisesRegex(ValueError,'pipeline recovery pending'):restore(target,self.manifest,self.store)
        self.assertFalse((target/RESTORE_PENDING).exists())

    def test_legacy_missing_raw_is_explicit_not_a_fabricated_blob(self):
        folder=self.source/'data/price-snapshots';folder.mkdir();(folder/'psnap_old.json').write_text(json.dumps({'id':'psnap_old','content_sha256':'0'*64}))
        manifest=build_manifest(self.source,'1'*40);ref=manifest['snapshots']['psnap_old'];self.assertEqual(ref['rawState'],'legacy_raw_missing');self.assertEqual(ref['rawPaths'],[])
        self.assertNotIn('0'*64,{p['rawSha256'] for p in manifest['files'].values()})

if __name__=='__main__':unittest.main()
