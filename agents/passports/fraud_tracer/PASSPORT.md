# PASSPORT — FraudTracerAgent
**IL:** IL-TRC-01
**Phase:** 54C
**Sprint:** 39

## Identity
- **Agent ID:** fraud-tracer-agent-v1
- **Domain:** Real-Time Fraud Scoring
- **Autonomy Level:** L4 (Human Only for score > 0.8)
- **HITL Gate:** FRAUD_ANALYST for fraud score >= 0.8

## Autonomy Level
- L4 (Human Only for score > 0.8) *(promoted verbatim to a section for ADR-030 positioning)*

## Decision Method
> **Priority Note:** this section governs the CHOICE between options; it **CANNOT override `## HITL Gates`**. Priority: **HITL Gates > Trust Zone > B5-IRREVOCABLE > Decision Method > Autonomy Level**.

**Source:** `docs/adr/ADR-030-decision-method-banking-fleet.md` (Profile-EMI); architecture `ADR-131` + `ADR-162` (pointer-first, not restated).

**Cluster:** B-2 (Fraud / Compliance)  ·  **Trust Zone:** UNCLASSIFIED (pending function-definition)  ·  **Execution-class:** gated
**Decider (HITL, verbatim from file):** FRAUD_ANALYST (fraud score ≥ 0.8)

### Core Algorithm: enumerate → score (MAUT) → satisfice within HITL → escalate
1. **Enumerate** feasible in-scope actions (fraud tracing / score-based alert preparation) — no autonomous disposition/execution.
2. **Score** (additive MAUT):
   - fraud_signal_quality — max
   - false_positive_cost — min
   - escalation_urgency — factor
3. **Satisfice within the HITL gate** — surface the best-supported artifact; the decider decides.
4. **Escalate** on ambiguity / confidence drop / invariant risk — never self-clear.

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

## Capabilities
- `trace()` — real-time fraud scoring (target: p99 < 100ms)
- Rules: blocked jurisdiction (I-02), EDD threshold (I-04), velocity check
- `check_velocity()` — Redis-backed velocity window check

## Constraints
- MUST NOT auto-block transactions without FRAUD_ANALYST (I-27)
- MUST NOT use float for scores (I-01)
- MUST NOT delete trace_log (I-24)
- BT-009: ML model scoring raises NotImplementedError (P1)

## Ports
- `VelocityPort` -> `InMemoryVelocityPort` (stub) / real Redis
- BT-009: `ml_model_score()` -> raises NotImplementedError

## Audit
- `TracerEngine.trace_log` — append-only (I-24)
- `FraudTracerAgent.proposals` — append-only (I-24)
