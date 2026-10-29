#!/usr/bin/env python3
"""Validate a migration transfer and unpack SHA-addressed files as maasdata.

Does not restore PostgreSQL, publish a pointer or change running services.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import tarfile


def validate_bundle(root):
    manifest = json.loads((root / 'transfer-manifest.json').read_text())
    required = {'blobs.tar.gz', 'shadow.dump', 'raw-manifest.json', 'parity.json'}
    if manifest.get('phase') != 'shadow-only' or set(manifest['files']) != required:
        raise ValueError('unexpected transfer manifest')
    for name in required:
        p = root / name
        if p.is_symlink() or not p.is_file():
            raise ValueError('transfer path is not a regular file')
        h = hashlib.sha256()
        with p.open('rb') as stream:
            while chunk := stream.read(1024 * 1024):
                h.update(chunk)
        meta = manifest['files'][name]
        if h.hexdigest() != meta['sha256'] or p.stat().st_size != meta['bytes']:
            raise ValueError('transfer checksum mismatch')
    if json.loads((root / 'parity.json').read_text()).get('status') != 'passed':
        raise ValueError('source parity did not pass')


def unpack(root, store):
    verified = 0
    with tarfile.open(root / 'blobs.tar.gz', 'r|gz') as archive:
        for member in archive:
            name = member.name.rstrip('/')
            # BSD tar on macOS adds AppleDouble extended-attribute records.
            # They are not CAS objects. Recognize only the exact metadata paths
            # and file signature; never extract them or relax object validation.
            apple = re.fullmatch(r'(?:\._sha256|sha256/\._[0-9a-f]{2}|sha256/[0-9a-f]{2}/\._[0-9a-f]{64})', name)
            if apple:
                if not member.isfile() or not 26 <= member.size <= 1024 * 1024:
                    raise ValueError('archive metadata type/size rejected')
                with archive.extractfile(member) as stream:
                    if stream.read(4) != b'\x00\x05\x16\x07':
                        raise ValueError('archive metadata signature rejected')
                continue
            if member.isdir() and re.fullmatch(r'sha256(?:/[0-9a-f]{2})?', name):
                continue
            match = re.fullmatch(r'sha256/([0-9a-f]{2})/([0-9a-f]{64})', name)
            if not match or not member.isfile() or match[1] != match[2][:2]:
                raise ValueError('archive member path/type rejected')
            # Fixed source corpus has bounded individual objects. Avoid trusting
            # a compressed archive header to allocate unbounded memory.
            if not 0 <= member.size <= 256 * 1024 * 1024:
                raise ValueError('archive object exceeds import budget')
            with archive.extractfile(member) as stream:
                raw = stream.read(member.size + 1)
            if len(raw) != member.size or hashlib.sha256(raw).hexdigest() != match[2]:
                raise ValueError('archive object checksum mismatch')
            store.putIfAbsent(match[2], raw)
            verified += 1
    return verified


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, required=True)
    parser.add_argument('--blob-root', type=Path, required=True)
    parser.add_argument('--pipeline-root', type=Path, required=True)
    parser.add_argument('--report', type=Path, required=True)
    args = parser.parse_args()
    validate_bundle(args.bundle)
    sys.path.insert(0, str(args.pipeline_root))
    from blob_store import FilesystemBlobStore
    result = {'status': 'passed', 'phase': 'shadow-only',
              'verifiedArchiveObjects': unpack(args.bundle, FilesystemBlobStore(args.blob_root))}
    args.report.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print('shadow transfer failed: ' + type(error).__name__, file=sys.stderr)
        sys.exit(2)
