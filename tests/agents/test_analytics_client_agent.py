"""Tests for the ADR-054 Analytics / Reporting (C7) mask agent
(services/agents/analytics_agent.py — the client-facing AnalyticsClientAgent).

Covers every mask path in the §D2 gate-chain order: AUTO reads (spending summary,
portfolio view, report, listing) and their PII-fail → BLOCK + DPO escalation; the
below-AUTO read re-check halt; request_export AUTO, the data-egress override → forced
REVIEW HITL hold then proceed-with-reviewer (regardless of confidence), the port
materiality guard ExportTooLarge → recorded-then-raised, the egress-compliance fail →
BLOCK + egress escalation; cost-cap breach (per-request token-heavy AND per-window);
BLOCK on low confidence; unresolved process_ref; out-of-scope refusal; the no-raw-PII-in-
lineage R-SEC guarantee; and the lineage-per-action obligation (ADR-046). The port and the
recorder are fakes — the agent is exercised as pure governance logic with no live infra and
NO dependency on the domain reporting_analytics implementation.
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.agents.analytics_agent import (
    AgentDecisionRecord,
    AnalyticsClientAgent,
    AnalyticsMask,
    AutonomyLevel,
    BudgetBreach,
    ComplianceOverlay,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    GetReportIntent,
    ListReportsIntent,
    PortfolioViewIntent,
    ProcessRef,
    RequestCost,
    RequestExportIntent,
    SpendingSummaryIntent,
)
from services.reporting_analytics.analytics_port import (
    AnalyticsPort,
    ComplianceBlock,
    ExportRequest,
    ExportResult,
    ExportStatus,
    ExportTooLarge,
    PortfolioView,
    ReportDescriptor,
    ReportFormat,
    ReportNotFound,
    ReportView,
    SpendingSummary,
    SpendPeriod,
)

# ── Fakes (the port & sink are injected interfaces; never implemented in services) ──


class FakeRecorder(DecisionRecorder):
    def __init__(self) -> None:
        self.records: list[AgentDecisionRecord] = []

    async def record(self, record: AgentDecisionRecord) -> None:
        self.records.append(record)


class FakeAnalyticsPort(AnalyticsPort):
    """In-test AnalyticsPort double. Records calls; returns canned read-only results or
    raises a configured AnalyticsPortError so the agent's governance logic is exercised
    without any live reporting_analytics adapter."""

    def __init__(
        self,
        *,
        summary: SpendingSummary | None = None,
        portfolio: PortfolioView | None = None,
        report: ReportView | None = None,
        listing: list[ReportDescriptor] | None = None,
        export_result: ExportResult | None = None,
        export_raises: Exception | None = None,
        report_raises: Exception | None = None,
    ) -> None:
        self._summary = summary or SpendingSummary(
            entity_id="ent-1",
            period=SpendPeriod.MONTH,
            total=Decimal("100.00"),
            currency="EUR",
            by_category={"groceries": Decimal("100.00")},
        )
        self._portfolio = portfolio or PortfolioView(
            entity_id="ent-1", total_value=Decimal("5000.00"), currency="EUR"
        )
        self._report = report or ReportView(
            report_id="rep-1", entity_id="ent-1", title="Q1", format=ReportFormat.PDF
        )
        self._listing = (
            listing
            if listing is not None
            else [ReportDescriptor(report_id="rep-1", title="Q1", format=ReportFormat.PDF)]
        )
        self._export_result = export_result or ExportResult(
            report_id="rep-1",
            format=ReportFormat.CSV,
            status=ExportStatus.READY,
            size_bytes=1024,
            file_hash="abc123",
        )
        self._export_raises = export_raises
        self._report_raises = report_raises
        self.summary_calls: list[tuple[str, SpendPeriod]] = []
        self.portfolio_calls: list[str] = []
        self.report_calls: list[str] = []
        self.listing_calls: list[str] = []
        self.export_calls: list[ExportRequest] = []

    async def get_spending_summary(self, entity_id: str, period: SpendPeriod) -> SpendingSummary:
        self.summary_calls.append((entity_id, period))
        return self._summary

    async def get_portfolio_view(self, entity_id: str) -> PortfolioView:
        self.portfolio_calls.append(entity_id)
        return self._portfolio

    async def get_report(self, report_id: str) -> ReportView:
        self.report_calls.append(report_id)
        if self._report_raises is not None:
            raise self._report_raises
        return self._report

    async def list_available_reports(self, entity_id: str) -> list[ReportDescriptor]:
        self.listing_calls.append(entity_id)
        return self._listing

    async def request_export(self, request: ExportRequest) -> ExportResult:
        self.export_calls.append(request)
        if self._export_raises is not None:
            raise self._export_raises
        return self._export_result


# ── Builders ──────────────────────────────────────────────────────────────────


def make_mask(**overrides) -> AnalyticsMask:
    base = {
        "cost_cap": CostCap(
            max_request_tokens=50_000,
            max_request_cost=Decimal("1.00"),
            max_window_tokens=500_000,
            max_window_cost=Decimal("10.00"),
        ),
    }
    base.update(overrides)
    return AnalyticsMask(**base)


def make_agent(
    *,
    mask: AnalyticsMask | None = None,
    port: FakeAnalyticsPort | None = None,
    recorder: FakeRecorder | None = None,
    cost_window: CostWindow | None = None,
) -> tuple[AnalyticsClientAgent, FakeAnalyticsPort, FakeRecorder]:
    port = port or FakeAnalyticsPort()
    recorder = recorder or FakeRecorder()
    agent = AnalyticsClientAgent(
        analytics_port=port,
        recorder=recorder,
        mask=mask or make_mask(),
        cost_window=cost_window,
    )
    return agent, port, recorder


def _ref(resolved: bool = True) -> ProcessRef:
    return (
        ProcessRef(process_id="PROC-ANALYTICS", version="1")
        if resolved
        else ProcessRef(process_id="", version="")
    )


def make_summary_intent(
    *, confidence: float = 0.99, cost: RequestCost | None = None, resolved: bool = True
) -> SpendingSummaryIntent:
    return SpendingSummaryIntent(
        intent_text="Show my spending this month",
        process_ref=_ref(resolved),
        entity_id="ent-1",
        period=SpendPeriod.MONTH,
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=2_000, cost=Decimal("0.04")),
    )


def make_portfolio_intent(*, confidence: float = 0.99) -> PortfolioViewIntent:
    return PortfolioViewIntent(
        intent_text="Show my portfolio",
        process_ref=_ref(),
        entity_id="ent-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=1_500, cost=Decimal("0.03")),
    )


def make_report_intent(*, confidence: float = 0.99) -> GetReportIntent:
    return GetReportIntent(
        intent_text="Open my Q1 report",
        process_ref=_ref(),
        report_id="rep-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=500, cost=Decimal("0.01")),
    )


def make_listing_intent(*, confidence: float = 0.99) -> ListReportsIntent:
    return ListReportsIntent(
        intent_text="What reports can I see?",
        process_ref=_ref(),
        entity_id="ent-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=RequestCost(tokens=300, cost=Decimal("0.006")),
    )


def make_export_intent(
    *,
    confidence: float = 0.99,
    cost: RequestCost | None = None,
    sensitive: bool = False,
    include_pii: bool = False,
) -> RequestExportIntent:
    return RequestExportIntent(
        intent_text="Export my Q1 report",
        process_ref=_ref(),
        entity_id="ent-1",
        report_id="rep-1",
        format=ReportFormat.CSV,
        actor="user-1",
        correlation_id="corr-1",
        confidence_score=confidence,
        request_cost=cost or RequestCost(tokens=3_000, cost=Decimal("0.05")),
        include_pii=include_pii,
        data_egress_sensitive=sensitive,
    )


# ── AUTO reads ────────────────────────────────────────────────────────────────


async def test_spending_summary_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.get_spending_summary(make_summary_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_hitl is False
    assert outcome.requires_step_up is False
    assert port.summary_calls == [("ent-1", SpendPeriod.MONTH)]
    assert outcome.result.total == Decimal("100.00")
    assert recorder.records[0].action_taken == "GET_SPENDING_SUMMARY"
    assert len(recorder.records) == 1


async def test_portfolio_view_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.get_portfolio_view(make_portfolio_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.portfolio_calls == ["ent-1"]
    assert outcome.result.total_value == Decimal("5000.00")
    assert recorder.records[0].action_taken == "GET_PORTFOLIO_VIEW"


async def test_get_report_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.get_report(make_report_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.report_calls == ["rep-1"]
    assert outcome.result.report_id == "rep-1"
    assert recorder.records[0].action_taken == "GET_REPORT"


async def test_list_available_reports_auto_read_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.list_available_reports(make_listing_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert port.listing_calls == ["ent-1"]
    assert outcome.result[0].report_id == "rep-1"
    assert recorder.records[0].action_taken == "LIST_AVAILABLE_REPORTS"


# ── PII overlay (ADR-016) on reads → BLOCK + DPO ──────────────────────────────


async def test_spending_summary_pii_fail_blocks_and_escalates_dpo():
    agent, port, recorder = make_agent()
    outcome = await agent.get_spending_summary(
        make_summary_intent(), compliance_result=ComplianceResult.FAIL
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "DPO"
    assert port.summary_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL
    assert recorder.records[0].escalated_to == "DPO"


async def test_portfolio_view_pii_fail_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.get_portfolio_view(make_portfolio_intent())
    assert outcome.executed is True  # baseline PASS
    out2 = await agent.get_portfolio_view(
        make_portfolio_intent(), compliance_result=ComplianceResult.ESCALATE
    )
    assert out2.decision is ConfirmationDecision.BLOCK
    assert out2.escalated_to == "DPO"
    assert recorder.records[-1].action_taken == "HALT_COMPLIANCE_BLOCK"


# ── below-AUTO read re-check halt ─────────────────────────────────────────────


async def test_spending_summary_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.get_spending_summary(make_summary_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.halt_reason == "review_deferred"
    assert port.summary_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


async def test_get_report_below_auto_halts_for_recheck():
    agent, port, recorder = make_agent()
    outcome = await agent.get_report(make_report_intent(confidence=0.85))
    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.halt_reason == "review_deferred"
    assert port.report_calls == []
    assert recorder.records[0].action_taken == "HALT_REVIEW_DEFERRED"


# ── request_export: AUTO, data-egress REVIEW, ExportTooLarge, egress fail ──────


async def test_export_auto_small_executes():
    agent, port, recorder = make_agent()
    outcome = await agent.request_export(make_export_intent(confidence=0.99, sensitive=False))

    assert outcome.decision is ConfirmationDecision.AUTO
    assert outcome.executed is True
    assert outcome.requires_step_up is False
    assert len(port.export_calls) == 1
    assert outcome.result.status is ExportStatus.READY
    assert recorder.records[0].action_taken == "REQUEST_EXPORT"


async def test_export_sensitive_forces_review_hold_even_at_auto_confidence():
    agent, port, recorder = make_agent()
    outcome = await agent.request_export(make_export_intent(confidence=0.99, sensitive=True))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert outcome.requires_step_up is False  # NO biometric — data-egress, not money movement
    assert outcome.halt_reason == "hitl_review_required"
    assert port.export_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert recorder.records[0].human_reviewed_by is None
    assert "ADR-054-data-egress-REVIEW" in recorder.records[0].policies_evaluated


async def test_export_sensitive_proceeds_with_reviewer():
    agent, port, recorder = make_agent()
    outcome = await agent.request_export(
        make_export_intent(confidence=0.99, sensitive=True),
        human_reviewed_by="dpo@banxe",
    )

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is True
    assert len(port.export_calls) == 1
    assert recorder.records[0].action_taken == "REQUEST_EXPORT"
    assert recorder.records[0].human_reviewed_by == "dpo@banxe"


async def test_export_low_confidence_review_band_holds_for_hitl():
    # A non-sensitive export in the REVIEW band still holds for HITL (export supports it).
    agent, port, recorder = make_agent()
    outcome = await agent.request_export(make_export_intent(confidence=0.80))

    assert outcome.decision is ConfirmationDecision.REVIEW
    assert outcome.executed is False
    assert outcome.requires_hitl is True
    assert port.export_calls == []
    assert recorder.records[0].action_taken == "HOLD_FOR_REVIEW"
    assert "ADR-054-data-egress-REVIEW" not in recorder.records[0].policies_evaluated


async def test_export_too_large_records_then_raises():
    # Port materiality guard fires (defense-in-depth): lineage emitted then re-raised.
    port = FakeAnalyticsPort(
        export_raises=ExportTooLarge("dataset over materiality", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ExportTooLarge):
        await agent.request_export(make_export_intent(confidence=0.99))

    assert len(recorder.records) == 1
    rec = recorder.records[0]
    assert rec.action_taken == "HALT_PROVIDER_ERROR:ExportTooLarge"
    assert rec.human_reviewed_by is None
    # The blocked export must NOT count against the window (executed=False).


async def test_export_egress_compliance_fail_blocks_and_escalates_egress():
    agent, port, recorder = make_agent(mask=make_mask(egress_role="ComplianceEgress"))
    outcome = await agent.request_export(
        make_export_intent(confidence=0.99, include_pii=True),
        compliance_result=ComplianceResult.FAIL,
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert outcome.escalated_to == "ComplianceEgress"
    assert port.export_calls == []
    assert recorder.records[0].action_taken == "HALT_COMPLIANCE_BLOCK"
    assert recorder.records[0].compliance_result is ComplianceResult.FAIL


async def test_export_port_compliance_block_records_then_raises():
    port = FakeAnalyticsPort(
        export_raises=ComplianceBlock("PII overlay forbade un-redacted export", correlation_id="c")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ComplianceBlock):
        await agent.request_export(make_export_intent(confidence=0.99, include_pii=True))
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:ComplianceBlock"


# ── get_report unknown → ReportNotFound recorded then raised ───────────────────


async def test_get_report_unknown_records_then_raises():
    port = FakeAnalyticsPort(
        report_raises=ReportNotFound("no such report", correlation_id="corr-1")
    )
    agent, port, recorder = make_agent(port=port)
    with pytest.raises(ReportNotFound):
        await agent.get_report(make_report_intent(confidence=0.99))
    assert recorder.records[0].action_taken == "HALT_PROVIDER_ERROR:ReportNotFound"


# ── cost-cap breach (token-heavy per-request AND per-window) ───────────────────


async def test_per_request_token_cap_breach_blocks():
    # Token-heavy aggregation must be refused before any port call (ADR-047 runaway guard).
    agent, port, recorder = make_agent()
    intent = make_summary_intent(cost=RequestCost(tokens=999_999, cost=Decimal("0.01")))
    outcome = await agent.get_spending_summary(intent)

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.summary_calls == []
    assert recorder.records[0].budget_breach_flag is BudgetBreach.BREACH
    assert recorder.records[0].action_taken == "HALT_COST_CAP_BREACH"


async def test_per_window_token_cap_breach_blocks():
    window = CostWindow(used_tokens=499_900, used_cost=Decimal("0.00"))
    agent, port, _ = make_agent(cost_window=window)
    outcome = await agent.get_spending_summary(
        make_summary_intent(cost=RequestCost(tokens=2_000, cost=Decimal("0.01")))
    )

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "cost_cap_breach"
    assert port.summary_calls == []


async def test_window_accumulates_on_successful_read():
    window = CostWindow()
    agent, _, _ = make_agent(cost_window=window)
    await agent.get_spending_summary(
        make_summary_intent(cost=RequestCost(tokens=2_000, cost=Decimal("0.04")))
    )
    assert window.used_tokens == 2_000
    assert window.used_cost == Decimal("0.04")


# ── BLOCK / scope / process resolution ─────────────────────────────────────────


async def test_block_low_confidence_export():
    agent, port, recorder = make_agent()
    outcome = await agent.request_export(make_export_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.executed is False
    assert port.export_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_block_low_confidence_read():
    agent, port, recorder = make_agent()
    outcome = await agent.get_spending_summary(make_summary_intent(confidence=0.40))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert port.summary_calls == []
    assert recorder.records[0].action_taken == "BLOCK_LOW_CONFIDENCE"


async def test_unresolved_process_ref_blocks():
    agent, port, recorder = make_agent()
    outcome = await agent.get_spending_summary(make_summary_intent(resolved=False))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "unresolved_process_ref"
    assert port.summary_calls == []
    assert recorder.records[0].action_taken == "HALT_UNRESOLVED_PROCESS"


async def test_out_of_scope_op_refused():
    # An op not on the mask allow-list is refused outright (ADR-054 §D1).
    agent, port, recorder = make_agent(mask=make_mask(scope=("AnalyticsPort.get_report",)))
    outcome = await agent.get_spending_summary(make_summary_intent(confidence=0.99))

    assert outcome.decision is ConfirmationDecision.BLOCK
    assert outcome.halt_reason == "out_of_scope"
    assert port.summary_calls == []
    assert recorder.records[0].action_taken == "REJECT_OUT_OF_SCOPE"


@pytest.mark.parametrize(
    ("confidence", "expected"),
    [
        (0.91, ConfirmationDecision.AUTO),
        (0.90, ConfirmationDecision.REVIEW),
        (0.70, ConfirmationDecision.REVIEW),
        (0.6999, ConfirmationDecision.BLOCK),
    ],
)
async def test_confidence_band_boundaries(confidence, expected):
    agent, _, _ = make_agent()
    outcome = await agent.request_export(
        make_export_intent(confidence=confidence), human_reviewed_by="dpo@banxe"
    )
    assert outcome.decision is expected


async def test_invalid_confidence_raises():
    agent, _, _ = make_agent()
    with pytest.raises(ValueError):
        await agent.get_spending_summary(make_summary_intent(confidence=1.5))


# ── R-SEC: no raw PII in any lineage record ────────────────────────────────────


async def test_no_raw_pii_in_lineage_records():
    """R-SEC (R-SEC-NEW-01): lineage carries only opaque entity_id / report_id. A PII-like
    sentinel reachable ONLY through the port's return value must never appear in any
    recorded AgentDecisionRecord field — the result rides on AgentOutcome.result, never on
    the record."""
    pii_sentinel = "IBAN-GB29-NWBK-SECRET-PII"
    # The port returns a result whose payload carries the sentinel; the entity/report ids
    # the agent records are opaque handles only.
    port = FakeAnalyticsPort(
        summary=SpendingSummary(
            entity_id="opaque-ent-7",
            period=SpendPeriod.MONTH,
            total=Decimal("1.00"),
            currency=pii_sentinel,  # stand-in for any PII-bearing field behind the port
            by_category={pii_sentinel: Decimal("1.00")},
        )
    )
    agent, port, recorder = make_agent(port=port)
    intent = SpendingSummaryIntent(
        intent_text="spending summary request",  # caller text — contains NO raw PII
        process_ref=_ref(),
        entity_id="opaque-ent-7",
        period=SpendPeriod.MONTH,
        correlation_id="corr-opaque-1",
        confidence_score=0.99,
        request_cost=RequestCost(tokens=2_000, cost=Decimal("0.04")),
    )
    outcome = await agent.get_spending_summary(intent)

    # The PII-bearing result is delivered to the caller …
    assert outcome.result.currency == pii_sentinel
    # … but NEVER recorded in lineage.
    rec = recorder.records[0]
    serialised = " ".join(
        str(v)
        for v in (
            rec.triggering_event,
            rec.intent,
            rec.reasoning_summary,
            rec.action_taken,
            rec.correlation_id,
            " ".join(rec.policies_evaluated),
            str(rec.human_reviewed_by),
        )
    )
    assert pii_sentinel not in serialised
    # Only the opaque entity_id is keyed into the lineage event.
    assert "opaque-ent-7" in rec.triggering_event


# ── Lineage obligation (ADR-046) ───────────────────────────────────────────────


async def test_lineage_record_emitted_per_action_with_adr046_fields():
    agent, _, recorder = make_agent()
    await agent.get_spending_summary(make_summary_intent())
    await agent.get_spending_summary(make_summary_intent(confidence=0.40))  # a halt also records
    assert len(recorder.records) == 2

    rec = recorder.records[0]
    assert rec.record_id
    assert rec.timestamp.tzinfo is not None
    assert rec.agent_id == "analytics_client_agent"
    assert rec.intent == "Show my spending this month"
    assert rec.correlation_id == "corr-1"
    assert rec.policies_evaluated  # non-empty ordered policy list
    assert 0.0 <= rec.confidence_score <= 1.0
    assert rec.cost_tokens == 2_000
    assert rec.cost_amount == Decimal("0.04")
    assert rec.budget_window_ref == "analytics_client_agent:default"


# ── Mask config-as-data ────────────────────────────────────────────────────────


async def test_mask_is_auto_biased_with_pii_and_egress_gate():
    mask = make_mask()
    assert mask.autonomy_level is AutonomyLevel.AUTO_BIASED
    assert mask.compliance_gate == ("PII", "DATA_EGRESS")
    assert mask.dpo_role == "DPO"
    assert mask.egress_role == "DPO"
    assert "AnalyticsPort.request_export" in mask.scope
    assert "AnalyticsPort.get_spending_summary" in mask.scope


async def test_compliance_overlay_routing_values():
    # PII overlay → DPO; data-egress overlay → egress role (escalation routing is overlay-keyed).
    assert ComplianceOverlay.PII.value == "PII"
    assert ComplianceOverlay.DATA_EGRESS.value == "DATA_EGRESS"


async def test_custom_pii_escalation_role_used():
    agent, _, _ = make_agent(mask=make_mask(dpo_role="DataOfficer"))
    pii = await agent.get_portfolio_view(
        make_portfolio_intent(), compliance_result=ComplianceResult.FAIL
    )
    assert pii.escalated_to == "DataOfficer"
