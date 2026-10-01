#!/usr/bin/env python3
"""Deterministic trigger classification and main-ancestor candidate selection."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import subprocess


def classify(paths: list[str]) -> dict:
    weekly = any(p.startswith('data/weekly/') and p.endswith('.md') for p in paths)
    def runtime(p):
        if p.startswith(('data/', 'site/src/content/')):
            return True
        if p.startswith(('docs/', 'research/')) or p.endswith('.md'):
            return False
        return True
    return {'deploy': any(runtime(p) for p in paths), 'importWeekly': weekly}


def git(repo: Path, *args: str) -> str:
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()


def candidate(repo: Path, sha: str, main: str) -> dict:
    if len(sha) != 40 or any(c not in '0123456789abcdef' for c in sha):
        return {'eligible': False, 'reason': 'candidate must be a full SHA'}
    if git(repo, 'rev-parse', 'HEAD') != sha:
        return {'eligible': False, 'reason': 'checkout does not match candidate'}
    ancestor = subprocess.run(['git', '-C', str(repo), 'merge-base', '--is-ancestor', sha, main], capture_output=True).returncode
    if ancestor != 0:
        return {'eligible': False, 'reason': 'candidate is not an approved main ancestor'}
    changes = git(repo, 'diff', '--name-only', sha, main).splitlines()
    if classify(changes)['deploy']:
        return {'eligible': False, 'reason': 'superseded by runtime changes on main'}
    return {'eligible': True, 'reason': 'exact main candidate; later documentation is harmless'}


def main():
    p = argparse.ArgumentParser()
    p.add_argument('mode', choices=['trigger', 'candidate'])
    p.add_argument('--repo', type=Path, default=Path.cwd())
    p.add_argument('--before')
    p.add_argument('--after')
    p.add_argument('--sha')
    p.add_argument('--main-ref', default='origin/main')
    a = p.parse_args()
    if a.mode == 'candidate':
        result = candidate(a.repo, a.sha or '', a.main_ref)
    else:
        try:
            paths = git(a.repo, 'diff', '--name-only', a.before or '', a.after or 'HEAD').splitlines()
            result = classify(paths)
        except subprocess.CalledProcessError:
            # Missing history cannot prove a documentation-only change.
            result = {'deploy': True, 'importWeekly': False}
    print(json.dumps(result, ensure_ascii=False))

if __name__ == '__main__':
    main()
