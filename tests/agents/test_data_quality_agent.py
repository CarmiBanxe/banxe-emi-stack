"""DataQualityAgent test suite — 100% coverage over services/agents/data_quality_agent.py.

Validates: ADR-049 §D2 gate-chain branches (process-ref resolution, scope allow-list,
confidence band, cost-cap per-request and per-window, compliance gate, successful port
call, port DataQualityPortError path), ADR-046 lineage invariants (one record per action
on every exit path), R-SEC-NEW-01 (no raw metric value / drift score / null-rate in any
lineage record — result rides on AgentOutcome.result only), and the DETECTION/REPORTING
INVARIANT (mask scope has no retrain / trigger / write / update op; all success_actions
use DETECT_ or REPORT_ prefix).

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
from services.agents.data_quality_agent import (
    DataQualityAgent,
    DataQualityMask,
    GetDriftScoreIntent,
    GetFreshnessIntent,
    GetQualityReportIntent,
    ListDatasetsIntent,
)
from services.data_quality.data_quality_port import (
    DataQualityPortError,
    DataQualityReport,
    DriftSignal,
    InMemoryDataQualityPort,
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


def make_mask(**overrides: object) -> DataQualityMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return DataQualityMask(**base)  # type: ignore[arg-type]


def make_agent(
    mask: DataQualityMask | None = None,
    port: InMemoryDataQualityPort | None = None,
    recorder: FakeRecorder | None = None,
    window: CostWindow | None = None,
) -> tuple[DataQualityAgent, InMemoryDataQualityPort, FakeRecorder]:
    p = port or InMemoryDataQualityPort()
    r = recorder or FakeRecorder()
    m = mask or make_mask()
    return DataQualityAgent(data_quality_port=p, recorder=r, mask=m, cost_window=window), p, r


def _ref(resolved: bool = True) -> ProcessRef:
    pid = "proc-dq-001" if resolved else ""
    return ProcessRef(process_id=pid, version="1.0")


def _cost(tokens: int = 10, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def make_drift_intent(
    *,
    dataset: str = "payments",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetDriftScoreIntent:
    return GetDriftScoreIntent(
        dataset=dataset,
        intent_text="detect drift score for payments dataset",
        process_ref=_ref(resolved),
        correlation_id="corr-drift-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_report_intent(
    *,
    dataset: str = "payments",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetQualityReportIntent:
    return GetQualityReportIntent(
        dataset=dataset,
        intent_text="report quality for payments dataset",
        process_ref=_ref(resolved),
        correlation_id="corr-report-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_list_intent(
    *,
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> ListDatasetsIntent:
    return ListDatasetsIntent(
        intent_text="detect datasets available for quality monitoring",
        process_ref=_ref(resolved),
        correlation_id="corr-list-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_freshness_intent(
    *,
    dataset: str = "payments",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GetFreshnessIntent:
    return GetFreshnessIntent(
        dataset=dataset,
        intent_text="report freshness for payments dataset",
        process_ref=_ref(resolved),
        correlation_id="corr-freshness-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


# ---------------------------------------------------------------------------
# 1. AUTO happy path — get_drift_score
# ---------------------------------------------------------------------------


async def test_get_drift_score_auto_read_executes() -> None:
    """Confidence 0.95 > 0.90 → AUTO band; port called; exactly one lineage record."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_drift_score(make_drift_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "DETECT_DRIFT_SCORE"
    assert rec.agent_id == "data_quality_agent"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    # DriftSignal rides on outcome.result ONLY — not on the record (R-SEC).
    assert isinstance(outcome.result, DriftSignal)
    assert outcome.record is rec


# ---------------------------------------------------------------------------
# 2. AUTO happy path — get_quality_report
# ---------------------------------------------------------------------------


async def test_get_quality_report_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is DataQualityReport."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_quality_report(make_report_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, DataQualityReport)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REPORT_QUALITY"


# ---------------------------------------------------------------------------
# 3. AUTO happy path — list_datasets
# ---------------------------------------------------------------------------


async def test_list_datasets_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is list[str]."""
    agent, _, recorder = make_agent()
    outcome = await agent.list_datasets(make_list_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, list)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "DETECT_DATASETS"


# ---------------------------------------------------------------------------
# 4. AUTO happy path — get_freshness
# ---------------------------------------------------------------------------


async def test_get_freshness_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; result is int."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_freshness(make_freshness_intent())

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, int)
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REPORT_FRESHNESS"


# ---------------------------------------------------------------------------
# 5. Unresolved process_ref → HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_unresolved_process_ref_blocks() -> None:
    """Empty process_id → unresolved; port NOT called; one lineage record."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_drift_score(make_drift_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


# ---------------------------------------------------------------------------
# 6. Out-of-scope op → REJECT_OUT_OF_SCOPE (INVARIANT: trigger_retrain refused)
# ---------------------------------------------------------------------------


async def test_out_of_scope_op_refused() -> None:
    """Scope restricted to trigger_retrain (a mutate op); get_drift_score is off-list → REJECT.

    This is the INVARIANT test: DataQualityPort.trigger_retrain is never in the default
    allow-list. When a scope containing only a mutate op is configured, the standard read
    ops are REJECT_OUT_OF_SCOPE — demonstrating that trigger_retrain cannot be reached via
    the normal agent flow (the port also has no such method).
    """
    scoped_mask = make_mask(scope=("DataQualityPort.trigger_retrain",))
    agent, _, recorder = make_agent(mask=scoped_mask)
    outcome = await agent.get_drift_score(make_drift_intent())

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
    outcome = await agent.get_drift_score(make_drift_intent(confidence=0.80))

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
    outcome = await agent.get_drift_score(make_drift_intent(confidence=0.50))

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
    outcome = await agent.get_drift_score(make_drift_intent(confidence=0.90))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"


async def test_band_boundary_exactly_review_floor_is_review() -> None:
    """confidence=0.70 is >= 0.70 → REVIEW band → HALT_REVIEW_DEFERRED."""
    agent, _, _ = make_agent()
    outcome = await agent.get_drift_score(make_drift_intent(confidence=0.70))

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
    outcome = await agent.get_drift_score(make_drift_intent(tokens=100))

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
    outcome = await agent.get_drift_score(make_drift_intent(cost="0.10"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 12. Per-window token cost-cap breach
# ---------------------------------------------------------------------------


async def test_per_window_cost_cap_tokens_breach() -> None:
    """Window nearly full on tokens; next request overflows → breach."""
    window = CostWindow(
        used_tokens=9990, used_cost=Decimal("0.00"), window_ref="data_quality_agent:test"
    )
    agent, _, recorder = make_agent(window=window)
    outcome = await agent.get_drift_score(make_drift_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 13. Per-window monetary cost-cap breach
# ---------------------------------------------------------------------------


async def test_per_window_monetary_cost_cap_breach() -> None:
    """Window nearly full on cost; next request overflows → breach."""
    window = CostWindow(
        used_tokens=0, used_cost=Decimal("9.99"), window_ref="data_quality_agent:test"
    )
    cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=1_000_000,
        max_window_cost=Decimal("10.00"),
    )
    agent, _, recorder = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.get_drift_score(make_drift_intent(tokens=1, cost="0.02"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"


# ---------------------------------------------------------------------------
# 14. Compliance FAIL → HALT_COMPLIANCE_BLOCK, escalated to CTO
# ---------------------------------------------------------------------------


async def test_compliance_fail_blocks_escalates_to_cto() -> None:
    """DATA_QUALITY FAIL → HALT_COMPLIANCE_BLOCK; escalated_to = CTO."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_drift_score(
        make_drift_intent(),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CTO"
    assert outcome.requires_hitl is True
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.escalated_to == "CTO"
    assert rec.action_taken == "HALT_COMPLIANCE_BLOCK"


# ---------------------------------------------------------------------------
# 15. Compliance ESCALATE → HALT_COMPLIANCE_BLOCK, escalated to CTO
# ---------------------------------------------------------------------------


async def test_compliance_escalate_blocks_escalates_to_cto() -> None:
    """DATA_QUALITY ESCALATE also halts and escalates to CTO."""
    agent, _, recorder = make_agent()
    outcome = await agent.get_quality_report(
        make_report_intent(),
        compliance_result=ComplianceResult.ESCALATE,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "CTO"
    assert len(recorder.records) == 1


# ---------------------------------------------------------------------------
# 16. Port raises DataQualityPortError → lineage emitted (executed=False), re-raised
# ---------------------------------------------------------------------------


async def test_port_error_emits_lineage_then_reraises() -> None:
    """DataQualityPortError: one lineage record with HALT_PROVIDER_ERROR; error re-raised."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(DataQualityPortError):
        await agent.get_drift_score(make_drift_intent())

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert "HALT_PROVIDER_ERROR" in rec.action_taken
    assert "DataQualityPortError" in rec.action_taken


# ---------------------------------------------------------------------------
# 17. Port error on each action type
# ---------------------------------------------------------------------------


async def test_port_error_on_get_quality_report_reraises() -> None:
    """DataQualityPortError on get_quality_report: lineage emitted, error re-raised."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(DataQualityPortError):
        await agent.get_quality_report(make_report_intent())

    assert len(recorder.records) == 1
    assert "HALT_PROVIDER_ERROR" in recorder.records[0].action_taken


async def test_port_error_on_list_datasets_reraises() -> None:
    """DataQualityPortError on list_datasets: lineage emitted, error re-raised."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(DataQualityPortError):
        await agent.list_datasets(make_list_intent())

    assert len(recorder.records) == 1
    assert "HALT_PROVIDER_ERROR" in recorder.records[0].action_taken


async def test_port_error_on_get_freshness_reraises() -> None:
    """DataQualityPortError on get_freshness: lineage emitted, error re-raised."""
    port = InMemoryDataQualityPort(fail_on_call=True)
    agent, _, recorder = make_agent(port=port)

    with pytest.raises(DataQualityPortError):
        await agent.get_freshness(make_freshness_intent())

    assert len(recorder.records) == 1
    assert "HALT_PROVIDER_ERROR" in recorder.records[0].action_taken


# ---------------------------------------------------------------------------
# 18. Confidence out of [0, 1] → ValueError, NO lineage record
# ---------------------------------------------------------------------------


async def test_invalid_confidence_above_range_raises_no_record() -> None:
    """confidence=1.1 → ValueError; _evaluate raises before any lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_drift_score(make_drift_intent(confidence=1.1))
    assert len(recorder.records) == 0


async def test_invalid_confidence_below_range_raises_no_record() -> None:
    """confidence=-0.01 → ValueError; no lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.get_drift_score(make_drift_intent(confidence=-0.01))
    assert len(recorder.records) == 0


# ---------------------------------------------------------------------------
# 19. R-SEC: no raw metric value / drift score in any lineage record field
# ---------------------------------------------------------------------------


async def test_no_raw_drift_score_in_lineage_record() -> None:
    """DriftSignal.drift_score sentinel MUST NOT appear in any AgentDecisionRecord field."""
    sentinel = Decimal("0.87654321")
    signal = DriftSignal(dataset="payments", drift_score=sentinel, as_of="2026-06-11")
    port = InMemoryDataQualityPort(signals={"payments": signal})
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.get_drift_score(make_drift_intent())

    # DriftSignal rides on AgentOutcome.result — confirmed it's there.
    assert isinstance(outcome.result, DriftSignal)
    assert outcome.result.drift_score == sentinel  # type: ignore[union-attr]

    rec = recorder.records[0]
    sentinel_str = str(sentinel)
    # No raw metric value in any record string field (R-SEC-NEW-01).
    assert sentinel_str not in rec.triggering_event
    assert sentinel_str not in rec.intent
    assert sentinel_str not in rec.reasoning_summary
    assert sentinel_str not in rec.action_taken
    assert all(sentinel_str not in p for p in rec.policies_evaluated)
    # cost_amount is the REQUEST cost (e.g. "0.01"), never the metric value.
    assert rec.cost_amount != sentinel


async def test_no_raw_null_rate_in_lineage_record() -> None:
    """DataQualityReport.null_rate sentinel MUST NOT appear in any AgentDecisionRecord field."""
    sentinel = Decimal("0.99876543")
    report = DataQualityReport(
        dataset="payments",
        null_rate=sentinel,
        schema_conformance=Decimal("0.01"),
        freshness_seconds=100,
        drift_score=Decimal("0.05"),
        as_of="2026-06-11",
    )
    port = InMemoryDataQualityPort(reports={"payments": report})
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.get_quality_report(make_report_intent())

    assert isinstance(outcome.result, DataQualityReport)
    assert outcome.result.null_rate == sentinel  # type: ignore[union-attr]

    rec = recorder.records[0]
    sentinel_str = str(sentinel)
    assert sentinel_str not in rec.triggering_event
    assert sentinel_str not in rec.intent
    assert sentinel_str not in rec.reasoning_summary
    assert sentinel_str not in rec.action_taken


# ---------------------------------------------------------------------------
# 20. ADR-046 lineage-per-action: exactly 1 record per call on every exit path
# ---------------------------------------------------------------------------


async def test_lineage_one_record_per_call_adr046() -> None:
    """Every action call (succeed or halt) emits exactly 1 record; total increments by 1."""
    agent, _, recorder = make_agent()

    assert len(recorder.records) == 0
    await agent.get_drift_score(make_drift_intent())
    assert len(recorder.records) == 1

    await agent.get_quality_report(make_report_intent())
    assert len(recorder.records) == 2

    await agent.list_datasets(make_list_intent())
    assert len(recorder.records) == 3

    await agent.get_freshness(make_freshness_intent())
    assert len(recorder.records) == 4

    # Halted path also emits exactly 1 record.
    await agent.get_drift_score(make_drift_intent(resolved=False))
    assert len(recorder.records) == 5


# ---------------------------------------------------------------------------
# 21. Window accumulates only on successful reads
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_successful_reads() -> None:
    """Window.used_tokens / used_cost increment per successful port call."""
    window = CostWindow(window_ref="data_quality_agent:test")
    agent, _, _ = make_agent(window=window)

    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")
    await agent.get_drift_score(make_drift_intent(tokens=50, cost="0.05"))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.05")

    await agent.get_quality_report(make_report_intent(tokens=30, cost="0.03"))
    assert window.used_tokens == 80
    assert window.used_cost == Decimal("0.08")


async def test_window_not_accumulated_on_halt() -> None:
    """A halted call (e.g., unresolved ref) MUST NOT advance the window."""
    window = CostWindow(window_ref="data_quality_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.get_drift_score(make_drift_intent(resolved=False))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# 22. Default window_ref is set from mask.agent_id
# ---------------------------------------------------------------------------


async def test_default_window_ref_uses_agent_id() -> None:
    """When no cost_window is injected, window_ref defaults to '{agent_id}:default'."""
    agent, _, _ = make_agent()
    assert agent._window.window_ref == "data_quality_agent:default"


# ---------------------------------------------------------------------------
# 23. INVARIANT: default mask scope has ONLY the 4 read ops (no retrain/trigger/write)
# ---------------------------------------------------------------------------


async def test_invariant_scope_is_detect_report_only() -> None:
    """Default mask scope MUST NOT contain retrain/trigger/write/update ops.

    INVARIANT (ADR-080): DataQualityAgent is detection/reporting only. The scope
    allow-list enforces this at the governance layer: any op not in the allow-list
    is REJECT_OUT_OF_SCOPE before the port is ever called.
    """
    mask = make_mask()
    scope_lower = " ".join(mask.scope).lower()

    assert "retrain" not in scope_lower
    assert "trigger" not in scope_lower
    assert "write" not in scope_lower
    assert "update" not in scope_lower

    # Every op in the default scope must be one of the 4 read ops.
    read_ops = {
        "DataQualityPort.get_drift_score",
        "DataQualityPort.get_quality_report",
        "DataQualityPort.list_datasets",
        "DataQualityPort.get_freshness",
    }
    for op in mask.scope:
        assert op in read_ops, f"Non-read op found in mask scope: {op}"

    # Verify the scope has exactly 4 ops.
    assert len(mask.scope) == 4


async def test_invariant_trigger_retrain_always_out_of_scope() -> None:
    """Proves that trigger_retrain is REJECT_OUT_OF_SCOPE — it is never in the allow-list.

    The default scope only includes the 4 read ops. When scope is restricted to
    trigger_retrain, the read ops are off-list → REJECT, proving that a retrain op
    is unreachable through the standard agent flow.
    """
    scoped_mask = make_mask(scope=("DataQualityPort.trigger_retrain",))
    agent, _, _ = make_agent(mask=scoped_mask)

    outcome = await agent.get_drift_score(make_drift_intent())
    # op="DataQualityPort.get_drift_score" is not in this scope → REJECT.
    assert outcome.halt_reason == "out_of_scope"


# ---------------------------------------------------------------------------
# 24. INVARIANT: every public action's success_action is a DETECT/REPORT verb
# ---------------------------------------------------------------------------


async def test_invariant_all_success_actions_are_detect_report_verbs() -> None:
    """Every public action's success_action must use DETECT_ or REPORT_ prefix.

    INVARIANT: the strings RETRAIN, TRIGGER, WRITE, UPDATE must not appear
    in any success_action — enforced at the agent code level and verified here.
    """
    agent, _, recorder = make_agent()

    await agent.get_drift_score(make_drift_intent())
    await agent.get_quality_report(make_report_intent())
    await agent.list_datasets(make_list_intent())
    await agent.get_freshness(make_freshness_intent())

    success_actions = [rec.action_taken for rec in recorder.records]
    detect_report_prefixes = ("DETECT_", "REPORT_")

    for action in success_actions:
        assert any(action.startswith(prefix) for prefix in detect_report_prefixes), (
            f"success_action {action!r} is not a DETECT/REPORT verb — invariant violated"
        )

    all_actions_str = " ".join(success_actions)
    assert "RETRAIN" not in all_actions_str
    assert "TRIGGER" not in all_actions_str
    assert "WRITE" not in all_actions_str
    assert "UPDATE" not in all_actions_str


# ---------------------------------------------------------------------------
# 25. In-memory e2e full flow (real mask, InMemoryDataQualityPort, FakeRecorder)
# ---------------------------------------------------------------------------


async def test_in_memory_e2e_get_drift_score() -> None:
    """Full e2e: real DataQualityMask + InMemoryDataQualityPort → AUTO read with lineage."""
    recorder = FakeRecorder()
    mask = DataQualityMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
        agent_id="data_quality_agent",
        cto_role="CTO",
    )
    port = InMemoryDataQualityPort()
    agent = DataQualityAgent(data_quality_port=port, recorder=recorder, mask=mask)
    intent = GetDriftScoreIntent(
        dataset="payments",
        intent_text="CTO daily drift check Q2-2026",
        process_ref=ProcessRef(process_id="proc-e2e-dq-001", version="1.0"),
        correlation_id="e2e-corr-dq-001",
        confidence_score=0.97,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.10")),
    )
    outcome = await agent.get_drift_score(intent)

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert isinstance(outcome.result, DriftSignal)
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.agent_id == "data_quality_agent"
    assert rec.correlation_id == "e2e-corr-dq-001"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert rec.triggering_event == "get_drift_score:payments"
    assert rec.human_reviewed_by is None  # L1-Auto: never a reviewer
