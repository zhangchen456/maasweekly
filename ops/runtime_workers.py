"""Coordinate fixed worker units under release.lock; never kill in-flight model calls."""
import json, subprocess, time
from pathlib import Path

WORKERS = ('editorial', 'diagnostic')

def state(name):
    result = subprocess.run(['systemctl', 'show', 'maas-'+name+'-worker.service',
                             '-p', 'MainPID', '-p', 'ActiveState'], check=True,
                            capture_output=True, text=True, timeout=10)
    return dict(line.split('=', 1) for line in result.stdout.splitlines() if '=' in line)

def drain(timeout=210):
    # kill --signal sends only TERM, unlike stop it has no later forced KILL.
    # The worker stops claiming and finishes its current fenced task before exit.
    for name in WORKERS:
        if int(state(name).get('MainPID', 0)):
            subprocess.run(['systemctl', 'kill', '--kill-whom=main', '--signal=SIGTERM',
                            'maas-'+name+'-worker.service'], check=True, timeout=10)
    deadline = time.monotonic()+timeout
    while True:
        if all(int(state(name).get('MainPID', 0)) == 0 for name in WORKERS):return
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
                    receipt = json.loads((root/'shared/state'/f'{name}-worker.json').read_text())
                    if receipt != {'protocol':1,'pid':pid,'code':package.name,'phase':'ready'}:continue
                proofs[name] = {'pid':pid,'code':package.name,'protocol':protocol}
            except (OSError, ValueError):continue
        if len(proofs) == len(WORKERS):return proofs
        if time.monotonic() >= deadline:raise RuntimeError('worker process identity/readiness mismatch')
        time.sleep(.25)

def managed(package):
    path = package/'metadata/runtime-manifest.json'
    return path.exists() and json.loads(path.read_text()).get('components', {}).get('workerProtocol') == 1
