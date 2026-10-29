#!/usr/bin/env python3
"""Build a verified external data candidate from PostgreSQL. Never activates it.

MAAS_DATA_DSN uses local peer auth in production. Code and data IDs are separate;
this command never writes tracked data or invokes Astro, npm or Git commit.
"""
import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import sys
import time

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'pipeline'))
from blob_store import FilesystemBlobStore
from input_snapshot import atomic
from shadow_store import PostgresInputView
from page_projection import store_projections


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-version', required=True)
    parser.add_argument('--code-commit', required=True)
    parser.add_argument('--config-root', type=Path, default=BASE)
    parser.add_argument('--blob-root', type=Path, required=True)
    parser.add_argument('--candidate-dir', type=Path, required=True)
    parser.add_argument('--expected-dataset')
    parser.add_argument('--expected-manifest', type=Path,
                        help='migration gate: require byte-identical business files to an existing manifest')
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch('[0-9a-f]{40}', args.code_commit):
        parser.error('fixed --code-commit required')
    destination = args.candidate_dir.resolve()
    if destination.is_relative_to(BASE) or destination.is_relative_to(args.config_root.resolve()):
        parser.error('candidate must be outside code/config repository')
    if destination.exists() and any(destination.iterdir()):
        parser.error('candidate directory must be empty')
    started = time.monotonic()
    spec = importlib.util.spec_from_file_location('database_exporter', BASE / 'pipeline/scripts/export-public-data.py')
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    import psycopg2
    from psycopg2.extras import Json
    connection = psycopg2.connect(os.environ['MAAS_DATA_DSN'])
    try:
        view = PostgresInputView(connection, args.input_version, FilesystemBlobStore(args.blob_root))
        release = exporter.build_release(args.config_root.resolve(), input_view=view)
        if args.expected_dataset and release['datasetVersion'] != args.expected_dataset:
            raise ValueError('expected dataset version differs')
        if args.expected_manifest:
            expected = json.loads(args.expected_manifest.read_text())
            if expected['datasetVersion'] != release['datasetVersion']:
                raise ValueError('baseline dataset version differs')
            files = {Path(row['path']).name: row for row in expected['files']}
            if set(files) != set(exporter.BUSINESS_FILES):
                raise ValueError('baseline file membership differs')
            for name in exporter.BUSINESS_FILES:
                key = 'modelIdentities' if name == 'model-identities.json' else name[:-5]
                raw = (json.dumps(release[key], ensure_ascii=False, indent=2) + '\n').encode()
                if len(raw) != files[name]['bytes'] or hashlib.sha256(raw).hexdigest() != files[name]['sha256']:
                    raise ValueError('baseline business file bytes differ')
        if exporter.publish(destination, release) != 0 or exporter.run_check(destination) != 0:
            raise ValueError('candidate output validation failed')
        manifest = json.loads((destination / 'manifest.json').read_text())
        # Record a verified candidate, not a published/latest pointer. Existing
        # code/config must explicitly opt into it after compatibility smoke tests.
        with connection:
            projection_names = store_projections(connection, args.config_root.resolve(), view, args.code_commit)
            with connection.cursor() as cursor:
                cursor.execute('''INSERT INTO maas_data.data_candidates
                  (dataset_version,input_version,code_commit,data_through,files)
                  VALUES (%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING''',
                  (release['datasetVersion'], view.version, args.code_commit, release['dataThrough'], Json(manifest['files'])))
                cursor.execute('''SELECT files FROM maas_data.data_candidates
                  WHERE dataset_version=%s AND input_version=%s AND code_commit=%s''',
                  (release['datasetVersion'], view.version, args.code_commit))
                if cursor.fetchone()[0] != manifest['files']:
                    raise ValueError('candidate audit conflicts with verified output')
                cursor.execute('''UPDATE maas_data.data_candidates SET page_format_version=1
                  WHERE dataset_version=%s AND input_version=%s AND code_commit=%s''',
                  (release['datasetVersion'], view.version, args.code_commit))
        manifest['site'] = {'inputVersion':view.version,'codeCommit':args.code_commit,'formatVersion':1}
        atomic(destination / 'publication.json', (json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode())
        report = {'status': 'verified_candidate', 'activated': False,
                  'datasetVersion': release['datasetVersion'], 'inputVersion': view.version,
                  'codeCommit': args.code_commit, 'dataThrough': release['dataThrough'],
                  'baselineByteParity': True if args.expected_manifest else None,
                  'pageFormatVersion': 1, 'pageProjections': projection_names,
                  'publicationSha256': hashlib.sha256((destination / 'publication.json').read_bytes()).hexdigest(),
                  'manifestSha256': hashlib.sha256((destination / 'manifest.json').read_bytes()).hexdigest(),
                  'files': manifest['files'], 'elapsedSeconds': time.monotonic() - started}
        atomic(args.report, (json.dumps(report, indent=2) + '\n').encode())
        print(json.dumps(report))
    finally:
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('database candidate failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(2)
