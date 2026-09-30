#!/usr/bin/env bash
# Ubuntu/Debian cluster contract; source only, never starts or changes a database.
umami_pg_discover() {
  command -v pg_lsclusters >/dev/null || { echo '需要 postgresql-common / pg_lsclusters' >&2; return 1; }
  local rows row major cluster port status owner data rest count=0
  rows=$(pg_lsclusters --no-header) || return 1
  while read -r major cluster port status owner data rest; do
    [ "$port" = 5432 ] || continue
    count=$((count + 1))
    PG_MAJOR=$major
    PG_CLUSTER=$cluster
    PG_DATA=$data
    PG_SERVER="/usr/lib/postgresql/$major/bin/postgres"
  done <<< "$rows"
  [ "$count" = 1 ] || { echo '需要唯一、端口为 5432 的 PostgreSQL cluster' >&2; return 1; }
  [[ "$PG_MAJOR" =~ ^[0-9]+$ ]] || return 1
  [ -x "$PG_SERVER" ] || { echo "缺少 server binary: $PG_SERVER" >&2; return 1; }
  "$PG_SERVER" --version || return 1
  [ -x /usr/bin/psql ] || { echo '缺少 /usr/bin/psql' >&2; return 1; }
}

umami_pg_validate_connection() {
  local result version port data
  result=$(sudo -u postgres "$PG_BIN" -X -v ON_ERROR_STOP=1 \
    -h /var/run/postgresql -p 5432 -d postgres -At -F '|' \
    -c "SELECT current_setting('server_version_num'), current_setting('port'), current_setting('data_directory')") || return 1
  IFS='|' read -r version port data <<< "$result"
  [[ "$version" =~ ^[0-9]+$ ]] && [ "$version" -ge 120014 ] || {
    echo '需要 PostgreSQL v12.14+' >&2; return 1;
  }
  [ "$((version / 10000))" = "$PG_MAJOR" ] && [ "$port" = 5432 ] && [ "$data" = "$PG_DATA" ] || {
    echo 'PostgreSQL 实际连接与已发现的 cluster 不一致' >&2; return 1;
  }
}
