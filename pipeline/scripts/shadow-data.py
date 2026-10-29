#!/usr/bin/env python3
"""Explicit PostgreSQL shadow import/recovery. DSN comes from MAAS_SHADOW_DSN."""
import argparse
import json
import os
import subprocess
import time
from pathlib import Path
import sys

BASE = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BASE / 'pipeline'))
from blob_store import FilesystemBlobStore
from shadow_store import migrate, import_view, restore_view, verify_view, ensure_source_order, backfill_ordered_json


def main():
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['migrate', 'import', 'restore', 'verify', 'backfill-order', 'backfill-json'])
    parser.add_argument('--blob-root', type=Path)
    parser.add_argument('--source-root', type=Path, default=BASE)
    parser.add_argument('--commit')
    parser.add_argument('--parent')
    parser.add_argument('--version')
    parser.add_argument('--destination', type=Path)
    args = parser.parse_args()
    if args.action != 'migrate' and not args.blob_root:
        parser.error('--blob-root required')
    if args.action == 'import' and not args.commit:
        parser.error('--commit required')
    if args.action == 'restore' and (not args.version or not args.destination):
        parser.error('--version and --destination required')
    if args.action in ('verify', 'backfill-order', 'backfill-json') and not args.version:
        parser.error('--version required')
    import psycopg2
    connection = psycopg2.connect(os.environ['MAAS_SHADOW_DSN'])
    try:
        if args.action == 'migrate':
            result = {'schemaVersion': migrate(connection)}
        elif args.action == 'import':
            actual = subprocess.check_output(['git', '-C', str(args.source_root), 'rev-parse', 'HEAD'], text=True).strip()
            if actual != args.commit:
                raise ValueError('source commit mismatch')
            dirty = subprocess.check_output(['git', '-C', str(args.source_root), 'status', '--porcelain', '--', 'data/'], text=True)
            if dirty.strip():
                raise ValueError('source data differs from fixed commit')
            result = import_view(connection, args.source_root, FilesystemBlobStore(args.blob_root),
                                 source_commit=args.commit, parent=args.parent)
        elif args.action == 'restore':
            result = restore_view(connection, args.version, FilesystemBlobStore(args.blob_root), args.destination)
        elif args.action == 'backfill-order':
            with connection:
                result = {'inputVersion': args.version, 'sourceOrder': ensure_source_order(connection, args.version, FilesystemBlobStore(args.blob_root))}
        elif args.action == 'backfill-json':
            with connection:
                result = backfill_ordered_json(connection, args.version, FilesystemBlobStore(args.blob_root))
        else:
            result = verify_view(connection, args.version, FilesystemBlobStore(args.blob_root))
        print(json.dumps({**result, 'elapsedSeconds': time.monotonic() - started}))
    finally:
        connection.close()


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Connection exceptions may contain credentials or server details.
        print('shadow operation failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(2)
