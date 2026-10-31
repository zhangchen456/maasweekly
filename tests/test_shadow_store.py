"""Real PostgreSQL tests; use only an isolated MAAS_SHADOW_TEST_DSN database."""
import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'pipeline'))
from blob_store import FilesystemBlobStore
from input_snapshot import capture, load_view
from shadow_store import migrate, import_view, entries, restore_view, verify_view, PostgresInputView, backfill_ordered_json


@unittest.skipUnless(os.environ.get('MAAS_SHADOW_TEST_DSN'), 'isolated PostgreSQL DSN required')
class ShadowTests(unittest.TestCase):
    def setUp(self):
        import psycopg2
        self.connection = psycopg2.connect(os.environ['MAAS_SHADOW_TEST_DSN'])
        # Never drop arbitrary schemas in an operator-supplied database. The
        # dedicated database name is verified before destructive fixture reset.
        with self.connection.cursor() as c:
            c.execute('SELECT current_database()')
            if c.fetchone()[0] != 'maas_shadow_test':
                raise RuntimeError('dedicated maas_shadow_test database required')
            c.execute('DROP SCHEMA IF EXISTS maas_data CASCADE')
        self.connection.commit()
        migrate(self.connection)
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.root = self.base / 'source'
        self.root.mkdir()
        self.store = FilesystemBlobStore(self.base / 'blobs')
        self.write('a.json', {'id': 'fixture:a', 'revision': 1, 'amount': '0.00001'})
        self.write('b.json', {'id': 'fixture:b', 'text': '保留原文'})
        self.version = capture(self.root, 'fixture-run')

    def tearDown(self):
        self.connection.close()
        self.tmp.cleanup()

    def write(self, name, value):
        p = self.root / 'data/derived' / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n')

    def do_import(self, parent=None):
        return import_view(self.connection, self.root, self.store, source_commit='a' * 40, parent=parent)

    def test_import_idempotence_and_exact_restore(self):
        self.assertEqual(self.do_import()['deltaFiles'], 2)
        migrate(self.connection)
        self.assertTrue(self.do_import()['idempotent'])
        destination = self.base / 'restored'
        restore_view(self.connection, self.version, self.store, destination)
        view = load_view(destination)
        original = load_view(self.root)
        self.assertEqual(view.version, self.version)
        for logical in original.files:
            self.assertEqual(original.path(logical).read_bytes(), view.path(logical).read_bytes())
        with self.connection.cursor() as c:
            c.execute("SELECT payload->>'amount' FROM maas_data.documents WHERE entity_id='fixture:a'")
            self.assertEqual(c.fetchone()[0], '0.00001')

    def test_delta_tombstone_and_old_view_survives(self):
        self.do_import()
        (self.root / 'data/derived/b.json').unlink()
        self.write('a.json', {'id': 'fixture:a', 'revision': 2})
        second = capture(self.root, 'next-run')
        self.assertEqual(self.do_import(self.version)['deltaFiles'], 2)
        self.assertEqual(len(entries(self.connection, second)), 1)
        self.assertEqual(len(entries(self.connection, self.version)), 2)
        self.write('c.json', {'id': 'fixture:c'})
        third = capture(self.root, 'third-run')
        self.assertEqual(self.do_import(second)['deltaFiles'], 1)
        self.assertEqual(len(entries(self.connection, third)), 2)
        self.assertNotIn('data/derived/b.json', entries(self.connection, third))

    def test_corrupt_or_missing_blob_refuses_reimport_and_recovery(self):
        self.do_import()
        meta = next(iter(entries(self.connection, self.version).values()))
        path = self.store.path(meta['sha256'])
        raw = path.read_bytes()
        for replacement in [b'bad', None]:
            if replacement is None:
                path.unlink()
            else:
                path.write_bytes(replacement)
            with self.assertRaises((OSError, ValueError)):
                self.do_import()
            destination = self.base / ('missing' if replacement is None else 'corrupt')
            with self.assertRaises((OSError, ValueError)):
                restore_view(self.connection, self.version, self.store, destination)
            self.assertFalse((destination / 'data/inputs-current.json').exists())
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)

    def test_failed_import_rolls_back_and_can_retry(self):
        for n in range(501):
            self.write(f'a-{n:04}.json', {'id': f'fixture:{n}'})
        self.version = capture(self.root, 'large-batch')
        view = load_view(self.root)
        physical = self.root / view.files['data/derived/b.json']['path']
        raw = physical.read_bytes()
        physical.write_bytes(b'corrupt')
        with self.assertRaises(ValueError):
            self.do_import()
        with self.connection.cursor() as c:
            c.execute('SELECT count(*) FROM maas_data.input_versions')
            self.assertEqual(c.fetchone()[0], 0)
            c.execute('SELECT count(*) FROM maas_data.documents')
            self.assertEqual(c.fetchone()[0], 0)
        self.connection.commit()
        physical.write_bytes(raw)
        self.do_import()

    def test_unknown_parent_pending_and_inside_repo_store_rejected(self):
        with self.assertRaises(ValueError):
            self.do_import('in_' + 'b' * 64)
        with self.assertRaises(ValueError):
            import_view(self.connection, self.root, FilesystemBlobStore(self.root / 'blobs'), source_commit='a' * 40)
        (self.root / 'data/pipeline-pending.json').write_text('{}')
        with self.assertRaises(ValueError):
            self.do_import()

    def test_existing_restore_target_and_tampered_database_rejected(self):
        self.do_import()
        destination = self.base / 'existing'
        destination.mkdir()
        (destination / 'preserve').write_text('keep')
        with self.assertRaises(ValueError):
            restore_view(self.connection, self.version, self.store, destination)
        with self.connection:
            with self.connection.cursor() as c:
                c.execute('DELETE FROM maas_data.input_deltas WHERE logical_path=%s', ('data/derived/b.json',))
        with self.assertRaises(ValueError):
            restore_view(self.connection, self.version, self.store, self.base / 'bad-view')

    def test_nul_and_surrogate_content_roundtrips_without_loss(self):
        self.write('nul.json', {'text': 'before\x00after', 'literal': r'\u0000'})
        # JSON escaped surrogate is valid archive input but not JSONB text.
        (self.root / 'data/derived/surrogate.json').write_text('{"text":"\\ud800"}')
        version = capture(self.root, 'special-text')
        self.do_import()
        self.assertEqual(verify_view(self.connection, version, self.store)['fallbackJsonObjects'], 2)
        restore_view(self.connection, version, self.store, self.base / 'special-restored')
        self.assertEqual(load_view(self.root).path('data/derived/nul.json').read_bytes(),
                         load_view(self.base / 'special-restored').path('data/derived/nul.json').read_bytes())

    def test_structured_payload_corruption_is_detected(self):
        self.do_import()
        with self.connection:
            with self.connection.cursor() as c:
                c.execute("UPDATE maas_data.documents SET payload='{\"wrong\":true}' WHERE entity_id='fixture:a'")
        with self.assertRaises(ValueError):
            verify_view(self.connection, self.version, self.store)
        with self.assertRaises(ValueError):
            self.do_import()

    def test_inherited_blob_corruption_rolls_back_new_delta_and_retry_succeeds(self):
        self.do_import()
        original = entries(self.connection, self.version)
        meta = original['data/derived/a.json']
        blob = self.store.path(meta['sha256']); raw = blob.read_bytes()
        self.write('new.json', {'id':'fixture:new'})
        new_version = capture(self.root, 'incremental')
        for replacement in [b'corrupt', None]:
            if replacement is None:blob.unlink()
            else:blob.write_bytes(replacement)
            with self.assertRaises((ValueError,OSError)):self.do_import(self.version)
            with self.connection.cursor() as c:
                c.execute('SELECT count(*) FROM maas_data.input_versions WHERE version=%s',(new_version,))
                self.assertEqual(c.fetchone()[0],0)
                c.execute("SELECT count(*) FROM maas_data.documents WHERE entity_id='fixture:new'")
                self.assertEqual(c.fetchone()[0],0)
            self.connection.commit();blob.write_bytes(raw)
        self.do_import(self.version)
        self.assertEqual(len(entries(self.connection,new_version)),3)

    def test_inherited_sql_representation_corruption_blocks_new_version(self):
        self.do_import()
        self.write('new.json', {'id':'fixture:new'})
        new_version=capture(self.root,'new-version')
        for field,value in [('payload','{"wrong":true}'),('payload_json','{"wrong":true}')]:
            with self.connection.cursor() as c:
                c.execute('SELECT '+field+' FROM maas_data.documents WHERE entity_id=%s',('fixture:a',));old=c.fetchone()[0]
            with self.connection:
                with self.connection.cursor() as c:c.execute('UPDATE maas_data.documents SET '+field+'=%s WHERE entity_id=%s',(value,'fixture:a'))
            with self.assertRaises(ValueError):self.do_import(self.version)
            with self.connection.cursor() as c:
                c.execute('SELECT count(*) FROM maas_data.input_versions WHERE version=%s',(new_version,));self.assertEqual(c.fetchone()[0],0)
            self.connection.commit()
            with self.connection:
                with self.connection.cursor() as c:c.execute('UPDATE maas_data.documents SET '+field+'=%s WHERE entity_id=%s',(json.dumps(old) if field=='payload' else old,'fixture:a'))
        self.do_import(self.version)

    def test_unchanged_aliases_are_verified_once_per_object_before_commit(self):
        from collections import Counter
        from unittest.mock import patch
        source=self.root/'data/derived/a.json';(source.parent/'alias.json').write_bytes(source.read_bytes())
        self.version=capture(self.root,'aliases');self.do_import()
        inherited={x['sha256'] for x in entries(self.connection,self.version).values()}
        self.write('new.json', {'id':'fixture:new'});capture(self.root,'incremental')
        reads=Counter();get=self.store.get
        def counted(sha,**kwargs):
            reads[sha]+=1;return get(sha,**kwargs)
        with patch.object(self.store,'get',side_effect=counted):self.do_import(self.version)
        self.assertTrue(inherited)
        for sha in inherited:self.assertEqual(reads[sha],1)

    def test_process_crash_after_sql_batch_preserves_old_state_and_retries(self):
        for n in range(502):
            self.write(f'a-{n:04}.json', {'id': f'crash:{n}'})
        self.version = capture(self.root, 'crash-batch')
        code = '''
import os,sys,psycopg2
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from shadow_store import import_view
from blob_store import FilesystemBlobStore
class CrashStore(FilesystemBlobStore):
    calls=0
    def putIfAbsent(self,*args):
        self.calls+=1
        if self.calls==502: os._exit(73)
        return super().putIfAbsent(*args)
c=psycopg2.connect(os.environ['MAAS_SHADOW_TEST_DSN'])
import_view(c,Path(sys.argv[2]),CrashStore(Path(sys.argv[3])),source_commit='a'*40)
'''
        result = subprocess.run([sys.executable, '-c', code, str(Path(__file__).resolve().parents[1] / 'pipeline'),
                                 str(self.root), str(self.store.root)], capture_output=True, timeout=30)
        self.assertEqual(result.returncode, 73, result.stderr.decode())
        with self.connection.cursor() as c:
            c.execute('SELECT count(*) FROM maas_data.input_versions')
            self.assertEqual(c.fetchone()[0], 0)
            c.execute('SELECT count(*) FROM maas_data.documents')
            self.assertEqual(c.fetchone()[0], 0)
        self.connection.commit()
        self.do_import()
        self.assertEqual(len(entries(self.connection, self.version)), 504)

    def test_database_reader_pins_version_and_does_not_read_json_blobs(self):
        self.do_import()
        old_view = PostgresInputView(self.connection, self.version, self.store)
        self.write('a.json', {'id': 'fixture:a', 'revision': 2})
        new_version = capture(self.root, 'updated')
        self.do_import(self.version)
        new_view = PostgresInputView(self.connection, new_version, self.store)
        for path in self.store.root.glob('sha256/*/*'):
            path.unlink()
        self.assertEqual(old_view.read_json('data/derived/a.json')['revision'], 1)
        self.assertEqual(new_view.read_json('data/derived/a.json')['revision'], 2)
        self.assertEqual(len(list(new_view.iter_json('data/derived', '*.json'))), 2)

    def test_jsonb_source_order_preserves_the_public_status_contract(self):
        path = self.root / 'data/price-facts/current.json'
        path.parent.mkdir(parents=True)
        path.write_text('{"facts":{},"sources":{"long-first":{"status":"ok"},"a":{"status":"ok"}}}')
        first = capture(self.root, 'ordered')
        self.do_import()
        view = PostgresInputView(self.connection, first, self.store)
        self.assertEqual(list(view.read_json('data/price-facts/current.json')['sources']), ['long-first', 'a'])
        path.write_text('{"facts":{},"sources":{"a":{"status":"ok"},"long-first":{"status":"ok"}}}')
        second = capture(self.root, 'reordered')
        self.do_import(first)
        self.assertEqual(list(PostgresInputView(self.connection, second, self.store).read_json('data/price-facts/current.json')['sources']), ['a', 'long-first'])
        self.assertEqual(list(view.read_json('data/price-facts/current.json')['sources']), ['long-first', 'a'])

    def test_legacy_order_backfill_is_explicit_and_byte_checked(self):
        self.do_import()
        with self.connection:
            with self.connection.cursor() as c:
                c.execute("UPDATE maas_data.documents SET payload_json=NULL WHERE entity_id='fixture:a'")
        view = PostgresInputView(self.connection, self.version, self.store)
        with self.assertRaises(ValueError):
            view.read_json('data/derived/a.json')
        with self.connection:
            result = backfill_ordered_json(self.connection, self.version, self.store)
        self.assertEqual(result['updatedObjects'], 1)
        self.assertEqual(view.read_json('data/derived/a.json')['revision'], 1)
        self.assertEqual(verify_view(self.connection, self.version, self.store)['orderedJsonObjects'], 2)

    def test_arbitrary_source_keys_preserve_order_with_bounded_decoder_state(self):
        expected = {f'field_{n}': n for n in range(3000)}
        self.write('many-keys.json', expected)
        version = capture(self.root, 'many-source-keys')
        self.do_import()
        view = PostgresInputView(self.connection, version, self.store)
        actual = view.read_json('data/derived/many-keys.json')
        self.assertEqual(list(actual.items()), list(expected.items()))
        self.assertLessEqual(len(view._field_names), 1024)

    def test_compact_export_matches_full_archive_bytes_and_historical_evidence_time(self):
        base = Path(__file__).resolve().parents[1]
        spec = importlib.util.spec_from_file_location('public_fixture', base / 'tests/test_public_export.py')
        fixture_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(fixture_module)
        fixture = fixture_module.FixtureRepo()
        self.addCleanup(fixture.cleanup)
        fixture.add_obs(summary='保留顺序与原文')
        bundle = fixture.add_price()
        # Unreachable facts must not be retained as full objects, but they still
        # contribute to the legacy evidence observation window.
        extra = dict(bundle['pfv'], version_id='pfv_' + 'f' * 64, observedAt='2020-01-01T00:00:00Z')
        fixture._p(f"data/price-facts/versions/{extra['version_id']}.json").write_text(json.dumps(extra))
        version = capture(fixture.root, 'export-fixture')
        import_view(self.connection, fixture.root, self.store, source_commit='a' * 40)
        script_spec = importlib.util.spec_from_file_location('fixture_exporter', base / 'pipeline/scripts/export-public-data.py')
        exporter = importlib.util.module_from_spec(script_spec)
        script_spec.loader.exec_module(exporter)
        expected = exporter.build_release(fixture.root)
        view = PostgresInputView(self.connection, version, self.store)
        actual = exporter.build_release(fixture.root, input_view=view)
        self.assertEqual(expected['datasetVersion'], actual['datasetVersion'])
        for key in ('changes', 'items', 'prices', 'evidence', 'weekly', 'status', 'modelIdentities'):
            self.assertEqual(json.dumps(expected[key], ensure_ascii=False, indent=2),
                             json.dumps(actual[key], ensure_ascii=False, indent=2), key)
        from page_projection import projections, store_projections
        from pricing.archive import build_price_index
        sys.path.insert(0, str(base / 'pipeline/scripts'))
        from record_archive import build_index
        materialized = dict(projections(fixture.root, view))
        self.assertEqual(materialized['site/src/data/record-index.json'],
                         build_index(fixture.root / 'data/records'))
        self.assertEqual(materialized['site/src/data/price-record-index.json'],
                         build_price_index(fixture.root / 'data/price-records'))
        with self.connection:
            store_projections(self.connection, fixture.root, view, 'a' * 40)
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT name,payload_json,sha256,bytes FROM maas_data.page_projections')
            for name, body, sha, size in cursor.fetchall():
                self.assertEqual(json.loads(body), materialized[name])
                self.assertEqual(len(body.encode()), size)
                self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), sha)


if __name__ == '__main__':
    unittest.main()
