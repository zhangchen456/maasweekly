"""Real-PG, temporary-filesystem atomic publication and crash recovery tests."""
import hashlib,importlib.util,json,os,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'pipeline'))
import test_shadow_store as shadow
from test_public_export import FixtureRepo
from blob_store import FilesystemBlobStore
from input_snapshot import capture
from shadow_store import import_view,PostgresInputView
from page_projection import store_projections
from data_publication import activate,digest

@unittest.skipUnless(os.environ.get('MAAS_SHADOW_TEST_DSN'),'isolated PostgreSQL DSN required')
class ActivationTests(unittest.TestCase):
    setUp=shadow.ShadowTests.setUp
    tearDown=shadow.ShadowTests.tearDown
    write=shadow.ShadowTests.write
    def candidate(self,n=1,code='a'*40):
        from psycopg2.extras import Json
        fx=FixtureRepo();self.addCleanup(fx.cleanup);fx.add_obs(title='fixture '+str(n));fx.add_price()
        version=capture(fx.root,'publish-fixture')
        import_view(self.connection,fx.root,self.store,source_commit=code)
        path=Path(__file__).resolve().parents[1]/'pipeline/scripts/export-public-data.py'
        spec=importlib.util.spec_from_file_location('activation_exporter',path);ex=importlib.util.module_from_spec(spec);spec.loader.exec_module(ex)
        candidate=self.base.resolve()/('candidate-'+str(n)+'-'+code[0]);ex.publish(candidate,ex.build_release(fx.root))
        manifest=json.loads((candidate/'manifest.json').read_text());manifest['site']={'inputVersion':version,'codeCommit':code,'formatVersion':1}
        (candidate/'publication.json').write_text(json.dumps(manifest))
        with self.connection:
            store_projections(self.connection,fx.root,PostgresInputView(self.connection,version,self.store),code)
            with self.connection.cursor() as c:
                c.execute('INSERT INTO maas_data.data_candidates(dataset_version,input_version,code_commit,data_through,files,page_format_version) VALUES(%s,%s,%s,%s,%s,1) ON CONFLICT DO NOTHING',[manifest['datasetVersion'],version,code,manifest['dataThrough'],Json(manifest['files'])])
        return candidate,manifest
    def target(self):return self.base.resolve()/'public-cache'
    def test_activation_is_idempotent_and_preserves_immutable_versions(self):
        candidate,m=self.candidate();root=self.target()
        result=activate(self.connection,candidate,root,'empty');self.assertEqual(result['status'],'activated')
        first=(root/'publication.json').read_bytes()
        self.assertEqual(activate(self.connection,candidate,root,'empty')['status'],'already_active')
        self.assertEqual((root/'publication.json').read_bytes(),first)
        second,m2=self.candidate(2)
        activate(self.connection,second,root,digest(first))
        pointer=json.loads((root/'publication.json').read_bytes())
        self.assertEqual({r['datasetVersion'] for r in pointer['retainedVersions']},{m['datasetVersion'],m2['datasetVersion']})
        self.assertTrue((root/'releases'/m['datasetVersion']/'items.json').exists())
    def test_crash_before_pointer_keeps_old_visibility_and_retry_recovers(self):
        candidate,_=self.candidate();root=self.target()
        def fail(stage):
            if stage=='after_public_manifest':raise RuntimeError('simulated interruption')
        with self.assertRaises(RuntimeError):activate(self.connection,candidate,root,'empty',failpoint=fail)
        self.assertFalse((root/'publication.json').exists())
        self.assertEqual(activate(self.connection,candidate,root,'empty')['status'],'activated')
    def test_crash_after_pointer_reconciles_exact_audit_on_retry(self):
        candidate,_=self.candidate();root=self.target()
        def fail(stage):
            if stage=='after_pointer':raise RuntimeError('simulated interruption')
        with self.assertRaises(RuntimeError):activate(self.connection,candidate,root,'empty',failpoint=fail)
        before=(root/'publication.json').read_bytes()
        self.assertEqual(activate(self.connection,candidate,root,'empty')['status'],'already_active')
        self.assertEqual((root/'publication.json').read_bytes(),before)
        with self.connection.cursor() as c:
            c.execute('SELECT state FROM maas_data.data_publications');self.assertEqual(c.fetchone()[0],'published')
    def test_corruption_and_stale_compare_swap_cannot_change_pointer(self):
        first,_=self.candidate();root=self.target();activate(self.connection,first,root,'empty')
        before=(root/'publication.json').read_bytes();second,m=self.candidate(2)
        with self.assertRaises(ValueError):activate(self.connection,second,root,'empty')
        file=second/m['files'][0]['path'];file.write_bytes(file.read_bytes()+b' ')
        with self.assertRaises(ValueError):activate(self.connection,second,root,digest(before))
        self.assertEqual((root/'publication.json').read_bytes(),before)
    def test_page_only_publication_keeps_public_dataset_and_updates_binding(self):
        candidate,m=self.candidate();root=self.target();activate(self.connection,candidate,root,'empty')
        before=(root/'publication.json').read_bytes();second,m2=self.candidate(code='b'*40)
        self.assertEqual(m['datasetVersion'],m2['datasetVersion'])
        activate(self.connection,second,root,digest(before))
        pointer=json.loads((root/'publication.json').read_bytes());self.assertEqual(pointer['site']['codeCommit'],'b'*40)
        self.assertEqual(pointer['datasetVersion'],m['datasetVersion'])
    def test_unverified_database_candidate_is_not_visible(self):
        candidate,_=self.candidate();root=self.target()
        with self.connection:
            with self.connection.cursor() as c:c.execute('DELETE FROM maas_data.data_candidates')
        with self.assertRaises(ValueError):activate(self.connection,candidate,root,'empty')
        self.assertFalse((root/'publication.json').exists())
    def test_legacy_bootstrap_preserves_previous_cursor_versions(self):
        import shutil
        first,m=self.candidate();old=self.target();activate(self.connection,first,old,'empty')
        root=self.base.resolve()/'bootstrap';shutil.copytree(old,root);(root/'publication.json').unlink()
        second,m2=self.candidate(2);activate(self.connection,second,root,'empty')
        pointer=json.loads((root/'publication.json').read_bytes())
        self.assertIn(m['datasetVersion'],[r['datasetVersion'] for r in pointer['retainedVersions']])
if __name__=='__main__':unittest.main()
