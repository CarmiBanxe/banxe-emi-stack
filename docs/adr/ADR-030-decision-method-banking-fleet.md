# ADR-030: Decision Method — Best-Decision Profile-EMI for the Banking Agent Fleet

**Date:** 2026-07-08
**Status:** Proposed
**IL:** IL-DM-EMI-01
**Author:** Moriel Carmi / Claude Code

---

## Context

`banxe-architecture` uses ADR-131 (R6 methodology) as its decision-method canon. `banxe-emi-stack` has a
**different** soul format (`## Identity` / `## Capabilities` / `## Constraints` / `## HITL Rules`|`## HITL Gates` /
`## Autonomy Level` (L3/L4) / `## Protocol DI Ports` / `## Audit` / `## My Promise`), Trust Zones (RED/AMBER/GREEN),
FCA/MLR references in headers, and its own governance (`guardian.yml` — non-strict, no section whitelist;
`INSTRUCTION-LEDGER.md` flat format; no ADR-131; no `souls-format-check`). This ADR adapts R6 for emi-stack as
**"Profile-EMI"** without breaking soul format or CI.

## Decision

Adopt R6 core (enumerate → score → satisfice → escalate; MAUT; Lexicographic L0; B1–B5; Variant C; `DecisionRecord`;
no-adoption-right) as a `## Decision Method` section, adapted for emi-stack:

1. **POSITION:** insert `## Decision Method` **AFTER** `## Autonomy Level` (emi-stack has no `## HITL Gate` section).

2. **PRIORITY** (preamble in every Decision Method block):
   `HITL Gates table > Trust Zone > B5-IRREVOCABLE > Decision Method > Autonomy Level`.
   Decision Method governs the **CHOICE between options**; it **CANNOT override HITL Gates**.

3. **BANKING CLUSTERS (MAUT weights):**
   - **B-1 Payments/Settlement:** `settlement_finality` .30, `regulatory_admissibility` .25, `counterparty_risk` .20,
     `amount_threshold_breach` .15, `rail_availability` .10; satisfice **P1+P2 ≥ .55**.
   - **B-2 Compliance/AML/Sanctions:** `regulatory_admissibility` .35 (**L0 mandatory =1.0 else BLOCKED**),
     `evidence_quality` .25, `false_positive_cost` .20, `tipping_off_risk` .15, `escalation_urgency` .05.
     **NO advisory branch.**
   - **B-3 Customer/Support/Products:** `consumer_duty_compliance` .30, `pii_exposure_risk` .25, `reversibility` .20,
     `cx_outcome_quality` .15, `data_minimization` .10; satisfice **U1+U3 ≥ .50**.
   - **B-4 Treasury/Reporting/Finance:** `regulatory_submission_finality` .35 (**L0 =1.0**), `ledger_integrity` .30,
     `disclosure_risk` .20, `materiality_threshold` .15; **F2 ≥ .80 else BLOCKED**.

4. **B5-IRREVOCABLE** (new, above B4): `action.finality==irreversible AND env==PRODUCTION` → **mandatory HITL gate**,
   `DecisionRecord` emitted **BEFORE** execution, rollback **IMPOSSIBLE**, ClickHouse entry with `humanReviewedBy`
   populated. Applies to: SEPA credit T+0, on-chain crypto, card permanent block, treasury sweep >£100k, FCA
   regulatory submission.

5. **LEXICOGRAPHIC ORDER:** `L0-TZ` (Trust Zone RED → gated/blocked, no scoring) → `L0-REG`
   (`regulatory_admissibility < 1.0` → BLOCKED) → `L1` MAUT cluster satisfice → `L2` B1–B5 variant. **RED agents:
   advisory PROHIBITED** (`evidence_gatherer` / `gated_recommendation` / `blocked_reporter` only) — POCA 2002 s.330,
   MLR 2017, SAMLA 2018 place personal liability on MLRO/SMF17; the agent never assumes it.

6. **EXECUTION-CLASS ↔ Autonomy mapping:** `advisory→L3+Monitor`; `gated(SHARED)→L3+Review`; `gated(PROD)→L3+Gate`;
   `blocked→L4+AUTO-BLOCK`; `B4/B5→L4+irreversible`. Decision Method is the choice-algorithm **INSIDE** the existing
   L3/L4 class, not a new level.

7. **DEDUP / CANONICAL SOURCE:** `canonical_id = <domain>.<agent>`. Source priority `PASSPORT.md > SOUL.md > *.soul.md`.
   Decision Method inserted **ONLY** in the canonical file; other formats get a read-only pointer-mirror. Cross-repo:
   architecture = template (PROPOSED, no concrete roles); emi-stack = instance (concrete SMF roles from HITL Gates).
   **Never train the same soul in both repos.**

8. **RATIFICATION by Trust Zone (SMCR):**
   - GREEN → Operator + CTO (SMF26);
   - AMBER → Operator + COO (SMF24);
   - RED non-financial → Operator + CRO (SMF4) + MLRO awareness;
   - RED AML/sanctions/SAR → Operator + MLRO (SMF17) + CEO (SMF1);
   - RED financial → Operator + CFO (SMF2) + COO (SMF24) + CRO awareness.

9. **RUNTIME GATE for RED activation** (before ACTIVE, not just PROPOSED): kill switch (Temporal terminate),
   `DecisionRecord` emission (ClickHouse `agent_decision_records`, 7y TTL), HITL dashboard, Prometheus metrics/alerts,
   Langfuse audit sampling, budget policy. SOUL declaration suffices only at PROPOSED.

## Consequences

- **+** Banking fleet gains a canonical, FCA-aware decision method without breaking emi-stack soul format or CI.
- **+** RED agents structurally cannot act autonomously (advisory prohibited).
- **−** Requires per-Trust-Zone SMF ratification; adds B5-IRREVOCABLE handling; runtime-gate prerequisite for RED
  activation.
- `guardian.yml`: **NO change needed** (non-strict, no section whitelist — verified 2026-07-08).

## Alternatives Considered

- **Pointer-only to ADR-131:** REJECTED — Trust Zones, FCA headers, B5-IRREVOCABLE do not exist in ADR-131;
  pointer-only would create an unresolvable review mismatch. ADR-030 is the local primary source, referencing ADR-131
  as parent pattern.
- **Extend `## HITL Rules` table:** REJECTED — HITL Rules = *when* to hand to a human; Decision Method = *how* the
  agent chooses. Different layers.
- **New autonomy level:** REJECTED — L3/L4 unchanged; Decision Method is an intra-level algorithm.

## Pointer to Architecture Canon

Adaptation of `banxe-architecture/docs/adr/ADR-131` (+ ADR-162 best-decision principle). On conflict: **ADR-030 governs
emi-stack agents; ADR-131 governs architecture/factory agents.**
