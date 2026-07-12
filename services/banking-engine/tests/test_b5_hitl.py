"""
Banking Engine Sprint B-5 — HITL + Compliance Layer Tests

Coverage:
  (a) SAR proposal is PENDING; never auto-applied (I-27).
  (b) L2 agent cannot self-approve an L3+ action (autonomy enforcement).
  (c) Expired gate resolves to EXPIRED, never APPROVED.
  (d) Every state transition emits one audit record (I-24).

Sandbox only. No network. No real PII/IBAN/thresholds.
Run: pytest services/banking-engine/tests/test_b5_hitl.py -v
"""

from collections.abc import Generator
from datetime import UTC, datetime, timedelta
import json
from pathlib import Path

from audit.audit_trail import write_audit_record
from hitl.autonomy import AutonomyLevel, check_autonomy
from hitl.gates import (
    GATE_TIMEOUTS,
    GateStatus,
    HITLGateType,
    approve,
    propose,
    reject,
    set_audit_fn,
)
import pytest

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def audited_path(tmp_path: Path) -> Generator[Path, None, None]:
    """
    Sets up a temporary audit JSONL file and wires it into the gate module.
    Resets the audit hook after each test to avoid cross-test pollution.
    """
    audit_path = tmp_path / "hitl-audit.jsonl"
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


def _read_records(path: Path) -> list[dict]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


# ---------------------------------------------------------------------------
# (a) SAR proposal is PENDING — never auto-applied
# ---------------------------------------------------------------------------


def test_sar_proposal_status_is_pending() -> None:
    """I-27: propose() must return PENDING — no auto-approve path exists."""
    proposal = propose(
        gate_type=HITLGateType.SAR_FILING,
        proposing_agent="sar-agent-sandbox",
        payload={"reason": "sandbox-test-only", "customer_ref": "SANDBOX"},
    )
    assert proposal.status == GateStatus.PENDING


def test_sar_proposal_is_not_approved() -> None:
    """Confirm the status is explicitly NOT APPROVED immediately after creation."""
    proposal = propose(HITLGateType.SAR_FILING, "sar-agent", {})
    assert proposal.status != GateStatus.APPROVED


def test_pep_proposal_is_pending() -> None:
    """PEP_onboarding gate also starts PENDING."""
    proposal = propose(HITLGateType.PEP_ONBOARDING, "pep-agent", {})
    assert proposal.status == GateStatus.PENDING
    assert proposal.resolved_by is None
    assert proposal.resolved_at is None


def test_proposal_has_gate_id() -> None:
    """Each proposal gets a unique gate_id."""
    p1 = propose(HITLGateType.SAR_FILING, "agent", {})
    p2 = propose(HITLGateType.SAR_FILING, "agent", {})
    assert p1.gate_id != p2.gate_id


def test_proposal_expires_at_set_from_gate_type() -> None:
    """expires_at is computed from GATE_TIMEOUTS for the given gate type."""
    before = datetime.now(UTC)
    proposal = propose(HITLGateType.SANCTIONS_REVERSAL, "agent", {})
    after = datetime.now(UTC)

    expected_timeout = GATE_TIMEOUTS[HITLGateType.SANCTIONS_REVERSAL]
    assert before + expected_timeout <= proposal.expires_at <= after + expected_timeout


# ---------------------------------------------------------------------------
# (b) L2 agent cannot self-approve an L3 action (autonomy enforcement)
# ---------------------------------------------------------------------------


def test_l2_cannot_self_approve_l3_action() -> None:
    """L2 agent acting on an L3-required action must get REQUIRE_HITL."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L2,
        action_required_level=AutonomyLevel.L3,
    )
    assert outcome == "REQUIRE_HITL"


def test_l1_cannot_act_on_l4_action() -> None:
    """L1 (fully auto) agent cannot perform a human-only (L4) action."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L1,
        action_required_level=AutonomyLevel.L4,
    )
    assert outcome == "REQUIRE_HITL"


def test_l2_cannot_act_on_l4_action() -> None:
    """L2 agent also blocked from L4 action."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L2,
        action_required_level=AutonomyLevel.L4,
    )
    assert outcome == "REQUIRE_HITL"


def test_l3_cannot_act_on_l4_action() -> None:
    """Even L3 cannot bypass L4 (human-only) gate."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L3,
        action_required_level=AutonomyLevel.L4,
    )
    assert outcome == "REQUIRE_HITL"


def test_l4_can_act_on_l4_action() -> None:
    """Authorised human (L4) may act on an L4 action."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L4,
        action_required_level=AutonomyLevel.L4,
    )
    assert outcome == "ALLOW"


def test_l3_can_act_on_l2_action() -> None:
    """Higher autonomy level can perform lower-level actions."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L3,
        action_required_level=AutonomyLevel.L2,
    )
    assert outcome == "ALLOW"


def test_l1_can_act_on_l1_action() -> None:
    """Equal-level match → ALLOW."""
    outcome = check_autonomy(
        agent_level=AutonomyLevel.L1,
        action_required_level=AutonomyLevel.L1,
    )
    assert outcome == "ALLOW"


# ---------------------------------------------------------------------------
# (c) Expired gate → EXPIRED, never APPROVED
# ---------------------------------------------------------------------------


def test_expired_gate_cannot_be_approved() -> None:
    """Calling approve() on a timed-out proposal yields EXPIRED, not APPROVED."""
    proposal = propose(HITLGateType.SANCTIONS_REVERSAL, "sanctions-agent", {})
    # Force expiry by backdating the expires_at
    proposal.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    result = approve(proposal, approver="sanctions-reviewer-sandbox")

    assert result.status == GateStatus.EXPIRED
    assert result.status != GateStatus.APPROVED


def test_refresh_status_transitions_to_expired() -> None:
    """refresh_status() on an elapsed proposal flips PENDING → EXPIRED."""
    proposal = propose(HITLGateType.AML_THRESHOLD_CHANGE, "aml-agent", {})
    proposal.expires_at = datetime.now(UTC) - timedelta(seconds=1)

    status = proposal.refresh_status()

    assert status == GateStatus.EXPIRED


def test_approved_gate_stays_approved_after_backdating() -> None:
    """An already-approved proposal is NOT re-expired by refresh_status()."""
    proposal = propose(HITLGateType.PEP_ONBOARDING, "pep-agent", {})
    approve(proposal, approver="mlro-sandbox")
    assert proposal.status == GateStatus.APPROVED

    proposal.expires_at = datetime.now(UTC) - timedelta(days=1)
    proposal.refresh_status()

    assert proposal.status == GateStatus.APPROVED


def test_fresh_proposal_is_not_expired() -> None:
    """Freshly created proposal has a future expires_at."""
    proposal = propose(HITLGateType.SAR_FILING, "sar-agent", {})
    assert not proposal.is_expired()


def test_rejected_gate_is_not_re_opened() -> None:
    """Rejected gate stays REJECTED even if refresh_status() is called."""
    proposal = propose(HITLGateType.SAR_FILING, "sar-agent", {})
    reject(proposal, approver="mlro-sandbox")
    assert proposal.status == GateStatus.REJECTED
    proposal.refresh_status()
    assert proposal.status == GateStatus.REJECTED


# ---------------------------------------------------------------------------
# (d) Every state transition writes an audit record (I-24)
# ---------------------------------------------------------------------------


def test_propose_writes_audit_record(audited_path: Path) -> None:
    """propose() emits NONE → PENDING audit record."""
    propose(HITLGateType.SAR_FILING, "sar-agent", {"test": True})

    records = _read_records(audited_path)
    assert len(records) == 1
    assert records[0]["to_state"] == "PENDING"
    assert records[0]["from_state"] == "NONE"
    assert records[0]["entity_type"] == "hitl_gate"
    assert records[0]["actor"] == "sar-agent"


def test_approve_writes_audit_record(audited_path: Path) -> None:
    """approve() emits PENDING → APPROVED audit record."""
    proposal = propose(HITLGateType.PEP_ONBOARDING, "pep-agent", {})
    # Clear propose record to isolate approve's record
    audited_path.write_text("", encoding="utf-8")

    approve(proposal, approver="mlro-sandbox")

    records = _read_records(audited_path)
    assert any(r["to_state"] == "APPROVED" for r in records)
    assert any(r["from_state"] == "PENDING" for r in records)
    assert any(r["actor"] == "mlro-sandbox" for r in records)


def test_reject_writes_audit_record(audited_path: Path) -> None:
    """reject() emits PENDING → REJECTED audit record."""
    proposal = propose(HITLGateType.AML_THRESHOLD_CHANGE, "aml-agent", {})
    audited_path.write_text("", encoding="utf-8")

    reject(proposal, approver="ceo-sandbox")

    records = _read_records(audited_path)
    assert any(r["to_state"] == "REJECTED" for r in records)
    assert any(r["actor"] == "ceo-sandbox" for r in records)


def test_expiry_writes_audit_record(audited_path: Path) -> None:
    """refresh_status() on elapsed gate emits PENDING → EXPIRED audit record."""
    proposal = propose(HITLGateType.SANCTIONS_REVERSAL, "sanctions-agent", {})
    audited_path.write_text("", encoding="utf-8")  # clear propose record

    proposal.expires_at = datetime.now(UTC) - timedelta(seconds=1)
    proposal.refresh_status()

    records = _read_records(audited_path)
    assert any(r["to_state"] == "EXPIRED" for r in records)
    assert any(r["actor"] == "system:timeout" for r in records)


def test_audit_record_has_required_fields(audited_path: Path) -> None:
    """Each audit record contains all mandatory I-24 fields."""
    propose(HITLGateType.SAR_FILING, "sar-agent", {})

    records = _read_records(audited_path)
    r = records[0]
    assert "event_id" in r
    assert "timestamp" in r
    assert "entity_type" in r
    assert "entity_id" in r
    assert "from_state" in r
    assert "to_state" in r
    assert "actor" in r
    assert "metadata" in r


def test_audit_records_append_not_overwrite(audited_path: Path) -> None:
    """Multiple transitions append to the JSONL file; nothing is overwritten."""
    proposal = propose(HITLGateType.PEP_ONBOARDING, "pep-agent", {})
    approve(proposal, approver="mlro-sandbox")

    records = _read_records(audited_path)
    # At minimum: NONE→PENDING (propose) + PENDING→APPROVED (approve)
    assert len(records) >= 2
    states = [r["to_state"] for r in records]
    assert "PENDING" in states
    assert "APPROVED" in states
