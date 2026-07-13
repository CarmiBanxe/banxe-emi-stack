# Banking Engine B-7 — Full Sandbox Validation Report

**Sprint:** B-7 (FINAL sprint)
**Date:** 2026-07-13
**Branch:** `agent/factory/bankingengine/b7-validation`
**Predecessor:** B-6 merged → main (f47cf35, PR #303)
**Status:** CLOSED ✅

---

## Purpose

Validate that the complete Banking Engine sandbox satisfies all seven compliance
domains before closing the Banking Engine sprint series:

| Domain | Code | Done criterion |
|--------|------|----------------|
| End-to-end flow | E2E | Payment intent → LangGraph stub → HITL gate → PENDING; never auto-executed |
| Boundary isolation | ISO | No write path from Legion into live banking ledger or banking memory (ADR-103) |
| HITL gates | HITL | All four gate types (SAR, AML, sanctions, PEP) produce PENDING proposals |
| Autonomy | AUT | L2 agent cannot self-approve L3+ actions (I-27) |
| Audit trail | AUD | Every gate transition writes an append-only audit record (I-24) |
| EU AI Act Art.14 | AIA | `requires_human_oversight=True` present in all L3+ decisions |
| Data loss prevention | DLP | No PII/IBAN crosses the banking ↔ Legion boundary |

---

## Validation Test Suite

**File:** `services/banking-engine/tests/test_b7_validation.py`

| # | Test name | Domain | Assertion |
|---|-----------|--------|-----------|
| 1 | `test_e2e_payment_intent_creates_pending_proposal` | E2E | proposal.status == PENDING |
| 2 | `test_e2e_payment_is_not_auto_executed` | E2E | resolved_by is None; no APPROVED/REJECTED on creation |
| 3 | `test_e2e_sandbox_confirmation_requires_human` | E2E | check_autonomy(L3, L4) == REQUIRE_HITL |
| 4 | `test_e2e_graph_node_output_is_proposal_not_action` | E2E | result is HITLProposal, not a direct action |
| 5 | `test_iso_ledger_stub_marks_all_writes_as_test_data` | ISO | create_transaction → is_test_data=True |
| 6 | `test_iso_ledger_read_is_test_data` | ISO | get_balance → is_test_data=True |
| 7 | `test_iso_banking_memory_not_reachable_from_legion` | ISO | BANKING_MEMORY_URL != evo1 IP (ADR-103) |
| 8 | `test_iso_sandbox_stub_has_no_production_url` | ISO | McpLedgerStub has no Midaz/8095/prod URL |
| 9 | `test_iso_no_live_ledger_env_var` | ISO | MIDAZ_BASE_URL != evo1 IP |
| 10 | `test_hitl_sar_gate_blocks_pending_approval` | HITL | SAR_FILING → PENDING |
| 11 | `test_hitl_aml_threshold_gate_blocks_pending_approval` | HITL | AML_THRESHOLD_CHANGE → PENDING |
| 12 | `test_hitl_sanctions_gate_blocks_pending_approval` | HITL | SANCTIONS_REVERSAL → PENDING |
| 13 | `test_hitl_pep_gate_blocks_pending_approval` | HITL | PEP_ONBOARDING → PENDING |
| 14 | `test_hitl_all_gates_start_pending` | HITL | All HITLGateType values → PENDING |
| 15 | `test_hitl_gate_timeout_leads_to_expired_not_approved` | HITL | Elapsed gate → EXPIRED, not APPROVED |
| 16 | `test_aut_l2_cannot_self_approve_l3_action` | AUT | check_autonomy(L2, L3) == REQUIRE_HITL |
| 17 | `test_aut_l2_cannot_self_approve_l4_action` | AUT | check_autonomy(L2, L4) == REQUIRE_HITL |
| 18 | `test_aut_no_agent_level_below_l4_can_act_on_l4` | AUT | L1/L2/L3 all → REQUIRE_HITL for L4 actions |
| 19 | `test_aut_l4_human_can_resolve_gate` | AUT | approve() by human → APPROVED |
| 20 | `test_aud_payment_flow_writes_audit_record` | AUD | propose() writes PENDING record to JSONL |
| 21 | `test_aud_all_gate_transitions_audited` | AUD | propose + approve → PENDING + APPROVED in trail |
| 22 | `test_aud_records_are_append_only` | AUD | propose + reject → both records present (no overwrite) |
| 23 | `test_aud_record_has_required_fields` | AUD | 8 mandatory I-24 fields present in each record |
| 24 | `test_aia_l3_plus_gates_require_human_oversight` | AIA | GATE_REQUIRED_LEVEL[*] >= L4 |
| 25 | `test_aia_proposal_payload_contains_oversight_flag` | AIA | payload["requires_human_oversight"] is True |
| 26 | `test_aia_all_gate_types_have_human_resolution_level` | AIA | all gate types >= L3 |
| 27 | `test_aia_l2_agent_on_payment_requires_hitl` | AIA | check_autonomy(L2, L4) == REQUIRE_HITL |
| 28 | `test_dlp_no_iban_in_sandbox_payload` | DLP | no IBAN regex match in proposal payload |
| 29 | `test_dlp_no_real_pii_in_ledger_stub` | DLP | customer.is_test_data=True; name contains "test/sandbox" |
| 30 | `test_dlp_payment_intent_uses_synthetic_data_only` | DLP | is_test_data=True; no IBAN in narrative |
| 31 | `test_dlp_narrative_contains_no_iban` | DLP | 3 test narratives → no IBAN pattern |

---

## Compliance Verification

| Invariant | Verified by |
|-----------|-------------|
| I-24 Append-only audit | tests 20–23 (AUD group) |
| I-27 AI PROPOSES, human DECIDES | tests 1–4 (E2E), tests 16–18 (AUT) |
| EU AI Act Art.14 | tests 24–27 (AIA group) |
| ADR-103 DLP boundary | tests 7–9 (ISO group) |
| Sandbox isolation | tests 5–9 (ISO group), tests 28–31 (DLP group) |

---

## Architecture References

| Component | Sprint | Module |
|-----------|--------|--------|
| LangGraph sandbox | B-1 | `services/banking-engine/graph_sandbox.py` |
| HITL gates | B-5 | `services/banking-engine/hitl/gates.py` |
| Autonomy enforcement | B-5 | `services/banking-engine/hitl/autonomy.py` |
| Audit trail (JSONL) | B-5 | `services/banking-engine/audit/audit_trail.py` |
| MCP ledger stub | B-2 | `services/banking-engine/stubs/mcp_ledger_stub.py` |
| Compliance memory | B-6 | `infra/docker/docker-compose.compliance-memory.yml` |

---

## Open Items

| ID | Description | Priority | Owner |
|----|-------------|----------|-------|
| OI-1 | HITL numeric thresholds remain PLACEHOLDER — awaiting MLRO/CRO sign-off | P0 | MLRO |
| OI-2 | Graphiti/Neo4j seed ingestion pipeline (no-op in sandbox) | P1 | CTO |
| OI-3 | Production egress logger (`egress_logger.py`) integration tests | P1 | Factory |
| OI-4 | SqliteSaver checkpoint durability test (`BANKSY_CHECKPOINT_URI` path) | P1 | Factory |
| OI-8 | LangGraph banking_node LiteLLM integration test (requires live `LITELLM_API_KEY`) | P2 | CTO |

---

## Result

All 31 sandbox validation tests pass. Banking Engine sprint series B-0 → B-7 **COMPLETE**.

SANDBOX ONLY — no live PSD2, no live Midaz, no real customer data. Operator executes
production deployment; factory prepares artefacts only (Central Terminal Rule, I-28).
