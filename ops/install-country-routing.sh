#!/usr/bin/env bash
# Minimal root installation, only after the concrete deployment package is approved.
# Run from an uploaded ops/ checkout. No nginx reload or release activation here.
set -euo pipefail
MODE="${1:---dry-run}"
OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$OPS_DIR/server/maasweekly-activate"
DEST=/usr/local/sbin/maasweekly-activate
BASE_SHA=5792816251c2f76552ea25c5d1a1ba54dca307f7eabd969a904da4fb13e0f27f
[ "$MODE" = --dry-run ] || [ "$MODE" = --apply ] || { echo 'Use --dry-run or --apply'; exit 2; }
bash -n "$SOURCE"
[ "$MODE" = --apply ] || {
  echo "Verify installed activator SHA-256: $BASE_SHA (or identical candidate)"
  echo "Back up $DEST, install reviewed candidate (root:root 0750)."
  echo 'Existing nginx includes and current release remain untouched until standard activation.'
  echo 'Rollback: restore the recorded activator backup, then roll back the release.'
  exit 0
}
[ "$(id -u)" = 0 ] || { echo 'Requires approved root execution'; exit 1; }
exec 9>/srv/maasweekly/locks/release.lock
flock -w 60 9
CURRENT_SHA="$(sha256sum "$DEST" | cut -d' ' -f1)"
NEXT_SHA="$(sha256sum "$SOURCE" | cut -d' ' -f1)"
[ "$CURRENT_SHA" != "$NEXT_SHA" ] || { echo 'Already installed'; exit 0; }
[ "$CURRENT_SHA" = "$BASE_SHA" ] || { echo 'Installed activator changed; review required'; exit 1; }
BACKUP="$DEST.pre-country-$(date -u +%Y%m%dT%H%M%SZ)"
cp -p "$DEST" "$BACKUP"
install -m 0750 -o root -g root "$SOURCE" "$DEST.country-next"
mv "$DEST.country-next" "$DEST"
echo "Installed activator $NEXT_SHA; backup: $BACKUP"
