# Reconciliation Core Boundary — two CASS regimes, one shared mechanics core

**Sprint:** S6.2 | **Created:** 2026-06-09
**FCA rules:** FCA CASS 15 (IL-SAF-01 / "ADR-SAF-01"), FCA CASS 7.15
**Code:** `src/recon_core/` (shared), `src/safeguarding/` (CASS 15), `services/recon/` (CASS 7.15)

---

## Decision (one line)

The two safeguarding reconciliation paths share ONE regime-agnostic **mechanics** core
(`src/recon_core/`); their **regulatory regimes stay distinct**, and every threshold is an
injected parameter — **deliberately NOT unified**.

## The two regimes (legitimately different — do NOT merge)

| | Router A — CASS 15 | Router B — CASS 7.15 |
|---|---|---|
| Code | `src/safeguarding/*` | `services/recon/*` |
| API | `/v1/safeguarding/*` | `/v1/safeguarding-recon/*` |
| Engine | `DailyReconciliation` | `ReconciliationEngineV2` + `ReconAgent` |
| Granularity | **aggregate** internal-vs-statutory-bank balance | **line-item** ledger-vs-statement per IBAN |
| Match tolerance | £0.01 penny-exact | £0.01 penny-exact (per item) |
| Breach rule | `> £0.01` → `ReconStatus.BREAK` | `> £100` net → `HITLProposal` (COMPLIANCE_OFFICER) |
| Statutory output | FIN060 monthly return, 48h resolution pack | HITL breach-resolution workflow |
| Governing record | IL-SAF-01, `docs/compliance/cass15-controls.md` | IL-REC-01 |

The **£0.01** and **£100** thresholds are **NOT competing values of one rule**. They belong to
two different FCA regimes:

- **£0.01 (CASS 15)** = aggregate-balance *penny-exactness* — does the firm's total client-money
  position match the statutory safeguarding bank balance to the penny?
- **£100 (CASS 7.15)** = line-item *HITL escalation* — is a transaction-level discrepancy large
  enough to require a human (COMPLIANCE_OFFICER) to resolve it rather than auto-recording it?

Collapsing them would be a **compliance behaviour change** and is explicitly out of scope.

## What IS shared — the mechanics core (`src/recon_core/`)

Only the regime-agnostic plumbing, previously duplicated as inline loops in each engine:

| Module | Mechanic | Consumed by |
|---|---|---|
| `compare.py` | Decimal-safe `signed_difference` / `absolute_difference` / `within_tolerance` (I-01 guarded) | A `DailyReconciliation`, B `ReconciliationEngineV2` |
| `breach_evaluator.py` | `BreachEvaluator(threshold, breach_kind)` → `BreachDecision`; **breach ⟺ amount > threshold** (strict) | A (`£0.01`/`BREAK`), B `ReconAgent` (`£100`/`HITL`) |
| `result.py` | `CoreReconResult` + `evaluate_balances()` — neutral outcome both **map to/from** (does NOT replace `ReconciliationResult` / `ReconciliationReport`) | A `DailyReconciliation` |
| `audit.py` | `ReconAuditEvent` + `emit_recon_audit()` — normalized, Decimal-string, refs-not-balances audit emit (R-SEC), fail-open | A + B (additive) |

**Thresholds are inputs.** The core enumerates no regimes and holds no threshold constant.
Each regime injects its own:

```python
# CASS 15 (src/safeguarding/daily_reconciliation.py)
BreachEvaluator(threshold=Decimal("0.01"), breach_kind="BREAK")

# CASS 7.15 (services/recon/recon_agent.py)
BreachEvaluator(threshold=BREACH_HITL_THRESHOLD, breach_kind="HITL")  # Decimal("100")
```

## Shared boundary rule (equivalence-critical)

Both regimes previously used **strict `>`** for breach and **`<=`** for clear/match. The core
preserves this exactly:

```
breach  ⟺  amount  >  threshold     # equal-to-threshold is NOT a breach
clear   ⟺  amount  <= threshold
```

This means: CASS 15 still MATCHES at exactly £0.01 and BREAKS above it; CASS 7.15 still returns a
report at exactly £100 net and escalates to HITL above it. Locked by
`tests/test_recon_core/test_no_regime_drift.py` and the characterization tests.

## Equivalence guarantee (no-loss)

Characterization tests (`tests/test_recon_core/test_characterization.py`) captured each regime's
observable behaviour **before** the refactor and stay green **after**. Both routers' pre-existing
suites (`test_src_safeguarding.py`, `test_recon/`) pass **unchanged**. No public API, endpoint,
status enum, threshold, FIN060 shape, or HITLProposal shape changed.

## Out of scope (future dedup candidates — NOT touched in S6.2)

`services/recon/breach_detector.py` (streak, £10/3-day), `src/safeguarding/breach_detector.py`
(severity/streak), `services/recon/recon_engine.py` (£50k HITL_MLRO), and
`services/recon/reconciliation_engine.py` (£1.00) solve *different* problems (streak detection,
large-value flagging) and were left untouched to keep this change equivalence-provable.

## Supersedes

This decision **refines and supersedes** the recommendation in
`docs/audit/SAFEGUARDING-BOUNDARY-AUDIT-2026-06-09.md`, which proposed a *single canonical engine /
single breach model* that would "eliminate the £0.01/£100 breach divergence". That would merge two
distinct regulatory regimes. S6.2 instead shares only the **mechanics** and keeps the regimes — and
their thresholds — deliberately separate.

## Cross-references

- IL-SAF-01 / "ADR-SAF-01" — `docs/architecture/ARCHITECTURE-SAFEGUARDING-ENGINE.md`
- `docs/compliance/cass15-controls.md` (CASS-02 daily recon, CASS-04 breach notification)
- ADR-007 (Decimal for money, I-01), ADR-002 (ClickHouse audit log, I-24)
