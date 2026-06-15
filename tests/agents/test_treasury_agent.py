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
from services.agents.treasury_agent import (
    GetFXExposureIntent,
    GetTotalFXExposureIntent,
    ReconcileNostroIntent,
    TreasuryAgent,
    TreasuryMask,
)
from services.treasury.fx_exposure_port import (
    FXExposurePortError,
    FXPosition,
    InMemoryFXExposurePort,
)
from services.treasury.nostro_recon_port import (
    InMemoryNOSTROReconPort,
    NostroBalance,
    NostroReconPortError,
)

# ------------------------------------------------------------------ fixtures/helpers

_DEFAULT_CAP = CostCap(
    max_request_tokens=5000,
    max_request_cost=Decimal("5.00"),
    max_window_tokens=50000,
    max_window_cost=Decimal("50.00"),
)
_SMALL_COST = RequestCost(tokens=100, cost=Decimal("0.10"))
_PROC = ProcessRef(process_id="FX-001", version="v1.0")
_UNRESOLVED = ProcessRef(process_id="", version="")


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


def make_mask(**overrides: object) -> TreasuryMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return TreasuryMask(**base)  # type: ignore[arg-type]


def make_agent(
    *,
    mask: TreasuryMask | None = None,
    window: CostWindow | None = None,
    fx_positions: list[FXPosition] | None = None,
) -> tuple[TreasuryAgent, InMemoryFXExposurePort, InMemoryNOSTROReconPort, FakeRecorder]:
    fx = InMemoryFXExposurePort(
        fx_positions or [FXPosition("GBP/USD", Decimal("5000.00"), "2026-06-09")]
    )
    nostro = InMemoryNOSTROReconPort()
    nostro.seed(NostroBalance("ACCT-001", Decimal("10000"), Decimal("10000"), "2026-06-09"))
    rec = FakeRecorder()
    agent = TreasuryAgent(
        fx_port=fx,
        nostro_port=nostro,
        recorder=rec,
        mask=mask or make_mask(),
        window=window,
    )
    return agent, fx, nostro, rec


def fx_intent(
    confidence: float = 0.95,
    amount_gbp: str = "50000.00",
    pair: str = "GBP/USD",
    proc: ProcessRef = _PROC,
) -> GetFXExposureIntent:
    return GetFXExposureIntent(
        intent_text="get FX exposure",
        process_ref=proc,
        currency_pair=pair,
        correlation_id="corr-001",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
        amount_gbp=Decimal(amount_gbp),
    )


def total_fx_intent(
    confidence: float = 0.95,
    amount_gbp: str = "50000.00",
) -> GetTotalFXExposureIntent:
    return GetTotalFXExposureIntent(
        intent_text="get total FX exposure",
        process_ref=_PROC,
        correlation_id="corr-002",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
        amount_gbp=Decimal(amount_gbp),
    )


def nostro_intent(
    confidence: float = 0.95,
    amount_gbp: str = "50000.00",
    account_id: str = "ACCT-001",
) -> ReconcileNostroIntent:
    return ReconcileNostroIntent(
        intent_text="reconcile NOSTRO",
        process_ref=_PROC,
        account_id=account_id,
        as_of="2026-06-09",
        correlation_id="corr-003",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
        amount_gbp=Decimal(amount_gbp),
    )


# ------------------------------------------------------------------ AUTO happy paths


async def test_get_fx_exposure_auto_proceeds_and_returns_result() -> None:
    agent, fx, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "GET_FX_EXPOSURE"


async def test_get_total_fx_exposure_auto_proceeds() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_total_fx_exposure(total_fx_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert len(rec.records) == 1


async def test_reconcile_nostro_auto_proceeds() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.reconcile_nostro(nostro_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "RECONCILE_NOSTRO"


# ------------------------------------------------------------------ gate halts


async def test_halt_unresolved_process_ref() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(proc=_UNRESOLVED))
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_reject_out_of_scope() -> None:
    mask = make_mask(scope=("OTHER.op",))
    agent, _, _, rec = make_agent(mask=mask)
    outcome = await agent.get_fx_exposure(fx_intent())
    assert outcome.halt_reason == "out_of_scope"
    assert rec.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


async def test_block_low_confidence() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.50))
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ------------------------------------------------------------------ REVIEW band


async def test_review_band_no_reviewer_holds_for_hitl() -> None:
    agent, fx, _, rec = make_agent()
    fx_calls: list[str] = []
    original = fx.get_exposure

    async def patched(pair: str) -> FXPosition:
        fx_calls.append(pair)
        return await original(pair)

    fx.get_exposure = patched  # type: ignore[method-assign]
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.80))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_hitl is True
    assert fx_calls == []  # port NOT called
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"


async def test_review_band_with_reviewer_proceeds() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(
        fx_intent(confidence=0.80), human_reviewed_by="alice@banxe.com"
    )
    assert outcome.executed is True
    assert rec.records[0].human_reviewed_by == "alice@banxe.com"


# ------------------------------------------------------------------ CFO step-up


async def test_cfo_stepup_auto_confidence_large_amount_holds() -> None:
    agent, _, _, rec = make_agent()
    # AUTO confidence (0.95) but amount >= £100k → force REVIEW → HOLD
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.95, amount_gbp="100000.00"))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.escalated_to == "CFO"
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "CFO"


async def test_cfo_stepup_with_reviewer_proceeds() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(
        fx_intent(confidence=0.95, amount_gbp="100000.00"),
        human_reviewed_by="cfo@banxe.com",
    )
    assert outcome.executed is True
    assert rec.records[0].human_reviewed_by == "cfo@banxe.com"


async def test_auto_small_amount_no_hold() -> None:
    agent, _, _, rec = make_agent()
    # AUTO confidence (0.95) + amount < £100k → no step-up, proceeds freely
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.95, amount_gbp="99999.99"))
    assert outcome.executed is True
    assert rec.records[0].action_taken == "GET_FX_EXPOSURE"


async def test_cfo_stepup_exact_threshold_triggers() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.95, amount_gbp="100000.00"))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.escalated_to == "CFO"


# ------------------------------------------------------------------ cost-cap breaches


async def test_halt_cost_cap_per_request_tokens() -> None:
    cap = CostCap(
        max_request_tokens=50,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=5000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.get_fx_exposure(fx_intent())  # _SMALL_COST=100 tokens > 50
    assert outcome.halt_reason == "cost_cap_breach"
    assert rec.records[0].budget_breach_flag is BudgetBreach.BREACH


async def test_halt_cost_cap_per_request_cost() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("0.05"),
        max_window_tokens=50000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.get_fx_exposure(fx_intent())  # 0.10 > 0.05
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_tokens() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=150,
        max_window_cost=Decimal("100.00"),
    )
    window = CostWindow(used_tokens=100)
    agent, _, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.get_fx_exposure(fx_intent())  # 100+100=200 > 150
    assert outcome.halt_reason == "cost_cap_breach"


async def test_halt_cost_cap_per_window_cost() -> None:
    cap = CostCap(
        max_request_tokens=5000,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=50000,
        max_window_cost=Decimal("0.15"),
    )
    window = CostWindow(used_cost=Decimal("0.10"))
    agent, _, _, rec = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.get_fx_exposure(fx_intent())  # 0.10+0.10=0.20 > 0.15
    assert outcome.halt_reason == "cost_cap_breach"


# ------------------------------------------------------------------ compliance gate


async def test_halt_compliance_fail_escalates_to_cfo() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(), compliance_result=ComplianceResult.FAIL)
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CFO"
    assert rec.records[0].escalated_to == "CFO"


async def test_halt_compliance_escalate_also_blocks() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(), compliance_result=ComplianceResult.ESCALATE)
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CFO"


# ------------------------------------------------------------------ provider errors


async def test_provider_error_fx_emits_record_then_reraises() -> None:
    fx = InMemoryFXExposurePort()  # empty → raises on get_exposure
    nostro = InMemoryNOSTROReconPort()
    rec = FakeRecorder()
    agent = TreasuryAgent(fx_port=fx, nostro_port=nostro, recorder=rec, mask=make_mask())
    with pytest.raises(FXExposurePortError):
        await agent.get_fx_exposure(fx_intent(pair="GBP/USD"))
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


async def test_provider_error_nostro_emits_record_then_reraises() -> None:
    fx = InMemoryFXExposurePort()
    nostro = InMemoryNOSTROReconPort()  # empty → raises on reconcile
    rec = FakeRecorder()
    agent = TreasuryAgent(fx_port=fx, nostro_port=nostro, recorder=rec, mask=make_mask())
    with pytest.raises(NostroReconPortError):
        await agent.reconcile_nostro(nostro_intent(account_id="MISSING"))
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


# ------------------------------------------------------------------ confidence validation


async def test_confidence_above_one_raises_value_error() -> None:
    agent, _, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_fx_exposure(fx_intent(confidence=1.01))


async def test_confidence_below_zero_raises_value_error() -> None:
    agent, _, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_fx_exposure(fx_intent(confidence=-0.01))


# ------------------------------------------------------------------ band boundaries


async def test_band_boundary_exactly_090_is_auto() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.90))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True


async def test_band_boundary_exactly_070_is_review() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.70))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.decision is ConfirmationDecision.REVIEW


# ------------------------------------------------------------------ R-SEC invariant


async def test_rsec_no_financial_values_in_lineage_record() -> None:
    agent, _, _, rec = make_agent()
    await agent.get_fx_exposure(fx_intent(confidence=0.95, amount_gbp="50000.00"))
    r = rec.records[0]
    # amount_gbp must NOT appear in triggering_event or intent text
    assert "50000" not in r.triggering_event
    assert "50000" not in (r.intent or "")
    # triggering_event is opaque handle (currency_pair), not a balance
    assert r.triggering_event == "get_fx_exposure:GBP/USD"


async def test_rsec_result_not_in_record() -> None:
    agent, _, _, rec = make_agent()
    outcome = await agent.get_fx_exposure(fx_intent(confidence=0.95))
    # result rides only on AgentOutcome, never serialised into record
    assert outcome.result is not None
    # record has no 'result' field — only action_taken, intent, triggering_event
    assert not hasattr(rec.records[0], "result") or rec.records[0].result is None  # type: ignore[union-attr]


# ------------------------------------------------------------------ window & port-call discipline


async def test_window_accumulates_on_success() -> None:
    agent, _, _, _ = make_agent()
    assert agent._window.used_tokens == 0
    await agent.get_fx_exposure(fx_intent(confidence=0.95))
    assert agent._window.used_tokens == 100
    assert agent._window.used_cost == Decimal("0.10")


async def test_window_not_accumulated_on_halt() -> None:
    agent, _, _, _ = make_agent()
    await agent.get_fx_exposure(fx_intent(proc=_UNRESOLVED))
    assert agent._window.used_tokens == 0


async def test_exactly_one_record_per_action() -> None:
    agent, _, _, rec = make_agent()
    await agent.get_fx_exposure(fx_intent(confidence=0.95))
    await agent.get_fx_exposure(fx_intent(confidence=0.80))  # HOLD
    await agent.reconcile_nostro(nostro_intent(confidence=0.95))
    assert len(rec.records) == 3
