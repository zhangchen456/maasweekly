#!/usr/bin/env bash
# Add an isolated data database/filesystem account to the existing PG cluster.
# No application switch, cron, public listener or deletion of existing data.
set -euo pipefail
case "${1:---plan}" in
  --plan)
    cat <<'PLAN'
Use the existing PostgreSQL cluster; do not install/restart PostgreSQL.
Create system account maasdata and peer-authenticated database role maasdata.
Create dedicated database maas_data; cap this role at four connections.
Create /srv/maasweekly/shared/data-store/{blobs,backups,reports} outside releases.
Keep every existing application/writer/release active and unchanged.
PLAN
    exit 0 ;;
  --apply) ;;
  *) echo 'usage: provision-data-store.sh [--plan|--apply]' >&2; exit 2 ;;
esac
test "$(id -u)" -eq 0 || { echo 'root required' >&2; exit 2; }
command -v psql >/dev/null
command -v runuser >/dev/null
available_kb=$(df -Pk /srv/maasweekly | awk 'NR==2 {print $4}')
test "$available_kb" -ge 8388608 || { echo 'at least 8 GiB available required' >&2; exit 2; }
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -At -c 'SELECT 1' >/dev/null
if ! id maasdata >/dev/null 2>&1; then
  useradd --system --home-dir /var/lib/maasdata --create-home --shell /usr/sbin/nologin maasdata
fi
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 <<'SQL'
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname='maasdata') THEN
    CREATE ROLE maasdata LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 4;
  END IF;
  IF EXISTS (SELECT FROM pg_roles WHERE rolname='maasdata' AND
      (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR NOT rolcanlogin)) THEN
    RAISE EXCEPTION 'existing maasdata role has unexpected privileges';
  END IF;
END $$;
SELECT 'CREATE DATABASE maas_data OWNER maasdata'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname='maas_data')\gexec
DO $$ BEGIN
  IF NOT EXISTS (SELECT FROM pg_database d JOIN pg_roles r ON r.oid=d.datdba
                 WHERE d.datname='maas_data' AND r.rolname='maasdata') THEN
    RAISE EXCEPTION 'existing maas_data database has unexpected owner';
  END IF;
END $$;
ALTER ROLE maasdata CONNECTION LIMIT 4;
ALTER ROLE maasdata IN DATABASE maas_data SET work_mem='4MB';
ALTER ROLE maasdata IN DATABASE maas_data SET maintenance_work_mem='64MB';
ALTER ROLE maasdata IN DATABASE maas_data SET statement_timeout='120s';
ALTER ROLE maasdata IN DATABASE maas_data SET lock_timeout='5s';
REVOKE ALL ON DATABASE maas_data FROM PUBLIC;
SQL
for name in data-store data-store/blobs data-store/backups data-store/reports; do
  target="/srv/maasweekly/shared/$name"
  test ! -L "$target" || { echo 'symlink target rejected' >&2; exit 2; }
  install -d -o maasdata -g maasdata -m 0700 "$target"
done
runuser -u maasdata -- test -w /srv/maasweekly/shared/data-store/blobs
runuser -u maasdata -- psql -X -v ON_ERROR_STOP=1 -d maas_data -At -c 'SELECT current_user,current_database()'
echo 'Provisioned isolated data store. Active writers and application remain unchanged.'
