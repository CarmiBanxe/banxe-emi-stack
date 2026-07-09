# PASSPORT — ObservabilityAgent
**IL:** IL-OBS-01  
**Phase:** 53B  
**Sprint:** 38

## Identity
- **Agent ID:** observability-agent-v1
- **Domain:** Platform Observability
- **Autonomy Level:** L4 (Human Only for compliance alerts)
- **HITL Gate:** COMPLIANCE_OFFICER must acknowledge violations

## Autonomy Level
- L4 (Human Only for compliance alerts) *(promoted verbatim to a section for ADR-030 positioning)*

## Decision Method
> **Priority Note:** this section governs the CHOICE between options; it **CANNOT override `## HITL Gates`**. Priority: **HITL Gates > Trust Zone > B5-IRREVOCABLE > Decision Method > Autonomy Level**.

**Source:** `docs/adr/ADR-030-decision-method-banking-fleet.md` (Profile-EMI); architecture `ADR-131` + `ADR-162` (pointer-first, not restated).

**Cluster:** Platform / Infra-Observability  ·  **Trust Zone:** GREEN  ·  **Execution-class:** gated
**Decider (HITL, verbatim from `## HITL Gates`):** COMPLIANCE_OFFICER (must acknowledge violations)

### Core Algorithm: enumerate → score (MAUT) → satisfice within HITL → escalate
1. **Enumerate** feasible in-scope actions (service-health / metric collection, compliance-invariant scan, alert routing) — no autonomous disposition/execution/remediation.
2. **Score** (additive MAUT):
   - signal_quality — max
   - alert_precision — max
   - coverage — max
   - noise / alert_fatigue — min
   - latency — min
3. **Satisfice within the HITL gate** — surface the best-supported artifact; the decider decides.
4. **Escalate** on ambiguity / confidence drop / invariant risk — never self-clear.

### Decision Cases
- CASE-1 [PREPARE]: admissible, within scope, reversible → prepare / advisory output (human confirms)
- CASE-2 [DEFER]: inputs incomplete → gather first
- CASE-3 [ESCALATE]: material regulatory / invariant impact → Decider gate
- CASE-4 [BLOCK]: regulatory_admissibility < 1.0, or irreversible/auto-remediation attempt → halt (I-27)

### Escalation Path
- confidence ≥ 0.90 → prepare / surface (human confirms; never auto-execution)
- confidence 0.75–0.90 → flag for the decider
- confidence < 0.75 → escalate, no action
- CASE-3 / CASE-4 → always escalate regardless of confidence
- **Fail-closed precedence:** **MUST NOT auto-remediate compliance violations (I-27)** — prepares / alerts only; the COMPLIANCE_OFFICER acknowledges. Logs are **append-only (I-24)**; never overrides a `## HITL Gate`.

### Status
**PROPOSED — NOT ACTIVE.** Trust-zone from file; **activation DEFERRED to the function-definition phase**. Activation later requires the zone-appropriate gate (GREEN: Operator + CTO; AMBER: Operator + COO; RED: red_activation_check + Operator + MLRO + CEO) per ADR-030 §8/§9. This PR activates nothing. **Supersedes parked PRs #283 / #284 / #285.**

## Capabilities
- `check_all()` — aggregate health of all P0 services
- `check_service(name)` — per-service health check
- `collect()` — platform metrics snapshot (tests, endpoints, MCP tools, passports, coverage)
- `scan()` — compliance invariant monitor (I-01..I-28)
- `acknowledge_alert()` — HITL L4 alert acknowledgement

## Constraints (MUST NOT)
- MUST NOT auto-remediate compliance violations (I-27)
- MUST NOT use float for coverage_pct (I-01)
- MUST NOT delete health_log or alert_log (I-24)
- MUST NOT push to Grafana without BT-008 resolved (NotImplementedError)

## Ports (Protocol DI)
- `HealthCheckPort` → `InMemoryHealthCheckPort` (stub)
- `ComplianceCheckPort` → `InMemoryComplianceCheckPort` (stub)

## Audit
- `HealthAggregator.health_log` — append-only (I-24)
- `ObservabilityAgent.alert_log` — append-only (I-24)

## BT Stubs
- BT-008: `MetricsCollector.push_to_grafana()` → raises NotImplementedError
