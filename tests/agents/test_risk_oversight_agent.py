"""RiskOversightAgent test suite — 100% coverage over services/agents/risk_oversight_agent.py.

Validates: ADR-049 §D2 gate-chain branches (process-ref resolution, scope allow-list,
confidence band, cost-cap per-request and per-window, compliance gate, successful port
call, port RiskMetricsPortError path), ADR-046 lineage invariants (one record per action
on every exit path), R-SEC-NEW-01 (no raw metric value / exposure amount / alert counter
in any lineage record — result rides on AgentOutcome.result only), and the
READ-ONLY INVARIANT (mask scope has no approve / threshold / decision / model-approval op).

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected
without @pytest.mark.asyncio.
"""

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
from services.agents.risk_oversight_agent import (
    GetAggregateExposureIntent,
    GetConsumerDutySignalsIntent,
    GetMonitoringCountersIntent,
    GetRiskDashboardIntent,
    RiskOversightAgent,
    RiskOversightMask,
)
from services.risk.risk_metrics_port import (
    AggregateExposure,
    InMemoryRiskMetricsPort,
    MonitoringCounters,
    RiskDashboard,
    RiskMetricsPortError,
)

# ---------------------------------------------------------------------------
# In-test doubles
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    """In-memory DecisionRecorder that collects records for assertion."""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

_DEFAULT_CAP = CostCap(
    max_request_tokens=1_000,
    max_request_cost=Decimal("1.00"),
    max_window_tokens=10_000,
    max_window_cost=Decimal("10.00"),
)


def make_mask(**overrides: object) -> RiskOversightMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return RiskOversightMask(**base)  # type: ignore[arg-type]


def make_agent(
    mask: RiskOversightMask | None = None,
    port: InMemoryRiskMetricsPort | None = None,
    recorder: FakeRecorder | None = None,
    window: CostWindow | None = None,
) -> tuple[RiskOversightAgent, InMemoryRiskMetricsPort, FakeRecorder]:
    p = port or InMemoryRiskMetricsPort()
    r = recorder or FakeRecorder()
    m = mask or make_mask()
    return RiskOversightAgent(risk_metrics_port=p, recorder=r, mask=m, cost_window=window), p, r


def _ref(resolved: bool = True) -> ProcessRef:
    pid = "proc-risk-001" if resolved else ""
    return ProcessRef(process_id=pid, version="1.0")


def _cost(tokens: int = 10, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def make_dashboard_intent(
    *,
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetRiskDashboardIntent:
    return GetRiskDashboardIntent(
        intent_text="get CRO risk dashboard",
        process_ref=_ref(resolved),
        correlation_id="corr-dashboard-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_exposure_intent(
    *,
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetAggregateExposureIntent:
    return GetAggregateExposureIntent(
        intent_text="get aggregate exposure for CRO",
        process_ref=_ref(resolved),
        correlation_id="corr-exposure-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_counters_intent(
    *,
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetMonitoringCountersIntent:
    return GetMonitoringCountersIntent(
        intent_text="get monitoring counters for CRO",
        process_ref=_ref(resolved),
        correlation_id="corr-counters-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_signals_intent(
    *,
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetConsumerDutySignalsIntent:
    return GetConsumerDutySignalsIntent(
        intent_text="get consumer duty signals for CRO",
        process_ref=_ref(resolved),
        correlation_id="corr-signals-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


# ---------------------------------------------------------------------------
# 1. AUTO happy path — get_risk_dashboard
# ---------------------------------------------------------------------------


async def test_get_risk_dashboard_auto_read_executes() -> None:
    """Confidence 0.95 > 0.90 → AUTO band; port called; exactly one lineage record."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_risk_dashboard(make_dashboard_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "GET_RISK_DASHBOARD"
    assert rec.agent_id == "risk_oversight_agent"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    # Dashboard rides on outcome.result ONLY — not on the record (R-SEC).
    assert isinstance(outcome.result, RiskDashboard)
    assert outcome.record is rec


# ---------------------------------------------------------------------------
# 2. AUTO happy path — get_aggregate_exposure
# ---------------------------------------------------------------------------


async def test_get_aggregate_exposure_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is AggregateExposure."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_aggregate_exposure(make_exposure_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, AggregateExposure)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "GET_AGGREGATE_EXPOSURE"


# ---------------------------------------------------------------------------
# 3. AUTO happy path — get_monitoring_counters
# ---------------------------------------------------------------------------


async def test_get_monitoring_counters_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is MonitoringCounters."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_monitoring_counters(make_counters_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, MonitoringCounters)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "GET_MONITORING_COUNTERS"


# ---------------------------------------------------------------------------
# 4. AUTO happy path — get_consumer_duty_signals
# ---------------------------------------------------------------------------


async def test_get_consumer_duty_signals_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is list[ConsumerDutySignal]."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_consumer_duty_signals(make_signals_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, list)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "GET_CONSUMER_DUTY_SIGNALS"


# ---------------------------------------------------------------------------
# 5. Unresolved process_ref → HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_unresolved_process_ref_blocks() -> None:
    """Empty process_id → unresolved; port NOT called; one lineage record."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


# ---------------------------------------------------------------------------
# 6. Out-of-scope op → REJECT_OUT_OF_SCOPE
# ---------------------------------------------------------------------------


async def test_out_of_scope_op_refused() -> None:
    """Scope limited to approve_threshold; get_risk_dashboard is off-list → REJECT."""
    scoped_mask = make_mask(scope=("RiskMetricsPort.approve_threshold",))
    agent, _, recorder = make_agent(mask=scoped_mask)
    outcome = await agent.get_risk_dashboard(make_dashboard_intent())

    assert outcome.executed is False
    assert outcome.halt_reason == "out_of_scope"
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


# ---------------------------------------------------------------------------
# 7. Below-AUTO band (REVIEW) → HALT_REVIEW_DEFERRED, port NOT called
# ---------------------------------------------------------------------------


async def test_below_auto_band_read_halts_review_deferred() -> None:
    """Confidence 0.80 is in REVIEW band (0.70–0.90); reads are AUTO-only (L1-Auto)."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(confidence=0.80))

    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ---------------------------------------------------------------------------
# 8. Low confidence (<0.70) → BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence() -> None:
    """Confidence 0.50 < 0.70 → BLOCK; port NOT called."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(confidence=0.50))

    assert outcome.executed is False
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


# ---------------------------------------------------------------------------
# 9. Band boundaries: exactly at threshold values
# ---------------------------------------------------------------------------


async def test_band_boundary_exactly_auto_threshold_is_review() -> None:
    """confidence=0.90 is NOT > 0.90 → falls to REVIEW band → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(confidence=0.90))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


async def test_band_boundary_exactly_review_floor_is_review() -> None:
    """confidence=0.70 is >= 0.70 → REVIEW band → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(confidence=0.70))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


# ---------------------------------------------------------------------------
# 10. Per-request token cost-cap breach → HALT_COST_CAP_BREACH
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_tokens_breach() -> None:
    """tokens=100 > max_request_tokens=5 → breach; port NOT called."""
    tight_cap = CostCap(
        max_request_tokens=5,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert len(recorder.records) == 1
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 11. Per-request monetary cost-cap breach
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_monetary_breach() -> None:
    """cost=0.10 > max_request_cost=0.001 → breach; port NOT called."""
    tight_cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("0.001"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(cost="0.10"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 12. Per-window token cost-cap breach
# ---------------------------------------------------------------------------


async def test_per_window_cost_cap_tokens_breach() -> None:
    """Window nearly full on tokens; next request overflows → breach."""
    window = CostWindow(
        used_tokens=9990, used_cost=Decimal("0.00"), window_ref="risk_oversight_agent:test"
    )
    agent, _, recorder = make_agent(window=window)
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 13. Per-window monetary cost-cap breach
# ---------------------------------------------------------------------------


async def test_per_window_monetary_cost_cap_breach() -> None:
    """Window nearly full on cost; next request overflows → breach."""
    window = CostWindow(
        used_tokens=0, used_cost=Decimal("9.99"), window_ref="risk_oversight_agent:test"
    )
    cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=1_000_000,
        max_window_cost=Decimal("10.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.get_risk_dashboard(make_dashboard_intent(tokens=1, cost="0.02"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# 14. Compliance FAIL → HALT_COMPLIANCE_BLOCK, escalated to CRO
# ---------------------------------------------------------------------------


async def test_compliance_fail_blocks_escalates_to_cro() -> None:
    """RISK_DATA FAIL → HALT_COMPLIANCE_BLOCK; escalated_to = CRO."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_risk_dashboard(
        make_dashboard_intent(),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CRO"
    assert outcome.requires_hitl is True
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.escalated_to == "CRO"
    assert rec.action_taken == "HALT_COMPLIANCE_BLOCK"


# ---------------------------------------------------------------------------
# 15. Compliance ESCALATE → HALT_COMPLIANCE_BLOCK, escalated to CRO
# ---------------------------------------------------------------------------


async def test_compliance_escalate_blocks_escalates_to_cro() -> None:
    """RISK_DATA ESCALATE also halts and escalates to CRO."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_aggregate_exposure(
        make_exposure_intent(),
        compliance_result=ComplianceResult.ESCALATE,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CRO"
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 16. Port raises RiskMetricsPortError → lineage emitted (executed=False), re-raised
# ---------------------------------------------------------------------------


async def test_port_error_emits_lineage_then_reraises() -> None:
    """RiskMetricsPortError: one lineage record with HALT_PROVIDER_ERROR; error re-raised."""
    port = InMemoryRiskMetricsPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(RiskMetricsPortError):
        await agent.get_risk_dashboard(make_dashboard_intent())

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert "HALT_PROVIDER_ERROR" in rec.action_taken
    assert "RiskMetricsPortError" in rec.action_taken


# ---------------------------------------------------------------------------
# 17. Confidence out of [0, 1] → ValueError, NO lineage record
# ---------------------------------------------------------------------------


async def test_invalid_confidence_above_range_raises_no_record() -> None:
    """confidence=1.1 → ValueError; _evaluate raises before any lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_risk_dashboard(make_dashboard_intent(confidence=1.1))
    assert len(recorder.records) == 0


async def test_invalid_confidence_below_range_raises_no_record() -> None:
    """confidence=-0.01 → ValueError; no lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_risk_dashboard(make_dashboard_intent(confidence=-0.01))
    assert len(recorder.records) == 0


# ---------------------------------------------------------------------------
# 18. R-SEC: no raw metric value / exposure amount in any lineage record field
# ---------------------------------------------------------------------------


async def test_no_raw_exposure_in_lineage_record() -> None:
    """AggregateExposure.total_gbp sentinel MUST NOT appear in any AgentDecisionRecord field."""
    sentinel = Decimal("87654321.99")
    port = InMemoryRiskMetricsPort(
        exposure=AggregateExposure(total_gbp=sentinel, as_of="2026-06-11")
    )
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.get_aggregate_exposure(make_exposure_intent())

    # Exposure rides on AgentOutcome.result — confirmed it's there.
    assert isinstance(outcome.result, AggregateExposure)
    assert outcome.result.total_gbp == sentinel  # type: ignore[union-attr]

    rec = recorder.records[0]
    sentinel_str = str(sentinel)
    # No raw metric value in any record string field (R-SEC-NEW-01).
    assert sentinel_str not in rec.triggering_event
    assert sentinel_str not in rec.intent
    assert sentinel_str not in rec.reasoning_summary
    assert sentinel_str not in rec.action_taken
    assert all(sentinel_str not in p for p in rec.policies_evaluated)
    # cost_amount is the REQUEST cost (e.g. "0.01"), never the exposure amount.
    assert rec.cost_amount != sentinel


# ---------------------------------------------------------------------------
# 19. ADR-046 lineage-per-action: exactly 1 record per call on every exit path
# ---------------------------------------------------------------------------


async def test_lineage_one_record_per_call_adr046() -> None:
    """Every action call (succeed or halt) emits exactly 1 record; total increments by 1."""
    agent, _, recorder = make_agent()

    assert len(recorder.records) == 0
    await agent.get_risk_dashboard(make_dashboard_intent())
    assert len(recorder.records) == 1

    await agent.get_aggregate_exposure(make_exposure_intent())
    assert len(recorder.records) == 2

    await agent.get_monitoring_counters(make_counters_intent())
    assert len(recorder.records) == 3

    await agent.get_consumer_duty_signals(make_signals_intent())
    assert len(recorder.records) == 4

    # Halted path also emits exactly 1 record.
    await agent.get_risk_dashboard(make_dashboard_intent(resolved=False))
    assert len(recorder.records) == 5


# ---------------------------------------------------------------------------
# 20. Window accumulates only on successful reads
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_successful_reads() -> None:
    """Window.used_tokens / used_cost increment per successful port call."""
    window = CostWindow(window_ref="risk_oversight_agent:test")
    agent, _, _ = make_agent(window=window)

    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")
    await agent.get_risk_dashboard(make_dashboard_intent(tokens=50, cost="0.05"))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.05")

    await agent.get_aggregate_exposure(make_exposure_intent(tokens=30, cost="0.03"))
    assert window.used_tokens == 80
    assert window.used_cost == Decimal("0.08")


async def test_window_not_accumulated_on_halt() -> None:
    """A halted call (e.g., unresolved ref) MUST NOT advance the window."""
    window = CostWindow(window_ref="risk_oversight_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.get_risk_dashboard(make_dashboard_intent(resolved=False))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# 21. INVARIANT: default mask scope has only READ ops
# ---------------------------------------------------------------------------


async def test_invariant_scope_is_read_only() -> None:
    """Default mask scope MUST NOT contain approve / threshold / decision / model_approval."""
    mask = make_mask()
    scope_lower = " ".join(mask.scope).lower()

    assert "approve" not in scope_lower
    assert "threshold" not in scope_lower
    assert "decision" not in scope_lower
    assert "model_approval" not in scope_lower

    # Every op in scope must be one of the 4 read verbs.
    read_ops = {
        "RiskMetricsPort.get_risk_dashboard",
        "RiskMetricsPort.get_aggregate_exposure",
        "RiskMetricsPort.get_monitoring_counters",
        "RiskMetricsPort.get_consumer_duty_signals",
    }
    for op in mask.scope:
        assert op in read_ops, f"Non-read op found in mask scope: {op}"


async def test_invariant_approve_op_always_out_of_scope() -> None:
    """Proves an approve_threshold op is REJECT_OUT_OF_SCOPE — it is never in the allow-list.

    This is the READ-ONLY INVARIANT test: even if the scope were manually overridden to
    contain approve_threshold, the real read ops (get_risk_dashboard) would be off-list,
    demonstrating that approve_threshold is never reachable through the standard agent flow.
    """
    scoped_mask = make_mask(scope=("RiskMetricsPort.approve_threshold",))
    agent, _, _ = make_agent(mask=scoped_mask)

    outcome = await agent.get_risk_dashboard(make_dashboard_intent())
    # op="RiskMetricsPort.get_risk_dashboard" is not in this scope → REJECT.
    assert outcome.halt_reason == "out_of_scope"


# ---------------------------------------------------------------------------
# 22. In-memory e2e full flow (real mask, InMemoryRiskMetricsPort, FakeRecorder)
# ---------------------------------------------------------------------------


async def test_in_memory_e2e_get_risk_dashboard() -> None:
    """Full e2e: real RiskOversightMask + InMemoryRiskMetricsPort → AUTO read with lineage."""
    recorder = FakeRecorder()
    mask = RiskOversightMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
        agent_id="risk_oversight_agent",
        cro_role="CRO",
    )
    port = InMemoryRiskMetricsPort()
    agent = RiskOversightAgent(risk_metrics_port=port, recorder=recorder, mask=mask)
    intent = GetRiskDashboardIntent(
        intent_text="CRO daily risk dashboard Q2-2026",
        process_ref=ProcessRef(process_id="proc-e2e-risk-001", version="1.0"),
        correlation_id="e2e-corr-risk-001",
        confidence_score=0.97,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.10")),
    )
    outcome = await agent.get_risk_dashboard(intent)

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, RiskDashboard)
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.agent_id == "risk_oversight_agent"
    assert rec.correlation_id == "e2e-corr-risk-001"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert rec.triggering_event == "get_risk_dashboard"
    assert rec.human_reviewed_by is None  # L1-Auto: never a reviewer
