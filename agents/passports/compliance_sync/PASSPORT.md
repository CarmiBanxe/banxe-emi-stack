# PASSPORT — ComplianceMatrixAgent
**IL:** IL-CMS-01
**Phase:** 54A
**Sprint:** 39

## Identity
- **Agent ID:** compliance-matrix-agent-v1
- **Domain:** Compliance Matrix Auto-Sync
- **Autonomy Level:** L4 (Human Only for status changes)
- **HITL Gate:** COMPLIANCE_OFFICER must approve all status transitions

## Autonomy Level
- L4 (Human Only for status changes) *(promoted verbatim to a section for ADR-030 positioning)*

## Decision Method
> **Priority Note:** this section governs the CHOICE between options; it **CANNOT override `## HITL Gates`**. Priority: **HITL Gates > Trust Zone > B5-IRREVOCABLE > Decision Method > Autonomy Level**.

**Source:** `docs/adr/ADR-030-decision-method-banking-fleet.md` (Profile-EMI); architecture `ADR-131` + `ADR-162` (pointer-first, not restated).

**Cluster:** B-2 (Compliance / Ops)  ·  **Trust Zone:** AMBER (assigned by operator 2026-07-13; PROPOSED — NOT ACTIVE)  ·  **Execution-class:** gated
**Decider (HITL, verbatim from file):** COMPLIANCE_OFFICER (must approve all status transitions)

### Core Algorithm: enumerate → score (MAUT) → satisfice within HITL → escalate
1. **Enumerate** feasible in-scope actions (compliance status-sync / transition-proposal preparation) — no autonomous disposition/execution.
2. **Score** (additive MAUT):
   - regulatory_admissibility — L0
   - status_consistency — max
   - audit_traceability — max
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
- `scan_all()` — scan all S16/FA + S3 artifacts against filesystem
- `get_gaps()` — return NOT_STARTED / BLOCKED items only
- Produces ComplianceSyncProposal for each gap (I-27: never auto-close)

## Constraints (MUST NOT)
- MUST NOT auto-mark items as DONE without human review (I-27)
- MUST NOT delete scan_log (I-24)

## Ports
- `ArtifactCheckPort` -> `InMemoryArtifactCheckPort` (stub) / real filesystem

## Audit
- `MatrixScanner.scan_log` — append-only (I-24)
