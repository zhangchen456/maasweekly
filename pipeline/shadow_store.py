"""PostgreSQL shadow import of a committed InputView, with byte-exact recovery.

No writer switch, live publication or implicit fallback. Filesystem blobs live
outside the repository. PostgreSQL transactions make a complete imported view
visible at once; interrupted copies may leave harmless, unreferenced blobs.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from blob_store import FilesystemBlobStore, safe_path
from input_snapshot import InputView, atomic, canonical, canonical_digest, assert_no_pending

# Bound decoded payload batches by bytes as well as count. Large individual
# documents are processed alone; the limit is not a maximum document size.
DOCUMENT_BATCH_BYTES = 2 * 1024 * 1024
DOCUMENT_BATCH_COUNT = 128


def document_batches(metadata):
    batch, size = [], 0
    for sha, meta in metadata.items():
        if batch and (size + meta['bytes'] > DOCUMENT_BATCH_BYTES or len(batch) >= DOCUMENT_BATCH_COUNT):
            yield batch
            batch, size = [], 0
        batch.append(sha)
        size += meta['bytes']
    if batch:
        yield batch


def migrate(connection):
    sql = '\n'.join(p.read_text() for p in sorted(Path(__file__).with_name('migrations').glob('*.sql')))
    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(184067231, 1)')
            cursor.execute(sql)
            cursor.execute('SELECT max(version) FROM maas_data.schema_versions')
            return cursor.fetchone()[0]


def entries(connection, version):
    if not re.fullmatch(r'in_[0-9a-f]{64}', version):
        raise ValueError('invalid input version')
    with connection.cursor() as cursor:
        cursor.execute('SELECT 1 FROM maas_data.input_versions WHERE version=%s', (version,))
        if not cursor.fetchone():
            raise ValueError('unknown input version')
        cursor.execute('''WITH RECURSIVE chain AS (
          SELECT version,parent_version,0 AS depth FROM maas_data.input_versions WHERE version=%s
          UNION ALL SELECT v.version,v.parent_version,c.depth+1
          FROM maas_data.input_versions v JOIN chain c ON v.version=c.parent_version
        ), resolved AS (
          SELECT DISTINCT ON (d.logical_path) d.logical_path,d.physical_path,d.sha256
          FROM chain c JOIN maas_data.input_deltas d ON d.input_version=c.version
          ORDER BY d.logical_path,c.depth
        ) SELECT r.logical_path,r.physical_path,r.sha256,d.bytes
          FROM resolved r JOIN maas_data.documents d ON d.sha256=r.sha256
          ORDER BY r.logical_path''', (version,))
        return {logical: {'path': physical, 'sha256': sha, 'bytes': size}
                for logical, physical, sha, size in cursor}


def _validate_files(files, version):
    if 'in_' + canonical_digest(files) != version:
        raise ValueError('input version content mismatch')
    for logical, meta in files.items():
        for value in (logical, meta['path']):
            p = Path(value)
            if not value.startswith('data/') or p.is_absolute() or '..' in p.parts:
                raise ValueError('input path escape')
        if not re.fullmatch('[0-9a-f]{64}', meta['sha256']) or type(meta['bytes']) is not int or meta['bytes'] < 0:
            raise ValueError('invalid input blob metadata')


def _jsonb_safe(value):
    if isinstance(value, str):
        return not any(ord(c) == 0 or 0xd800 <= ord(c) <= 0xdfff for c in value)
    if isinstance(value, dict):
        return all(_jsonb_safe(k) and _jsonb_safe(v) for k, v in value.items())
    if isinstance(value, list):
        return all(_jsonb_safe(v) for v in value)
    return True


def verify_view(connection, version, store):
    """Verify both original bytes AND the structured database representation."""
    files = entries(connection, version)
    _validate_files(files, version)
    by_sha = {v['sha256']: v for v in files.values()}
    json_shas = {v['sha256'] for logical, v in files.items() if Path(logical).suffix == '.json'}
    checked = fallback = ordered = 0
    with connection.cursor() as cursor:
        for batch in document_batches(by_sha):
            cursor.execute('''SELECT sha256,bytes,payload,payload_json FROM maas_data.documents
                              WHERE sha256=ANY(%s)''', (batch,))
            rows = cursor.fetchall()
            if len(rows) != len(batch):
                raise ValueError('missing structured documents')
            for sha, size, payload, payload_json in rows:
                meta = by_sha[sha]
                if size != meta['bytes']:
                    raise ValueError('document size mismatch')
                raw = store.get(sha, expected_bytes=size)
                original = json.loads(raw) if sha in json_shas else None
                if payload_json is not None:
                    decoded = json.loads(payload_json)
                    if json.dumps(decoded, ensure_ascii=True) != json.dumps(original, ensure_ascii=True):
                        raise ValueError('ordered JSON differs from original')
                    ordered += 1
                    fallback += int(not _jsonb_safe(original))
                if sha in json_shas and _jsonb_safe(original) and payload != original:
                    raise ValueError('structured payload differs from original')
                if sha in json_shas and not _jsonb_safe(original) and (payload is not None or payload_json is None):
                    raise ValueError('exceptional JSON representation is invalid')
                checked += 1
            # Do not retain the preceding decoded batch while fetching the next.
            del rows
    return {'inputVersion': version, 'files': len(files), 'verifiedObjects': checked,
            'orderedJsonObjects': ordered, 'fallbackJsonObjects': fallback}


def backfill_ordered_json(connection, version, store):
    """Preserve original JSON member order for byte-stable compatibility exports.

    JSONB remains queryable; its ordered JSON companion is not a second writer.
    Both representations are populated together and verified against pinned bytes.
    """
    from psycopg2.extras import execute_values
    files = entries(connection, version)
    _validate_files(files, version)
    hashes = {v['sha256']: v for name, v in files.items() if Path(name).suffix == '.json'}
    updated = 0
    with connection.cursor() as cursor:
        for batch in document_batches(hashes):
            cursor.execute('SELECT sha256 FROM maas_data.documents WHERE sha256=ANY(%s) AND payload_json IS NULL', (batch,))
            rows = []
            for (sha,) in cursor.fetchall():
                raw = store.get(sha, expected_bytes=hashes[sha]['bytes'])
                rows.append((sha, json.dumps(json.loads(raw), ensure_ascii=True)))
            if rows:
                execute_values(cursor, '''UPDATE maas_data.documents d SET payload_json=v.body
                  FROM (VALUES %s) AS v(sha,body) WHERE d.sha256=v.sha AND d.payload_json IS NULL''', rows)
                updated += len(rows)
    return {'inputVersion': version, 'updatedObjects': updated}


def ensure_source_order(connection, version, store):
    """Backfill small derived ordering metadata from the pinned original bytes."""
    from psycopg2.extras import Json
    files = entries(connection, version)
    _validate_files(files, version)
    meta = files.get('data/price-facts/current.json')
    order = list(json.loads(store.get(meta['sha256'], expected_bytes=meta['bytes'])).get('sources', {})) if meta else []
    with connection.cursor() as cursor:
        cursor.execute('SELECT source_order FROM maas_data.input_versions WHERE version=%s FOR UPDATE', (version,))
        old = cursor.fetchone()[0]
        if old is not None and old != order:
            raise ValueError('source order metadata differs from original')
        cursor.execute('UPDATE maas_data.input_versions SET source_order=%s WHERE version=%s AND source_order IS NULL', (Json(order), version))
    return order


def import_view(connection, root, store, *, source_commit, parent=None):
    """Import one frozen view; parent is explicit, never inferred from wall time."""
    from psycopg2.extras import Json, execute_values
    root = Path(root).resolve()
    if not re.fullmatch('[0-9a-f]{40}', source_commit):
        raise ValueError('fixed source commit required')
    # Storing blobs within an input tree would silently put data back in Git.
    if store.root.resolve().is_relative_to(root):
        raise ValueError('blob root must be outside source repository')
    assert_no_pending(root)
    pointer_bytes = safe_path(root, 'data/inputs-current.json').read_bytes()
    pointer = json.loads(pointer_bytes)
    view = InputView(root, pointer)
    _validate_files(view.files, view.version)
    with connection:
        with connection.cursor() as cursor:
            cursor.execute('SELECT pg_advisory_xact_lock(184067231, 2)')
            cursor.execute('SELECT parent_version FROM maas_data.input_versions WHERE version=%s', (view.version,))
            old = cursor.fetchone()
            if old:
                files = entries(connection, view.version)
                if files != view.files:
                    raise ValueError('existing database view differs')
                verify_view(connection, view.version, store)
                ensure_source_order(connection, view.version, store)
                return {'inputVersion': view.version, 'files': len(files), 'deltaFiles': 0, 'idempotent': True}
            previous = entries(connection, parent) if parent else {}
            if parent == view.version:
                raise ValueError('input cannot parent itself')
            docs, deltas = {}, []
            batch_bytes = 0
            copied = 0
            for logical, meta in view.files.items():
                if previous.get(logical) == meta:
                    # Reverify inherited objects too: corruption must not pass
                    # merely because this batch contains no changes to a path.
                    store.verify(meta['sha256'], expected_bytes=meta['bytes'])
                    continue
                if docs and (batch_bytes + meta['bytes'] > DOCUMENT_BATCH_BYTES or len(docs) >= DOCUMENT_BATCH_COUNT):
                    execute_values(cursor, '''INSERT INTO maas_data.documents
                      (sha256,bytes,payload,entity_id,revision,payload_json) VALUES %s ON CONFLICT DO NOTHING''', list(docs.values()))
                    docs.clear()
                    batch_bytes = 0
                raw = view.path(logical).read_bytes()
                if len(raw) != meta['bytes'] or hashlib.sha256(raw).hexdigest() != meta['sha256']:
                    raise ValueError('source changed during import')
                copied += store.putIfAbsent(meta['sha256'], raw)
                value = json.loads(raw) if Path(logical).suffix == '.json' else None
                entity = value if isinstance(value, dict) else {}
                supported = _jsonb_safe(value)
                docs[meta['sha256']] = (meta['sha256'], meta['bytes'], Json(value) if value is not None and supported else None,
                                       str(entity.get('id') or entity.get('version_id') or '') or None,
                                       str(entity['revision']) if entity.get('revision') is not None else None,
                                       json.dumps(value, ensure_ascii=True) if Path(logical).suffix == '.json' else None)
                deltas.append((view.version, logical, meta['path'], meta['sha256']))
                batch_bytes += meta['bytes']
            if docs:
                execute_values(cursor, '''INSERT INTO maas_data.documents
                  (sha256,bytes,payload,entity_id,revision,payload_json) VALUES %s ON CONFLICT DO NOTHING''', list(docs.values()))
            docs.clear()
            deltas.extend((view.version, logical, None, None) for logical in previous.keys() - view.files.keys())
            del previous
            assert_no_pending(root)
            if safe_path(root, 'data/inputs-current.json').read_bytes() != pointer_bytes:
                raise ValueError('input pointer changed during import')
            cursor.execute('''INSERT INTO maas_data.input_versions
              (version,parent_version,source_commit,origin_run_id,file_count,byte_count)
              VALUES (%s,%s,%s,%s,%s,%s)''', (view.version, parent, source_commit,
                 view.origin_run_id, len(view.files), sum(v['bytes'] for v in view.files.values())))
            if deltas:
                execute_values(cursor, '''INSERT INTO maas_data.input_deltas
                  (input_version,logical_path,physical_path,sha256) VALUES %s''', deltas, page_size=1000)
            delta_count = len(deltas)
            del deltas
            if entries(connection, view.version) != view.files:
                raise ValueError('database import parity failed')
            verify_view(connection, view.version, store)
            ensure_source_order(connection, view.version, store)
    return {'inputVersion': view.version, 'files': len(view.files), 'deltaFiles': delta_count,
            'copiedObjects': copied, 'idempotent': False}


def restore_view(connection, version, store, destination):
    """Recover into an empty directory. A failed recovery never publishes a pointer."""
    root = Path(destination)
    if root.exists() and any(root.iterdir()):
        raise ValueError('restore destination must be empty')
    verify_view(connection, version, store)
    files = entries(connection, version)
    _validate_files(files, version)
    with connection.cursor() as cursor:
        cursor.execute('SELECT origin_run_id,file_count,byte_count FROM maas_data.input_versions WHERE version=%s', (version,))
        origin, count, size = cursor.fetchone()
    if len(files) != count or sum(v['bytes'] for v in files.values()) != size:
        raise ValueError('database view counts differ')
    for meta in files.values():
        raw = store.get(meta['sha256'], expected_bytes=meta['bytes'])
        path = safe_path(root, meta['path'])
        if path.exists():
            if path.read_bytes() != raw:
                raise ValueError('conflicting physical paths')
        else:
            atomic(path, raw)
    manifest = {'schemaVersion': 1, 'inputVersion': version, 'originRunId': origin, 'files': files}
    manifest_path = f'data/input-manifests/{version}.json'
    atomic(safe_path(root, manifest_path), (canonical(manifest) + '\n').encode())
    pointer = {'schemaVersion': 1, 'inputVersion': version, 'manifestPath': manifest_path}
    atomic(safe_path(root, 'data/inputs-current.json'), (canonical(pointer) + '\n').encode())
    return {'inputVersion': version, 'files': count, 'bytes': size}


class PostgresInputView:
    """Read committed structured inputs directly, without restoring 190k files.

    JSON is authoritative in PostgreSQL. Byte-level audit is verify_view's
    responsibility before migration acceptance; Markdown uses the verified CAS.
    """
    def __init__(self, connection, version, store):
        self.connection, self.version, self.store = connection, version, store
        self.compact_archives = True
        # JSON's per-document decoder otherwise allocates the same field names
        # hundreds of thousands of times. Bound this cache; arbitrary source
        # keys must not grow a process-global intern table.
        self._field_names = {}
        self.files = entries(connection, version)
        _validate_files(self.files, version)
        with connection.cursor() as cursor:
            cursor.execute('SELECT source_order FROM maas_data.input_versions WHERE version=%s', (version,))
            self.source_order = cursor.fetchone()[0]

    def _documents(self, hashes):
        with self.connection.cursor() as cursor:
            cursor.execute('SELECT sha256,payload_json FROM maas_data.documents WHERE sha256=ANY(%s)', (list(set(hashes)),))
            rows = {}
            for sha, text in cursor.fetchall():
                if text is None:
                    raise ValueError('ordered JSON backfill required before database export')
                rows[sha] = json.loads(text, object_pairs_hook=self._ordered_object)
        if set(rows) != set(hashes):
            raise ValueError('committed structured document missing')
        return rows

    def _ordered_object(self, pairs):
        out = {}
        for key, value in pairs:
            if key in self._field_names:
                key = self._field_names[key]
            elif len(self._field_names) < 1024 and len(key) <= 40:
                self._field_names[key] = key
            out[key] = value
        return out

    def read_json(self, logical):
        sha = self.files[logical]['sha256']
        value = self._documents([sha])[sha]
        if logical == 'data/price-facts/current.json':
            order = self.source_order
            if order is None or len(set(order)) != len(order) or set(order) != set(value.get('sources', {})):
                raise ValueError('source ordering metadata missing or corrupt')
            value['sources'] = {key: value['sources'][key] for key in order}
        return value

    def iter_json(self, relative, pattern):
        names = sorted(name for name in self.files if Path(name).match(relative + '/' + pattern))
        for offset in range(0, len(names), 500):
            batch = names[offset:offset + 500]
            rows = self._documents([self.files[name]['sha256'] for name in batch])
            for name in batch:
                yield name, rows[self.files[name]['sha256']]

    def read_text(self, logical):
        meta = self.files[logical]
        return self.store.get(meta['sha256'], expected_bytes=meta['bytes']).decode('utf-8')
