"""BIAgent test suite — full branch coverage over services/agents/bi_agent.py.

Validates: ADR-049 §D2 gate-chain branches (process-ref resolution, scope allow-list,
confidence band, cost-cap per-request and per-window, compliance gate, successful port
call, port AnalyticsPortError path), ADR-046 lineage invariants (one record per action
on every exit path), and R-SEC-NEW-01 (no raw report content or PII in any lineage
record field — the result rides on AgentOutcome.result only).

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
from services.agents.bi_agent import (
    BIAgent,
    BIMask,
    GenerateDashboardIntent,
    KpiAlertIntent,
    ListDashboardsIntent,
)
from services.reporting_analytics.analytics_port import (
    AnalyticsPort,
    AnalyticsPortError,
    EntityId,
    ExportRequest,
    ExportResult,
    PortfolioView,
    ReportDescriptor,
    ReportFormat,
    ReportId,
    ReportView,
    SpendingSummary,
    SpendPeriod,
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


class FakeBIAnalyticsPort(AnalyticsPort):
    """Duck-type AnalyticsPort for BIAgent unit tests.

    Configurable return values and per-method optional raises so every gate-chain
    branch and the port-error path can be exercised independently. Only the three
    ops the BI mask calls are configured; get_spending_summary and request_export
    are stubs (BIAgent never calls them).
    """

    def __init__(
        self,
        *,
        report: ReportView | None = None,
        listing: list[ReportDescriptor] | None = None,
        portfolio: PortfolioView | None = None,
        report_raises: Exception | None = None,
        listing_raises: Exception | None = None,
        portfolio_raises: Exception | None = None,
    ) -> None:
        self._report = report or ReportView(
            report_id="rep-bi-001",
            entity_id="ent-bi-001",
            title="Q1 BI Dashboard",
            format=ReportFormat.PDF,
        )
        self._listing = (
            listing
            if listing is not None
            else [
                ReportDescriptor(
                    report_id="rep-bi-001", title="Q1 BI Dashboard", format=ReportFormat.PDF
                )
            ]
        )
        self._portfolio = portfolio or PortfolioView(
            entity_id="ent-bi-001",
            total_value=Decimal("75000.00"),
            currency="GBP",
        )
        self._report_raises = report_raises
        self._listing_raises = listing_raises
        self._portfolio_raises = portfolio_raises
        self.report_calls: list[str] = []
        self.listing_calls: list[str] = []
        self.portfolio_calls: list[str] = []

    async def get_report(self, report_id: ReportId) -> ReportView:
        self.report_calls.append(report_id)
        if self._report_raises is not None:
            raise self._report_raises
        return self._report

    async def list_available_reports(self, entity_id: EntityId) -> list[ReportDescriptor]:
        self.listing_calls.append(entity_id)
        if self._listing_raises is not None:
            raise self._listing_raises
        return self._listing

    async def get_portfolio_view(self, entity_id: EntityId) -> PortfolioView:
        self.portfolio_calls.append(entity_id)
        if self._portfolio_raises is not None:
            raise self._portfolio_raises
        return self._portfolio

    async def get_spending_summary(
        self, entity_id: EntityId, period: SpendPeriod
    ) -> SpendingSummary:
        raise NotImplementedError("BIAgent never calls get_spending_summary")

    async def request_export(self, request: ExportRequest) -> ExportResult:
        raise NotImplementedError("BIAgent never calls request_export")


# ---------------------------------------------------------------------------
# Builders
# ---------------------------------------------------------------------------

_DEFAULT_CAP = CostCap(
    max_request_tokens=1_000,
    max_request_cost=Decimal("1.00"),
    max_window_tokens=10_000,
    max_window_cost=Decimal("10.00"),
)


def make_mask(**overrides: object) -> BIMask:
    base: dict[str, object] = {"cost_cap": _DEFAULT_CAP}
    base.update(overrides)
    return BIMask(**base)  # type: ignore[arg-type]


def make_agent(
    mask: BIMask | None = None,
    port: FakeBIAnalyticsPort | None = None,
    recorder: FakeRecorder | None = None,
    window: CostWindow | None = None,
) -> tuple[BIAgent, FakeBIAnalyticsPort, FakeRecorder]:
    p = port or FakeBIAnalyticsPort()
    r = recorder or FakeRecorder()
    m = mask or make_mask()
    return BIAgent(analytics_port=p, recorder=r, mask=m, cost_window=window), p, r


def _ref(resolved: bool = True) -> ProcessRef:
    pid = "proc-bi-001" if resolved else ""
    return ProcessRef(process_id=pid, version="1.0")


def _cost(tokens: int = 10, cost: str = "0.01") -> RequestCost:
    return RequestCost(tokens=tokens, cost=Decimal(cost))


def make_dashboard_intent(
    *,
    report_id: str = "rep-001",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> GenerateDashboardIntent:
    return GenerateDashboardIntent(
        intent_text="generate management dashboard for Q1",
        process_ref=_ref(resolved),
        report_id=report_id,
        correlation_id="corr-dash-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_list_intent(
    *,
    entity_id: str = "ent-001",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> ListDashboardsIntent:
    return ListDashboardsIntent(
        intent_text="list available BI dashboards",
        process_ref=_ref(resolved),
        entity_id=entity_id,
        correlation_id="corr-list-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


def make_kpi_intent(
    *,
    entity_id: str = "ent-001",
    confidence: float = 0.95,
    resolved: bool = True,
    tokens: int = 10,
    cost: str = "0.01",
) -> KpiAlertIntent:
    return KpiAlertIntent(
        intent_text="read portfolio KPIs for C-suite alert",
        process_ref=_ref(resolved),
        entity_id=entity_id,
        correlation_id="corr-kpi-001",
        confidence_score=confidence,
        request_cost=_cost(tokens, cost),
    )


# ---------------------------------------------------------------------------
# 1. AUTO happy path — generate_dashboard
# ---------------------------------------------------------------------------


async def test_generate_dashboard_auto_read_executes() -> None:
    """Confidence 0.95 > 0.90 → AUTO band; port called; exactly one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.generate_dashboard(make_dashboard_intent(report_id="rep-42"))

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert port.report_calls == ["rep-42"]
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "GENERATE_DASHBOARD"
    assert rec.agent_id == "bi_agent"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert outcome.record is rec


# ---------------------------------------------------------------------------
# 2. AUTO happy path — list_dashboards
# ---------------------------------------------------------------------------


async def test_list_dashboards_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; port called; exactly one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.list_dashboards(make_list_intent(entity_id="ent-99"))

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert port.listing_calls == ["ent-99"]
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "LIST_DASHBOARDS"
    assert isinstance(outcome.result, list)


# ---------------------------------------------------------------------------
# 3. AUTO happy path — kpi_alert
# ---------------------------------------------------------------------------


async def test_kpi_alert_auto_read_executes() -> None:
    """Confidence 0.95 → AUTO; get_portfolio_view called; one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.kpi_alert(make_kpi_intent(entity_id="ent-mgmt"))

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.halt_reason is None
    assert port.portfolio_calls == ["ent-mgmt"]
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "KPI_ALERT"
    assert outcome.result is not None


# ---------------------------------------------------------------------------
# 4. Unresolved process_ref → HALT_UNRESOLVED_PROCESS
# ---------------------------------------------------------------------------


async def test_unresolved_process_ref_blocks() -> None:
    """Empty process_id → unresolved; port NOT called; one lineage record."""
    agent, port, recorder = make_agent()
    outcome = await agent.generate_dashboard(make_dashboard_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert outcome.requires_hitl is True
    assert port.report_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_unresolved_process_ref_blocks_kpi_alert() -> None:
    """Unresolved ref halts kpi_alert; port not called."""
    agent, port, recorder = make_agent()
    outcome = await agent.kpi_alert(make_kpi_intent(resolved=False))

    assert outcome.executed is False
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.portfolio_calls == []


# ---------------------------------------------------------------------------
# 5. Out-of-scope op → REJECT_OUT_OF_SCOPE
# ---------------------------------------------------------------------------


async def test_out_of_scope_op_refused_generate_dashboard() -> None:
    """Mask scope = list+portfolio only; calling generate_dashboard is off-list."""
    agent, port, recorder = make_agent(
        mask=make_mask(
            scope=(
                "AnalyticsPort.list_available_reports",
                "AnalyticsPort.get_portfolio_view",
            )
        )
    )
    outcome = await agent.generate_dashboard(make_dashboard_intent())

    assert outcome.executed is False
    assert outcome.halt_reason == "out_of_scope"
    assert port.report_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


async def test_out_of_scope_op_refused_list_dashboards() -> None:
    """Mask scope = get_report only; list_dashboards is refused."""
    agent, port, recorder = make_agent(mask=make_mask(scope=("AnalyticsPort.get_report",)))
    outcome = await agent.list_dashboards(make_list_intent())

    assert outcome.executed is False
    assert outcome.halt_reason == "out_of_scope"
    assert port.listing_calls == []


# ---------------------------------------------------------------------------
# 6. Below-AUTO band (REVIEW) → HALT_REVIEW_DEFERRED, requires_hitl, port NOT called
# ---------------------------------------------------------------------------


async def test_below_auto_band_halts_review_deferred() -> None:
    """Confidence 0.80 is in REVIEW band (0.70–0.90); reads are AUTO-only (L1-Auto)."""
    agent, port, recorder = make_agent()
    outcome = await agent.generate_dashboard(make_dashboard_intent(confidence=0.80))

    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert port.report_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_review_band_boundary_at_floor() -> None:
    """Confidence exactly at review_floor (0.70) → REVIEW → HALT_REVIEW_DEFERRED."""
    agent, port, recorder = make_agent()
    outcome = await agent.list_dashboards(make_list_intent(confidence=0.70))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"
    assert port.listing_calls == []


# ---------------------------------------------------------------------------
# 7. Low confidence (<0.70) → BLOCK_LOW_CONFIDENCE
# ---------------------------------------------------------------------------


async def test_block_low_confidence_generate_dashboard() -> None:
    """Confidence 0.50 < 0.70 → BLOCK; port NOT called."""
    agent, port, recorder = make_agent()
    outcome = await agent.generate_dashboard(make_dashboard_intent(confidence=0.50))

    assert outcome.executed is False
    assert outcome.halt_reason == "low_confidence"
    assert outcome.requires_hitl is True
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.report_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_kpi_alert() -> None:
    """Confidence 0.00 → BLOCK on kpi_alert."""
    agent, port, recorder = make_agent()
    outcome = await agent.kpi_alert(make_kpi_intent(confidence=0.00))

    assert outcome.executed is False
    assert outcome.halt_reason == "low_confidence"
    assert port.portfolio_calls == []


# ---------------------------------------------------------------------------
# 8. Per-request token cost-cap breach → HALT_COST_CAP_BREACH
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_tokens_breach() -> None:
    """tokens=100 > max_request_tokens=5 → breach; port NOT called."""
    tight_cap = CostCap(
        max_request_tokens=5,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, port, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.generate_dashboard(make_dashboard_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.report_calls == []
    assert len(recorder.records) == 1
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 9. Per-request monetary cost-cap breach → HALT_COST_CAP_BREACH
# ---------------------------------------------------------------------------


async def test_per_request_cost_cap_monetary_breach() -> None:
    """cost=0.10 > max_request_cost=0.001 → breach; port NOT called."""
    tight_cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("0.001"),
        max_window_tokens=100_000,
        max_window_cost=Decimal("9999.00"),
    )
    agent, port, recorder = make_agent(mask=make_mask(cost_cap=tight_cap))
    outcome = await agent.generate_dashboard(make_dashboard_intent(cost="0.10"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.report_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH


# ---------------------------------------------------------------------------
# 10. Per-window cost-cap breach → HALT_COST_CAP_BREACH
# ---------------------------------------------------------------------------


async def test_per_window_token_cap_breach() -> None:
    """Window nearly full on tokens; next request overflows → breach."""
    window = CostWindow(used_tokens=9990, used_cost=Decimal("0.00"), window_ref="bi_agent:test")
    agent, port, recorder = make_agent(window=window)
    outcome = await agent.generate_dashboard(make_dashboard_intent(tokens=100))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.report_calls == []
    assert len(recorder.records) == 1


async def test_per_window_monetary_cost_cap_breach() -> None:
    """Window nearly full on cost; next request overflows → breach."""
    window = CostWindow(used_tokens=0, used_cost=Decimal("9.99"), window_ref="bi_agent:test")
    cap = CostCap(
        max_request_tokens=1_000_000,
        max_request_cost=Decimal("999.00"),
        max_window_tokens=1_000_000,
        max_window_cost=Decimal("10.00"),
    )
    agent, port, recorder = make_agent(mask=make_mask(cost_cap=cap), window=window)
    outcome = await agent.generate_dashboard(make_dashboard_intent(tokens=1, cost="0.02"))

    assert outcome.executed is False
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.report_calls == []


# ---------------------------------------------------------------------------
# 11. Compliance FAIL → BLOCK + escalate to DPO
# ---------------------------------------------------------------------------


async def test_compliance_fail_blocks_escalates_to_dpo() -> None:
    """PII FAIL → HALT_COMPLIANCE_BLOCK; escalated_to = DPO."""
    agent, port, recorder = make_agent()
    outcome = await agent.generate_dashboard(
        make_dashboard_intent(),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "DPO"
    assert outcome.requires_hitl is True
    assert port.report_calls == []
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.escalated_to == "DPO"
    assert rec.action_taken == "HALT_COMPLIANCE_BLOCK"
    assert rec.compliance_result is ComplianceResult.FAIL


# ---------------------------------------------------------------------------
# 12. Compliance ESCALATE → BLOCK + escalate to DPO
# ---------------------------------------------------------------------------


async def test_compliance_escalate_blocks_escalates_to_dpo() -> None:
    """PII ESCALATE also halts and escalates to DPO."""
    agent, port, recorder = make_agent()
    outcome = await agent.kpi_alert(
        make_kpi_intent(),
        compliance_result=ComplianceResult.ESCALATE,
    )

    assert outcome.executed is False
    assert outcome.halt_reason == "compliance_block"
    assert outcome.escalated_to == "DPO"
    assert port.portfolio_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"


async def test_compliance_fail_list_dashboards_escalates_to_dpo() -> None:
    """PII FAIL on list_dashboards → BLOCK + escalated to DPO."""
    agent, port, recorder = make_agent()
    outcome = await agent.list_dashboards(
        make_list_intent(),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.executed is False
    assert outcome.escalated_to == "DPO"
    assert port.listing_calls == []


# ---------------------------------------------------------------------------
# 13. Compliance NA → gate passes (NA is treated same as PASS)
# ---------------------------------------------------------------------------


async def test_compliance_na_does_not_block() -> None:
    """ComplianceResult.NA passes the compliance gate — not a failure."""
    agent, port, recorder = make_agent()
    outcome = await agent.generate_dashboard(
        make_dashboard_intent(),
        compliance_result=ComplianceResult.NA,
    )

    assert outcome.executed is True
    assert outcome.halt_reason is None
    assert port.report_calls != []


# ---------------------------------------------------------------------------
# 14. Custom DPO role from mask config-as-data
# ---------------------------------------------------------------------------


async def test_custom_dpo_role_used_on_compliance_fail() -> None:
    """dpo_role config-as-data is used for escalation — not hardcoded."""
    agent, port, recorder = make_agent(mask=make_mask(dpo_role="DataProtectionOfficer"))
    outcome = await agent.generate_dashboard(
        make_dashboard_intent(),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.escalated_to == "DataProtectionOfficer"
    assert recorder.records[0].escalated_to == "DataProtectionOfficer"


# ---------------------------------------------------------------------------
# 15. AnalyticsPortError → lineage emitted (executed=False) then re-raised
# ---------------------------------------------------------------------------


async def test_port_error_emits_lineage_then_reraises_get_report() -> None:
    """AnalyticsPortError: one lineage record with HALT_PROVIDER_ERROR; error re-raised."""
    err = AnalyticsPortError("ClickHouse connection failed", correlation_id="corr-err-001")
    port = FakeBIAnalyticsPort(report_raises=err)
    agent, port, recorder = make_agent(port=port)

    with pytest.raises(AnalyticsPortError, match="ClickHouse connection failed"):
        await agent.generate_dashboard(make_dashboard_intent(report_id="rep-err"))

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert "HALT_PROVIDER_ERROR" in rec.action_taken
    assert "AnalyticsPortError" in rec.action_taken
    assert port.report_calls == ["rep-err"]


async def test_port_error_emits_lineage_then_reraises_portfolio() -> None:
    """AnalyticsPortError on kpi_alert: lineage emitted (executed=False) then re-raised."""
    err = AnalyticsPortError("Timeout reading portfolio", correlation_id="corr-err-002")
    port = FakeBIAnalyticsPort(portfolio_raises=err)
    agent, port, recorder = make_agent(port=port)

    with pytest.raises(AnalyticsPortError):
        await agent.kpi_alert(make_kpi_intent(entity_id="ent-err"))

    assert len(recorder.records) == 1
    assert "HALT_PROVIDER_ERROR" in recorder.records[0].action_taken
    assert port.portfolio_calls == ["ent-err"]


async def test_port_error_emits_lineage_then_reraises_listing() -> None:
    """AnalyticsPortError on list_dashboards: lineage emitted then re-raised."""
    err = AnalyticsPortError("Report catalogue unavailable", correlation_id="corr-err-003")
    port = FakeBIAnalyticsPort(listing_raises=err)
    agent, port, recorder = make_agent(port=port)

    with pytest.raises(AnalyticsPortError):
        await agent.list_dashboards(make_list_intent(entity_id="ent-err-list"))

    assert len(recorder.records) == 1
    assert "HALT_PROVIDER_ERROR" in recorder.records[0].action_taken


# ---------------------------------------------------------------------------
# 16. Confidence out of [0, 1] → ValueError, NO lineage record
# ---------------------------------------------------------------------------


async def test_invalid_confidence_above_range_raises_no_record() -> None:
    """confidence=1.1 → ValueError; _evaluate raises before any lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.generate_dashboard(make_dashboard_intent(confidence=1.1))
    assert len(recorder.records) == 0


async def test_invalid_confidence_below_range_raises_no_record() -> None:
    """confidence=-0.01 → ValueError; no lineage record."""
    agent, _, recorder = make_agent()
    with pytest.raises(ValueError, match="confidence_score"):
        await agent.kpi_alert(make_kpi_intent(confidence=-0.01))
    assert len(recorder.records) == 0


# ---------------------------------------------------------------------------
# 17. R-SEC: no raw report content in any lineage record field (R-SEC-NEW-01)
# ---------------------------------------------------------------------------


async def test_no_raw_report_content_in_lineage_record() -> None:
    """Report content sentinel MUST NOT appear in any AgentDecisionRecord field."""
    pii_sentinel = "SECRET-KPI-PAYLOAD-7654321"
    fake_report = ReportView(
        report_id="rep-rsec-001",
        entity_id="ent-rsec-001",
        title=pii_sentinel,  # PII-bearing field behind the port
        format=ReportFormat.PDF,
    )
    port = FakeBIAnalyticsPort(report=fake_report)
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.generate_dashboard(make_dashboard_intent(report_id="rep-rsec-001"))

    # The report content is delivered to the caller via result …
    assert outcome.result is fake_report

    rec = recorder.records[0]
    sentinel_str = pii_sentinel
    assert sentinel_str not in rec.triggering_event
    assert sentinel_str not in rec.intent
    assert sentinel_str not in rec.reasoning_summary
    assert sentinel_str not in rec.action_taken
    assert all(sentinel_str not in p for p in rec.policies_evaluated)
    # triggering_event uses only the opaque report_id
    assert "rep-rsec-001" in rec.triggering_event


async def test_no_raw_portfolio_value_in_lineage_record() -> None:
    """Portfolio value sentinel MUST NOT appear in any lineage record field."""
    sentinel_value = Decimal("87654321.99")
    fake_portfolio = PortfolioView(
        entity_id="ent-rsec-002",
        total_value=sentinel_value,
        currency="GBP",
    )
    port = FakeBIAnalyticsPort(portfolio=fake_portfolio)
    agent, _, recorder = make_agent(port=port)

    outcome = await agent.kpi_alert(make_kpi_intent(entity_id="ent-rsec-002"))

    assert outcome.result is fake_portfolio
    rec = recorder.records[0]
    sentinel_str = str(sentinel_value)
    assert sentinel_str not in rec.triggering_event
    assert sentinel_str not in rec.reasoning_summary
    assert rec.cost_amount != sentinel_value


# ---------------------------------------------------------------------------
# 18. Lineage-per-action (ADR-046): exactly 1 record per call on every exit path
# ---------------------------------------------------------------------------


async def test_lineage_one_record_per_call_adr046() -> None:
    """Every action call (succeed or halt) emits exactly 1 record; total increments by 1."""
    agent, _, recorder = make_agent()

    assert len(recorder.records) == 0
    await agent.generate_dashboard(make_dashboard_intent(report_id="rep-A"))
    assert len(recorder.records) == 1

    await agent.list_dashboards(make_list_intent(entity_id="ent-B"))
    assert len(recorder.records) == 2

    await agent.kpi_alert(make_kpi_intent(entity_id="ent-C"))
    assert len(recorder.records) == 3

    # Halted path also emits exactly 1 record.
    await agent.generate_dashboard(make_dashboard_intent(resolved=False))
    assert len(recorder.records) == 4

    # Scope-refused also emits exactly 1 record.
    agent2, _, recorder2 = make_agent(
        mask=make_mask(scope=("AnalyticsPort.list_available_reports",))
    )
    await agent2.generate_dashboard(make_dashboard_intent())
    assert len(recorder2.records) == 1


# ---------------------------------------------------------------------------
# 19. Cost window accumulates only on successful reads (executed=True)
# ---------------------------------------------------------------------------


async def test_window_accumulates_on_successful_reads() -> None:
    """Window.used_tokens / used_cost increment per successful port call."""
    window = CostWindow(window_ref="bi_agent:test")
    agent, _, _ = make_agent(window=window)

    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")
    await agent.generate_dashboard(make_dashboard_intent(tokens=50, cost="0.05"))
    assert window.used_tokens == 50
    assert window.used_cost == Decimal("0.05")

    await agent.list_dashboards(make_list_intent(tokens=30, cost="0.03"))
    assert window.used_tokens == 80
    assert window.used_cost == Decimal("0.08")

    await agent.kpi_alert(make_kpi_intent(tokens=20, cost="0.02"))
    assert window.used_tokens == 100
    assert window.used_cost == Decimal("0.10")


async def test_window_not_accumulated_on_halt() -> None:
    """A halted call (e.g., unresolved ref) MUST NOT advance the window."""
    window = CostWindow(window_ref="bi_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.generate_dashboard(make_dashboard_intent(resolved=False))
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


async def test_window_not_accumulated_on_compliance_fail() -> None:
    """A compliance-blocked call MUST NOT advance the window."""
    window = CostWindow(window_ref="bi_agent:test")
    agent, _, _ = make_agent(window=window)

    await agent.generate_dashboard(make_dashboard_intent(), compliance_result=ComplianceResult.FAIL)
    assert window.used_tokens == 0
    assert window.used_cost == Decimal("0")


# ---------------------------------------------------------------------------
# 20. Port NOT called on band halt
# ---------------------------------------------------------------------------


async def test_port_not_called_on_review_band_halt() -> None:
    """REVIEW band halt must not invoke the port (L1-Auto: reads are AUTO-only)."""
    agent, port, _ = make_agent()
    await agent.generate_dashboard(make_dashboard_intent(confidence=0.75))
    assert port.report_calls == []


async def test_port_not_called_on_block_band() -> None:
    """BLOCK band must not invoke the port."""
    agent, port, _ = make_agent()
    await agent.list_dashboards(make_list_intent(confidence=0.40))
    assert port.listing_calls == []


# ---------------------------------------------------------------------------
# 21. ADR-046 lineage record field invariants
# ---------------------------------------------------------------------------


async def test_lineage_record_field_invariants() -> None:
    """Every lineage record satisfies the ADR-046 structural invariants."""
    agent, _, recorder = make_agent()
    await agent.generate_dashboard(make_dashboard_intent(report_id="rep-fields"))

    rec = recorder.records[0]
    assert rec.record_id  # non-empty UUID
    assert rec.timestamp.tzinfo is not None  # timezone-aware (UTC)
    assert rec.agent_id == "bi_agent"
    assert rec.triggering_event == "generate_dashboard:rep-fields"
    assert rec.intent == "generate management dashboard for Q1"
    assert rec.correlation_id == "corr-dash-001"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 10
    assert rec.cost_amount == Decimal("0.01")
    assert rec.budget_window_ref == "bi_agent:default"
    assert rec.human_reviewed_by is None  # L1-Auto: never a reviewer


# ---------------------------------------------------------------------------
# 22. In-memory e2e happy path — full flow (real BIMask, FakeBIAnalyticsPort)
# ---------------------------------------------------------------------------


async def test_in_memory_e2e_generate_dashboard() -> None:
    """Full e2e: real BIMask + FakeBIAnalyticsPort → AUTO report read with lineage."""
    fake_report = ReportView(
        report_id="rep-e2e-bi-001",
        entity_id="ent-e2e-bi-001",
        title="CEO Q1 Dashboard",
        format=ReportFormat.PDF,
    )
    port = FakeBIAnalyticsPort(report=fake_report)
    recorder = FakeRecorder()
    mask = BIMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
        agent_id="bi_agent",
        dpo_role="DPO",
    )
    agent = BIAgent(analytics_port=port, recorder=recorder, mask=mask)
    intent = GenerateDashboardIntent(
        intent_text="Generate CEO Q1 management dashboard",
        process_ref=ProcessRef(process_id="proc-e2e-bi-001", version="1.0"),
        report_id="rep-e2e-bi-001",
        correlation_id="e2e-corr-bi-001",
        confidence_score=0.97,
        request_cost=RequestCost(tokens=100, cost=Decimal("0.10")),
    )
    outcome = await agent.generate_dashboard(intent)

    assert outcome.executed is True
    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.result is fake_report
    assert outcome.halt_reason is None
    assert outcome.requires_hitl is False
    assert outcome.escalated_to is None
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.agent_id == "bi_agent"
    assert rec.correlation_id == "e2e-corr-bi-001"
    assert rec.compliance_result is ComplianceResult.PASS
    assert rec.budget_breach_flag is BudgetBreach.NONE
    assert rec.triggering_event == "generate_dashboard:rep-e2e-bi-001"
    assert rec.human_reviewed_by is None  # L1-Auto: never a reviewer


async def test_in_memory_e2e_list_dashboards() -> None:
    """Full e2e: real BIMask + FakeBIAnalyticsPort → AUTO listing with lineage."""
    descriptors = [
        ReportDescriptor(report_id="rep-list-001", title="Monthly P&L", format=ReportFormat.PDF),
        ReportDescriptor(report_id="rep-list-002", title="Cash Flow", format=ReportFormat.CSV),
    ]
    port = FakeBIAnalyticsPort(listing=descriptors)
    recorder = FakeRecorder()
    mask = BIMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
    )
    agent = BIAgent(analytics_port=port, recorder=recorder, mask=mask)
    intent = ListDashboardsIntent(
        intent_text="List all available BI dashboards for CFO",
        process_ref=ProcessRef(process_id="proc-e2e-bi-002", version="1.0"),
        entity_id="ent-e2e-bi-002",
        correlation_id="e2e-corr-bi-002",
        confidence_score=0.94,
        request_cost=RequestCost(tokens=50, cost=Decimal("0.05")),
    )
    outcome = await agent.list_dashboards(intent)

    assert outcome.executed is True
    assert outcome.halt_reason is None
    assert outcome.result == descriptors
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.triggering_event == "list_dashboards:ent-e2e-bi-002"
    assert rec.action_taken == "LIST_DASHBOARDS"


async def test_in_memory_e2e_kpi_alert() -> None:
    """Full e2e: real BIMask + FakeBIAnalyticsPort → AUTO portfolio KPI read with lineage."""
    portfolio = PortfolioView(
        entity_id="ent-e2e-bi-003",
        total_value=Decimal("1_250_000.00"),
        currency="GBP",
    )
    port = FakeBIAnalyticsPort(portfolio=portfolio)
    recorder = FakeRecorder()
    mask = BIMask(
        cost_cap=CostCap(
            max_request_tokens=500,
            max_request_cost=Decimal("0.50"),
            max_window_tokens=50_000,
            max_window_cost=Decimal("50.00"),
        ),
    )
    agent = BIAgent(analytics_port=port, recorder=recorder, mask=mask)
    intent = KpiAlertIntent(
        intent_text="KPI alert for C-suite portfolio review",
        process_ref=ProcessRef(process_id="proc-e2e-bi-003", version="1.0"),
        entity_id="ent-e2e-bi-003",
        correlation_id="e2e-corr-bi-003",
        confidence_score=0.96,
        request_cost=RequestCost(tokens=75, cost=Decimal("0.07")),
    )
    outcome = await agent.kpi_alert(intent)

    assert outcome.executed is True
    assert outcome.halt_reason is None
    assert outcome.result is portfolio
    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.triggering_event == "kpi_alert:ent-e2e-bi-003"
    assert rec.action_taken == "KPI_ALERT"


# ---------------------------------------------------------------------------
# 23. Confidence band boundary parametrisation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("confidence", "expected_decision"),
    [
        (0.91, ConfirmationDecision.AUTO),  # above auto_threshold
        (0.90, ConfirmationDecision.REVIEW),  # at auto_threshold — not strictly above
        (0.70, ConfirmationDecision.REVIEW),  # at review_floor
        (0.6999, ConfirmationDecision.BLOCK),  # below review_floor
    ],
)
async def test_confidence_band_boundaries(
    confidence: float, expected_decision: ConfirmationDecision
) -> None:
    agent, _, recorder = make_agent()
    outcome = await agent.generate_dashboard(make_dashboard_intent(confidence=confidence))
    assert outcome.decision is expected_decision
