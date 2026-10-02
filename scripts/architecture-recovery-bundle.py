#!/usr/bin/env python3
"""Retain interrupted runner data for a same-commit recovery checkout. No credentials."""
import argparse
import json
import sys
import tarfile
from pathlib import Path
BASE = Path(__file__).resolve().parents[1]; sys.path.insert(0, str(BASE / 'pipeline'))
from input_snapshot import PENDING, POINTER, role_files, safe

def bundle(root, output):
    pending = safe(root, PENDING)
    if not pending.exists(): return False
    paths = set(role_files(root)) | {PENDING, POINTER}
    for pattern in ('data/input-objects/*', 'data/input-manifests/*.json', 'data/*-runs/staging/*/journal.json', 'data/snapshots/content/*', 'data/*-runs/staging/*/discarded/**/*'):
        paths.update(str(p.relative_to(root)) for p in root.glob(pattern) if p.is_file())
    for logical in sorted(paths): safe(root, logical)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, 'w:gz') as archive:
        for logical in sorted(paths): archive.add(safe(root, logical), arcname=logical, recursive=False)
    print(json.dumps({'files': len(paths), 'bytes': output.stat().st_size, 'pendingRun': json.loads(pending.read_text())['runId']}))
    return True
if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__); parser.add_argument('--input-root',type=Path,default=BASE); parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args(); bundle(args.input_root.resolve(),args.output)
