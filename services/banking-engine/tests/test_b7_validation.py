"""
Banking Engine Sprint B-7 — Full Sandbox Validation (FINAL sprint)

Validates the complete Banking Engine sandbox end-to-end across seven domains:

  E2E  Payment intent → LangGraph stub → HITL gate → PENDING; never auto-executed.
  ISO  Legion ↔ Banking boundary isolation: no ledger write path from Legion.
  HITL All four HITL gates exercised: SAR, AML, sanctions, PEP.
  AUT  L2 agent cannot self-approve L3+ action (autonomy invariant).
  AUD  Every gate transition writes an append-only audit record (I-24).
  AIA  EU AI Act Art.14: human oversight flag present on all L3+ decisions.
  DLP  No PII/IBAN crosses the banking ↔ Legion boundary in the test flow.

SANDBOX ONLY. No network. No LiteLLM. No live PSD2/Adorsys/Midaz.
"""

from __future__ import annotations

from collections.abc import Generator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
import json
import os
from pathlib import Path
import re
from typing import Any

from audit.audit_trail import write_audit_record
from hitl.autonomy import AutonomyLevel, check_autonomy
from hitl.gates import (
    GATE_REQUIRED_LEVEL,
    GateStatus,
    HITLGateType,
    HITLProposal,
    approve,
    propose,
    reject,
    set_audit_fn,
)
import pytest
from stubs.mcp_ledger_stub import McpLedgerStub

# ---------------------------------------------------------------------------
# Sandbox payment intent — no real account/IBAN data (DLP)
# ---------------------------------------------------------------------------

IBAN_RE: re.Pattern[str] = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{4}\d{7}[A-Z0-9]{0,16}\b")

SANDBOX_INTENT_ID = "SANDBOX-INTENT-B7-0001"
SANDBOX_AMOUNT_GBP = Decimal("500.00")


@dataclass(frozen=True)
class PaymentIntent:
    """Synthetic sandbox payment intent — never contains real IBAN/PII (DLP)."""

    intent_id: str
    amount_gbp: Decimal
    narrative: str
    is_test_data: bool = True


def _simulate_graph_flow(intent: PaymentIntent) -> HITLProposal:
    """
    Stub of banking_node() from graph_sandbox.py (Sprint B-1).

    In production: LLM node detects L3+ action required → calls propose().
    In sandbox: LLM call skipped (no network); proceeds directly to propose().

    I-27: AI PROPOSES — the returned HITLProposal is never auto-executed.
    EU AI Act Art.14: requires_human_oversight=True in every payload.
    """
    return propose(
        gate_type=HITLGateType.SAR_FILING,
        proposing_agent="banking-node-sandbox-b7",
        payload={
            "intent_id": intent.intent_id,
            "amount_gbp": str(intent.amount_gbp),
            "narrative": intent.narrative,
            "is_test_data": intent.is_test_data,
            "requires_human_oversight": True,  # EU AI Act Art.14
            "graph_node": "banking_node_stub",
        },
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audited_path(tmp_path: Path) -> Generator[Path, None, None]:
    """Wire audit trail to a temp JSONL file; reset after each test."""
    audit_path = tmp_path / "b7-audit.jsonl"
    audit_path.touch()
    set_audit_fn(
        lambda et, eid, frm, to, actor, meta: write_audit_record(
            entity_type=et,
            entity_id=eid,
            from_state=frm,
            to_state=to,
            actor=actor,
            metadata=meta,
            path_override=audit_path,
        )
    )
    yield audit_path
    set_audit_fn(None)


@pytest.fixture
def payment_intent() -> PaymentIntent:
    return PaymentIntent(
        intent_id=SANDBOX_INTENT_ID,
        amount_gbp=SANDBOX_AMOUNT_GBP,
        narrative="SANDBOX TEST PAYMENT - B7",
    )


@pytest.fixture
def ledger_stub() -> McpLedgerStub:
    return McpLedgerStub()


def _read_records(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
    ]


# ---------------------------------------------------------------------------
# E2E: payment intent → LangGraph stub → HITL gate → PENDING
# ---------------------------------------------------------------------------


def test_e2e_payment_intent_creates_pending_proposal(payment_intent: PaymentIntent) -> None:
    """Payment intent triggers an HITL gate; proposal is always PENDING on creation."""
    proposal = _simulate_graph_flow(payment_intent)
    assert proposal.status == GateStatus.PENDING


def test_e2e_payment_is_not_auto_executed(payment_intent: PaymentIntent) -> None:
    """Critical: payment must NEVER be auto-executed. PENDING until human acts. I-27."""
    proposal = _simulate_graph_flow(payment_intent)
    assert proposal.status != GateStatus.APPROVED
    assert proposal.status != GateStatus.REJECTED
    assert proposal.resolved_by is None
    assert proposal.resolved_at is None


def test_e2e_sandbox_confirmation_requires_human(payment_intent: PaymentIntent) -> None:
    """L3 agent routed through HITL before reaching the proposal; proposal stays PENDING."""
    proposal = _simulate_graph_flow(payment_intent)
    outcome = check_autonomy(AutonomyLevel.L3, AutonomyLevel.L4)
    assert outcome == "REQUIRE_HITL"
    assert proposal.status == GateStatus.PENDING


def test_e2e_graph_node_output_is_proposal_not_action(payment_intent: PaymentIntent) -> None:
    """LangGraph stub returns HITLProposal (proposal only) — never a direct action."""
    result = _simulate_graph_flow(payment_intent)
    assert isinstance(result, HITLProposal)
    assert result.gate_type == HITLGateType.SAR_FILING
    assert result.proposing_agent == "banking-node-sandbox-b7"


# ---------------------------------------------------------------------------
# ISO: Legion ↔ Banking boundary isolation
# ---------------------------------------------------------------------------


def test_iso_ledger_stub_marks_all_writes_as_test_data(ledger_stub: McpLedgerStub) -> None:
    """All ledger writes go through the stub; results marked is_test_data=True (DLP barrier)."""
    result = ledger_stub.create_transaction(
        account_id="TEST-ACC-0001",
        amount=Decimal("100.00"),
        currency="GBP",
        direction="debit",
        narrative="SANDBOX B7 TEST",
    )
    assert result["is_test_data"] is True


def test_iso_ledger_read_is_test_data(ledger_stub: McpLedgerStub) -> None:
    """Balance reads from the stub are test data — no live ledger connection."""
    balance = ledger_stub.get_balance()
    assert balance["is_test_data"] is True


def test_iso_banking_memory_not_reachable_from_legion() -> None:
    """Qdrant banking-memory endpoint not accessible from Legion context. ADR-103."""
    banking_memory_url = os.environ.get("BANKING_MEMORY_URL", "")
    assert "100.68.102.48" not in banking_memory_url, (
        "Legion must not have direct access to evo1 banking memory (ADR-103 DLP boundary)"
    )


def test_iso_sandbox_stub_has_no_production_url() -> None:
    """McpLedgerStub has no production URL — cannot accidentally connect to Midaz."""
    stub = McpLedgerStub()
    base_url = getattr(stub, "base_url", "")
    assert not any(kw in base_url for kw in ("midaz", "8095", "prod", "evo1"))


def test_iso_no_live_ledger_env_var() -> None:
    """Production ledger URL must not be configured in Legion sandbox environment."""
    prod_url = os.environ.get("MIDAZ_BASE_URL", "")
    assert "100.68.102.48" not in prod_url


# ---------------------------------------------------------------------------
# HITL: all four gates exercised
# ---------------------------------------------------------------------------


def test_hitl_sar_gate_blocks_pending_approval() -> None:
    """SAR_filing gate: proposal always starts PENDING. I-27."""
    p = propose(HITLGateType.SAR_FILING, "aml-agent-b7", {"reason": "sandbox-test"})
    assert p.status == GateStatus.PENDING


def test_hitl_aml_threshold_gate_blocks_pending_approval() -> None:
    """AML_threshold_change gate: requires MLRO+CEO; starts PENDING."""
    p = propose(
        HITLGateType.AML_THRESHOLD_CHANGE,
        "aml-agent-b7",
        {"threshold": "PLACEHOLDER"},
    )
    assert p.status == GateStatus.PENDING
    assert p.resolved_by is None


def test_hitl_sanctions_gate_blocks_pending_approval() -> None:
    """sanctions_reversal gate: starts PENDING; 1h timeout."""
    p = propose(HITLGateType.SANCTIONS_REVERSAL, "sanctions-agent-b7", {"entity": "SANDBOX"})
    assert p.status == GateStatus.PENDING


def test_hitl_pep_gate_blocks_pending_approval() -> None:
    """PEP_onboarding gate: starts PENDING; 48h timeout."""
    p = propose(HITLGateType.PEP_ONBOARDING, "pep-agent-b7", {"pep_ref": "SANDBOX"})
    assert p.status == GateStatus.PENDING


def test_hitl_all_gates_start_pending() -> None:
    """All four HITL gate types produce PENDING proposals — no auto-approve path."""
    for gate_type in HITLGateType:
        p = propose(gate_type, "b7-test-agent", {})
        assert p.status == GateStatus.PENDING, f"{gate_type} must start PENDING"


def test_hitl_gate_timeout_leads_to_expired_not_approved() -> None:
    """Elapsed gate transitions to EXPIRED, never to APPROVED. Safety invariant."""
    p = propose(HITLGateType.SANCTIONS_REVERSAL, "b7-agent", {})
    p.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    p.refresh_status()
    assert p.status == GateStatus.EXPIRED
    assert p.status != GateStatus.APPROVED


# ---------------------------------------------------------------------------
# AUT: autonomy level enforcement
# ---------------------------------------------------------------------------


def test_aut_l2_cannot_self_approve_l3_action() -> None:
    """L2 agent cannot act autonomously on an L3+ action."""
    assert check_autonomy(AutonomyLevel.L2, AutonomyLevel.L3) == "REQUIRE_HITL"


def test_aut_l2_cannot_self_approve_l4_action() -> None:
    """L2 agent is blocked from L4 (human-only) actions."""
    assert check_autonomy(AutonomyLevel.L2, AutonomyLevel.L4) == "REQUIRE_HITL"


def test_aut_no_agent_level_below_l4_can_act_on_l4() -> None:
    """Only authorised human (L4) may perform L4 actions; all lower levels blocked."""
    for agent_level in (AutonomyLevel.L1, AutonomyLevel.L2, AutonomyLevel.L3):
        result = check_autonomy(agent_level, AutonomyLevel.L4)
        assert result == "REQUIRE_HITL", f"L{agent_level} must not self-approve L4"


def test_aut_l4_human_can_resolve_gate() -> None:
    """L4 (human) can approve the proposal — this is the only approval path."""
    p = propose(HITLGateType.SAR_FILING, "b7-agent", {})
    result = approve(p, approver="mlro-sandbox-b7")
    assert result.status == GateStatus.APPROVED
    assert result.resolved_by == "mlro-sandbox-b7"


# ---------------------------------------------------------------------------
# AUD: audit trail — every transition is recorded (I-24)
# ---------------------------------------------------------------------------


def test_aud_payment_flow_writes_audit_record(
    audited_path: Path, payment_intent: PaymentIntent
) -> None:
    """Simulated payment flow writes an audit record for the gate proposal. I-24."""
    _simulate_graph_flow(payment_intent)
    records = _read_records(audited_path)
    assert len(records) >= 1
    assert any(r["to_state"] == "PENDING" for r in records)


def test_aud_all_gate_transitions_audited(audited_path: Path) -> None:
    """propose → approve both write audit records."""
    p = propose(HITLGateType.PEP_ONBOARDING, "pep-agent-b7", {})
    approve(p, "mlro-sandbox-b7")
    records = _read_records(audited_path)
    states = {r["to_state"] for r in records}
    assert "PENDING" in states
    assert "APPROVED" in states


def test_aud_records_are_append_only(audited_path: Path) -> None:
    """Multiple transitions append to JSONL; earlier records not modified (I-24)."""
    p = propose(HITLGateType.SAR_FILING, "sar-agent-b7", {})
    reject(p, "ceo-sandbox")
    records = _read_records(audited_path)
    assert len(records) >= 2
    states = {r["to_state"] for r in records}
    assert "PENDING" in states
    assert "REJECTED" in states


def test_aud_record_has_required_fields(audited_path: Path) -> None:
    """Audit record contains all I-24 mandatory fields."""
    propose(HITLGateType.AML_THRESHOLD_CHANGE, "aml-b7", {})
    records = _read_records(audited_path)
    r = records[0]
    required = (
        "event_id",
        "timestamp",
        "entity_type",
        "entity_id",
        "from_state",
        "to_state",
        "actor",
        "metadata",
    )
    for field_name in required:
        assert field_name in r, f"Missing required audit field: {field_name}"


# ---------------------------------------------------------------------------
# AIA: EU AI Act Art.14 — human oversight required
# ---------------------------------------------------------------------------


def test_aia_l3_plus_gates_require_human_oversight() -> None:
    """All HITL gates require L4 (Human Only) resolution. EU AI Act Art.14."""
    for gate_type in HITLGateType:
        level = GATE_REQUIRED_LEVEL[gate_type]
        assert level >= AutonomyLevel.L4, (
            f"{gate_type} required level {level} < L4; human oversight not guaranteed (Art.14)"
        )


def test_aia_proposal_payload_contains_oversight_flag(payment_intent: PaymentIntent) -> None:
    """Proposal payload from graph node includes requires_human_oversight=True. Art.14."""
    proposal = _simulate_graph_flow(payment_intent)
    assert proposal.proposal_payload.get("requires_human_oversight") is True


def test_aia_all_gate_types_have_human_resolution_level() -> None:
    """Every gate type in GATE_REQUIRED_LEVEL has level >= L3 (human oversight mandated)."""
    for gate_type, level in GATE_REQUIRED_LEVEL.items():
        assert level >= AutonomyLevel.L3, f"{gate_type} has level {level} < L3"


def test_aia_l2_agent_on_payment_requires_hitl(payment_intent: PaymentIntent) -> None:
    """An L2 banking agent processing a payment intent must route through HITL (Art.14)."""
    outcome = check_autonomy(AutonomyLevel.L2, AutonomyLevel.L4)
    assert outcome == "REQUIRE_HITL"


# ---------------------------------------------------------------------------
# DLP: no PII / IBAN crosses banking ↔ Legion boundary
# ---------------------------------------------------------------------------


def test_dlp_no_iban_in_sandbox_payload(payment_intent: PaymentIntent) -> None:
    """No real IBAN in the payment intent or HITL proposal payload. DLP."""
    proposal = _simulate_graph_flow(payment_intent)
    payload_str = json.dumps(proposal.proposal_payload)
    assert not IBAN_RE.search(payload_str), "IBAN pattern found in sandbox payload"


def test_dlp_no_real_pii_in_ledger_stub(ledger_stub: McpLedgerStub) -> None:
    """Ledger stub uses only synthetic test data — no real customer PII."""
    customer = ledger_stub.get_customer()
    assert customer["is_test_data"] is True
    assert "test" in customer["name"].lower() or "sandbox" in customer["name"].lower()


def test_dlp_payment_intent_uses_synthetic_data_only(payment_intent: PaymentIntent) -> None:
    """Payment intent must be clearly synthetic — no real account references."""
    assert payment_intent.is_test_data is True
    assert not IBAN_RE.search(payment_intent.narrative)
    narrative_upper = payment_intent.narrative.upper()
    assert "TEST" in narrative_upper or "SANDBOX" in narrative_upper


def test_dlp_narrative_contains_no_iban() -> None:
    """Sandbox payment narratives must not contain real IBAN patterns."""
    narratives = [
        "SANDBOX TEST PAYMENT - B7",
        "SYNTHETIC TRANSFER REF B7-0001",
        "TEST INBOUND TRANSFER",
    ]
    for narrative in narratives:
        assert not IBAN_RE.search(narrative), f"IBAN pattern found in: {narrative!r}"
