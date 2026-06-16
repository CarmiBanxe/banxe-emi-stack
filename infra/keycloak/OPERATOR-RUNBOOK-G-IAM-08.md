# Operator runbook — G-IAM-08 Keycloak DB password hardening

Owner sprint: S12.5.
Anchors: G-IAM-08, IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12,
IL-OPS-S12-5-G-IAM-08-PREP-2026-05-12.

---

## Purpose

Deploy the G-IAM-08 mitigation on production evo1: replace the
`--db-password=<literal>` argument on the Keycloak systemd unit with
`--db-password-file=/etc/keycloak/db.password`.

## Non-goal

**This runbook does NOT deploy from inside this repo PR.** The PR delivers
only the prep package (templates + plan + installer + validator). Deployment
is operator-driven on evo1 and gated by Central + operator approval per the
HITL gate in `G-IAM-08-MIGRATION-PLAN.md` §6.

## Pre-checks (run before any change)

1. `systemctl status keycloak` — capture baseline; confirm `active (running)`.
2. `systemctl cat keycloak > /root/keycloak.unit.pre-g-iam-08.txt` — full
   effective unit snapshot for rollback reference.
3. `ps -ef | grep '[k]eycloak.*--db-password='` — confirm the exposure that
   triggered G-IAM-08 is still present (do not log the result to anywhere
   shared).
4. `journalctl -u keycloak -n 100 --no-pager | head -20` — capture KC
   version + JDK + profile lines.
5. `ss -ltnp | grep 8080` (or configured port) — confirm listener.

## Deploy steps

The reference files in this PR live at `infra/keycloak/` in the
banxe-emi-stack repo. Operator workflow on evo1:

1. **Stage password file.**
   - Read the current DB password from the operator's source-of-truth vault
     (NOT from `ps -ef` after deploy starts).
   - `umask 077; printf '%s' "<PASSWORD>" > /root/.kc-db.password.tmp`
   - Run the installer:
     `./install-db-password-file.sh /root/.kc-db.password.tmp /etc/keycloak`
   - `ls -l /etc/keycloak/db.password` — verify
     `-rw-r----- 1 root keycloak ...`.
   - `shred -u /root/.kc-db.password.tmp`.

2. **Render + install the systemd drop-in.**
   - Substitute `{{KC_HOME}}` in
     `keycloak.service.d/g-iam-08-fix.conf.template`
     (e.g. `/home/banxe/keycloak-26.2.5`).
   - `install -d -m 0755 /etc/systemd/system/keycloak.service.d`
   - Place the rendered file at
     `/etc/systemd/system/keycloak.service.d/g-iam-08-fix.conf`.
   - `chmod 0644 /etc/systemd/system/keycloak.service.d/g-iam-08-fix.conf`.

3. **Reload + restart.**
   - `systemctl daemon-reload`
   - `systemctl restart keycloak`

## Validation steps (smoke checklist)

After restart, run all of the following. ALL must pass before sign-off.

- [ ] `systemctl status keycloak` — `active (running)`.
- [ ] `journalctl -u keycloak -n 50 --no-pager` — no DB-auth errors; no
      `password-file` errors.
- [ ] `ss -ltnp | grep 8080` (or configured port) — listening.
- [ ] KC health endpoint responds (or realm login sanity check if the
      operational profile permits).
- [ ] `ps -ef | grep '[k]eycloak.*--db-password='` — returns NO matches
      (exposure closed).
- [ ] `cat /proc/$(pgrep -f keycloak)/cmdline | tr '\0' ' '` does NOT
      contain `--db-password=`.
- [ ] `ls -l /etc/keycloak/db.password` — owner `root:keycloak`, mode `0640`.

## Rollback (if any validation step fails)

Follow `G-IAM-08-MIGRATION-PLAN.md` §5 verbatim:

1. `rm -f /etc/systemd/system/keycloak.service.d/g-iam-08-fix.conf`
2. `systemctl daemon-reload`
3. `systemctl restart keycloak`
4. Compare `systemctl cat keycloak` against the pre-migration baseline
   captured in pre-check #2.
5. Confirm `systemctl status keycloak` returns to `active (running)`.

## Operator sign-off block

Fill in upon completion (success or rollback). Append to the operator
sign-off ledger.

```
Date           : __________________________
Executor       : __________________________
Reviewer       : __________________________
Result         : [ ] PASS    [ ] FAIL    [ ] ROLLBACK
Rollback needed: [ ] No      [ ] Yes (details below)
Notes          :


```

## References

- `G-IAM-08-MIGRATION-PLAN.md` (this directory) — full plan + rationale.
- `keycloak.service.d/g-iam-08-fix.conf.template` — systemd drop-in.
- `db.password.template` — password-file placeholder.
- `install-db-password-file.sh` — installer.
- `validate-g-iam-08-mitigation.sh` — offline validator (run from CI / dev).
- IL-OPS-S12-1-DONE-EVIDENCE-AND-NEW-GAPS-2026-05-12 — gap origin.
- IL-OPS-S12-5-G-IAM-08-PREP-2026-05-12 — this prep package's IL pairing.
