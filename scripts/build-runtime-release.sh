#!/usr/bin/env bash
# Code-only candidate; current static production activator intentionally rejects this format.
set -euo pipefail
root=$(cd "$(dirname "$0")/.." && pwd)
cd "$root"
test "$#" -eq 2 && test "$1" = --output || { echo 'usage: build-runtime-release.sh --output ABSOLUTE_NEW_DIRECTORY' >&2; exit 2; }
case "$2" in /*) output=$2;; *) echo 'absolute output required' >&2; exit 2;; esac
test ! -e "$output" || { echo 'output already exists' >&2; exit 2; }
test -z "$(git status --porcelain)" || { echo 'clean committed checkout required' >&2; exit 2; }
commit=$(git rev-parse HEAD)
python3 scripts/generate-public-contract.py --check
node scripts/ensure-node-deps.mjs services/agent-api
node scripts/ensure-node-deps.mjs site
npm --prefix services/agent-api test
npm --prefix site run build:runtime
test -z "$(git status --porcelain)" || { echo 'build changed tracked inputs' >&2; exit 2; }
umask 027
mkdir -p "$output/agent-api" "$output/site" "$output/metadata" "$output/scripts"
cp -R services/agent-api/dist services/agent-api/package.json services/agent-api/package-lock.json "$output/agent-api/"
cp -R site/dist site/package.json site/package-lock.json "$output/site/"
cp scripts/verify-runtime-site.mjs "$output/scripts/"
(cd "$output/agent-api" && npm ci --omit=dev --prefer-offline --silent)
(cd "$output/site" && npm ci --omit=dev --prefer-offline --silent)
python3 - "$output" "$commit" <<'MANIFEST'
import hashlib,json,sys
from pathlib import Path
root=Path(sys.argv[1]);files=[]
for p in sorted(root.rglob('*')):
    if p.is_symlink():
        if not p.resolve().is_relative_to(root.resolve()):raise ValueError('package symlink escape')
        files.append({'path':str(p.relative_to(root)),'symlink':str(p.readlink())})
    elif p.is_file():
        files.append({'path':str(p.relative_to(root)),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()})
manifest={'format':'maas-runtime-candidate-v1','codeCommit':sys.argv[2],'pageFormatVersion':1,
          'activated':False,'productionCompatible':False,'requires':'isolated Linux SSR/permission/blue-green/rollback acceptance before production activation',
          'dataIncluded':False,'files':files,'totalBytes':sum(f.get('bytes',0) for f in files)}
(root/'metadata/runtime-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({k:v for k,v in manifest.items() if k!='files'}))
MANIFEST
