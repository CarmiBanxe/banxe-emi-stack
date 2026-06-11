from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents._lineage import (
    AgentDecisionRecord,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    ProcessRef,
    RequestCost,
)
from services.agents.chargeback_agent import (
    ChargebackAgent,
    ChargebackMask,
    GetChargebackStatusIntent,
    InitiateChargebackIntent,
    SubmitRepresentmentIntent,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeChargebackHandle:
    """In-memory chargeback handle stub for testing."""

    def __init__(self, raise_value_error: bool = False) -> None:
        self._raise = raise_value_error
        self.initiate_calls: list[dict] = []
        self.submit_calls: list[dict] = []
        self.status_calls: list[str] = []

    def initiate_chargeback(
        self,
        dispute_id: str,
        scheme: str,
        amount: Decimal,
        reason_code: str,
    ) -> dict[str, str]:
        if self._raise:
            raise ValueError("fake domain error: unknown scheme")
        self.initiate_calls.append({"dispute_id": dispute_id, "scheme": scheme})
        return {
            "chargeback_id": "CB-001",
            "dispute_id": dispute_id,
            "scheme": scheme,
            "amount": str(amount),
            "status": "INITIATED",
        }

    def submit_representment(
        self,
        chargeback_id: str,
        evidence_hashes: list[str],
    ) -> dict[str, object]:
        if self._raise:
            raise ValueError("fake domain error: not found")
        self.submit_calls.append({"chargeback_id": chargeback_id})
        return {
            "chargeback_id": chargeback_id,
            "status": "REPRESENTMENT_SUBMITTED",
            "evidence_count": len(evidence_hashes),
        }

    def get_chargeback_status(self, chargeback_id: str) -> dict[str, str]:
        if self._raise:
            raise ValueError("fake domain error: not found")
        self.status_calls.append(chargeback_id)
        return {"chargeback_id": chargeback_id, "status": "INITIATED"}


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------

_DEFAULT_CAP = CostCap(
    max_request_tokens=5000,
    max_request_cost=Decimal("5.00"),
    max_window_tokens=50000,
    max_window_cost=Decimal("50.00"),
)
_SMALL_COST = RequestCost(tokens=100, cost=Decimal("0.10"))
_PROC = ProcessRef(process_id="CB-P-001", version="v1.0")
_UNRESOLVED = ProcessRef(process_id="", version="")


def make_mask(**overrides: object) -> ChargebackMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return ChargebackMask(**base)  # type: ignore[arg-type]


def make_agent(
    *,
    mask: ChargebackMask | None = None,
    window: CostWindow | None = None,
    raise_value_error: bool = False,
) -> tuple[ChargebackAgent, FakeChargebackHandle, FakeRecorder]:
    handle = FakeChargebackHandle(raise_value_error=raise_value_error)
    rec = FakeRecorder()
    agent = ChargebackAgent(
        chargeback_handle=handle,
        recorder=rec,
        mask=mask or make_mask(),
        cost_window=window,
    )
    return agent, handle, rec


def initiate_intent(
    confidence: float = 0.95,
    dispute_id: str = "DSP-001",
    proc: ProcessRef = _PROC,
) -> InitiateChargebackIntent:
    return InitiateChargebackIntent(
        intent_text="initiate chargeback",
        process_ref=proc,
        dispute_id=dispute_id,
        scheme="VISA",
        amount=Decimal("250.00"),
        reason_code="4853",
        correlation_id="corr-001",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def submit_intent(
    confidence: float = 0.95,
    chargeback_id: str = "CB-001",
    proc: ProcessRef = _PROC,
) -> SubmitRepresentmentIntent:
    return SubmitRepresentmentIntent(
        intent_text="submit representment",
        process_ref=proc,
        chargeback_id=chargeback_id,
        evidence_hashes=("hash-abc", "hash-def"),
        correlation_id="corr-002",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def status_intent(
    confidence: float = 0.95,
    chargeback_id: str = "CB-001",
    proc: ProcessRef = _PROC,
) -> GetChargebackStatusIntent:
    return GetChargebackStatusIntent(
        intent_text="get chargeback status",
        process_ref=proc,
        chargeback_id=chargeback_id,
        correlation_id="corr-003",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


# ---------------------------------------------------------------------------
# L1 AUTO read — get_chargeback_status happy path
# ---------------------------------------------------------------------------


async def test_get_status_auto_proceeds_and_returns_result() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_chargeback_status(status_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, dict)
    assert outcome.result["status"] == "INITIATED"
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "GET_CHARGEBACK_STATUS"
    # R-SEC: result dict NOT in the lineage record
    assert not hasattr(rec.records[0], "result")
    assert handle.status_calls == ["CB-001"]


# ---------------------------------------------------------------------------
# L2 REVIEW happy path — initiate/submit WITH reviewer → domain called
# ---------------------------------------------------------------------------


async def test_initiate_with_reviewer_proceeds_domain_called() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.initiate_chargeback(
        initiate_intent(confidence=0.95), human_reviewed_by="coo@banxe.com"
    )
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.REVIEW  # force_review pushed AUTO→REVIEW
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "INITIATE_CHARGEBACK"
    assert rec.records[0].human_reviewed_by == "coo@banxe.com"
    assert len(handle.initiate_calls) == 1


async def test_submit_with_reviewer_proceeds_domain_called() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.submit_representment(
        submit_intent(confidence=0.95), human_reviewed_by="coo@banxe.com"
    )
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "SUBMIT_REPRESENTMENT"
    assert len(handle.submit_calls) == 1


# ---------------------------------------------------------------------------
# HOLD_FOR_REVIEW — L2 ops with no reviewer → domain NOT called, escalate→COO
# ---------------------------------------------------------------------------


async def test_initiate_no_reviewer_hold_for_review_domain_not_called() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.initiate_chargeback(initiate_intent(confidence=0.95))
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "COO"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "COO"
    assert handle.initiate_calls == []


async def test_submit_no_reviewer_hold_for_review_domain_not_called() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.submit_representment(submit_intent(confidence=0.95))
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "COO"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert handle.submit_calls == []


# ---------------------------------------------------------------------------
# HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_halt_unresolved_process_ref_initiate() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.initiate_chargeback(initiate_intent(proc=_UNRESOLVED))
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"
    assert handle.initiate_calls == []


# ---------------------------------------------------------------------------
# REJECT_OUT_OF_SCOPE
# ---------------------------------------------------------------------------


async def test_reject_out_of_scope_op() -> None:
    mask = make_mask(scope=("OTHER.op",))
    agent, handle, rec = make_agent(mask=mask)
    outcome = await agent.initiate_chargeback(initiate_intent())
    assert outcome.halt_reason == "out_of_scope"
    assert rec.records[0].action_taken == "REJECT_OUT_OF_SCOPE"
    assert handle.initiate_calls == []


# ---------------------------------------------------------------------------
# HALT_REVIEW_DEFERRED — status read below AUTO band → domain NOT called
# ---------------------------------------------------------------------------


async def test_status_review_band_halts_deferred_domain_not_called() -> None:
    agent, handle, rec = make_agent()
    # confidence=0.80 → REVIEW band, no force_review → HALT_REVIEW_DEFERRED
    outcome = await agent.get_chargeback_status(status_intent(confidence=0.80))
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_REVIEW_DEFERRED"
    assert handle.status_calls == []


# ---------------------------------------------------------------------------
# BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence_initiate() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.initiate_chargeback(initiate_intent(confidence=0.50))
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert handle.initiate_calls == []


async def test_block_low_confidence_status() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_chargeback_status(status_intent(confidence=0.60))
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# HALT_COST_CAP_BREACH (per-request tokens / per-request cost /
#                        per-window tokens / per-window cost)
# ---------------------------------------------------------------------------


async def test_halt_cost_cap_per_request_tokens() -> None:
    cap = CostCap(
        max_request_tokens=50,  # < _SMALL_COST.tokens=100
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.initiate_chargeback(initiate_intent(), human_reviewed_by="coo@banxe.com")
    assert outcome.halt_reason == "cost_cap_breach"
    assert rec.records[0].budget_breach_flag is BudgetBreach.BREACH


async def test_halt_cost_cap_per_request_cost() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("0.05"),  # < 0.10
        max_window_tokens=50000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.initiate_chargeback(initiate_intent(), human_reviewed_by="coo@banxe.com")
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_tokens() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=150,  # used_tokens=100 + request=100 = 200 > 150
        max_window_cost=Decimal("100.00"),
    )
    window = CostWindow(used_tokens=100)
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.initiate_chargeback(initiate_intent(), human_reviewed_by="coo@banxe.com")
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_cost() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50000,
        max_window_cost=Decimal("0.15"),  # used=0.10 + request=0.10 = 0.20 > 0.15
    )
    window = CostWindow(used_cost=Decimal("0.10"))
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.initiate_chargeback(initiate_intent(), human_reviewed_by="coo@banxe.com")
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# HALT_COMPLIANCE_BLOCK — non-PASS → escalate to COO
# ---------------------------------------------------------------------------


async def test_halt_compliance_fail_escalates_to_coo() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.initiate_chargeback(
        initiate_intent(),
        human_reviewed_by="coo@banxe.com",
        compliance_result=ComplianceResult.FAIL,
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "COO"
    assert rec.records[0].escalated_to == "COO"
    assert rec.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert handle.initiate_calls == []


async def test_halt_compliance_escalate_also_blocks() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_chargeback_status(
        status_intent(), compliance_result=ComplianceResult.ESCALATE
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "COO"


# ---------------------------------------------------------------------------
# HALT_PROVIDER_ERROR — handle raises ValueError → emit executed=False + re-raise
# ---------------------------------------------------------------------------


async def test_provider_error_initiate_emits_record_then_reraises() -> None:
    agent, _, rec = make_agent(raise_value_error=True)
    with pytest.raises(ValueError, match="fake domain error"):
        await agent.initiate_chargeback(initiate_intent(), human_reviewed_by="coo@banxe.com")
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")
    assert rec.records[0].action_taken == "HALT_PROVIDER_ERROR:ValueError"


async def test_provider_error_status_emits_record_then_reraises() -> None:
    agent, _, rec = make_agent(raise_value_error=True)
    with pytest.raises(ValueError):
        await agent.get_chargeback_status(status_intent(confidence=0.95))
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


# ---------------------------------------------------------------------------
# ValueError on confidence out of [0, 1]
# ---------------------------------------------------------------------------


async def test_confidence_above_one_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.initiate_chargeback(initiate_intent(confidence=1.01))


async def test_confidence_below_zero_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_chargeback_status(status_intent(confidence=-0.01))


# ---------------------------------------------------------------------------
# Band boundaries
# ---------------------------------------------------------------------------


async def test_band_boundary_exactly_090_status_is_auto_proceeds() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_chargeback_status(status_intent(confidence=0.90))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert handle.status_calls == ["CB-001"]


async def test_band_boundary_exactly_070_status_is_review_deferred() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_chargeback_status(status_intent(confidence=0.70))
    # 0.70 >= review_floor → REVIEW band → HALT_REVIEW_DEFERRED for L1 read
    assert outcome.halt_reason == "review_deferred"
    assert outcome.decision is ConfirmationDecision.REVIEW


async def test_band_boundary_exactly_090_initiate_force_review_hold() -> None:
    agent, handle, rec = make_agent()
    # confidence=0.90 → AUTO band → force_review pushes to REVIEW → no reviewer → HOLD
    outcome = await agent.initiate_chargeback(initiate_intent(confidence=0.90))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert handle.initiate_calls == []


# ---------------------------------------------------------------------------
# R-SEC — no amount or PII in any lineage record field
# ---------------------------------------------------------------------------


async def test_rsec_no_amount_in_triggering_event_initiate() -> None:
    agent, _, rec = make_agent()
    await agent.initiate_chargeback(initiate_intent(dispute_id="DSP-SEC-01"))
    r = rec.records[0]
    # amount "250.00" must not appear in triggering_event or intent text
    assert "250" not in r.triggering_event
    assert "250" not in (r.intent or "")
    # triggering_event is keyed on opaque dispute_id only
    assert r.triggering_event == "initiate_chargeback:DSP-SEC-01"


async def test_rsec_result_not_in_record_status() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_chargeback_status(status_intent(confidence=0.95))
    assert outcome.result is not None
    # AgentDecisionRecord has no 'result' field — result rides on AgentOutcome only
    assert not hasattr(rec.records[0], "result")


async def test_rsec_no_amount_in_record_submit() -> None:
    agent, _, rec = make_agent()
    await agent.submit_representment(
        submit_intent(chargeback_id="CB-SEC-02"), human_reviewed_by="coo@banxe.com"
    )
    r = rec.records[0]
    assert "CB-SEC-02" in r.triggering_event
    assert r.triggering_event == "submit_representment:CB-SEC-02"


# ---------------------------------------------------------------------------
# Exactly 1 record per action
# ---------------------------------------------------------------------------


async def test_exactly_one_record_per_action() -> None:
    agent, _, rec = make_agent()
    # L1 read (AUTO)
    await agent.get_chargeback_status(status_intent(confidence=0.95))
    # HOLD (no reviewer)
    await agent.initiate_chargeback(initiate_intent(confidence=0.95))
    # HALT_UNRESOLVED
    await agent.submit_representment(submit_intent(proc=_UNRESOLVED))
    assert len(rec.records) == 3


# ---------------------------------------------------------------------------
# Window accumulation
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_success() -> None:
    agent, _, _ = make_agent()
    assert agent._window.used_tokens == 0
    await agent.get_chargeback_status(status_intent(confidence=0.95))
    assert agent._window.used_tokens == 100
    assert agent._window.used_cost == Decimal("0.10")


async def test_window_not_accumulated_on_halt() -> None:
    agent, _, _ = make_agent()
    await agent.initiate_chargeback(initiate_intent(proc=_UNRESOLVED))
    assert agent._window.used_tokens == 0
