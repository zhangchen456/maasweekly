# Runtime components, evidence and bounded verification

The code package declares worker protocol 1, controller protocol 2 and the writer
requirements digest in `metadata/runtime-manifest.json`. Root helpers remain an
explicit audited installation (`ops/install-reliability.py`) from the active,
hash-verified package. A code upload cannot replace privileged helpers. The
existing writer-image requirements equality check continues to reject incompatible
packages before staging.

After bootstrapping controller 2, every switch to/from a worker-protocol package
stops both fixed worker units without blocking, cancelling queued automatic restarts,
and waits for their current fenced task to
finish (up to 210 seconds), and only then switches `current`. It never escalates to
KILL: both audited units set `SendSIGKILL=no`, which is checked before stopping any
worker. A crash loop therefore cannot prevent rollback by continuously restarting.
The unit also pins the receipt directory for older protocol-1 packages. New workers must report ready with their PID/code and have the expected
`/proc/PID/cwd`. Failure restores nginx, runtime state and the old workers; the
pending recovery marker is retained if recovery fails. Old rollback packages use
process cwd plus systemd state because they lack the new readiness protocol.
`runtime.json` records worker proofs and actual root-controller hashes. Queued
work stays in SQLite. New requests can still queue during the short worker gap.

Bootstrap: deploy the tested package, run the audited helper installer, then
stage/activate that exact code under `runtime-control.py`'s release lock. Exercise
rollback and reactivation and check both actual PIDs, the loaded publication,
private-route boundaries and pending-marker absence. No separate manual worker
restart should be needed after bootstrap. Cloud backup units are unaffected.

Daily digest model output is a strict selection schema: platform, type, evidence
ID. The backend generates extractive text from that evidence instead of trusting
model-authored prices or service-termination claims. Evidence IDs hash the source,
quote, observation date and structured facts. Removed lines are never eligible;
sunset requires current explicit termination language and a date. This is a
conservative extraction policy, not semantic proof of arbitrary prose. Prices
require full current/previous facts and retain currency, unit, region, tier and
context/time conditions; newly collected prices are not called newly launched.
A provider event without full pricing conditions is omitted from pricing highlights.
The UI links each verified item to its official source and observation date.
Old summaries remain visible as unverified history, with neutral classification.

Full CAS/SQL validation still visits every referenced object in the transaction,
including inherited objects. At most four local filesystem reads overlap within
the existing 128-object/2 MiB database batch (a single larger document is allowed
as before). Each read reopens the origin with NOFOLLOW and checks size and SHA256;
there is no successful-validation cache. SQL/ordered JSON/reference checks remain
serial and unchanged. Non-filesystem adapters retain serial semantics. Input
capture also reuses the bytes of a current record's immutable revision instead of
reading that revision twice. Performance claims must come from the same pinned
input, resource limits, counters and unchanged public business hashes.
