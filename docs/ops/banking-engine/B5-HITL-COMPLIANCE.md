# Banking Engine B-5 — HITL + Compliance Layer

**Sprint:** B-5  
**Status:** Complete (MLRO/CRO sign-off on BDSL thresholds pending — see GAP below)  
**Branch:** `agent/factory/bankingengine/b5-hitl-compliance`  
**Predecessor:** B-4 (Mobile UI, PR #298, commit 25a75b4)

---

## Scope

Sprint B-5 enforces the HITL (Human In The Loop) gate layer for the Banking Engine.  
All AI agents are restricted to PROPOSING actions; humans DECIDE.

Compliance references: I-27 (HITL), I-24 (audit trail), EU AI Act Art.14.

---

## Delivered Artifacts

| Artifact | Path |
|----------|------|
| Autonomy level enforcement | `services/banking-engine/hitl/autonomy.py` |
| HITL gate lifecycle | `services/banking-engine/hitl/gates.py` |
| NeMo Guardrails config (placeholder) | `services/banking-engine/compliance/guardrails_config.yaml` |
| Append-only audit trail stub | `services/banking-engine/audit/audit_trail.py` |
| Unit tests | `services/banking-engine/tests/test_b5_hitl.py` |
| B-4 ledger close | `ledger/entries/banking-engine-b4-close/` |
| B-5 ledger open | `ledger/entries/banking-engine-b5-open/` |

---

## Gate Matrix

| Gate Type | Timeout | Resolving Authority | BDSL Threshold |
|-----------|---------|---------------------|----------------|
| `SAR_filing` | 24 h | MLRO | PLACEHOLDER |
| `AML_threshold_change` | 4 h | MLRO + CEO | PLACEHOLDER |
| `sanctions_reversal` | 1 h | MLRO + CEO | PLACEHOLDER |
| `PEP_onboarding` | 48 h | MLRO | PLACEHOLDER |

**BDSL thresholds:** intentionally omitted — pending MLRO/CRO sign-off.  
**Timeout behaviour:** gates auto-expire (not auto-approve) when the window closes.

---

## Autonomy Level Matrix (L1–L4)

| Level | Name | Description | AI Action Permitted |
|-------|------|-------------|---------------------|
| L1 | Auto | Fully automated; no review | Yes — low-risk actions |
| L2 | Alert → Human | AI acts; human reviews | Yes — alerts sent |
| L3 | Auto + HITL | Automated up to the gate | Yes — blocked at gates |
| L4 | Human Only | No AI action | No — human must act |

All four gate types above require **L4** resolution.  
Any AI agent (L1–L3) proposing an L4 action receives `REQUIRE_HITL` from `check_autonomy()`.

---

## HITL Gate Lifecycle

```
propose() → PENDING
               │
               ├─ approve(approver) → APPROVED  (human decision)
               ├─ reject(approver)  → REJECTED  (human decision)
               └─ timeout           → EXPIRED   (system; no auto-approve)
```

- No path from PENDING → APPROVED without a named human `approver`.
- EXPIRED proposals cannot be approved retroactively.
- Every transition emits one audit record (I-24).

---

## EU AI Act Art.14 Note

All L3+ decisions route through an HITL gate before taking effect.  
The `check_autonomy()` function returns `REQUIRE_HITL` whenever:

    action_required_level > agent_level

This is the sole enforcement point. No bypass exists in the codebase.  
Reference: EU AI Act 2024/1689, Article 14 — Human Oversight.

---

## Audit Trail

- **Sandbox target:** `~/.banxe-sandbox/banking-engine-audit.jsonl` (JSONL append-only)
- **Production target:** pgAudit + ClickHouse (wire via `AuditPort` Protocol DI)
- Override path: `BANKING_ENGINE_AUDIT_PATH` environment variable
- I-24: Records are append-only. No UPDATE or DELETE path exists.

Each record:

```json
{
  "event_id": "<uuid4>",
  "timestamp": "<ISO-8601 UTC>",
  "entity_type": "hitl_gate",
  "entity_id": "<gate_id>",
  "from_state": "PENDING",
  "to_state": "APPROVED",
  "actor": "<human-identifier>",
  "metadata": {"gate_type": "SAR_filing"}
}
```

---

## Done Criteria

- [x] HITL gate lifecycle implemented (`gates.py`)
- [x] Autonomy level enforcement (`autonomy.py`)
- [x] Audit trail stub (`audit_trail.py`)
- [x] NeMo Guardrails placeholder (`guardrails_config.yaml`)
- [x] Tests: 23 test cases covering (a)–(d)
- [x] No auto-approve path in codebase
- [x] No real BDSL numeric thresholds in code
- [x] No real PII/IBAN in tests or config
- [ ] BDSL threshold values — **MLRO/CRO sign-off required** (GAP OI-7)
- [ ] NeMo Guardrails runtime integration — **GAP OI-7**
- [ ] ClickHouse / pgAudit adapter for audit trail (P1, post B-5)

---

## GAP: OI-7 — NeMo Guardrails Integration

**Status:** Open  
**Owner:** MLRO (threshold values) + CTIO (infra)  
**Blocker:** BDSL numeric threshold values require MLRO/CRO sign-off before encoding.

Required to close OI-7:
1. MLRO/CRO review and sign-off on BDSL threshold policy.
2. Replace PLACEHOLDER values in `guardrails_config.yaml`.
3. Install `nemo_guardrails` package in banking-engine container.
4. Wire NeMo output filter into LangGraph graph (B-1 wiring point).
5. End-to-end test with MLRO present.

---

## Running Tests

```bash
# From repo root (worktree)
pytest services/banking-engine/tests/test_b5_hitl.py -v

# Expected: 23 tests passing
```

No network required. No external services. Audit writes to `tmp_path` (pytest fixture).
