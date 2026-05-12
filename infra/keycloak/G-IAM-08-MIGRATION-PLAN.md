# G-IAM-08 — Keycloak DB password hardening (migration plan)

Owner sprint: S12.5 (per IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11).
Anchors: G-IAM-08, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12,
FCA SYSC 4.1, GDPR Art. 32.
Status: PREP (this PR delivers the package only; no production deploy here).

---

## 1. Problem statement

Verified evidence (2026-05-12 07:37:50Z, Central diagnostic on evo1):
the Keycloak systemd unit's `ExecStart` contains the live database password
as a command-line argument:

```
... --db-password=teral> ...
```

This makes the password visible to any user who can run `ps -ef`, including
unprivileged accounts on the same host. The disclosure path is:
`/proc/<pid>/cmdline` → process listing → log scrapers, oncall tooling,
backup snapshots.

Affected stack at the time of evidence:
- KC version: 26.2.5
- JDK: 21
- Profile: `prod`
- DB: PostgreSQL at `jdbc:postgresql://127.0.0.1:15433/keycloak`

Regulatory mapping:
- **FCA SYSC 4.1** — adequate management systems and controls.
- **GDPR Art. 32** — appropriate technical measures (credential confidentiality
  is a baseline technical measure).

Operational impact today:
- Blocks Sprint S12.4 realm provisioning (no realm authoring should land
  while an authoring credential is exposed in the process table).
- Increases blast radius of any compromise that gains shell access on evo1.

## 2. Candidate solutions

### (a) `--db-password-file=/etc/keycloak/db.password` (Keycloak 26.x native)

Keycloak 26.x supports `--db-password-file=<path>` as a first-class alternative
to `--db-password=<literal>`. Keycloak reads the file at startup; the file
contents never enter the process command line.

**Pros**
- Native KC flag; no shell-side wrapping required.
- File permissions are the only protection knob — easy to audit
  (`ls -l /etc/keycloak/db.password`).
- Matches the standard pattern used by other Quarkus services.

**Cons**
- File on disk → must be permissioned correctly (root:keycloak 0640).
- Operator must place + maintain the file out-of-band of systemd.

### (b) systemd `EnvironmentFile=` with `KC_DB_PASSWORD`

Switch the unit to load `KC_DB_PASSWORD` from a systemd `EnvironmentFile=`,
and drop the `--db-password=` argument; Keycloak picks the value up from the
environment variable.

**Pros**
- No on-disk file requires Keycloak-aware code; only systemd touches it.
- Existing operator familiarity with `EnvironmentFile=` pattern.

**Cons**
- The password ends up in `/proc/<pid>/environ`, readable by the same uid
  that runs Keycloak (and by root). On a multi-tenant host this can be a
  larger surface than a single file with 0640 perms.
- Environment variables are easier to leak via crash dumps, error
  reporters, debug pages.

## 3. Recommended solution: (a) `--db-password-file`

Adopt `--db-password-file=/etc/keycloak/db.password` with the file owned
`root:keycloak` and mode `0640`. This matches the principle of least
exposure: the password is readable by exactly the keycloak service user
(for read) and root (for management), and is never present on the process
command line or in the process environment.

The templates and runbook in this prep package implement option (a).

## 4. Migration steps (operator-runnable on evo1; NOT in this PR)

The steps below are written for Central or the operator to execute later on
evo1, gated by HITL approval (see §6). They are NOT executed by this commit.

1. **Pre-flight diagnostic**
   - `systemctl status keycloak` — confirm currently running, capture
     baseline ExecStart line.
   - `ps -ef | grep '[k]eycloak.*--db-password='` — confirm the exposure
     (this is the condition that triggered G-IAM-08).
   - `systemctl cat keycloak` — capture full effective unit for rollback
     reference.
   - Capture KC version + JDK + profile via `journalctl -u keycloak -n 100
     --no-pager | head -20`.
   - Test DB connectivity via the existing KC health endpoint or
     `psql -h 127.0.0.1 -p 15433 -U <user> -d keycloak -c '\conninfo'`.

2. **Create the password file (operator manual)**
   - Read the current value from the active `--db-password=` argument or
     from the operator's source-of-truth vault. Do NOT echo to shell history.
   - Write to a temp file (e.g. `/root/.kc-db.password.tmp`) with `umask 077`.
   - Move to `/etc/keycloak/db.password` (create directory if missing).

3. **Set permissions**
   - `chown root:keycloak /etc/keycloak/db.password`
   - `chmod 0640 /etc/keycloak/db.password`
   - `ls -l /etc/keycloak/db.password` → must show
     `-rw-r----- 1 root keycloak ...`.

4. **Install the systemd drop-in**
   - `install -d /etc/systemd/system/keycloak.service.d`
   - Render the template `infra/keycloak/keycloak.service.d/g-iam-08-fix.conf.template`
     by substituting `{{KC_HOME}}` with the live path (e.g.
     `/home/banxe/keycloak-26.2.5`).
   - Place at `/etc/systemd/system/keycloak.service.d/g-iam-08-fix.conf`.

5. **Reload + restart**
   - `systemctl daemon-reload`
   - `systemctl restart keycloak`

6. **Post-restart verification**
   - `systemctl status keycloak` — must be `active (running)`.
   - `journalctl -u keycloak -n 50 --no-pager` — no DB-auth errors.
   - `ss -ltnp | grep 8080` (or the configured KC port) — listening.
   - KC realm-login smoke (if a non-prod realm is available).
   - DB connectivity confirmed via KC health endpoint or `psql`.

7. **Confirm exposure closed**
   - `ps -ef | grep '[k]eycloak.*--db-password='` → must return NO matches.
   - `cat /proc/$(pgrep -f keycloak)/cmdline | tr '\0' ' '` → must not
     contain `--db-password=`.

## 5. Rollback procedure

If post-migration verification fails, rollback in this exact order:

1. `rm -f /etc/systemd/system/keycloak.service.d/g-iam-08-fix.conf`
   (drop the override; the original unit's ExecStart returns to effect).
2. `systemctl daemon-reload`
3. `systemctl restart keycloak`
4. Validate that `systemctl cat keycloak` matches the pre-migration baseline
   captured in §4 step 1.
5. Re-run `systemctl status keycloak` and the post-restart verification
   commands from §4 step 6.
6. Leave `/etc/keycloak/db.password` in place (no harm; not yet referenced)
   unless explicitly directed to remove. Removing it is a follow-up clean-up,
   not a rollback prerequisite.

## 6. HITL gate

This migration is destructive on production Keycloak (restart, brief auth
outage during restart). It requires **explicit Central + operator approval
before deploy**, recorded against IL-OPS-S12-5-G-IAM-08-PREP-2026-05-12 in
the operator-side ledger. The HITL artifact is the operator sign-off block
in `OPERATOR-RUNBOOK-G-IAM-08.md`.

## 7. Post-migration follow-up

- Schedule the DB password rotation per Sprint S12.5 90-day cadence
  (per IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 — "client
  secrets rotation 90d"). Future rotations only update
  `/etc/keycloak/db.password` and restart KC; no systemd-level changes.
- Add the file `/etc/keycloak/db.password` to the next backup-coverage
  review (the password file is now a secret-of-record).
- Record this hardening as evidence on the FCA SYSC 4.1 control map at
  the next compliance review.

## 8. Cross-references

- IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12 (gap origin).
- IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 (S12.5 owner).
- IL-CANON-TERMINAL-B-AUTONOMOUS-FIXATION-2026-05-12 (this PR's authority).
- IL-CANON-EXPLICIT-TARGET-INSTRUCTION-2026-05-12 (target = repo prep only).
- Sibling files in this directory:
  - `keycloak.service.d/g-iam-08-fix.conf.template` — systemd drop-in.
  - `db.password.template` — password-file placeholder.
  - `install-db-password-file.sh` — installer script.
  - `validate-g-iam-08-mitigation.sh` — offline validator.
  - `OPERATOR-RUNBOOK-G-IAM-08.md` — operator runbook.
