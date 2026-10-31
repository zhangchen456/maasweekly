"""Shared, root-owned deployment readiness and pre-write capacity gates."""
import json
import os
import re
import subprocess
import time
from pathlib import Path
from urllib.request import urlopen

GIB = 1024 ** 3


class CapacityError(RuntimeError):
    pass


def publication_identity(manifest):
    site = manifest['site']
    result = dict(datasetVersion=manifest['datasetVersion'], inputVersion=site['inputVersion'],
                  codeCommit=site['codeCommit'], formatVersion=site['formatVersion'])
    if (not re.fullmatch(r'ds_[a-f0-9]{64}', result['datasetVersion'])
            or not re.fullmatch(r'in_[a-f0-9]{64}', result['inputVersion'])
            or not re.fullmatch(r'[a-f0-9]{40}', result['codeCommit']) or result['formatVersion'] != 1):
        raise ValueError('invalid expected publication identity')
    return result


def accepts_runtime(health, manifest, process_code):
    return (isinstance(health,dict) and health.get('schemaVersion') == 1 and health.get('ready') is True
            and health.get('processCode') == process_code
            and health.get('publication') == publication_identity(manifest)
            and health.get('lastReloadError') is None
            and isinstance(health.get('lastReloadAt'), str))


def wait_runtime(port, manifest, process_code, *, timeout=90, read=None, sleep=time.sleep):
    if type(port) is not int or not 1024 <= port <= 65535:
        raise ValueError('invalid runtime port')
    def fetch():
        with urlopen(f'http://127.0.0.1:{port}/_runtime/health', timeout=5) as response:
            return json.loads(response.read(65537))
    read = read or fetch
    deadline = time.monotonic() + timeout
    while True:
        try:
            health = read()
            if accepts_runtime(health, manifest, process_code):
                return health
        except (OSError, ValueError, KeyError, TypeError):
            pass
        if time.monotonic() >= deadline:
            raise RuntimeError('runtime has not accepted the exact publication and code')
        sleep(min(2, max(0, deadline - time.monotonic())))


def capacity_budget(operation, *, free_bytes, free_inodes, total_bytes, database_bytes,
                    public_bytes, workspace_bytes=0, package_bytes=0, workspace_files=0):
    """Conservative incremental peak plus DB/OS reserve; no automatic deletion."""
    values = [free_bytes, free_inodes, total_bytes, database_bytes, public_bytes,
              workspace_bytes, package_bytes, workspace_files]
    if any(type(v) is not int or v < 0 for v in values) or total_bytes == 0:
        raise ValueError('invalid capacity measurement')
    reserve = max(2 * GIB, total_bytes // 20)
    if operation == 'code':
        peak = 2 * package_bytes + 256 * 1024 ** 2
        inodes = 60000
    elif operation in {'prepare', 'validate', 'update', 'weekly', 'aggregate', 'import', 'rebuild', 'resume'}:
        workspace = 0 if operation in {'rebuild', 'validate'} else workspace_bytes
        # Writer recovery may retain the old cache while reconstructing a complete one.
        peak = workspace + 2 * public_bytes + database_bytes + max(GIB // 2, database_bytes // 4)
        inodes = 10000 + (workspace_files if workspace else 0)
    elif operation == 'publish':
        peak = 2 * public_bytes + database_bytes + GIB // 2
        inodes = 10000
    else:
        raise ValueError('unknown capacity operation')
    result = {'schemaVersion': 1, 'operation': operation, 'freeBytes': free_bytes,
              'requiredFreeBytes': reserve + peak, 'reserveBytes': reserve, 'estimatedPeakBytes': peak,
              'freeInodes': free_inodes, 'requiredInodes': inodes,
              'databaseBytes': database_bytes, 'publicBytes': public_bytes,
              'workspaceBytes': workspace_bytes, 'packageBytes': package_bytes}
    result['allowed'] = free_bytes >= reserve + peak and free_inodes >= inodes
    return result


def measure_capacity(root, operation, package_bytes=0):
    root = Path(root)
    shared = root / 'shared'
    stat = os.statvfs(shared)
    manifest = json.loads((shared / 'public-data/v1/publication.json').read_text())
    public_bytes = sum(item['bytes'] for item in manifest['files'])
    result = subprocess.run(['runuser', '-u', 'maasdata', '--', 'psql', '-X', '-At', '-d', 'maas_data',
                             '-c', 'SELECT pg_database_size(current_database())'],
                            check=True, capture_output=True, text=True, timeout=10)
    database_bytes = int(result.stdout.strip())
    workspace_bytes = workspace_files = 0
    if operation not in {'code', 'publish', 'rebuild', 'validate'}:
        writer = shared / 'data-store/writer'
        size = subprocess.run(['du', '-sk', str(writer)], check=True, capture_output=True, text=True, timeout=60)
        workspace_bytes = int(size.stdout.split()[0]) * 1024
        # Input inventory file_count is not guaranteed to include all recovery files.
        workspace_files = sum(len(files) for _, _, files in os.walk(writer, followlinks=False))
    return capacity_budget(operation, free_bytes=stat.f_bavail * stat.f_frsize,
                           free_inodes=stat.f_favail, total_bytes=stat.f_blocks * stat.f_frsize,
                           database_bytes=database_bytes, public_bytes=public_bytes,
                           workspace_bytes=workspace_bytes, workspace_files=workspace_files,
                           package_bytes=package_bytes)


def require_capacity(root, operation, package_bytes=0):
    result = measure_capacity(root, operation, package_bytes)
    print(json.dumps({'kind': 'capacity.check', **result}), flush=True)
    if not result['allowed']:
        raise CapacityError('insufficient disk/inode headroom; current publication preserved')
    return result
