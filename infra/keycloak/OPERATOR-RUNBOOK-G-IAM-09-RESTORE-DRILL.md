# Operator runbook — G-IAM-09 Keycloak restore drill

Owner sprint: S12.6.
Anchors: G-IAM-09, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12,
IL-OPS-S12-6-G-IAM-09-PREP-2026-05-12, ADR-029 (Postgres backup strategy
— canonical in banxe-architecture).

---

## Purpose

Verify that a Keycloak Postgres backup artifact produced by the wrapper
defined in `G-IAM-09-BACKUP-POLICY.md` can be:

1. Located on the off-host target.
2. Verified against its `sha256` sidecar.
3. Decrypted with the operator-held passphrase.
4. Inspected via `pg_restore --list`.
5. Restored into a sandbox PG instance.
6. Read by a sandbox Keycloak instance with realm/user/client counts that
   match the production baseline recorded the day the backup was taken.

## Non-goal

**This runbook does NOT perform a production restore.** Every step below
operates on a sandbox PG + sandbox KC. Touching the production KC backend
or production realm is explicitly out of scope of this runbook.

Likewise, this prep PR does **not** execute any restore drill. The runbook
is operator-executable on evo1/sandbox after deploy of the G-IAM-09 backup
policy and after Central + operator HITL approval.

## Prerequisites

- G-IAM-09 backup wrapper installed and running daily (per `G-IAM-09-BACKUP-POLICY.md` §5).
- At least one full backup artifact present on the off-host target.
- Operator holds the encryption passphrase (out-of-band).
- A sandbox PG instance available (container, ephemeral VM, or non-prod DB
  with a `keycloak_drill` database created for this purpose).
- A sandbox Keycloak install available (matching KC version 26.2.5).
- Production baseline counts recorded the day of the source backup
  (realm count, user count, client count) — for parity assertion.

## Pre-checks

1. `ls -l <offhost-target>/keycloak-<YYYYMMDD-HHMMSS>.dump.gpg{,.sha256}` — both files present.
2. Free disk on sandbox host: at least 2× the encrypted artifact size.
3. `gpg --version`, `pg_restore --version`, `sha256sum --version` available
   on sandbox host.

## Drill steps

1. **Stage artifact.**
   - Copy artifact + sidecar from off-host target into a sandbox workdir
     (e.g. `/tmp/kc-drill-<YYYYMMDD>/`).
2. **Verify integrity.**
   - `cd <workdir> && sha256sum -c keycloak-<stamp>.dump.gpg.sha256`
   - Must report `OK`. Any mismatch ABORTS the drill.
3. **Decrypt.**
   - `gpg --batch --passphrase-file <passphrase-file>
        --decrypt -o keycloak-<stamp>.dump
        keycloak-<stamp>.dump.gpg`
   - Result: a `.dump` file (pg_dump custom format).
4. **Inspect catalog.**
   - `pg_restore --list keycloak-<stamp>.dump | head -50`
   - Must list expected schemas (`public`, `keycloak`-style tables).
5. **Provision sandbox DB.**
   - Create database `keycloak_drill` in the sandbox PG.
   - Create role with `CREATEDB`+`CREATEROLE` for the drill — NOT shared
     with any prod credential.
6. **Restore.**
   - `pg_restore --no-owner --no-privileges
        --host=<sandbox-host> --port=<sandbox-port> --username=<sandbox-user>
        --dbname=keycloak_drill keycloak-<stamp>.dump`
   - Capture stdout/stderr to `/tmp/kc-drill-<YYYYMMDD>/restore.log`.
   - Acceptable warnings: missing role grants (sandbox doesn't replicate
     prod roles). ABORT on real errors (FATAL, ERROR).
7. **Start sandbox Keycloak.**
   - Configure the sandbox KC's `--db-url` to the sandbox PG and
     `--db-name=keycloak_drill`.
   - Start KC; wait for `Listening on:` log line.
8. **Validate counts.**
   - Connect to sandbox KC admin OR run SQL directly:
     - `select count(*) from realm;`
     - `select count(*) from user_entity;`
     - `select count(*) from client;`
   - Compare against production baseline captured the day of the source
     backup. Variance within ±1 (in-flight changes during the dump window)
     is acceptable; larger variance ABORTS and triggers investigation.
9. **Capture evidence.**
   - `journalctl -u keycloak-sandbox -n 200 --no-pager > evidence-kc.log`
   - `cat /tmp/kc-drill-<YYYYMMDD>/restore.log >> evidence-restore.log`
   - Archive the directory under operator drill-evidence retention.
10. **Tear down.**
    - Stop sandbox KC.
    - `dropdb keycloak_drill` on sandbox PG.
    - `rm -rf /tmp/kc-drill-<YYYYMMDD>/` (decrypted dump must not linger).

## Validation checklist

- [ ] Artifact present on off-host target.
- [ ] `sha256sum -c` PASS.
- [ ] `gpg --decrypt` PASS.
- [ ] `pg_restore --list` PASS.
- [ ] Restore into sandbox PG PASS (no FATAL/ERROR).
- [ ] Sandbox KC starts cleanly against restored DB.
- [ ] realm count parity within tolerance.
- [ ] user_entity count parity within tolerance.
- [ ] client count parity within tolerance.
- [ ] Evidence archived.
- [ ] Sandbox torn down; decrypted dump removed.

## Rollback / cleanup

A drill is non-destructive on production. "Rollback" here is sandbox cleanup:

1. Stop sandbox KC (e.g. `systemctl stop keycloak-sandbox` or container down).
2. `dropdb keycloak_drill` on sandbox PG.
3. `shred -u` (or equivalent) the decrypted dump; `rm -rf` the workdir.
4. Retain evidence archive per operator policy (suggest 90 days).

## Operator sign-off block

```
Drill date     : __________________________
Source backup  : keycloak-_________________.dump.gpg
Off-host source: __________________________
Executor       : __________________________
Reviewer       : __________________________
Restore log    : __________________________ (path / artifact ID)
KC sandbox log : __________________________ (path / artifact ID)
Result         : [ ] PASS    [ ] FAIL    [ ] ABORTED
Notes / variance:


```

## References

- `G-IAM-09-BACKUP-POLICY.md` — full backup policy + ADR-029 alignment matrix.
- `scripts/kc-backup.sh.template` — wrapper template.
- `cron.d/kc-backup.cron.template` — cron template.
- `scripts/validate-g-iam-09-backup-prep.sh` — offline validator (run from CI / dev).
- `examples/backup.env.example` — env placeholder.
- `examples/offhost-target.example` — off-host target placeholder.
- IL-OPS-S12-6-G-IAM-09-PREP-2026-05-12 — this prep package's IL pairing.
