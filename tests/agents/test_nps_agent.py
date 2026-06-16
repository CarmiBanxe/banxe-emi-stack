"""NPSAgent test suite — 100% coverage over services/agents/nps_agent.py.

Validates: ADR-049 §D2 gate-chain branches (process-ref resolution, scope allow-list,
confidence band, per-request and per-window cost-cap, compliance gate, successful
handle call, ValueError provider-error path), ADR-046 lineage invariants (one record
per action on every exit path), R-SEC-NEW-01 (no raw feedback metrics / PII in any
lineage record — result rides on AgentOutcome.result only), and the READ-ONLY INVARIANT
(mask scope has only get_metrics; submit_csat is REJECT_OUT_OF_SCOPE).

asyncio_mode = "auto" (pyproject.toml): every ``async def test_*`` is auto-collected.
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
from services.agents.nps_agent import (
    GetFeedbackMetricsIntent,
    NPSAgent,
    NPSMask,
    _ActionContext,  # private — test-only access for scope-invariant test
)
from services.support.support_models import FeedbackMetrics

# ---------------------------------------------------------------------------
# In-test doubles
# ---------------------------------------------------------------------------


class FakeRecorder(DecisionRecorder):
    """In-memory DecisionRecorder that collects records for assertion."""

    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeFeedbackHandle:
    """In-memory FeedbackHandle stub — async get_metrics, optional ValueError raise."""

    def __init__(
        self,
        metrics: FeedbackMetrics | None = None,
        raise_value_error: bool = False,
    ) -> None:
        self._metrics = metrics or _default_metrics()
        self._raise = raise_value_error
        self.call_count: int = 0
        self.last_period_days: int | None = None

    async def get_metrics(self, period_days: int = 30) -> FeedbackMetrics:
        self.call_count += 1
        self.last_period_days = period_days
        if self._raise:
            raise ValueError("fake domain error: provider unavailable")
        return self._metrics


# ---------------------------------------------------------------------------
# Builders / helpers
# ---------------------------------------------------------------------------


def _default_metrics() -> FeedbackMetrics:
    return FeedbackMetrics(
        period_days=30,
        total_responses=100,
        avg_csat=4.2,
        avg_nps=7.5,
        nps_promoters=60,
        nps_detractors=15,
        nps_passives=25,
        nps_score=45.0,
        by_category={"PAYMENT": 4.5, "KYC": 3.8},
    )


_DEFAULT_CAP = CostCap(
    max_request_tokens=1_000,
    max_request_cost=Decimal("1.00"),
    max_window_tokens=10_000,
    max_window_cost=Decimal("10.00"),
)


def make_mask(**overrides: object) -> NPSMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return NPSMask(**base)  # type: ignore[arg-type]


def make_agent(
    mask: NPSMask | None = None,
    handle: FakeFeedbackHandle | None = None,
    recorder: FakeRecorder | None = None,
    window: CostWindow | None = None,
) -> tuple[NPSAgent, FakeFeedbackHandle, FakeRecorder]:
    h = handle or FakeFeedbackHandle()
    r = recorder or FakeRecorder()
    m = mask or make_mask()
    return NPSAgent(feedback_handle=h, recorder=r, mask=m, cost_window=window), h, r


def _ref(resolved: bool = True) -> ProcessRef:
    return ProcessRef(process_id="proc-nps-001" if resolved else "", version="1.0")


def _cost(tokens: int = 10, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def make_metrics_intent(
    *,
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
    period_days: int = 30,
    survey_id: str = "",
    cohort: str = "",
) -> GetFeedbackMetricsIntent:
    return GetFeedbackMetricsIntent(
        intent_text="CRO quarterly NPS/CSAT review",
        process_ref=_ref(resolved),
        correlation_id="corr-nps-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
        period_days=period_days,
        survey_id=survey_id,
        cohort=cohort,
    )


# ---------------------------------------------------------------------------
# 1. AUTO happy path — get_feedback_metrics
# ---------------------------------------------------------------------------


async def test_get_feedback_metrics_auto_happy_path() -> None:
    """Confidence 0.95 > 0.90 → AUTO band; handle called; exactly one lineage record.

    FeedbackMetrics rides on outcome.result ONLY — not on the record (R-SEC).
    """
    agent, handle, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1

    rec = recorder.records[0]
    assert rec.action_taken == "REPORT_FEEDBACK_METRICS"
    assert rec.agent_id == "nps_agent"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert rec.human_reviewed_by is None

    # FeedbackMetrics rides on outcome.result ONLY (R-SEC).
    assert isinstance(outcome.result, FeedbackMetrics)
    assert outcome.record is rec
    assert handle.call_count == 1
    assert handle.last_period_days == 30


# ---------------------------------------------------------------------------
# 2. survey_id and cohort appear in triggering_event (opaque handles)
# ---------------------------------------------------------------------------


async def test_triggering_event_includes_survey_and_cohort() -> None:
    """survey_id and cohort are included in triggering_event as opaque labels."""
    agent, _, recorder = make_agent()
    intent = make_metrics_intent(survey_id="SRV-Q2-2026", cohort="premium")
    await agent.get_feedback_metrics(intent)

    rec = recorder.records[0]
    assert "survey=SRV-Q2-2026" in rec.triggering_event
    assert "cohort=premium" in rec.triggering_event
    assert "period=30" in rec.triggering_event


async def test_triggering_event_period_only_when_no_survey_or_cohort() -> None:
    """With no survey_id/cohort, triggering_event contains only the period label."""
    agent, _, recorder = make_agent()
    await agent.get_feedback_metrics(make_metrics_intent(period_days=7))

    rec = recorder.records[0]
    assert rec.triggering_event == "get_feedback_metrics:period=7"
    assert "survey" not in rec.triggering_event
    assert "cohort" not in rec.triggering_event


# ---------------------------------------------------------------------------
# 3. Unresolved process_ref → HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_unresolved_process_ref_blocks() -> None:
    """Empty process_id → unresolved; handle NOT called; one lineage record."""
    agent, handle, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 4. REJECT_OUT_OF_SCOPE — submit_csat op refused (READ-ONLY INVARIANT)
# ---------------------------------------------------------------------------


async def test_reject_out_of_scope_submit_csat_refused() -> None:
    """submit_csat op is NOT on the NPS mask scope allow-list → REJECT_OUT_OF_SCOPE.

    INVARIANT: NPSAgent.scope contains ONLY get_metrics (the read op). The write
    op submit_csat is refused before the handle is ever called.
    """
    agent, handle, recorder = make_agent()
    # Construct a context with op = submit_csat (the write op outside scope).
    ctx = _ActionContext(
        intent_text="attempt to submit csat via nps agent",
        process_ref=_ref(resolved=True),
        correlation_id="scope-test-001",
        confidence_score=0.95,
        triggering_event="test:submit_csat",
        success_action="SUBMIT_CSAT",
        op="FeedbackAnalyticsAgent.submit_csat",
        request_cost=_cost(),
        compliance_result=ComplianceResult.PASS,
    )
    outcome = await agent._run_action(ctx, None)

    assert outcome.executed is False
    assert outcome.halt_reason == "out_of_scope"
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 5. HALT_REVIEW_DEFERRED — below AUTO band (L1-Auto: no HITL hold)
# ---------------------------------------------------------------------------


async def test_halt_review_deferred_below_auto_band() -> None:
    """Confidence 0.80 is in REVIEW band (0.70–0.90); reads are AUTO-only (L1-Auto)."""
    agent, handle, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(confidence=0.80))

    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 6. BLOCK_LOW_CONFIDENCE — confidence below review_floor
# ---------------------------------------------------------------------------


async def test_block_low_confidence() -> None:
    """Confidence 0.50 < 0.70 → BLOCK; handle NOT called."""
    agent, handle, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(confidence=0.50))

    assert outcome.executed is False
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 7. HALT_COST_CAP_BREACH — per-request token breach
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_tokens_breach() -> None:
    """tokens=100 > max_request_tokens=5 → breach; handle NOT called."""
    tight_cap = CostCap(
        max_request_tokens=5,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, handle, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.get_feedback_metrics(make_metrics_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert len(recorder.records) == 1
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 8. HALT_COST_CAP_BREACH — per-request monetary breach
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_monetary_breach() -> None:
    """cost=0.10 > max_request_cost=0.001 → breach; handle NOT called."""
    tight_cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("0.001"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.get_feedback_metrics(make_metrics_intent(cost="0.10"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 9. HALT_COST_CAP_BREACH — per-window token breach
# ---------------------------------------------------------------------------


async def test_per_window_tokens_breach() -> None:
    """Window nearly full on tokens; next request overflows → breach."""
    window = CostWindow(used_tokens=9990, used_cost=Decimal("0.00"), window_ref="nps_agent:test")
    agent, _, recorder = make_agent(window=window)
    outcome = await agent.get_feedback_metrics(make_metrics_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 10. HALT_COST_CAP_BREACH — per-window monetary breach
# ---------------------------------------------------------------------------


async def test_per_window_monetary_breach() -> None:
    """Window nearly full on cost; next request overflows → breach."""
    window = CostWindow(used_tokens=0, used_cost=Decimal("9.99"), window_ref="nps_agent:test")
    cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=1_000_000,
        max_window_cost=Decimal("10.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.get_feedback_metrics(make_metrics_intent(tokens=1, cost="0.02"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# 11. HALT_COMPLIANCE_BLOCK — CONSUMER_DUTY FAIL escalates to CRO
# ---------------------------------------------------------------------------


async def test_compliance_fail_blocks_escalates_to_cro() -> None:
    """CONSUMER_DUTY FAIL → HALT_COMPLIANCE_BLOCK; escalated_to = CRO."""
    agent, handle, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(
        make_metrics_intent(),
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
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 12. HALT_COMPLIANCE_BLOCK — CONSUMER_DUTY ESCALATE also blocks
# ---------------------------------------------------------------------------


async def test_compliance_escalate_blocks_escalates_to_cro() -> None:
    """CONSUMER_DUTY ESCALATE also halts and escalates to CRO."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(
        make_metrics_intent(),
        compliance_result=ComplianceResult.ESCALATE,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CRO"
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 13. HALT_PROVIDER_ERROR — handle raises ValueError → lineage + re-raise
# ---------------------------------------------------------------------------


async def test_halt_provider_error_emits_lineage_then_reraises() -> None:
    """ValueError from handle: one lineage record with HALT_PROVIDER_ERROR; re-raised."""
    h = FakeFeedbackHandle(raise_value_error=True)
    agent, _, recorder = make_agent(handle=h)

    with pytest.raises(ValueError, match="provider unavailable"):
        await agent.get_feedback_metrics(make_metrics_intent())

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "HALT_PROVIDER_ERROR:ValueError"
    assert rec.budget_breach_flag is BudgetBreach.NONE


# ---------------------------------------------------------------------------
# 14. Confidence out of [0, 1] → ValueError, NO lineage record
# ---------------------------------------------------------------------------


async def test_invalid_confidence_above_range_raises_no_record() -> None:
    """confidence=1.1 → ValueError; _evaluate raises before any lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_feedback_metrics(make_metrics_intent(confidence=1.1))
    assert len(recorder.records) == 0


async def test_invalid_confidence_below_range_raises_no_record() -> None:
    """confidence=-0.01 → ValueError; no lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_feedback_metrics(make_metrics_intent(confidence=-0.01))
    assert len(recorder.records) == 0


# ---------------------------------------------------------------------------
# 15. Band boundary values
# ---------------------------------------------------------------------------


async def test_band_boundary_exactly_auto_threshold_is_review() -> None:
    """confidence=0.90 is NOT > 0.90 → falls to REVIEW → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(confidence=0.90))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


async def test_band_boundary_exactly_review_floor_is_review() -> None:
    """confidence=0.70 is >= 0.70 → REVIEW → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(confidence=0.70))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


async def test_band_boundary_just_above_auto_threshold_is_auto() -> None:
    """confidence=0.901 > 0.90 → AUTO band; handle called."""
    agent, handle, _ = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(confidence=0.901))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert handle.call_count == 1


async def test_band_boundary_just_below_review_floor_is_block() -> None:
    """confidence=0.699 < 0.70 → BLOCK; handle NOT called."""
    agent, handle, _ = make_agent()
    outcome = await agent.get_feedback_metrics(make_metrics_intent(confidence=0.699))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "low_confidence"
    assert handle.call_count == 0


# ---------------------------------------------------------------------------
# 16. R-SEC: no feedback metrics values / PII in any lineage record field
# ---------------------------------------------------------------------------


async def test_rsec_no_feedback_metrics_in_lineage_record() -> None:
    """FeedbackMetrics sentinel values MUST NOT appear in any AgentDecisionRecord field.

    FeedbackMetrics rides on AgentOutcome.result ONLY (R-SEC-NEW-01, ADR-021).
    """
    sentinel_nps = 45.0
    sentinel_csat = 4.2
    metrics = FeedbackMetrics(
        period_days=30,
        total_responses=100,
        avg_csat=sentinel_csat,
        avg_nps=7.5,
        nps_promoters=60,
        nps_detractors=15,
        nps_passives=25,
        nps_score=sentinel_nps,
        by_category={"PAYMENT": 4.5},
    )
    h = FakeFeedbackHandle(metrics=metrics)
    agent, _, recorder = make_agent(handle=h)

    outcome = await agent.get_feedback_metrics(make_metrics_intent())

    # FeedbackMetrics rides on outcome.result — confirmed it's there.
    assert isinstance(outcome.result, FeedbackMetrics)
    assert outcome.result.nps_score == sentinel_nps  # type: ignore[union-attr]

    rec = recorder.records[0]
    nps_str = str(sentinel_nps)
    csat_str = str(sentinel_csat)
    # No raw metric value in any record string field.
    assert nps_str not in rec.triggering_event
    assert nps_str not in rec.intent
    assert nps_str not in rec.reasoning_summary
    assert nps_str not in rec.action_taken
    assert all(nps_str not in p for p in rec.policies_evaluated)
    assert csat_str not in rec.triggering_event
    assert csat_str not in rec.reasoning_summary


async def test_rsec_no_pii_in_triggering_event() -> None:
    """triggering_event uses opaque handles only — no customer data or feedback text."""
    agent, _, recorder = make_agent()
    intent = GetFeedbackMetricsIntent(
        intent_text="Q2 NPS review for premium cohort",
        process_ref=_ref(),
        correlation_id="pii-test",
        confidence_score=0.95,
        request_cost=_cost(),
        period_days=30,
        survey_id="SRV-OPAQUE-001",
        cohort="premium",
    )
    await agent.get_feedback_metrics(intent)

    rec = recorder.records[0]
    # triggering_event contains opaque labels only.
    assert "SRV-OPAQUE-001" in rec.triggering_event
    assert "premium" in rec.triggering_event
    # No raw PII patterns — no customer_id, no feedback_text content.
    assert "customer" not in rec.triggering_event.lower()
    assert "feedback_text" not in rec.triggering_event


# ---------------------------------------------------------------------------
# 17. ADR-046 lineage-per-action: exactly 1 record per call on every exit path
# ---------------------------------------------------------------------------


async def test_exactly_one_record_per_action_every_exit_path() -> None:
    """Every action call (succeed or halt) emits exactly 1 record; total increments by 1."""
    agent, _, recorder = make_agent()

    assert len(recorder.records) == 0
    await agent.get_feedback_metrics(make_metrics_intent())  # AUTO success
    assert len(recorder.records) == 1

    await agent.get_feedback_metrics(make_metrics_intent(resolved=False))  # HALT_UNRESOLVED
    assert len(recorder.records) == 2

    await agent.get_feedback_metrics(make_metrics_intent(confidence=0.80))  # HALT_REVIEW_DEFERRED
    assert len(recorder.records) == 3

    await agent.get_feedback_metrics(make_metrics_intent(confidence=0.50))  # BLOCK_LOW_CONFIDENCE
    assert len(recorder.records) == 4

    await agent.get_feedback_metrics(
        make_metrics_intent(), compliance_result=ComplianceResult.FAIL
    )  # HALT_COMPLIANCE_BLOCK
    assert len(recorder.records) == 5


# ---------------------------------------------------------------------------
# 18. Window accumulates only on successful reads
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_successful_read() -> None:
    """Window.used_tokens / used_cost increment per successful handle call."""
    window = CostWindow(window_ref="nps_agent:test")
    agent, _, _ = make_agent(window=window)

    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")

    await agent.get_feedback_metrics(make_metrics_intent(tokens=50, cost="0.05"))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.05")

    await agent.get_feedback_metrics(make_metrics_intent(tokens=20, cost="0.02"))
    assert window.used_tokens == 70
    assert window.used_cost == Decimal("0.07")


async def test_window_not_accumulated_on_halt() -> None:
    """A halted call MUST NOT advance the window."""
    window = CostWindow(window_ref="nps_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.get_feedback_metrics(make_metrics_intent(resolved=False))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# 19. Default window_ref is set from mask.agent_id
# ---------------------------------------------------------------------------


async def test_default_window_ref_uses_agent_id() -> None:
    """When no cost_window is injected, window_ref defaults to '{agent_id}:default'."""
    agent, _, _ = make_agent()
    assert agent._window.window_ref == "nps_agent:default"


# ---------------------------------------------------------------------------
# 20. INVARIANT: default mask scope is ONLY get_metrics (no submit_csat)
# ---------------------------------------------------------------------------


async def test_invariant_scope_contains_only_get_metrics() -> None:
    """Default mask scope MUST NOT contain submit_csat or any write op.

    INVARIANT (L1 read-only): NPSAgent is reporting only. The scope allow-list
    enforces this — any off-list op is REJECT_OUT_OF_SCOPE.
    """
    mask = make_mask()
    scope_str = " ".join(mask.scope).lower()

    assert "submit_csat" not in scope_str
    assert "submit" not in scope_str
    assert "write" not in scope_str

    # Exactly one op in scope: get_metrics.
    assert mask.scope == ("FeedbackAnalyticsAgent.get_metrics",)
    assert len(mask.scope) == 1


# ---------------------------------------------------------------------------
# 21. ComplianceResult.NA passes through (L1-Auto gate)
# ---------------------------------------------------------------------------


async def test_compliance_na_passes_through() -> None:
    """ComplianceResult.NA is treated as non-blocking at the compliance gate."""
    agent, handle, recorder = make_agent()
    outcome = await agent.get_feedback_metrics(
        make_metrics_intent(),
        compliance_result=ComplianceResult.NA,
    )

    assert outcome.executed is True
    assert outcome.halt_reason is None
    assert handle.call_count == 1
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 22. handle.get_metrics receives the correct period_days
# ---------------------------------------------------------------------------


async def test_handle_receives_correct_period_days() -> None:
    """period_days from intent is forwarded to handle.get_metrics."""
    agent, handle, _ = make_agent()
    await agent.get_feedback_metrics(make_metrics_intent(period_days=90))

    assert handle.last_period_days == 90
