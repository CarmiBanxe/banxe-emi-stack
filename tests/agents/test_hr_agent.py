"""Tests for the ORG §2.9 / FCA SM&CR HR mask agent (services/agents/hr_agent.py).

Covers every mask path in the §D2 gate-chain order: routine AUTO ops (training read,
conduct attestation), the routine below-AUTO re-check halt, the SMF-CEO-gate invariant
(appoint-SMF @ confidence 1.0 with NO CEO token → HALT, forced step-up to CEO, appointment
never applied) and the appoint-with-CEO-token proceed path (incl. a REVIEW-band proceed
and a new-vs-change incumbent read), HALT_UNRESOLVED_PROCESS, REJECT_OUT_OF_SCOPE,
HALT_REVIEW_DEFERRED, BLOCK_LOW_CONFIDENCE (routine + SMF), HALT_COST_CAP_BREACH
(per-request + per-window), HALT_COMPLIANCE_BLOCK, HALT_PROVIDER_ERROR (emit + reraise),
invalid confidence → ValueError, R-SEC, and the one-lineage-record-per-action obligation
(ADR-046). The port, SM&CR handle, and recorder are fakes — the agent is exercised as pure
governance logic with no live infra.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

import pytest

from services.agents.hr_agent import (
    AgentDecisionRecord,
    AppointSMFIntent,
    AttestConductIntent,
    BudgetBreach,
    CheckTrainingIntent,
    ComplianceResult,
    ConductRuleTier,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    HRAgent,
    HRMask,
    ProcessRef,
    RequestCost,
)
from services.hr.hr_port import (
    HRSourceUnavailable,
    InMemoryHRPort,
    InMemorySMCRReadHandle,
)

# ── Fakes / builders ───────────────────────────────────────────────────────────


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


@dataclass
class _SM:
    """A structural stand-in for a registered senior manager (has ``person_id``)."""

    person_id: str


def make_mask(**overrides) -> HRMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=10_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=100_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return HRMask(**base)


def make_agent(
    *,
    mask: HRMask | None = None,
    port: InMemoryHRPort | None = None,
    smcr: InMemorySMCRReadHandle | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[HRAgent, InMemoryHRPort, InMemorySMCRReadHandle, FakeRecorder]:
    port = port or InMemoryHRPort()
    smcr = smcr or InMemorySMCRReadHandle()
    recorder = recorder or FakeRecorder()
    agent = HRAgent(
        port=port,
        smcr_handle=smcr,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, smcr, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-HR", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_training_intent(*, confidence: float = 0.99) -> CheckTrainingIntent:
    return CheckTrainingIntent(
        intent_text="Check AML training for EMP-1",
        process_ref=_ref(),
        employee_id="EMP-1",
        course_id="AML-101",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.01")),
    )


def make_conduct_intent(*, confidence: float = 0.99) -> AttestConductIntent:
    return AttestConductIntent(
        intent_text="Record conduct attestation for EMP-1",
        process_ref=_ref(),
        employee_id="EMP-1",
        tier=ConductRuleTier.TIER_1,
        attested=True,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.01")),
    )


def make_appoint_intent(
    *,
    confidence: float = 0.99,
    ceo_token: str | None = None,
    cost: RequestCost | None = None,
    resolved: bool = True,
    role: str = "SMF1",
    candidate: str = "CAND-1",
) -> AppointSMFIntent:
    return AppointSMFIntent(
        intent_text=f"Appoint {candidate} to {role}",
        process_ref=_ref(resolved),
        role=role,
        candidate=candidate,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=400, cost=Decimal("0.04")),
        ceo_token=ceo_token,
    )


# ── Routine AUTO ops (training read / conduct attestation) ─────────────────────


async def test_check_training_auto_executes():
    agent, port, _, recorder = make_agent()
    port.add_training("EMP-1", "AML-101", completed=True)
    outcome = await agent.check_training(make_training_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.result is not None
    assert port.get_training_status_calls == [("EMP-1", "AML-101")]
    assert recorder.records[0].action_taken == "CHECK_TRAINING"
    assert len(recorder.records) == 1


async def test_attest_conduct_auto_executes():
    agent, port, _, recorder = make_agent()
    outcome = await agent.attest_conduct(make_conduct_intent(confidence=0.95))

    assert outcome.executed is True
    assert outcome.requires_step_up is False
    assert port.conduct_attestation_calls == [("EMP-1", ConductRuleTier.TIER_1, True)]
    assert recorder.records[0].action_taken == "ATTEST_CONDUCT"
    assert recorder.records[0].triggering_event == "attest_conduct:EMP-1:TIER_1"


async def test_routine_below_auto_band_halts_for_recheck():
    agent, port, _, recorder = make_agent()
    outcome = await agent.check_training(make_training_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.get_training_status_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_routine_low_confidence_blocks_without_escalation():
    agent, _, _, recorder = make_agent()
    outcome = await agent.check_training(make_training_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.escalated_to is None
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ── SMF-CEO-gate invariant (FCA SM&CR) ─────────────────────────────────────────


async def test_appoint_smf_full_confidence_no_token_halts_and_escalates():
    """The marquee invariant: an SMF appointment at confidence 1.0 with NO CEO token can
    NEVER be autonomous — it forces a CEO step-up and never applies the appointment
    (``apply_smf_appointment`` is never called)."""
    agent, port, _, recorder = make_agent()

    outcome = await agent.appoint_smf(make_appoint_intent(confidence=1.0, ceo_token=None))

    assert outcome.executed is False  # appointment NEVER applied
    assert outcome.requires_step_up is True
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "CEO"
    assert outcome.halt_reason == "smf_ceo_step_up_required"
    assert recorder.records[0].action_taken == "HALT_SMF_CEO_STEP_UP_REQUIRED"
    assert recorder.records[0].escalated_to == "CEO"
    assert "SMCR-SMF-CEO-step-up" in recorder.records[0].policies_evaluated
    # apply never called — no SMF holder appointed.
    assert port.apply_calls == []
    assert port.propose_calls == []
    # the CEO token is never recorded (R-SEC) — and there was none here anyway.
    assert recorder.records[0].human_reviewed_by is None


async def test_appoint_smf_with_ceo_token_proceeds_new_appointment():
    agent, port, smcr, recorder = make_agent()
    outcome = await agent.appoint_smf(
        make_appoint_intent(confidence=0.99, ceo_token="ceo-sig-abc")  # noqa: S106
    )

    assert outcome.executed is True
    assert outcome.result is not None
    # propose (prepare) then apply (commit) both ran, in order.
    assert port.propose_calls == [("SMF1", "CAND-1")]
    assert port.apply_calls == [("SMF-PROP-SMF1-CAND-1", "CAND-1")]
    # incumbent read through the read-only SM&CR handle (new appointment → no incumbent).
    assert smcr.get_senior_manager_calls == ["CAND-1"]
    assert recorder.records[0].triggering_event == "appoint_smf:SMF1:CAND-1:new"
    assert recorder.records[0].action_taken == "APPOINT_SMF"
    # CEO sign-off recorded as the opaque role — never the token value (R-SEC).
    assert recorder.records[0].human_reviewed_by == "CEO"


async def test_appoint_smf_change_reads_incumbent_via_handle():
    smcr = InMemorySMCRReadHandle(senior_managers={"CAND-1": _SM(person_id="CAND-1")})
    agent, _, _, recorder = make_agent(smcr=smcr)
    outcome = await agent.appoint_smf(
        make_appoint_intent(confidence=0.99, ceo_token="ceo-sig-abc")  # noqa: S106
    )
    assert outcome.executed is True
    assert recorder.records[0].triggering_event == "appoint_smf:SMF1:CAND-1:change"


async def test_appoint_smf_review_band_with_token_proceeds():
    # An SMF appointment in the REVIEW band still proceeds with a valid CEO token — the
    # SMF gate (not the routine read-deferred path) governs the SMF action.
    agent, port, _, _ = make_agent()
    outcome = await agent.appoint_smf(
        make_appoint_intent(confidence=0.80, ceo_token="ceo-sig-abc")  # noqa: S106
    )
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert port.apply_calls == [("SMF-PROP-SMF1-CAND-1", "CAND-1")]


async def test_appoint_smf_empty_token_treated_as_no_token():
    # An empty-string token is not a valid CEO authorization → HALT (defence-in-depth).
    agent, port, _, recorder = make_agent()
    outcome = await agent.appoint_smf(make_appoint_intent(confidence=1.0, ceo_token=""))
    assert outcome.executed is False
    assert recorder.records[0].action_taken == "HALT_SMF_CEO_STEP_UP_REQUIRED"
    assert port.apply_calls == []


async def test_appoint_smf_low_confidence_blocks_and_escalates():
    agent, _, _, recorder = make_agent()
    outcome = await agent.appoint_smf(make_appoint_intent(confidence=0.50, ceo_token=None))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "CEO"
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_smf_step_up_cannot_be_disabled_by_mask_config():
    # The CEO step-up is a regulatory floor — even a permissive mask cannot auto-appoint.
    agent, port, _, recorder = make_agent(mask=make_mask(auto_threshold=0.0, review_floor=0.0))
    outcome = await agent.appoint_smf(make_appoint_intent(confidence=1.0, ceo_token=None))
    assert outcome.executed is False
    assert recorder.records[0].action_taken == "HALT_SMF_CEO_STEP_UP_REQUIRED"
    assert port.apply_calls == []


# ── process resolution / scope ─────────────────────────────────────────────────


async def test_unresolved_process_ref_blocks():
    agent, _, _, recorder = make_agent()
    outcome = await agent.appoint_smf(make_appoint_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright.
    agent, port, _, recorder = make_agent(mask=make_mask(scope=("HRPort.get_training_status",)))
    outcome = await agent.appoint_smf(
        make_appoint_intent(confidence=0.99, ceo_token="ceo-sig-abc")  # noqa: S106
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"
    assert port.apply_calls == []


# ── Cost-cap breach ────────────────────────────────────────────────────────────


async def test_per_request_cost_cap_breach_blocks():
    agent, _, _, recorder = make_agent()
    intent = make_appoint_intent(
        confidence=1.0,
        ceo_token="ceo-sig-abc",  # noqa: S106
        cost=RequestCost(tokens=999_999, cost=Decimal("0.01")),
    )
    outcome = await agent.appoint_smf(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_cost_cap_breach_blocks():
    window = CostWindow(used_tokens=99_900, used_cost=Decimal("0.00"))
    agent, port, _, recorder = make_agent(cost_window=window)
    # the 400-token appoint pushes the window past its 100_000 cap → breach.
    outcome = await agent.appoint_smf(
        make_appoint_intent(confidence=1.0, ceo_token="ceo-sig-abc")  # noqa: S106
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"
    assert port.apply_calls == []


async def test_window_accumulates_on_successful_action():
    window = CostWindow()
    agent, port, _, _ = make_agent(cost_window=window)
    port.add_training("EMP-1", "AML-101", completed=True)
    await agent.check_training(make_training_intent(confidence=0.99))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.01")


# ── Compliance gate → CEO escalation ───────────────────────────────────────────


async def test_compliance_fail_blocks_and_escalates():
    agent, port, _, recorder = make_agent()
    outcome = await agent.appoint_smf(
        make_appoint_intent(confidence=0.99, ceo_token="ceo-sig-abc"),  # noqa: S106
        compliance_result=ComplianceResult.FAIL,
    )
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.escalated_to == "CEO"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert port.apply_calls == []  # compliance halt → appointment never applied


# ── Provider error (emit + reraise) ────────────────────────────────────────────


async def test_provider_error_records_then_raises():
    port = InMemoryHRPort()
    port.add_training("EMP-1", "AML-101", completed=True)
    port.set_unavailable(HRSourceUnavailable("hris down", correlation_id="corr-1"))
    agent, port, _, recorder = make_agent(port=port)

    with pytest.raises(HRSourceUnavailable):
        await agent.check_training(make_training_intent(confidence=0.99))

    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:HRSourceUnavailable"


# ── R-SEC + lineage obligation (ADR-046) ───────────────────────────────────────


async def test_rsec_lineage_carries_opaque_metadata_only():
    agent, _, _, recorder = make_agent()
    await agent.appoint_smf(
        make_appoint_intent(confidence=0.99, ceo_token="ceo-secret-xyz")  # noqa: S106
    )
    rec = recorder.records[0]
    # Only role / candidate ride on the record — never the CEO token, names, or salary.
    assert "SMF1" in rec.triggering_event
    assert "CAND-1" in rec.triggering_event
    assert "ceo-secret-xyz" not in rec.triggering_event
    assert "ceo-secret-xyz" not in rec.reasoning_summary
    assert rec.human_reviewed_by == "CEO"  # opaque role, not the token
    assert rec.agent_id == "hr_agent"


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, port, _, recorder = make_agent()
    port.add_training("EMP-1", "AML-101", completed=True)
    await agent.check_training(make_training_intent(confidence=0.99))
    await agent.check_training(make_training_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "hr_agent"
    assert rec.intent == "Check AML training for EMP-1"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 50
    assert rec.budget_window_ref == "hr_agent:default"


async def test_invalid_confidence_raises():
    agent, _, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.appoint_smf(make_appoint_intent(confidence=1.5))
