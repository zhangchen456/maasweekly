"""Public pointer repair and publish fail-closed before business writes."""
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'pipeline'))
from public_export.retention import checked_references
from public_export.loaders import ExportError
spec=importlib.util.spec_from_file_location('retention_export',ROOT/'pipeline/scripts/export-public-data.py')
export=importlib.util.module_from_spec(spec);spec.loader.exec_module(export)
DRAFT='ds_3516479a30448cbb47227b5833394f49e0c9b0a2f8da155571c1c5e94d55b361'
CURRENT='ds_'+'c'*64;UNKNOWN='ds_'+'d'*64

class PublicRetentionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup);self.root=Path(self.temp.name)
        self.release(CURRENT)
    def release(self,ds):
        folder=self.root/'releases'/ds;folder.mkdir(parents=True)
        files=[]
        for name in export.BUSINESS_FILES:
            raw=(json.dumps({'models':[],'families':[]})+'\n').encode() if name=='model-identities.json' else b'{}\n';(folder/name).write_bytes(raw)
            files.append({'path':f'releases/{ds}/{name}','sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)})
        manifest={'schemaVersion':'1.0','datasetVersion':ds,'generatedAt':'2026-01-01T00:00:00+00:00','dataThrough':'2026-01-01','coverage':{},'files':files,'retainedVersions':[]}
        (folder/'manifest.json').write_text(json.dumps(manifest));return manifest
    def pointer(self,extras=()):
        manifest=json.loads((self.root/'releases'/CURRENT/'manifest.json').read_text())
        manifest['retainedVersions']=[{'datasetVersion':ds,'generatedAt':'2026-01-01T00:00:00+00:00'} for ds in [CURRENT,*extras]]
        (self.root/'manifest.json').write_text(json.dumps(manifest));return manifest
    def test_known_missing_draft_repair_changes_only_mutable_pointer_and_is_idempotent(self):
        before=self.pointer([DRAFT]);immutable={str(p):p.read_bytes() for p in (self.root/'releases').rglob('*') if p.is_file()}
        export.repair_retention(self.root)
        after=json.loads((self.root/'manifest.json').read_text());self.assertEqual(after,{**before,'retainedVersions':before['retainedVersions'][:1]})
        self.assertEqual(immutable,{str(p):p.read_bytes() for p in (self.root/'releases').rglob('*') if p.is_file()})
        pointer=(self.root/'manifest.json').read_bytes();export.repair_retention(self.root);self.assertEqual(pointer,(self.root/'manifest.json').read_bytes())
    def test_missing_published_or_unknown_version_never_silently_disappears(self):
        self.pointer([UNKNOWN]);before=(self.root/'manifest.json').read_bytes()
        with self.assertRaises(ExportError):export.repair_retention(self.root)
        self.assertEqual(before,(self.root/'manifest.json').read_bytes())
        with self.assertRaises(ExportError):checked_references(self.root,[{'datasetVersion':DRAFT}],DRAFT,exclusions={DRAFT})
    def test_existing_excluded_version_is_kept_and_corruption_is_rejected(self):
        self.release(DRAFT);rows=[{'datasetVersion':CURRENT},{'datasetVersion':DRAFT}]
        kept,removed=checked_references(self.root,rows,CURRENT,exclusions={DRAFT})
        self.assertEqual(kept,rows);self.assertEqual(removed,[])
        (self.root/'releases'/DRAFT/'prices.json').write_text('tampered')
        with self.assertRaises(ExportError):checked_references(self.root,rows,CURRENT,exclusions={DRAFT})
    def test_publish_rejects_dangling_reference_before_creating_new_version(self):
        old=self.pointer([UNKNOWN]);new='ds_'+'e'*64
        old['retainedVersions'][1]['generatedAt']=export._now_iso();(self.root/'manifest.json').write_text(json.dumps(old))
        before=(self.root/'manifest.json').read_bytes()
        with self.assertRaises(ExportError):export.publish(self.root,{'datasetVersion':new})
        self.assertFalse((self.root/'releases'/new).exists());self.assertEqual(before,(self.root/'manifest.json').read_bytes())
    def test_at_least_previous_survives_when_a_missing_draft_precedes_it(self):
        self.pointer([DRAFT]);new='ds_'+'e'*64
        rel={key:[] for key in ['changes','items','prices','evidence','weekly']};rel.update(status={'providers':[{'providerId':'openai'}]},modelIdentities={'models':[],'families':[]},datasetVersion=new,dataThrough='2026-10-02')
        export.publish(self.root,rel)
        rows=json.loads((self.root/'manifest.json').read_text())['retainedVersions']
        self.assertEqual({r['datasetVersion'] for r in rows},{new,CURRENT})
    def test_symlinked_retained_directory_is_rejected(self):
        folder=self.root/'releases'/UNKNOWN;folder.symlink_to(self.root/'releases'/CURRENT)
        with self.assertRaises(ExportError):checked_references(self.root,[{'datasetVersion':CURRENT},{'datasetVersion':UNKNOWN}],CURRENT)

if __name__=='__main__':unittest.main()
