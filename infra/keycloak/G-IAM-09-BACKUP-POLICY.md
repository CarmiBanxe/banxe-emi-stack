# G-IAM-09 — Keycloak backup policy (forward + rollback)

Owner sprint: S12.6 (per IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11).
Anchors: G-IAM-09, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12,
ADR-029 (Postgres backup strategy — canonical lives in banxe-architecture),
FCA SYSC 4.1.5 (operational resilience).
Status: PREP (this PR delivers the policy + scaffolding only; no deploy here).

---

## 1. Problem statement

Verified evidence (2026-05-12 07:37:50Z, Central diagnostic on evo1):

- No Keycloak backup artifacts located on evo1: no files under
  `/var/backups`, `/opt/backups`, or any `*keycloak*backup*` path.
- KC 26.2.5 in production with the Postgres backend at
  `jdbc:postgresql://127.0.0.1:15433/keycloak` (port 15433 suggests
  containerized PG; verify at deploy time).
- Backup state RPO is effectively unbounded — any DB-loss event today
  results in total loss of realm, clients, users, sessions, audit rows.

Regulatory mapping:
- **FCA SYSC 4.1.5** — operational resilience and recoverability.
- **ADR-029 (Postgres backup strategy)** — canonical contract; this policy
  is the Keycloak-specific specialisation. Where ADR-029 specifies a value,
  this document reuses it. Where ADR-029 is silent or KC-specific, this
  document records a TODO + proposed default + rationale.

Operational impact today:
- Blocks S12.4 realm provisioning (no realm authoring should land while the
  authoring substrate has zero RPO).
- Cannot exercise rollback for the G-IAM-08 hardening (PR #133) — if KC fails
  post-migration, there is no restorable baseline.

## 2. Scope

In scope:
- The Keycloak Postgres backend database (port 15433, db `keycloak`).
- Realm metadata, clients, users, federated-identity links, audit table
  (`event_entity` etc.), session-state tables.
- Encryption-at-rest of the resulting artifact.
- Off-host copy of the artifact.
- Monthly restore-drill cadence with operator sign-off.

Out of scope:
- The Keycloak install tree itself (`/home/banxe/keycloak-26.2.5/`) —
  immutable / re-installable from packaging.
- Application-side databases other than the KC backend.
- Long-term archival beyond 12 months (separate retention conversation).

## 3. ADR-029 alignment matrix

Each row maps an ADR-029 requirement to a KC-specific tuning. The
canonical ADR-029 lives in `banxe-architecture/decisions/`; values listed
as TODO are proposed defaults pending Central confirmation against the
authoritative ADR text.

| ADR-029 requirement              | KC-specific value (this policy)                              | Source / status |
|----------------------------------|--------------------------------------------------------------|-----------------|
| Backup frequency                  | Daily, 02:30 local time (off-peak; avoids n8n at 02:00)      | TODO — confirm ADR-029 baseline; proposed |
| Dump format                       | `pg_dump -Fc` (custom format — selective restore + compact)  | Aligned with `services/backup/pg_backup_adapter.py:PgDumpBackupAdapter` (which already uses `--format=custom`) |
| Encryption at rest                | GPG symmetric (AES256) with passphrase file root:keycloak 0640 | TODO — confirm ADR-029 (alternative: age) |
| Off-host target                   | TODO — proposed: `s3://banxe-pg-backups/keycloak/<host>/<date>.gpg` if ADR-029 §1 MinIO bucket is in scope; fallback rsync to evo2:/data/banxe/backups/keycloak/ | TODO |
| Retention                         | 7 daily + 4 weekly + 12 monthly (rolling)                    | TODO — confirm ADR-029; proposed default mirrors `services/backup/factory.py:BACKUP_RETENTION_COUNT=7` baseline |
| Restore-drill cadence             | Monthly, first business day of month, sandbox-only           | TODO — confirm ADR-029 §4 schedule (current bank-side adapter `services/backup/restore_drill_port.py` exists but is not gated by ADR cadence text) |
| Drill validation                  | `pg_restore --list` + sandbox KC startup + realm/user count parity | This policy |
| Operator sign-off                 | Required for first backup + every restore drill              | This policy + HITL gate (§6) |

Bank-side code anchors usable as concrete reference points:
- `services/backup/backup_port.py` — `BackupPort` abstract contract.
- `services/backup/pg_backup_adapter.py` — `PgDumpBackupAdapter` with
  `--format=custom`, `BACKUP_PG_*` env contract, retention rotation.
- `services/backup/restore_drill_port.py` — `RestoreDrillPort` abstract.
- `services/backup/local_restore_drill_adapter.py` — `LocalRestoreDrillAdapter`
  (drill orchestration in code; sandbox-only).
- `services/backup/offsite_upload_port.py` — `OffsiteUploadPort` abstract;
  `InMemoryOffsiteAdapter` for dev; MinIO adapter pending real integration.

Where the policy mandates a value that ADR-029 does not yet specify for KC,
the operator deploy step (§4) carries the value selection into the rendered
cron + wrapper at install time.

## 4. Backup contract

| Property               | Value                                                        |
|------------------------|--------------------------------------------------------------|
| Source DB              | jdbc:postgresql://127.0.0.1:15433/keycloak                   |
| Source DB user         | `keycloak` (read-only role preferred; TODO — confirm) |
| Auth method            | Password file `/etc/keycloak/db.password` (root:keycloak 0640) — reuses the G-IAM-08 file (PR #133) |
| Dump command           | `pg_dump -Fc -h <host> -p <port> -U <user> -d keycloak`      |
| Artifact filename      | `keycloak-<YYYYMMDD-HHMMSS>.dump.gpg`                        |
| Encryption             | `gpg --symmetric --cipher-algo AES256 --batch --passphrase-file <PASSPHRASE_FILE>` |
| Local staging dir      | `/var/backups/keycloak/` (root:keycloak 0750)                |
| Integrity              | `sha256sum` of encrypted artifact written next to it (`.sha256` sidecar) |
| Off-host copy          | Operator-chosen MinIO bucket OR rsync target (TODO)         |
| Local retention        | 7 daily files; oldest pruned by wrapper script               |
| Off-host retention     | 7 daily + 4 weekly + 12 monthly (operator-managed)           |
| Cron schedule          | `30 2 * * *` (02:30 daily)                                   |
| Logging                | `/var/log/keycloak/backup.log` (root:keycloak 0640)          |

## 5. Operator deploy procedure (NOT executed in this PR)

The steps below are operator-runnable on evo1, gated by §6 HITL.

1. **Pre-flight on evo1**
   - Confirm PG reachable: `psql -h 127.0.0.1 -p 15433 -U keycloak -d keycloak -c '\conninfo'` (use password file).
   - Confirm disk space: `df -h /var/backups` — minimum 10 GB free.
   - Confirm `gpg` installed: `gpg --version`.
   - Confirm encryption passphrase file exists at the operator-chosen path,
     mode 0600, owner root. (NOT committed to git.)
   - Confirm off-host target reachable.

2. **Install the wrapper**
   - Render `infra/keycloak/scripts/kc-backup.sh.template` by substituting
     `{{KC_DB_HOST}}`, `{{KC_DB_PORT}}`, `{{KC_DB_NAME}}`, `{{KC_DB_USER}}`,
     `{{KC_DB_PASSWORD_FILE}}`, `{{BACKUP_DIR}}`, `{{ENCRYPTION_RECIPIENT}}`,
     `{{OFFHOST_TARGET}}`.
   - Place at `/usr/local/bin/kc-backup.sh` mode 0750 root:keycloak.

3. **Install cron entry**
   - Render `infra/keycloak/cron.d/kc-backup.cron.template` and install at
     `/etc/cron.d/kc-backup` mode 0644 root:root.

4. **First manual backup**
   - Run `sudo -u keycloak /usr/local/bin/kc-backup.sh` once interactively.
   - Verify artifact + sha256 sidecar present in `/var/backups/keycloak/`.
   - Verify off-host artifact present at the chosen target.

5. **Schedule first restore drill within 7 days**
   - See §7 for the drill procedure.
   - First drill must be operator-witnessed; result logged against
     `IL-OPS-S12-6-G-IAM-09-PREP-2026-05-12` (see `INSTRUCTION-LEDGER.md`).

## 6. HITL gate

- Initial deploy requires Central + operator approval per
  IL-CANON-TERMINAL-B-AUTONOMOUS-FIXATION-2026-05-12.
- Every restore drill requires operator witness + sign-off (see runbook).
- The first successful backup AND the first successful drill must be logged
  against `IL-OPS-S12-6-G-IAM-09-PREP-2026-05-12`.

## 7. Restore drill procedure (NOT executed in this PR)

See `OPERATOR-RUNBOOK-G-IAM-09-RESTORE-DRILL.md` for the operator-facing
runbook. Summary:

1. Provision a sandbox Postgres instance (container or temp DB, NOT prod).
2. Copy latest encrypted dump from off-host to sandbox host.
3. Verify `sha256sum -c` against sidecar.
4. `gpg --decrypt` → temp `.dump` file.
5. `pg_restore --list <dump>` succeeds (catalog readable).
6. `pg_restore -h <sandbox> -p <sandbox-port> -U <sandbox-user> -d keycloak_drill <dump>`.
7. Start a secondary KC instance pointing at the sandbox DB.
8. Verify `select count(*) from realm`, `select count(*) from user_entity`,
   `select count(*) from client` match the production baseline (recorded the day
   the backup was taken).
9. Tear down sandbox cleanly; never write back to production.

## 8. Rollback

Backup policy is additive — rollback removes the policy without affecting
prod KC operation:

1. `rm /etc/cron.d/kc-backup`
2. `rm /usr/local/bin/kc-backup.sh`
3. Optionally `rm -rf /var/backups/keycloak/` (keeps last artifact by default;
   document the choice).
4. No KC restart required.

Existing artifacts remain restorable via the runbook procedure regardless of
whether the cron is active.

## 9. Cross-references

- `OPERATOR-RUNBOOK-G-IAM-09-RESTORE-DRILL.md` — operator-facing drill runbook.
- `scripts/kc-backup.sh.template` — wrapper template.
- `cron.d/kc-backup.cron.template` — cron template.
- `scripts/validate-g-iam-09-backup-prep.sh` — offline lint validator.
- `examples/backup.env.example` — env placeholder.
- `examples/offhost-target.example` — off-host target placeholder.
- `G-IAM-08-MIGRATION-PLAN.md` — sibling sprint S12.5 (PR #133), shares the
  `/etc/keycloak/db.password` credential file.
- ADR-029 canonical (banxe-architecture) — Postgres backup strategy.
- IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 — S12.6 owner.
- IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12 — gap origin.
