"""Coordinate fixed worker units under release.lock; never kill in-flight model calls."""
import json, subprocess, time
from pathlib import Path

WORKERS = ('editorial', 'diagnostic')

def state(name):
    result = subprocess.run(['systemctl', 'show', 'maas-'+name+'-worker.service',
                             '-p', 'MainPID', '-p', 'ActiveState', '-p', 'SendSIGKILL'], check=True,
                            capture_output=True, text=True, timeout=10)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

def drain(timeout=210):
    # Stop cancels pending automatic restarts too. Refuse unless the audited
    # service configuration disables timeout KILL; an in-flight task may finish.
    states = [state(name) for name in WORKERS]
    if any(s.get('SendSIGKILL') != 'no' for s in states):
        raise RuntimeError('install worker units with SendSIGKILL=no before draining')
    for name in WORKERS:
        subprocess.run(['systemctl', 'stop', '--no-block', 'maas-'+name+'-worker.service'], check=True, timeout=10)
    deadline = time.monotonic()+timeout
    while True:
        states = [state(name) for name in WORKERS]
        if all(int(s.get('MainPID', 0)) == 0 and s.get('ActiveState') in ('inactive','failed') for s in states):return
        if time.monotonic() >= deadline:raise RuntimeError('worker drain timed out; no process was force-killed')
        time.sleep(.25)

def start_and_verify(root, package, timeout=30):
    manifest = json.loads((package/'metadata/runtime-manifest.json').read_text())
    protocol = manifest.get('components', {}).get('workerProtocol', 0)
    for name in WORKERS:
        subprocess.run(['systemctl', 'start', 'maas-'+name+'-worker.service'], check=True, timeout=15)
    deadline = time.monotonic()+timeout
    while True:
        proofs = {}
        for name in WORKERS:
            status = state(name);pid = int(status.get('MainPID', 0))
            try:
                if not pid or status.get('ActiveState') != 'active':continue
                if Path(f'/proc/{pid}/cwd').resolve(strict=True) != package/'agent-api':continue
                if protocol == 1:
                    receipt = json.loads((root/'shared/state/worker-runtime'/f'{name}-worker.json').read_text())
                    if receipt != {'protocol':1,'pid':pid,'code':package.name,'phase':'ready'}:continue
                proofs[name] = {'pid':pid,'code':package.name,'protocol':protocol}
            except (OSError, ValueError):continue
        if len(proofs) == len(WORKERS):return proofs
        if time.monotonic() >= deadline:raise RuntimeError('worker process identity/readiness mismatch')
        time.sleep(.25)

def managed(package):
    path = package/'metadata/runtime-manifest.json'
    return path.exists() and json.loads(path.read_text()).get('components', {}).get('workerProtocol') == 1
