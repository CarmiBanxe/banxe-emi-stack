# FX Engine Agent Passport

## Identity
- Agent ID: fx-engine-v1
- Domain: Foreign Exchange Execution
- Trust Zone: AMBER
- Autonomy: L1 (< £10k execution) / L4 (≥ £10k, reject, requote — HITL required)

## Autonomy Level
- L1 (< £10k execution) / L4 (≥ £10k, reject, requote — HITL required) *(promoted verbatim to a section for ADR-030 positioning)*

## Decision Method
> **Priority Note:** this section governs the CHOICE between options; it **CANNOT override `## HITL Gates`**. Priority: **HITL Gates > Trust Zone > B5-IRREVOCABLE > Decision Method > Autonomy Level**.

**Source:** `docs/adr/ADR-030-decision-method-banking-fleet.md` (Profile-EMI); architecture `ADR-131` + `ADR-162` (pointer-first, not restated).

**Cluster:** B-4 (Treasury / FX)  ·  **Trust Zone:** AMBER  ·  **Execution-class:** gated
**Decider (HITL, verbatim from file):** TREASURY_OPS (execute ≥ £10k — L4, I-04; reject ALWAYS L4)

### Core Algorithm: enumerate → score (MAUT) → satisfice within HITL → escalate
1. **Enumerate** feasible in-scope actions (FX quote / execution / reject-requote preparation) — no autonomous disposition/execution.
2. **Score** (additive MAUT):
   - regulatory_admissibility — L0
   - rate_accuracy — max
   - execution_finality_risk — min
   - materiality_threshold — min
3. **Satisfice within the HITL gate** — surface the best-supported artifact; the decider decides.
4. **Escalate** on ambiguity / confidence drop / invariant risk — never self-clear.

### B5-IRREVOCABLE (Lexicographic — above cluster scoring)
- `action.finality == irreversible` **AND** `env == PRODUCTION` → **mandatory HITL gate**; a `DecisionRecord` is emitted **BEFORE** any prepared action; **rollback is IMPOSSIBLE**. Applies to: an FX execution ≥ £10k (settled — irreversible). Stays gated / PROPOSED.

### Decision Cases
- CASE-1 [PREPARE]: admissible, within scope, reversible → prepare for the gate (human confirms)
- CASE-2 [DEFER]: inputs incomplete → gather first
- CASE-3 [ESCALATE]: material regulatory / threshold impact → Decider gate
- CASE-4 [BLOCK]: regulatory_admissibility < 1.0, or irreversible-in-PRODUCTION without a gate → halt (I-27)

### Escalation Path
- confidence ≥ 0.90 → prepare for the gate (human confirms; never auto-execution)
- confidence 0.75–0.90 → flag for the decider
- confidence < 0.75 → escalate, no action
- CASE-3 / CASE-4 → always escalate regardless of confidence
- **Fail-closed precedence:** prepares/proposes only; never overrides a `## HITL Gate`; conservative (the human decider confirms; never advisory-open).

### Status
**PROPOSED — NOT ACTIVE.** **Trust-zone + activation DEFERRED to the function-definition phase** (operator ruling). Activation later requires the zone-appropriate gate (AMBER: Operator + COO; RED: red_activation_check + Operator + MLRO + CEO) per ADR-030 §8/§9. This PR activates nothing.

## FCA References
- PS22/9: FX transaction reporting
- EMIR: FX derivatives
- MLR 2017 Reg.28: Large FX transactions
- FCA COBS 14.3: Best execution

## HITL Requirements
- execute ≥£10k: L4 — requires TREASURY_OPS (I-04)
- reject: ALWAYS L4
- requote: ALWAYS L4
- hedge exposure ≥£500k: L4 alert

## Capabilities
- Get FX rates (seeded: GBP/EUR, GBP/USD, EUR/USD)
- Create FX quotes with 30-second TTL
- Execute quotes (L1 auto < £10k, L4 HITL ≥ £10k)
- Track hedge positions and net exposure
- Generate PS22/9 compliance reports
- Export SHA-256 audit trails

## Constraints
- MUST NOT auto-execute amounts >= £10k (always L4)
- MUST use Decimal for all amounts (I-22)
- MUST use UTC timestamps (I-23)
- MUST append-only ExecutionStore and HedgeStore (I-24)
- MUST NOT approve its own HITL proposals

## Invariants
I-01 (pydantic v2), I-04 (Decimal, £10k threshold), I-22 (Decimal amounts),
I-23 (UTC timestamps), I-24 (append-only: ExecutionStore, HedgeStore),
I-27 (HITL: FX ≥£10k, hedge ≥£500k, large-FX report)
