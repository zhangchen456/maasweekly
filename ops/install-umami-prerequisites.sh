#!/usr/bin/env bash
# T08-1A prerequisites only. --execute requires the approved authorization package.
set -euo pipefail
MODE=${1:---dry-run}
case "$MODE" in --dry-run|--execute) ;; *) echo 'usage: install-umami-prerequisites.sh [--dry-run|--execute]' >&2; exit 2 ;; esac
NODE=/opt/node-v22.22.3/bin/node
COREPACK=/opt/node-v22.22.3/bin/corepack
run() {
  printf '·'; printf ' %q' "$@"; printf '\n'
  if [ "$MODE" = --execute ]; then "$@"; fi
}
if [ "$MODE" = --execute ]; then
  [ "$(id -u)" = 0 ] || { echo 'requires root' >&2; exit 1; }
  [ "$(readlink -f /usr/bin/node)" = "$NODE" ] || { echo 'Node distribution changed; stop' >&2; exit 1; }
  [ "$("$NODE" --version)" = v22.22.3 ] || exit 1
  [ "$("$COREPACK" --version)" = 0.34.6 ] || exit 1
  [ ! -e /usr/local/bin/pnpm ] && [ ! -L /usr/local/bin/pnpm ] || {
    echo '/usr/local/bin/pnpm already exists; stop rather than overwrite' >&2; exit 1;
  }
  # apt simulation must show no upgrades/removals before creating pnpm shims.
  simulation=$(LC_ALL=C apt-get -s install \
    postgresql=18+290ubuntu1 postgresql-18=18.6-0ubuntu0.26.04.1 \
    postgresql-client=18+290ubuntu1 postgresql-client-18=18.6-0ubuntu0.26.04.1)
  printf '%s\n' "$simulation"
  grep -Eq '^0 upgraded, [0-9]+ newly installed, 0 to remove' <<< "$simulation" || {
    echo 'APT dependency plan changed; stop' >&2; exit 1;
  }
fi
# Root builds Umami; its normal Corepack cache is sufficient. Runtime uses Node,
# never pnpm. No service-user cache or global npm installation is required.
run "$COREPACK" install --global pnpm@12.3.4
run "$COREPACK" enable --install-directory /usr/local/bin pnpm
run /usr/local/bin/pnpm --version
if [ "$MODE" = --execute ]; then
  [ "$(/usr/local/bin/pnpm --version)" = 12.3.4 ] || exit 1
fi
run apt-get install -y \
  postgresql=18+290ubuntu1 postgresql-18=18.6-0ubuntu0.26.04.1 \
  postgresql-client=18+290ubuntu1 postgresql-client-18=18.6-0ubuntu0.26.04.1
if [ "$MODE" = --execute ]; then
  OPS_DIR=$(cd "$(dirname "$0")" && pwd)
  source "$OPS_DIR/lib-umami-postgres.sh"
  PG_BIN=/usr/bin/psql
  umami_pg_discover
  umami_pg_validate_connection
  [ "$("$NODE" --version)" = v22.22.3 ] || exit 1
fi
echo 'Prerequisites complete. Umami, nginx, DNS and TLS are separate steps.'
