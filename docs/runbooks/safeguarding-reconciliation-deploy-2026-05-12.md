# Operator runbook — Safeguarding + Reconciliation engine deploy (S16.4 PREP)

Owner sprint: S16.4 (per IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11).
Anchors: Sprint S16.4, FCA SUP 15, FCA CASS 15 §15.10, ADR-013, ADR-014,
ADR-015, ADR-027.
Status: PREP (this PR delivers the package only; no production deploy here).

---

## Purpose

Deploy the Safeguarding + Reconciliation engine on evo1 once Sprint S20.1
delivers the real Modulr live-API adapter to replace the
`ModulrSafeguardingStub` shipped in this PREP package. This runbook is the
operator-facing checklist for that deploy.

## Non-goal

**This PR does NOT deploy.** Files committed here are scaffolding only:
the domain model, port interfaces, a stub adapter, an algorithm sketch,
a validation script, and this runbook. The first production run requires
the deliverables in the §Pre-checks section below to exist, and explicit
Central + operator + MLRO sign-off.

## Pre-checks (operator-side; run before any deploy)

1. **Real Modulr adapter present** — Sprint S20.1 must have replaced
   `services/safeguarding/internal/adapters/modulr_safeguarding_stub.py`
   with a tested live adapter and a sandbox-credentials path.
2. **Customer-balance source reachable** — `psql` to the Postgres slave
   that holds the customer-balance materialised view (or Midaz CBS
   primary per ADR-013).
3. **ClickHouse Guardian reachable** — `curl -sf <CH_URL>/ping` ⇒ `Ok.`
4. **ADR-027 BufferedAuditPort wired** — `services/safeguarding/audit_*`
   present and registered in the factory.
5. **EMERGENCY threshold calibrated** — Sprint S20.5 confirmed the value;
   `ReconciliationThreshold` config in env or DB has non-TODO values for
   every in-scope currency.
6. **MLRO Telegram channel** — Sprint S20.5 published a working webhook
   URL; smoke-test it with a synthetic alert before first real run.
7. **Disk space** — evo1 `/var/log/banxe/recon/` has ≥ 5 GB free for
   audit-cron output until the drain catches up.

## Deploy steps (operator-runnable; NOT executed in this PR)

1. **Stage configuration.**
   - Render thresholds-per-currency into the configured store
     (env / DB row); never commit production thresholds to git.
   - Confirm secrets file ownership (root:banxe-safeguarding 0640).

2. **Install the daily cron.**
   - Path: `/etc/cron.d/banxe-safeguarding-reconciliation`.
   - Schedule: `15 3 * * *` (03:15 UTC; after the 02:30 KC backup, before
     the 04:00 weekly drill window).
   - Command runs the engine in DRY-RUN mode first (no MLRO notify, no
     run finalisation) for the first 7 days post-deploy.

3. **First-run validation.**
   - Manually trigger one run in DRY-RUN: `sudo -u banxe-safeguarding
     /usr/local/bin/banxe-safeguarding-recon --dry-run --once`.
   - Inspect ClickHouse for `RECON_RUN_STARTED` + `RECON_RUN_COMPLETED`
     records; verify break counts vs expected baseline.
   - Re-run validation after every threshold-config change.

4. **Promote to LIVE.**
   - Switch cron command to remove `--dry-run`.
   - Capture the first LIVE run's `run_id`; MLRO co-signs the run's
     disposition before any consumer of the result acts on it.

5. **Post-deploy smoke.**
   - `journalctl -u banxe-safeguarding-recon -n 200 --no-pager` —
     confirm no Python stack traces.
   - `ss -lntp | grep banxe-safeguarding-recon` — no listening sockets
     expected (this is a cron job, not a long-running service).
   - Verify `RECON_BREAK_DETECTED` records have plausible
     `customer_id_hash` distributions (sha256[:16] looks uniform).

## HITL gate

Production deploy of this engine requires explicit, recorded sign-off:

1. **Central approval** — confirms code chain is Sub-B-merged and
   IL-S16-4-SAFEGUARDING-RECONCILIATION-PREP-2026-05-12 is fully cited
   in the deployment PR / operator-side ledger.
2. **Operator approval** — confirms operational pre-checks (§Pre-checks)
   are green at the moment of deploy.
3. **MLRO co-sign** — required before the first LIVE run is promoted out
   of DRY-RUN, and again any time the engine enters `AWAITING_HITL`
   status (EMERGENCY-threshold break).

All three are recorded in the operator-side sign-off ledger against the
deploy date and the post-deploy first-run `run_id`.

## Rollback

If post-deploy smoke fails or a LIVE run produces `AWAITING_HITL` and the
MLRO declines, roll back in this order:

1. **Disable the cron.** `chmod 0000 /etc/cron.d/banxe-safeguarding-reconciliation`
   (or remove the file). Disk-free, atomic, reversible.
2. **Mark service as DRY-RUN.** Re-render the cron command with the
   `--dry-run` flag so any cron-scheduled invocation that slips through
   cannot finalise a LIVE run.
3. **Keep last 7 days of run logs.** `find /var/log/banxe/recon -mtime
   +7 -type f -delete` runs only against logs older than the rollback
   window; everything from the failed deploy is retained for
   post-mortem.
4. **Notify** — page the on-call channel + MLRO with the failed `run_id`
   and the rollback action taken.
5. **Post-mortem evidence** — archive the run's ClickHouse audit
   records, the cron stdout/stderr, and the rollback timestamp into the
   incident ledger.

## Operator sign-off block

```
Deploy date    : __________________________
Executor       : __________________________
Central        : __________________________ (approval)
Operator       : __________________________ (approval)
MLRO           : __________________________ (co-sign)
First DRY-RUN  : run_id = ________________
First LIVE run : run_id = ________________
Smoke result   : [ ] PASS    [ ] FAIL    [ ] ROLLBACK
Rollback notes :


```

## References

- `services/safeguarding/internal/reconciliation/domain.py` — domain
  model + ports.
- `services/safeguarding/internal/adapters/modulr_safeguarding_stub.py` —
  dev/test stub; to be replaced in Sprint S20.1.
- `services/safeguarding/internal/reconciliation/algorithm.md` —
  algorithm sketch + invariants + failure modes + HITL trigger.
- `services/safeguarding/scripts/validate-prep.sh` — offline package
  validator.
- IL-S16-4-SAFEGUARDING-RECONCILIATION-PREP-2026-05-12 — this PR's
  IL pairing entry (see `INSTRUCTION-LEDGER.md`).
- ADR-027 BufferedAuditPort (canonical lives in the project-canon repo).
- ADR-013/014/015 (financial-stack canon).
