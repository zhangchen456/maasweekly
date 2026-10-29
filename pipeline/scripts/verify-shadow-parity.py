#!/usr/bin/env python3
"""Restore a shadow DB to an empty directory and compare canonical public output.

The source remains read-only; no LLM calls, HTTP fetches or publication occur.
MAAS_SHADOW_DSN should point at the database restored from a pg_dump backup.
"""
import argparse
import gc
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'pipeline'))
from blob_store import FilesystemBlobStore
from input_snapshot import atomic
from shadow_store import restore_view
from public_export.canonical import canonical_json


def digests(release):
    return {key: hashlib.sha256(canonical_json(release[key]).encode()).hexdigest()
            for key in ('changes', 'items', 'prices', 'evidence', 'weekly', 'status', 'modelIdentities')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-root', type=Path, default=BASE)
    parser.add_argument('--blob-root', type=Path, required=True)
    parser.add_argument('--destination', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    started = time.monotonic()
    source = args.source_root.resolve()
    pointer_path = source / 'data/inputs-current.json'
    pointer_bytes = pointer_path.read_bytes()
    version = json.loads(pointer_bytes)['inputVersion']
    commit = subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip()
    spec = importlib.util.spec_from_file_location('parity_exporter', BASE / 'pipeline/scripts/export-public-data.py')
    exporter = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(exporter)
    before = exporter.build_release(source)
    expected = digests(before)
    dataset = before['datasetVersion']
    del before
    gc.collect()
    import psycopg2
    connection = psycopg2.connect(os.environ['MAAS_SHADOW_DSN'])
    try:
        result = restore_view(connection, version, FilesystemBlobStore(args.blob_root), args.destination)
    finally:
        connection.close()
    # Human-maintained model identities and source mappings are code/config,
    # not collected runtime state. Restore them from the same fixed checkout.
    for relative in ('data/model-registry', 'pipeline/config'):
        shutil.copytree(source / relative, args.destination / relative)
    after = exporter.build_release(args.destination)
    actual = digests(after)
    if actual != expected or after['datasetVersion'] != dataset:
        raise ValueError('public collection parity failed')
    if pointer_path.read_bytes() != pointer_bytes:
        raise ValueError('source input changed during parity check')
    if subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() != commit:
        raise ValueError('source commit changed during parity check')
    report = {**result, 'status': 'passed', 'sourceCommit': commit,
              'datasetVersion': dataset, 'dataThrough': after['dataThrough'],
              'collectionSha256': actual, 'elapsedSeconds': time.monotonic() - started}
    atomic(args.report, (json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps(report))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('shadow parity failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(2)
