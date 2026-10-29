#!/usr/bin/env bash
# A fixed code install survives an SSH disconnect; runtime-control owns the lock.
set -euo pipefail
[[ $# -eq 1 && "$1" =~ ^rl_[0-9a-f]{10}_000000000000$ ]] || exit 2
umask 077
log=$(mktemp /srv/maasweekly/shared/data-store/reports/code-unit.XXXXXXXX.log)
rc=0
systemd-run --wait --collect --pipe --unit=maas-code-update \
  -p RuntimeMaxSec=3600 -p TimeoutStopSec=45 \
  /usr/bin/python3 /usr/local/lib/maasweekly/runtime-control.py install "$1" >"$log" 2>&1 || rc=$?
tail -20 "$log"
exit "$rc"
