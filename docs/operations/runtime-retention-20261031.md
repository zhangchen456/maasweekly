# Runtime retention

The new code-only runtime layout accumulated packages under `runtime/` and completed uploads under `incoming/`. The existing cleanup unit called the legacy embedded-release activator, so it did not enforce retention on these new paths.

`ops/runtime-cleanup.py` operates only on code-only runtime packages with validated manifests and matching file inventories/checksums. It retains the union of the current runtime, rollback runtime and newest three installed manifests, plus candidates, slot references, versions still used as process working directories and installed counterparts of uploads younger than one hour. A pending switch or invalid current/rollback state prevents deletion. Changed or unmanaged historical content is preserved and reported.

Completed runtime upload copies older than one hour are verified against their installed package before removal. Uploads are removed before retired runtimes, so a young upload temporarily protects its counterpart until it can be checked. Unknown uploads, legacy releases and shared business data are outside the deletion scope.

The helper defaults to a read-only plan (`--plan`); `--apply` performs cleanup. Both use the existing nonblocking release lock, deferring to deployments and data publication. All retained packages are verified before mutations, and file-tree fingerprints are rechecked immediately before deletion. Daily JSONL audit records are appended to root-owned `shared/runtime-cleanup/`.

Install the committed helper as `/usr/local/lib/maasweekly/runtime-cleanup.py` (root:root, 0750), create `shared/runtime-cleanup/` (root:root, 0700), and install the service and timer files in `/etc/systemd/system/`. Preserve the previous installed files for rollback. Validate with `systemd-analyze verify`, reload systemd, restart the existing `maas-release-cleanup.timer`, review a plan and start `maas-release-cleanup.service`. The timer runs every hour at minute 20, Asia/Shanghai. Its write access is confined to runtime/upload directories, the audit directory and release lock.

Verification includes disposable real-file package trees, current/rollback/latest union, staging and young-upload protection, repeat execution, corrupted rollback refusal, preservation of modified/unmanaged files, symlink isolation, changes during validation and busy-lock deferral. These tests run in PR integration and code-release checks. After applying, verify remaining versions, free space, timer schedule, public dataset identity and site responses.
