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
from services.agents.forecast_agent import (
    BuildLiquidityForecastIntent,
    ForecastAgent,
    ForecastMask,
    GetLiquidityPositionIntent,
)
from services.treasury.liquidity_forecast_port import (
    InMemoryLiquidityForecastPort,
    LiquidityForecastInputs,
    LiquidityForecastPortError,
)

# ------------------------------------------------------------------ fixtures/helpers

_DEFAULT_CAP = CostCap(
    max_request_tokens=5000,
    max_request_cost=Decimal("5.00"),
    max_window_tokens=50000,
    max_window_cost=Decimal("50.00"),
)
_SMALL_COST = RequestCost(tokens=100, cost=Decimal("0.10"))
_PROC = ProcessRef(process_id="LQ-001", version="v1.0")
_UNRESOLVED = ProcessRef(process_id="", version="")


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


def make_mask(**overrides: object) -> ForecastMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return ForecastMask(**base)  # type: ignore[arg-type]


def _default_inputs(horizon_days: int = 30) -> LiquidityForecastInputs:
    return LiquidityForecastInputs(
        as_of="2026-06-09",
        horizon_days=horizon_days,
        opening_balance_gbp=Decimal("500000.00"),
        projected_inflows_gbp=Decimal("200000.00"),
        projected_outflows_gbp=Decimal("150000.00"),
    )


def make_agent(
    *,
    mask: ForecastMask | None = None,
    window: CostWindow | None = None,
    inputs: LiquidityForecastInputs | None = None,
    inputs_raises: Exception | None = None,
    position_raises: Exception | None = None,
    current_position: Decimal | None = None,
) -> tuple[ForecastAgent, InMemoryLiquidityForecastPort, FakeRecorder]:
    port = InMemoryLiquidityForecastPort(
        inputs=inputs or _default_inputs(),
        current_position=current_position or Decimal("750000.00"),
        inputs_raises=inputs_raises,
        position_raises=position_raises,
    )
    rec = FakeRecorder()
    agent = ForecastAgent(
        port=port,
        recorder=rec,
        mask=mask or make_mask(),
        window=window,
    )
    return agent, port, rec


def build_intent(
    confidence: float = 0.95,
    horizon_days: int = 30,
    proc: ProcessRef = _PROC,
) -> BuildLiquidityForecastIntent:
    return BuildLiquidityForecastIntent(
        intent_text="build liquidity forecast",
        process_ref=proc,
        horizon_days=horizon_days,
        correlation_id="corr-001",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


def position_intent(
    confidence: float = 0.95,
    as_of: str = "2026-06-09",
    proc: ProcessRef = _PROC,
) -> GetLiquidityPositionIntent:
    return GetLiquidityPositionIntent(
        intent_text="get liquidity position",
        process_ref=proc,
        as_of=as_of,
        correlation_id="corr-002",
        confidence_score=confidence,
        request_cost=_SMALL_COST,
    )


# ------------------------------------------------------------------ AUTO happy paths


async def test_build_liquidity_forecast_auto_proceeds() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(build_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.result is not None
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "BUILD_LIQUIDITY_FORECAST"


async def test_get_liquidity_position_auto_proceeds() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_liquidity_position(position_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert len(rec.records) == 1
    assert rec.records[0].action_taken == "GET_LIQUIDITY_POSITION"


# ------------------------------------------------------------------ gate halts


async def test_halt_unresolved_process_ref() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(build_intent(proc=_UNRESOLVED))
    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert rec.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_reject_out_of_scope() -> None:
    mask = make_mask(scope=("OTHER.op",))
    agent, _, rec = make_agent(mask=mask)
    outcome = await agent.build_liquidity_forecast(build_intent())
    assert outcome.halt_reason == "out_of_scope"
    assert rec.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


async def test_block_low_confidence() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(build_intent(confidence=0.50))
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert rec.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ------------------------------------------------------------------ REVIEW band


async def test_review_band_no_reviewer_holds_escalates_to_head_of_fpa() -> None:
    agent, port, rec = make_agent()
    port_calls: list[int] = []
    original = port.get_forecast_inputs

    async def patched(h: int) -> LiquidityForecastInputs:
        port_calls.append(h)
        return await original(h)

    port.get_forecast_inputs = patched  # type: ignore[method-assign]
    outcome = await agent.build_liquidity_forecast(build_intent(confidence=0.80))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.requires_hitl is True
    assert outcome.escalated_to == "HEAD_OF_FPA"
    assert port_calls == []  # port NOT called
    assert rec.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert rec.records[0].escalated_to == "HEAD_OF_FPA"


async def test_review_band_with_reviewer_proceeds() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(
        build_intent(confidence=0.80), human_reviewed_by="analyst@banxe.com"
    )
    assert outcome.executed is True
    assert rec.records[0].human_reviewed_by == "analyst@banxe.com"


async def test_review_position_intent_no_reviewer_holds_escalates() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.get_liquidity_position(position_intent(confidence=0.80))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.escalated_to == "HEAD_OF_FPA"


# ------------------------------------------------------------------ no CFO step-up (intents have no amount_gbp)


async def test_no_cfo_stepup_gate_exists_on_forecast_agent() -> None:
    """ForecastAgent has no amount_gbp → no CFO step-up; AUTO proceeds freely."""
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(build_intent(confidence=0.95))
    assert outcome.executed is True
    assert outcome.escalated_to is None


# ------------------------------------------------------------------ cost-cap breaches


async def test_halt_cost_cap_per_request_tokens() -> None:
    cap = CostCap(
        max_request_tokens=50,
        max_request_cost=Decimal("100.00"),
        max_window_tokens=5000,
        max_window_cost=Decimal("100.00"),
    )
    agent, _, rec = make_agent(mask=make_mask(cost_cap=cap))
    outcome = await agent.build_liquidity_forecast(build_intent())
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
    outcome = await agent.build_liquidity_forecast(build_intent())
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
    outcome = await agent.build_liquidity_forecast(build_intent())
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
    outcome = await agent.build_liquidity_forecast(build_intent())
    assert outcome.halt_reason == "cost_cap_breach"


# ------------------------------------------------------------------ compliance gate


async def test_halt_compliance_fail_escalates_to_head_of_fpa() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(
        build_intent(), compliance_result=ComplianceResult.FAIL
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "HEAD_OF_FPA"
    assert rec.records[0].escalated_to == "HEAD_OF_FPA"


async def test_halt_compliance_escalate_escalates_to_head_of_fpa() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(
        build_intent(), compliance_result=ComplianceResult.ESCALATE
    )
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "HEAD_OF_FPA"


# ------------------------------------------------------------------ provider error


async def test_provider_error_inputs_emits_record_then_reraises() -> None:
    err = LiquidityForecastPortError("upstream down")
    agent, _, rec = make_agent(inputs_raises=err)
    with pytest.raises(LiquidityForecastPortError):
        await agent.build_liquidity_forecast(build_intent(confidence=0.95))
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


async def test_provider_error_position_emits_record_then_reraises() -> None:
    err = LiquidityForecastPortError("position unavailable")
    agent, _, rec = make_agent(position_raises=err)
    with pytest.raises(LiquidityForecastPortError):
        await agent.get_liquidity_position(position_intent(confidence=0.95))
    assert len(rec.records) == 1
    assert rec.records[0].action_taken.startswith("HALT_PROVIDER_ERROR")


# ------------------------------------------------------------------ confidence validation


async def test_confidence_above_one_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.build_liquidity_forecast(build_intent(confidence=1.01))


async def test_confidence_below_zero_raises_value_error() -> None:
    agent, _, _ = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.build_liquidity_forecast(build_intent(confidence=-0.01))


# ------------------------------------------------------------------ band boundaries


async def test_band_boundary_exactly_090_is_auto() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(build_intent(confidence=0.90))
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True


async def test_band_boundary_exactly_070_is_review() -> None:
    agent, _, rec = make_agent()
    outcome = await agent.build_liquidity_forecast(build_intent(confidence=0.70))
    assert outcome.halt_reason == "hitl_review_required"
    assert outcome.decision is ConfirmationDecision.REVIEW


# ------------------------------------------------------------------ R-SEC invariant


async def test_rsec_triggering_event_uses_opaque_handle_for_build() -> None:
    agent, _, rec = make_agent()
    await agent.build_liquidity_forecast(build_intent(horizon_days=30, confidence=0.95))
    r = rec.records[0]
    assert r.triggering_event == "build_liquidity_forecast:30"
    # no balance or position amount in record
    assert "500000" not in r.triggering_event
    assert "500000" not in (r.intent or "")


async def test_rsec_triggering_event_uses_opaque_handle_for_position() -> None:
    agent, _, rec = make_agent()
    await agent.get_liquidity_position(position_intent(as_of="2026-06-09", confidence=0.95))
    r = rec.records[0]
    assert r.triggering_event == "get_liquidity_position:2026-06-09"


# ------------------------------------------------------------------ window & discipline


async def test_window_accumulates_on_success() -> None:
    agent, _, _ = make_agent()
    assert agent._window.used_tokens == 0
    await agent.build_liquidity_forecast(build_intent(confidence=0.95))
    assert agent._window.used_tokens == 100
    assert agent._window.used_cost == Decimal("0.10")


async def test_window_not_accumulated_on_halt() -> None:
    agent, _, _ = make_agent()
    await agent.build_liquidity_forecast(build_intent(proc=_UNRESOLVED))
    assert agent._window.used_tokens == 0


async def test_exactly_one_record_per_action() -> None:
    agent, _, rec = make_agent()
    await agent.build_liquidity_forecast(build_intent(confidence=0.95))
    await agent.build_liquidity_forecast(build_intent(confidence=0.80))  # HOLD
    await agent.get_liquidity_position(position_intent(confidence=0.95))
    assert len(rec.records) == 3
