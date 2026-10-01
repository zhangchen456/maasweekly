#!/usr/bin/env bash
# Reviewed AR-02 shared configuration candidate. Never activates/reloads a slot.
set -euo pipefail
MODE="${1:---dry-run}"
OPS_DIR="$(cd "$(dirname "$0")" && pwd)"
SOURCE="$OPS_DIR/server/maasweekly-activate"
DEST=/usr/local/sbin/maasweekly-activate
ENV_FILE=/srv/maasweekly/shared/agent.env
[ "$MODE" = --dry-run ] || [ "$MODE" = --apply ] || { echo 'Use --dry-run or --apply <activator-sha> <env-sha>'; exit 2; }
bash -n "$SOURCE"
if [ "$MODE" = --dry-run ]; then
  echo 'AR-02: install reviewed activator; disable immutable-slot polling; enable controlled loopback proxy trust.'
  echo 'Apply requires SHA-256 of both installed activator and shared agent.env; secret values are never printed.'
  echo 'Backups preserve ownership and modes. No nginx reload, service restart or release activation.'
  echo 'Use standard activation only with the matching AR-02 API release. Restore both backups for rollback.'
  exit 0
fi
[ "$(id -u)" = 0 ] || { echo 'Requires approved root execution'; exit 1; }
EXPECTED_ACTIVATOR="${2:-}"
EXPECTED_ENV="${3:-}"
[[ "$EXPECTED_ACTIVATOR" =~ ^[0-9a-f]{64}$ && "$EXPECTED_ENV" =~ ^[0-9a-f]{64}$ ]] || { echo 'Two reviewed SHA-256 inputs required'; exit 2; }
exec 9>/srv/maasweekly/locks/release.lock
flock -w 60 9
[ "$(sha256sum "$DEST" | cut -d' ' -f1)" = "$EXPECTED_ACTIVATOR" ] || { echo 'Activator changed; review required'; exit 1; }
[ "$(sha256sum "$ENV_FILE" | cut -d' ' -f1)" = "$EXPECTED_ENV" ] || { echo 'Environment changed; review required'; exit 1; }
BACKUP="/srv/maasweekly/shared/ar02-backup-$(date -u +%Y%m%dT%H%M%SZ)-$$"
mkdir -m 0700 "$BACKUP"
cp -p "$DEST" "$BACKUP/maasweekly-activate"
cp -p "$ENV_FILE" "$BACKUP/agent.env"
restore() {
  cp -p "$BACKUP/maasweekly-activate" "$DEST"
  cp -p "$BACKUP/agent.env" "$ENV_FILE"
  rm -f "$DEST.ar02-next" "$ENV_FILE.ar02-next"
}
trap restore ERR
cp -p "$ENV_FILE" "$ENV_FILE.ar02-next"
python3 - "$ENV_FILE.ar02-next" <<'PY'
import pathlib, sys
p = pathlib.Path(sys.argv[1])
settings = {'RELOAD_INTERVAL_MS': '0', 'MAAS_TRUST_LOOPBACK_PROXY': '1'}
lines = p.read_text().splitlines()
lines = [line for line in lines if line.split('=', 1)[0].strip() not in settings]
lines.extend(f'{key}={value}' for key, value in settings.items())
p.write_text('\n'.join(lines) + '\n')
PY
install -m 0750 -o root -g root "$SOURCE" "$DEST.ar02-next"
mv "$ENV_FILE.ar02-next" "$ENV_FILE"
mv "$DEST.ar02-next" "$DEST"
trap - ERR
echo "AR-02 configuration installed; backups: $BACKUP; activation pending"
