#!/usr/bin/env python3
"""Run the complete existing regression and persist its real exit code/evidence."""
from __future__ import annotations
import argparse
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

BASE = Path(__file__).resolve().parent.parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--task', required=True)
    args = parser.parse_args()
    if not args.task.startswith('AR-') or any(c not in 'AR-0123456789abcdefghijklmnopqrstuvwxyz' for c in args.task):
        parser.error('task must be an AR task identifier')
    root = BASE / 'docs/architecture/refactoring-2026-10/acceptance' / args.task
    root.mkdir(parents=True, exist_ok=True)
    attempt = root / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    attempt.mkdir()
    log = attempt / 'regression.txt'
    started = datetime.datetime.now(datetime.timezone.utc).isoformat()
    before = subprocess.check_output(['git', 'status', '--short'], cwd=BASE, text=True)
    t = time.monotonic()
    with log.open('w') as stream:
        try:
            exit_code = subprocess.run(['bash', 'scripts/run-all-tests.sh'], cwd=BASE, stdout=stream, stderr=subprocess.STDOUT).returncode
        except KeyboardInterrupt:
            exit_code = 130
    report = {'task': args.task, 'startedAt': started,
              'completedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
              'commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=BASE, text=True).strip(),
              'python': subprocess.check_output(['python3', '--version'], text=True).strip(),
              'node': subprocess.check_output(['node', '--version'], text=True).strip(),
              'command': 'bash scripts/run-all-tests.sh', 'exitCode': exit_code,
              'elapsedSeconds': time.monotonic() - t,
              'log': str(log.relative_to(BASE)), 'logSha256': hashlib.sha256(log.read_bytes()).hexdigest(),
              'initialWorktree': before,
              'finalWorktree': subprocess.check_output(['git', 'status', '--short'], cwd=BASE, text=True)}
    payload = json.dumps(report, ensure_ascii=False, indent=2) + '\n'
    (attempt / 'regression.json').write_text(payload)
    (root / 'regression.json').write_text(payload)
    print(json.dumps({k: report[k] for k in ['task', 'exitCode', 'elapsedSeconds', 'log']}, ensure_ascii=False), flush=True)
    if exit_code:
        print('\n'.join(log.read_text().splitlines()[-35:]), flush=True)
    raise SystemExit(exit_code)

if __name__ == '__main__':
    main()
