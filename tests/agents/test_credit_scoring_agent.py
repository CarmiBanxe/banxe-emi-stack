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
from services.agents.credit_scoring_agent import (
    CreditScoringAgent,
    CreditScoringMask,
    DecideIntent,
    GetLatestScoreIntent,
    ScoreCustomerIntent,
)

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeCreditHandle:
    """In-memory credit handle stub for testing."""

    def __init__(self, raise_value_error: bool = False) -> None:
        self._raise = raise_value_error
        self.score_calls: list[str] = []
        self.get_score_calls: list[str] = []
        self.decide_calls: list[dict] = []

    def score_customer(
        self,
        customer_id: str,
        income: Decimal,
        account_age_months: int,
        aml_risk_score: Decimal,
    ) -> object:
        if self._raise:
            raise ValueError("fake domain error: invalid income")
        self.score_calls.append(customer_id)
        return {"customer_id": customer_id, "score": "750", "stub": True}

    def get_latest_score(self, customer_id: str) -> object | None:
        if self._raise:
            raise ValueError("fake domain error: customer not found")
        self.get_score_calls.append(customer_id)
        return {"customer_id": customer_id, "score": "700", "stub": True}

    def decide(self, application_id: str, credit_score: object, actor: str = "system") -> dict:
        if self._raise:
            raise ValueError("fake domain error: application not found")
        self.decide_calls.append({"application_id": application_id, "actor": actor})
        return {"status": "HITL_REQUIRED", "application_id": application_id}


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
_PROC = ProcessRef(process_id="CREDIT-P-001", version="v1.0")
_UNRESOLVED = ProcessRef(process_id="", version="")


def make_mask(**overrides: object) -> CreditScoringMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return CreditScoringMask(**base)  # type: ignore[arg-type]


def make_agent(
    *,
    mask: CreditScoringMask | None = None,
    window: CostWindow | None = None,
    raise_value_error: bool = False,
) -> tuple[CreditScoringAgent, FakeCreditHandle, FakeRecorder]:
    handle = FakeCreditHandle(raise_value_error=raise_value_error)
    rec = FakeRecorder()
    agent = CreditScoringAgent(
        credit_handle=handle,
        recorder=rec,
        mask=mask or make_mask(),
        cost_window=window,
    )
    return agent, handle, rec


def score_intent(
    confidence: float = 0.95,
    customer_id: str = "CUST-001",
    proc: ProcessRef = _PROC,
) -> ScoreCustomerIntent:
    return ScoreCustomerIntent(
        intent_text="score customer creditworthiness",
        process_ref=proc,
        customer_id=customer_id,
        income=Decimal("45000.00"),
        account_age_months=18,
        aml_risk_score=Decimal("5.0"),
        correlation_id="corr-score-001",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def get_score_intent(
    confidence: float = 0.95,
    customer_id: str = "CUST-001",
    proc: ProcessRef = _PROC,
) -> GetLatestScoreIntent:
    return GetLatestScoreIntent(
        intent_text="get latest credit score",
        process_ref=proc,
        customer_id=customer_id,
        correlation_id="corr-get-001",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def decide_intent(
    confidence: float = 0.95,
    application_id: str = "APP-001",
    is_rejection: bool = False,
    proc: ProcessRef = _PROC,
) -> DecideIntent:
    return DecideIntent(
        intent_text="apply credit decision",
        process_ref=proc,
        application_id=application_id,
        credit_score={"score": "750"},
        is_rejection=is_rejection,
        actor="underwriter",
        correlation_id="corr-decide-001",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


# ---------------------------------------------------------------------------
# L1 AUTO read — score_customer happy path
# ---------------------------------------------------------------------------


async def test_score_customer_auto_proceeds_and_returns_result() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.score_customer(score_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, dict)
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "SCORE_CUSTOMER"
    assert handle.score_calls == ["CUST-001"]
    assert not hasattr(rec.records[0], "result")


# ---------------------------------------------------------------------------
# L1 AUTO read — get_latest_score happy path
# ---------------------------------------------------------------------------


async def test_get_latest_score_auto_proceeds_and_returns_result() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_latest_score(get_score_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, dict)
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "GET_LATEST_SCORE"
    assert handle.get_score_calls == ["CUST-001"]


# ---------------------------------------------------------------------------
# decide — APPROVED (is_rejection=False) high confidence → proceeds
# ---------------------------------------------------------------------------


async def test_decide_approved_high_confidence_domain_called() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.decide(decide_intent(confidence=0.95, is_rejection=False))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "CREDIT_DECIDE"
    assert len(handle.decide_calls) == 1
    assert handle.decide_calls[0]["application_id"] == "APP-001"


# ---------------------------------------------------------------------------
# ⭐ MANDATORY-HITL-ON-REJECT INVARIANT
# ---------------------------------------------------------------------------


async def test_decide_rejection_no_reviewer_hold_for_review_domain_never_called() -> None:
    """REGULATORY: rejection at confidence=1.0 with no reviewer → HOLD_FOR_REVIEW."""
    agent, handle, rec = make_agent()
    outcome = await agent.decide(decide_intent(confidence=1.0, is_rejection=True))
    assert outcome.executed is False
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_step_up is True
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "CREDIT_OFFICER"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "CREDIT_OFFICER"
    assert handle.decide_calls == []  # domain NEVER called


async def test_decide_rejection_with_reviewer_proceeds() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.decide(
        decide_intent(confidence=0.95, is_rejection=True),
        human_reviewed_by="officer@banxe.com",
    )
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.REVIEW  # force_review pulled AUTO→REVIEW
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "CREDIT_DECIDE"
    assert rec.records[0].human_reviewed_by == "officer@banxe.com"
    assert len(handle.decide_calls) == 1


# ---------------------------------------------------------------------------
# HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_halt_unresolved_process_ref_score() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.score_customer(score_intent(proc=_UNRESOLVED))
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"
    assert handle.score_calls == []


async def test_halt_unresolved_process_ref_decide() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.decide(decide_intent(proc=_UNRESOLVED))
    assert outcome.halt_reason == "unresolved_process_ref"
    assert handle.decide_calls == []


# ---------------------------------------------------------------------------
# REJECT_OUT_OF_SCOPE
# ---------------------------------------------------------------------------


async def test_reject_out_of_scope_op() -> None:
    mask = make_mask(scope=("OTHER.op",))
    agent, handle, rec = make_agent(mask=mask)
    outcome = await agent.score_customer(score_intent())
    assert outcome.halt_reason == "out_of_scope"
    assert rec.records[0].action_taken == "REJECT_OUT_OF_SCOPE"
    assert handle.score_calls == []


# ---------------------------------------------------------------------------
# HALT_REVIEW_DEFERRED — L1 read below AUTO band → domain NOT called
# ---------------------------------------------------------------------------


async def test_halt_review_deferred_score_below_auto() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.score_customer(score_intent(confidence=0.80))
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "HALT_REVIEW_DEFERRED"
    assert handle.score_calls == []


async def test_halt_review_deferred_get_score_below_auto() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.get_latest_score(get_score_intent(confidence=0.80))
    assert outcome.halt_reason == "review_deferred"
    assert handle.get_score_calls == []


# ---------------------------------------------------------------------------
# BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence_score() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.score_customer(score_intent(confidence=0.50))
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert handle.score_calls == []


async def test_block_low_confidence_decide() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.decide(decide_intent(confidence=0.50))
    assert outcome.halt_reason == "low_confidence"
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# HALT_COST_CAP_BREACH (per-request tokens / cost; per-window tokens / cost)
# ---------------------------------------------------------------------------


async def test_halt_cost_cap_per_request_tokens() -> None:
    cap = CostCap(
        max_request_tokens=50,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.score_customer(score_intent())
    assert outcome.halt_reason == "cost_cap_breach"
    assert rec.records[0].budget_breach_flag is BudgetBreach.BREACH


async def test_halt_cost_cap_per_request_cost() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("0.05"),
        max_window_tokens=50000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.score_customer(score_intent())
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_tokens() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=150,
        max_window_cost=Decimal("100.00"),
    )
    window = CostWindow(used_tokens=100)
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.score_customer(score_intent())
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_cost() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50000,
        max_window_cost=Decimal("0.15"),
    )
    window = CostWindow(used_cost=Decimal("0.10"))
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.score_customer(score_intent())
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# HALT_COMPLIANCE_BLOCK — non-PASS → escalate to CREDIT_OFFICER
# ---------------------------------------------------------------------------


async def test_halt_compliance_fail_escalates_to_credit_officer() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.score_customer(score_intent(), compliance_result=ComplianceResult.FAIL)
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CREDIT_OFFICER"
    assert rec.records[0].escalated_to == "CREDIT_OFFICER"
    assert rec.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert handle.score_calls == []


async def test_halt_compliance_escalate_also_blocks() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_latest_score(
        get_score_intent(), compliance_result=ComplianceResult.ESCALATE
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CREDIT_OFFICER"


# ---------------------------------------------------------------------------
# HALT_PROVIDER_ERROR — handle raises ValueError → emit executed=False + re-raise
# ---------------------------------------------------------------------------


async def test_provider_error_score_emits_record_then_reraises() -> None:
    agent, _, rec = make_agent(raise_value_error=True)
    with pytest.raises(ValueError, match="fake domain error"):
        await agent.score_customer(score_intent())
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "HALT_PROVIDER_ERROR:ValueError"


async def test_provider_error_decide_emits_record_then_reraises() -> None:
    agent, _, rec = make_agent(raise_value_error=True)
    with pytest.raises(ValueError, match="fake domain error"):
        await agent.decide(decide_intent(), human_reviewed_by="officer@banxe.com")
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


# ---------------------------------------------------------------------------
# ValueError on confidence out of [0, 1]
# ---------------------------------------------------------------------------


async def test_confidence_above_one_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.score_customer(score_intent(confidence=1.01))


async def test_confidence_below_zero_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_latest_score(get_score_intent(confidence=-0.01))


# ---------------------------------------------------------------------------
# Band boundaries
# ---------------------------------------------------------------------------


async def test_band_boundary_exactly_090_score_is_auto_proceeds() -> None:
    agent, handle, rec = make_agent()
    outcome = await agent.score_customer(score_intent(confidence=0.90))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert handle.score_calls == ["CUST-001"]


async def test_band_boundary_exactly_070_score_is_review_deferred() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.score_customer(score_intent(confidence=0.70))
    assert outcome.halt_reason == "review_deferred"
    assert outcome.decision is ConfirmationDecision.REVIEW


async def test_band_boundary_rejection_confidence_090_force_review_hold() -> None:
    """Rejection with confidence=0.90 → AUTO → force_review → REVIEW → no reviewer → HOLD."""
    agent, handle, rec = make_agent()
    outcome = await agent.decide(decide_intent(confidence=0.90, is_rejection=True))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.requires_step_up is True
    assert handle.decide_calls == []


# ---------------------------------------------------------------------------
# R-SEC — no score / income / PII in any AgentDecisionRecord field
# ---------------------------------------------------------------------------


async def test_rsec_no_income_in_triggering_event() -> None:
    agent, _, rec = make_agent()
    await agent.score_customer(score_intent(customer_id="CUST-SEC-01"))
    r = rec.records[0]
    assert "45000" not in r.triggering_event
    assert "45000" not in (r.intent or "")
    assert r.triggering_event == "score_customer:CUST-SEC-01"


async def test_rsec_no_aml_risk_in_record() -> None:
    agent, _, rec = make_agent()
    await agent.score_customer(score_intent(customer_id="CUST-SEC-02"))
    r = rec.records[0]
    assert "5.0" not in r.triggering_event
    assert not hasattr(r, "aml_risk_score")


async def test_rsec_result_not_in_decision_record() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.score_customer(score_intent())
    assert outcome.result is not None
    assert not hasattr(rec.records[0], "result")


async def test_rsec_decide_application_id_only_in_triggering_event() -> None:
    agent, _, rec = make_agent()
    await agent.decide(decide_intent(application_id="APP-SEC-03"))
    r = rec.records[0]
    assert r.triggering_event == "decide:APP-SEC-03"
    assert "750" not in r.triggering_event


# ---------------------------------------------------------------------------
# Exactly 1 record per action — every exit path
# ---------------------------------------------------------------------------


async def test_exactly_one_record_per_action() -> None:
    agent, _, rec = make_agent()
    await agent.score_customer(score_intent(confidence=0.95))  # AUTO proceeds
    await agent.get_latest_score(get_score_intent(confidence=0.80))  # HALT_REVIEW_DEFERRED
    await agent.decide(decide_intent(is_rejection=True))  # HOLD_FOR_REVIEW
    await agent.score_customer(score_intent(proc=_UNRESOLVED))  # HALT_UNRESOLVED_PROCESS
    assert len(rec.records) == 4


# ---------------------------------------------------------------------------
# Window accumulation
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_success() -> None:
    agent, _, _ = make_agent()
    assert agent._window.used_tokens == 0
    await agent.score_customer(score_intent(confidence=0.95))
    assert agent._window.used_tokens == 100
    assert agent._window.used_cost == Decimal("0.10")


async def test_window_not_accumulated_on_halt() -> None:
    agent, _, _ = make_agent()
    await agent.score_customer(score_intent(proc=_UNRESOLVED))
    assert agent._window.used_tokens == 0
