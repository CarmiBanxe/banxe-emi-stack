# Reconciliation algorithm sketch — Sprint S16.4 PREP

Status: PREP (sketch only — no production code change in this PR).
Anchors: IL-OPS-ROADMAP-SPRINTS-S12-S25-APPROVED-2026-05-11 §S16.4,
ADR-013 (Midaz CBS primary), ADR-014 (composable financial stack),
ADR-015 (payment processing stack), ADR-027 (audit-trail durability),
FCA SUP 15, FCA CASS 15 §15.10.

This document specifies the daily reconciliation algorithm in
operator-readable pseudo-code. It is the contract that the real
ReconciliationPort adapter (Sprint S20+) must implement.

---

## 1. Inputs

- `run_id`: opaque identifier (e.g. `recon-YYYYMMDD-tenant-banxe`).
- `thresholds`: `list[ReconciliationThreshold]` — one per in-scope currency.
- `now`: injected clock (UTC) — never `datetime.now()` in adapter code.
- `internal_source`: customer balance store (Midaz CBS / Postgres slave).
- `external_source`: `SafeguardingExternalPort` — Modulr live (S20.1) or
  `ModulrSafeguardingStub` for dev / test.
- `audit_sink`: `AuditSinkPort` — production binding wraps ADR-027
  BufferedAuditPort.

## 2. Outputs

- A finalised `ReconciliationRun` with `status ∈ {APPROVED, AWAITING_HITL,
  REJECTED, FAILED}`.
- Zero or more `ReconciliationBreak` records persisted via `audit_sink`.
- A run-completion audit record emitted via `audit_sink`.

## 3. Invariants

- I-01: all monetary deltas are `int` minor units OR `Decimal` — never `float`.
- I-24 (ADR-027): audit records are append-only; no update / delete path.
- A run is idempotent on `run_id`: re-running the same `run_id` MUST NOT
  produce duplicate audit records (deduplication key = `run_id`).
- A break is identified by `(run_id, customer_id_hash, currency)`; a
  second detection on the same triple within the same run MUST overwrite
  (not duplicate) the in-run record but MUST emit only one
  `RECON_BREAK_DETECTED` audit event per triple per run.

## 4. Steps (pseudo-code)

```text
function run_reconciliation(run_id, thresholds, internal_source,
                            external_source, audit_sink, now):

    # Step 1 — start
    run = ReconciliationRun(id=run_id, started_at=now(),
                            ended_at=None, status=STARTED,
                            total_balance_internal=Decimal("0.00"),
                            total_balance_external=Decimal("0.00"),
                            break_count=0,
                            break_total=Decimal("0.00"),
                            thresholds=thresholds)
    audit_sink.log_run(run)                             # RECON_RUN_STARTED

    # Step 2 — ingest internal
    run.status = INGESTING
    try:
        internal_balances = internal_source.fetch_all()  # per (customer_id, currency)
    except Exception:
        run.status = FAILED
        run.ended_at = now()
        audit_sink.log_run(run)                          # RECON_RUN_COMPLETED (FAILED)
        return run
    run.total_balance_internal = sum(b for _, _, b in internal_balances)

    # Step 3 — ingest external
    external_balances = {}
    for account_id, currency in distinct((acct, curr) for _, curr, _ in internal_balances):
        try:
            external_balances[(account_id, currency)] =
                external_source.fetch_safeguarding_balance(account_id, currency)
        except Exception:
            run.status = FAILED
            run.ended_at = now()
            audit_sink.log_run(run)                      # RECON_RUN_COMPLETED (FAILED)
            return run
    run.total_balance_external = sum(external_balances.values())

    # Step 4 — detect breaks
    run.status = DETECTING
    for (customer_id, currency, internal) in internal_balances:
        account_id = map_customer_to_safeguarding_account(customer_id, currency)
        external = external_balances.get((account_id, currency), Decimal("0.00"))
        delta_abs_minor = to_minor_units(internal - external, currency)
        larger = max(abs(to_minor_units(internal, currency)),
                     abs(to_minor_units(external, currency)),
                     1)  # avoid division by zero
        delta_bps = round(delta_abs_minor * 10000 / larger)

        threshold = lookup_threshold(thresholds, currency)
        if threshold is None:
            continue                                     # currency out of scope
        breach_abs = abs(delta_abs_minor) > threshold.absolute_minor_units
        breach_rel = abs(delta_bps) > threshold.relative_basis_points
        if not (breach_abs or breach_rel):
            continue
        kind = BOTH if breach_abs and breach_rel else (
               ABSOLUTE if breach_abs else RELATIVE)
        break_record = ReconciliationBreak(
            id=f"{run_id}:{sha256_16(customer_id)}:{currency}",
            run_id=run_id,
            customer_id_hash=sha256_16(customer_id),
            currency=currency,
            internal_balance=internal,
            external_balance=external,
            delta_absolute=delta_abs_minor,
            delta_relative=delta_bps,
            threshold_breach_kind=kind,
            detected_at=now(),
        )
        run.breaks.append(break_record)
        run.break_count += 1
        run.break_total += abs(Decimal(delta_abs_minor)) / minor_unit_scale(currency)
        audit_sink.log_break(run, break_record)          # RECON_BREAK_DETECTED

    # Step 5 — HITL gate + finalize
    if run.break_total >= EMERGENCY_THRESHOLD:           # TODO Sprint S20.5
        run.status = AWAITING_HITL
        notify_mlro(run)                                 # TODO Sprint S20.5 Telegram
    elif run.break_count == 0:
        run.status = APPROVED
    else:
        run.status = APPROVED                            # under-threshold breaks logged but auto-approved
    run.ended_at = now()
    audit_sink.log_run(run)                              # RECON_RUN_COMPLETED
    return run
```

## 5. Failure modes

| Failure                                | Detection point | Algorithm response                                     |
|----------------------------------------|-----------------|--------------------------------------------------------|
| Internal balance store unreachable     | Step 2          | `status=FAILED`, emit `RECON_RUN_COMPLETED (FAILED)`   |
| External (Modulr) API timeout          | Step 3          | `status=FAILED`, emit `RECON_RUN_COMPLETED (FAILED)`   |
| External returns partial data          | Step 3          | `status=FAILED` — partial data is unsafe to reconcile  |
| Currency missing from threshold table  | Step 4          | Skip (out of scope); record under-coverage audit note  |
| Audit sink unavailable                 | Step 1 / 5      | Per ADR-027: sink swallows errors, log + continue      |
| EMERGENCY-tier break detected          | Step 5          | `status=AWAITING_HITL` — requires MLRO co-sign         |

## 6. Idempotency

- `run_id` is the deduplication key. The audit sink MUST refuse to record
  a second `RECON_RUN_STARTED` for the same `run_id` (sink-level
  responsibility; algorithm assumes the contract).
- Break IDs use `(run_id, customer_id_hash, currency)` — re-detection
  within the same run overwrites in-memory and emits ONE audit event.
- A re-run with a new `run_id` against the same date is a separate run
  and is permitted (operator initiates manual replay).

## 7. ClickHouse audit emission pattern (per ADR-027)

Three event types, all routed through `AuditSinkPort` which wraps the
ADR-027 BufferedAuditPort:

| Event type              | severity | entity_id      | payload (excerpt)                                            |
|-------------------------|----------|----------------|--------------------------------------------------------------|
| `RECON_RUN_STARTED`     | INFO     | `run.id`       | `started_at`, `currencies`                                   |
| `RECON_RUN_COMPLETED`   | INFO / MAJOR / CRITICAL | `run.id` | `status`, `break_count`, `break_total`, `ended_at`           |
| `RECON_BREAK_DETECTED`  | MAJOR / CRITICAL | `run.id` | `customer_id_hash`, `currency`, `delta_absolute`, `delta_relative`, `threshold_breach_kind` |

Severity for `RECON_RUN_COMPLETED`:
- `APPROVED` + `break_count == 0` → INFO
- `APPROVED` + `break_count > 0` → MAJOR
- `AWAITING_HITL` → CRITICAL
- `FAILED` → CRITICAL

Severity for `RECON_BREAK_DETECTED`:
- Under EMERGENCY threshold → MAJOR
- At / above EMERGENCY threshold → CRITICAL

## 8. MLRO notification trigger

Single trigger: `run.break_total >= EMERGENCY_THRESHOLD` at Step 5.

- Channel: Sprint S20.5 Telegram MLRO group (TODO — channel reference
  lands when S20.5 ships).
- Payload: `run_id`, `break_count`, `break_total`, top 3 breaks by
  absolute delta, link to the audit-trail entry.
- Idempotent on `run_id`: one notification per run regardless of retry.

## 9. HITL gate

A run enters `AWAITING_HITL` ONLY when `run.break_total >=
EMERGENCY_THRESHOLD`. To leave that state:

1. Central confirms the data input was correct (no source-data outage).
2. Operator confirms the operational context (no in-flight settlement).
3. MLRO co-signs the disposition.

All three sign-offs must be recorded against the run's audit thread
before the run can be marked `APPROVED` (or `REJECTED` with remediation
plan). The runbook `docs/runbooks/safeguarding-reconciliation-deploy-2026-05-12.md`
captures the operator-facing procedure.

## 10. Open TODOs (out of S16.4 PREP scope)

- `EMERGENCY_THRESHOLD` value — Sprint S20.5 calibration against historical breaks.
- Modulr account-id ↔ customer-id mapping table — Sprint S20.1.
- FX normalisation when totalling cross-currency aggregates — ADR-LCY-01.
- ClickHouse table schema for `RECON_*` events — Sprint S16 observability.
- Re-run / replay UI (operator surface) — Sprint S20+.
