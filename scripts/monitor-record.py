#!/usr/bin/env python3
"""Predefined CLI stage recorder. No admin execution endpoint; no raw error capture."""
import argparse
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
ACTIONS = {
    'site-projection': ['python3', 'pipeline/scripts/project-site-data.py'],
    'public-export': ['python3', 'pipeline/scripts/export-public-data.py'],
    'public-validation': ['python3', 'pipeline/scripts/export-public-data.py', '--check'],
    'archive-validation': ['python3', 'pipeline/scripts/validate-archive.py'],
    'price-validation': ['python3', 'pipeline/scripts/validate-price-archive.py'],
    'daily-summary': ['python3', 'pipeline/scripts/llm-digest.py'],
    'weekly-summary': ['python3', 'pipeline/scripts/llm-weekly-digest.py', '--all'],
    'weekly-import': ['python3', 'site/scripts/import-weekly.py'],
    'build-deploy': ['ops/deploy-release.sh'],
    'release-verify': ['ops/verify-release.sh'],
    'diff-sync': ['python3', 'pipeline/scripts/sync-diff-to-site.py'],
}
def now(): return int(datetime.now(timezone.utc).timestamp() * 1000)
def version():
    p = ROOT / 'data/inputs-current.json'
    try: return json.loads(p.read_text()).get('inputVersion')
    except (OSError, ValueError): return None

def output_version(action):
    if action == 'build-deploy': return None
    if action == 'release-verify': return os.environ.get('RELEASE_ID')
    if action in ('public-export', 'public-validation'):
        try: return json.loads((ROOT/'data/public/v1/manifest.json').read_text()).get('datasetVersion')
        except (OSError, ValueError): return None
    return version()

def main():
    ap = argparse.ArgumentParser(); ap.add_argument('action', choices=ACTIONS); args = ap.parse_args()
    command = list(ACTIONS[args.action])
    if args.action == 'build-deploy':
        candidate = os.environ.get('CANDIDATE_SHA', '')
        import re
        if not re.fullmatch(r'[a-f0-9]{40}', candidate): raise ValueError('exact commit required')
        command += ['--commit', candidate]
    if args.action == 'release-verify':
        release = os.environ.get('RELEASE_ID', '')
        import re
        if not re.fullmatch(r'rl_[a-f0-9]{10}_[a-f0-9]{12}', release): raise ValueError('release ID required')
        command += ['--online', '--expect-release', release]
    root = os.environ.get('MAAS_MONITOR_OUTPUT')
    if not root: return subprocess.call(command, cwd=ROOT)
    output = Path(root)
    if not output.is_absolute() or output.is_symlink(): raise ValueError('private absolute monitor output required')
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    started = now(); before = version()
    run_id = 'stage_' + uuid.uuid4().hex
    repo = os.environ.get('GITHUB_REPOSITORY', ''); ghid = os.environ.get('GITHUB_RUN_ID', '')
    import re
    link = f'https://github.com/{repo}/actions/runs/{ghid}' if re.fullmatch(r'[\w.-]+/[\w.-]+', repo) and ghid.isdigit() else None
    path = output / (run_id + '.json')
    initial = {'id': run_id, 'kind': args.action, 'trigger': 'schedule' if os.environ.get('GITHUB_EVENT_NAME') == 'schedule' else 'workflow' if ghid else 'manual',
               'state': 'running', 'stage': args.action, 'startedAt': started, 'finishedAt': None, 'observedAt': started,
               'inputVersion': os.environ.get('CANDIDATE_SHA') if args.action == 'build-deploy' else before, 'outputVersion': None, 'result': 'unknown',
               'validation': 'unknown', 'publication': 'unknown', 'errorCode': None, 'runLink': link, 'sources': []}
    def save(record):
        temporary = path.with_suffix('.tmp'); temporary.write_text(json.dumps(record,sort_keys=True)+'\n'); temporary.chmod(0o600); temporary.replace(path)
    save(initial)
    try: code = subprocess.call(command, cwd=ROOT)
    except OSError: code = 127
    finished = now()
    validation = 'passed' if code == 0 else 'failed'
    record = {'id': run_id, 'kind': args.action, 'trigger': 'schedule' if os.environ.get('GITHUB_EVENT_NAME') == 'schedule' else 'workflow' if ghid else 'manual',
              'state': 'succeeded' if code == 0 else 'failed', 'stage': args.action, 'startedAt': started, 'finishedAt': finished, 'observedAt': finished,
              'inputVersion': os.environ.get('CANDIDATE_SHA') if args.action == 'build-deploy' else before, 'outputVersion': output_version(args.action) if code == 0 else None, 'result': 'not_run' if code == 0 and args.action in ('daily-summary','weekly-summary') and not os.environ.get('LLM_API_KEY') else 'success' if code == 0 else 'failed',
              'validation': validation if args.action.endswith('validation') else 'unknown', 'publication': ('completed' if code == 0 else 'failed') if args.action == 'release-verify' else 'unknown' if args.action == 'build-deploy' else 'not_run',
              'errorCode': None if code == 0 else 'validation_failed' if args.action.endswith('validation') else 'execution_failed', 'runLink': link, 'sources': []}
    save(record)
    return code
if __name__ == '__main__': sys.exit(main())
