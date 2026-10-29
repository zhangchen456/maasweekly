#!/usr/bin/env bash
# One-time isolated shadow import. Does not change any application/data pointer.
set -euo pipefail
test "$(id -u)" -eq 0 || { echo 'root required' >&2; exit 2; }
root=/srv/maasweekly/shared/data-store
bundle="$root/incoming/migration-20261029"
code="$bundle/code"
version=in_72aa2a23b9fcff10f0d799dd23c06e5997d6ddceb4e5a112947f602b0c0cdd42
test -d "$bundle" && test ! -L "$bundle"
python3 - "$code" <<'PY'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);checks=json.loads((root/'code-manifest.json').read_text())
for name,sha in checks.items():
    p=root/name
    if not p.resolve().is_relative_to(root.resolve()) or p.is_symlink() or hashlib.sha256(p.read_bytes()).hexdigest()!=sha:
        raise ValueError('code transfer integrity')
print('Verified code/config files:',len(checks))
PY
chown -R maasdata:maasdata "$bundle"
# Keep migration processes inside a memory/CPU budget on the shared server.
systemd-run --unit=maasdata-shadow-unpack --wait --pipe --collect \
  -p User=maasdata -p MemoryMax=768M -p CPUQuota=100% -p Nice=10 \
  /usr/bin/python3 "$code/ops/verify-shadow-transfer.py" --bundle "$bundle" \
  --blob-root "$root/blobs" --pipeline-root "$code/pipeline" \
  --report "$root/reports/transfer-20261029.json"
tables=$(runuser -u maasdata -- psql -XAt -d maas_data -c "SELECT count(*) FROM information_schema.tables WHERE table_schema='maas_data'")
if test "$tables" -eq 0; then
  runuser -u maasdata -- pg_restore --exit-on-error --single-transaction \
    --no-owner --no-privileges -d maas_data "$bundle/shadow.dump"
fi
runuser -u maasdata -- env MAAS_SHADOW_DSN=dbname=maas_data \
  python3 "$code/pipeline/scripts/shadow-data.py" migrate
runuser -u maasdata -- env MAAS_SHADOW_DSN=dbname=maas_data \
  python3 "$code/pipeline/scripts/shadow-data.py" backfill-order \
  --version "$version" --blob-root "$root/blobs"
systemd-run --unit=maasdata-shadow-json-backfill --wait --pipe --collect \
  -p User=maasdata -p MemoryMax=768M -p CPUQuota=100% -p Nice=10 \
  --setenv=MAAS_SHADOW_DSN=dbname=maas_data \
  /usr/bin/python3 "$code/pipeline/scripts/shadow-data.py" backfill-json \
  --version "$version" --blob-root "$root/blobs"
systemd-run --unit=maasdata-shadow-verify --wait --pipe --collect \
  -p User=maasdata -p MemoryMax=768M -p CPUQuota=100% -p Nice=10 \
  --setenv=MAAS_SHADOW_DSN=dbname=maas_data \
  /usr/bin/python3 "$code/pipeline/scripts/shadow-data.py" verify \
  --version "$version" --blob-root "$root/blobs" > "$root/reports/database-verify-20261029.json"
runuser -u maasdata -- python3 - "$code/pipeline" "$bundle/raw-manifest.json" "$root/blobs" "$root/reports/raw-verify-20261029.json" <<'PY'
import json,sys
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from blob_store import FilesystemBlobStore
from storage_migration import verify_objects
result=verify_objects(json.loads(Path(sys.argv[2]).read_text()),FilesystemBlobStore(Path(sys.argv[3])))
Path(sys.argv[4]).write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result))
if result['failures']:raise SystemExit(2)
PY
echo 'Shadow import verified. Application, scheduler and published data pointers unchanged.'
