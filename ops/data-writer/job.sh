#!/usr/bin/env bash
# Secrets pass directly through stdin to an independent server unit.
set -euo pipefail
umask 077
log=$(mktemp /srv/maasweekly/shared/data-store/reports/data-unit.XXXXXXXX.log)
rc=0
systemd-run --wait --collect --pipe --unit=maas-data-update \
  -p RuntimeMaxSec=5700 -p TimeoutStopSec=45 \
  /usr/bin/python3 /usr/local/lib/maasweekly/data-update.py >"$log" 2>&1 || rc=$?
tail -20 "$log"
exit "$rc"
