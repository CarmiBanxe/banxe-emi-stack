# runtime_gate — ADR-030 §9 RED activation gate (scaffold, PROPOSED)

Builds **only the missing §9 components** a RED agent must pass **before** it may go
ACTIVE. It **does not activate anything** — activation is a separate operator + MLRO
(SMF17) + CEO (SMF1) act (ADR-030 §8) performed only after `red_activation_check`
returns **all-pass** and the runtime is live.

## REUSE vs BUILD
- **REUSED (referenced, not rebuilt):** DecisionRecord emission + HITL fields
  (`human_reviewed_by` / `escalated_to`) — `banxe.decision_records`
  (`infra/clickhouse/migrations/006_create_decision_records.sql`,
  `services/agents/_lineage.py`, `services/agents/recorders.py`). **No new table, no
  duplicate recorder.**
- **BUILT here (minimal, tested, InMemory sandbox default):**
  1. **Kill switch** — `kill_switch.py`: `KillSwitchPort` + `InMemoryKillSwitch`;
     `assert_can_act()` is **fail-closed** (HALTED, *or* an unreachable backend, ⇒
     the decision path refuses). Temporal = Outcome-C stub.
  2. **Budget policy** — `config/runtime_gate/agent-budget-policy.yaml` + `budget.py`:
     per-agent `max_tokens_window` / `max_cost_window` (**Decimal**) / `window`.
     Over-budget ⇒ refuse; no config / no entry ⇒ **fail-closed**.
  3. **Metrics + alert** — `metrics.py`: `agent_halt_triggered` / `decision_refused`
     / `budget_exceeded` counters (Prometheus-style, InMemory sink). Alert rule:
     `agent_halt_triggered > 0` → PAGE. PagerDuty = Outcome-C stub.
  4. **Audit sampling** — `audit_sampling.py`: `AuditSamplerPort` + `InMemorySampler`
     (100% sandbox / configurable). Every RED decision path calls
     `sampler.trace(decision_ref)`. **R-SEC/ADR-021:** a decision-ref is an opaque id
     — no secrets/PII; unsafe refs are refused. Langfuse = Outcome-C stub.
  5. **Activation checklist** — `red_activation_check.py`: PASS/FAIL per component.

## Pre-activation checklist (ALL must pass)
```text
[ ] kill switch reachable            (assert_can_act wired; backend up)
[ ] DecisionRecord emitting          (REUSED banxe.decision_records; recorder_ready)
[ ] budget config present            (agent has an entry in agent-budget-policy.yaml)
[ ] metrics wired                    (halt/refuse/budget counters + alert rule)
[ ] audit sampling on                (rate > 0; refs PII/secret-free — R-SEC)
```
Run: `python -m pytest services/runtime_gate/tests -q`. Use `red_activation_check(...)`
in the pre-activation runbook; a FAIL blocks activation (fail-closed).

## Status
PROPOSED / scaffold. Production adapters stubbed (Outcome-C); InMemory sandbox default.
No agent capture is activated by this module.
