#!/usr/bin/env bash
# Called only after staging deterministic projections. Never rebase/force push.
set -euo pipefail
MESSAGE="${1:?commit message required}"
[ ! -e data/pipeline-pending.json ] && [ ! -e data/storage-restore-pending.json ] || {
  echo 'input recovery is pending; complete recovery before committing data' >&2
  exit 76
}
git fetch --no-tags origin main
[ "$(git rev-parse HEAD)" = "$(git rev-parse origin/main)" ] || {
  echo 'main changed during collection; regenerate from latest inputs on a new run' >&2
  exit 75
}
if ! git diff --cached --quiet; then
  git commit -m "$MESSAGE"
  # A concurrent code push after the check makes this push fail safely.
  git push origin HEAD:main
fi
SHA="$(git rev-parse HEAD)"
echo "Exact data candidate: $SHA"
[ -z "${GITHUB_OUTPUT:-}" ] || echo "sha=$SHA" >> "$GITHUB_OUTPUT"
