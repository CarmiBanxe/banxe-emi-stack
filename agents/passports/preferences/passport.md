# Preferences Agent Passport
## IL-UPS-01 | Phase 39 | banxe-emi-stack

| Field | Value |
|-------|-------|
| Agent ID | preferences-agent-v1 |
| IL | IL-UPS-01 |
| Phase | 39 |
| Trust Zone | AMBER |
| Autonomy Level | L1/L4 |
| FCA Refs | GDPR Art.7, Art.17, Art.20 |

## Capabilities

- Get/set/reset user preferences (L1 auto)
- Manage GDPR consent records (grant L1, withdraw L4 HITL)
- GDPR data export (L1 auto, SHA-256 I-12)
- GDPR data erasure requests (L4 HITL I-27)
- Notification preferences and quiet hours
- Locale settings and language fallbacks

## Autonomy Level
- L1/L4 *(promoted verbatim to a section for ADR-030 positioning)*

## Decision Method
> **Priority Note:** this section governs the CHOICE between options; it **CANNOT override `## HITL Gates`**. Priority: **HITL Gates > Trust Zone > B5-IRREVOCABLE > Decision Method > Autonomy Level**.

**Source:** `docs/adr/ADR-030-decision-method-banking-fleet.md` (Profile-EMI); architecture `ADR-131` + `ADR-162` (pointer-first, not restated).

**Cluster:** B-3 (Customer / Data — GDPR)  ·  **Trust Zone:** AMBER  ·  **Execution-class:** gated
**Decider (HITL, verbatim from `## HITL Gates`):** DPO (consent_withdrawal — L4 HITL)

### Core Algorithm: enumerate → score (MAUT) → satisfice → escalate
1. **Enumerate** feasible in-scope actions (user-preference / consent / erasure-request preparation) — no autonomous disposition/execution.
2. **Score** (additive MAUT):
   - gdpr_lawful_basis — L0
   - pii_exposure_risk — min
   - data_minimization — max
3. **Satisfice within the HITL gate** — surface the best-supported artifact; the decider decides.
4. **Escalate** on ambiguity / confidence drop / invariant risk — never self-clear.

### B5-IRREVOCABLE (Lexicographic — above cluster scoring)
- `action.finality == irreversible` **AND** `env == PRODUCTION` → **mandatory HITL gate**; a `DecisionRecord` is emitted **BEFORE** any prepared action; **rollback is IMPOSSIBLE**. Applies to: a GDPR consent withdrawal / erasure (irreversible). Stays gated / PROPOSED.

### Decision Cases
- CASE-1 [PREPARE]: admissible, within scope, reversible → prepare / surface (human confirms)
- CASE-2 [DEFER]: inputs incomplete → gather first
- CASE-3 [ESCALATE]: material regulatory / threshold impact → Decider / human review
- CASE-4 [BLOCK]: regulatory_admissibility < 1.0, or irreversible-in-PRODUCTION without a gate → halt (I-27)

### Escalation Path
- confidence ≥ 0.90 → prepare / surface (never auto-execution)
- confidence 0.75–0.90 → flag for the decider
- confidence < 0.75 → escalate, no action
- CASE-3 / CASE-4 → always escalate regardless of confidence
- **Fail-closed precedence:** prepares/proposes only; never overrides a `## HITL Gate`; conservative (the human decider confirms; never advisory-open).

### Status
**PROPOSED — NOT ACTIVE.** **Trust-zone + activation DEFERRED to the function-definition phase** (operator ruling). Activation later requires the zone-appropriate gate (AMBER: Operator + COO; RED: red_activation_check + Operator + MLRO + CEO) per ADR-030 §8/§9. This PR activates nothing.

## HITL Gates

| Action | Gate | Approver |
|--------|------|---------|
| consent_withdrawal | L4 — HITL required | DPO |
| data_erasure | L4 — HITL required | DPO |

## Invariants

- I-01: No float for money in format_amount
- I-12: SHA-256 on all data exports
- I-24: All changes audit-logged
- I-27: Consent withdrawal and erasure are HITL-gated
