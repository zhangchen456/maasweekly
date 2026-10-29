#!/usr/bin/env bash
# Optional readonly peer role and shared read cache, no application/pointer switch.
set -euo pipefail
if test "${1:---plan}" = --plan; then
  echo 'Grant maasagent readonly access to maas_data; create /srv/maasweekly/shared/public-data/v1 as maasdata:maasagent 2750.'
  exit 0
fi
test "${1:-}" = --apply && test "$(id -u)" -eq 0 || { echo 'usage: provision-site-reader.sh --plan|--apply (root)' >&2; exit 2; }
id maasagent >/dev/null
runuser -u postgres -- psql -X -v ON_ERROR_STOP=1 -d maas_data <<'SQL'
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='maasagent') THEN
  CREATE ROLE maasagent LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION CONNECTION LIMIT 8;
 END IF;
 IF EXISTS(SELECT FROM pg_roles WHERE rolname='maasagent' AND (rolsuper OR rolcreatedb OR rolcreaterole OR rolreplication OR NOT rolcanlogin)) THEN
  RAISE EXCEPTION 'unexpected existing reader privileges';
 END IF;
END $$;
GRANT CONNECT ON DATABASE maas_data TO maasagent;
GRANT USAGE ON SCHEMA maas_data TO maasagent;
GRANT SELECT ON maas_data.input_versions,maas_data.input_deltas,maas_data.documents,maas_data.data_candidates,maas_data.page_projections TO maasagent;
ALTER ROLE maasagent IN DATABASE maas_data SET default_transaction_read_only=on;
ALTER ROLE maasagent IN DATABASE maas_data SET statement_timeout='5s';
ALTER ROLE maasagent IN DATABASE maas_data SET work_mem='4MB';
SQL
for target in /srv/maasweekly/shared/public-data /srv/maasweekly/shared/public-data/v1; do
 test ! -L "$target" || { echo 'symlink cache refused' >&2; exit 2; }
 install -d -o maasdata -g maasagent -m 2750 "$target"
done
runuser -u maasagent -- psql -X -At -v ON_ERROR_STOP=1 -d maas_data -c 'SELECT current_user,current_database()'
echo 'Readonly reader ready. Active application and data pointers unchanged.'
