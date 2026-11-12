#!/usr/bin/env bash
# Secrets pass directly through stdin to an independent server unit.
set -euo pipefail
umask 077
log=$(mktemp /srv/maasweekly/shared/data-store/reports/data-unit.XXXXXXXX.log)
rc=0
data_disk_device=$(/usr/bin/python3 -B /usr/local/lib/maasweekly/data_job_resources.py --device)
systemd-run --wait --collect --pipe --unit=maas-data-update \
  -p RuntimeMaxSec=5700 -p TimeoutStopSec=45 \
  -p MemoryLow=64M -p MemoryHigh=768M -p MemoryMax=1G -p MemorySwapMax=0 -p IOWeight=10 \
  -p "IOReadBandwidthMax=$data_disk_device 16777216" \
  -p "IOWriteBandwidthMax=$data_disk_device 16777216" \
  /usr/bin/python3 -B /usr/local/lib/maasweekly/data-update.py >"$log" 2>&1 || rc=$?
tail -20 "$log"
exit "$rc"
