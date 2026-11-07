# Local database backup retention

Approved by the operator on 2026-11-07. This only covers regular `maas_data-*.dump`
files and their `.sha256` companions in `/srv/maasweekly/shared/data-store/backups`.

- Keep everything younger than 24 hours, and always keep the latest two.
- Keep the latest verified backup per Shanghai calendar day for seven days,
  including today; keep the latest per completed Monday-Sunday week for four weeks.
- Keep the three explicitly named migration/earliest/pre-reliability-deployment
  pins in `ops/backup_retention.py` indefinitely. Removing a pin needs operator approval.
- Missing dates and weeks are reported as missing recovery coverage, never synthesized.
- 4 GiB is a soft budget. Exceeding it raises an alert without evicting protected points.

The daily publisher invokes retention only after a fresh database backup, successful
publication, SSR validation, runtime acceptance and monitor export. It retains the
existing exclusive release lock through verification and deletion. Other modes,
failed publication, failed backup, and unaccepted runtime never run retention.

Every run verifies each regular dump's SHA256, archive table of contents, timestamp,
regular-file status and unchanged metadata. Incomplete, unknown, damaged, linked or
changing files block cleanup and raise `database_backup_retention_unhealthy` through
the existing watchdog. Known migration/legacy bundles are excluded and never removed.
Before the first deletion, an operator must place actual isolated restore evidence in
`shared/backup-retention/restore-proof.json`; all three pinned hashes must match.
This evidence records the bootstrap restore drill, not a daily restore exercise.

The root-owned retention directory contains a durable audit written before unlinking,
per-pair progress, and `current.json`. Cleanup failure has a separate failure receipt
and does not relabel a successful publication as failed. A receipt older than 26 hours
or retained dump size above budget is visible in the independent operational alerts.
The publisher never shortens retention to pass a disk-capacity gate.

Install the helper from the deployed, manifest-verified runtime using
`ops/install-reliability.py`. Preserve the root-owned restore proof across deployments.
The initial 15-file cleanup uses the separately approved frozen inventory; newly
appearing files cannot expand that initial deletion set. Subsequent daily cleanups use
the approved rolling rules. No independent timer races the publisher.

These are same-host SQL backups. They do not contain CAS objects, account SQLite or
server configuration. The bootstrap drill restores temporary databases on this host
and validates database records against retained CAS objects. It does not establish
off-host disaster recovery; the existing cloud-backup jobs remain paused.
