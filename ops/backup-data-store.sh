#!/usr/bin/env bash
# Local, transaction-consistent database dump. Blobs must be backed up separately.
set -euo pipefail
test "$(id -un)" = maasdata || { echo 'run as maasdata' >&2; exit 2; }
root=/srv/maasweekly/shared/data-store/backups
test -d "$root" && test ! -L "$root"
umask 077
stamp=$(date -u +%Y%m%dT%H%M%SZ)
temp=$(mktemp "$root/.dump.XXXXXXXX")
trap 'rm -f "$temp"' EXIT
pg_dump --format=custom --no-owner --no-privileges --dbname=maas_data --file="$temp"
pg_restore --list "$temp" >/dev/null
target="$root/maas_data-$stamp.dump"
# Never overwrite an older backup with an identical-second invocation.
ln "$temp" "$target"
sha256sum "$target" > "$target.sha256"
echo "Database backup: $target"
echo 'Local backup only. Filesystem blobs and an off-host recovery copy are still required.'
