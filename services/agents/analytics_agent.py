"""AnalyticsClientAgent — L2 client-facing Analytics / Reporting agent (ADR-054 C7).

WHY: ADR-054 (Analytics / Reporting client-facing mask, C7 — the extended-catalogue
entry added via ADR-053 over ADR-049) specifies the governed surface through which a
resolved client intent becomes a bounded read / report / export action. This module is
the emi-stack sibling of ``services/agents/kyc_onboarding_agent.py``,
``notification_agent.py``, ``crm_agent.py`` and ``cards_agent.py`` and the analogue of
banxe-payment-core's ``src/agents/payments_agent.py`` — it implements the agent *logic*
and *governance enforcement* of the Analytics (C7) mask in front of the AnalyticsPort
CONTRACT.

NAME COLLISION (intentional, documented): the *domain* analytics agent lives at
``services/reporting_analytics/analytics_agent.py`` and sits BEHIND ``AnalyticsPort`` as
the adapter (untouched here, ADR-054 §D2 boundary). THIS module is the *client-facing*
agent in a different package (``services/agents``); its class is :class:`AnalyticsClientAgent`
to keep the two unambiguous. The client agent depends only on the ``AnalyticsPort``
INTERFACE (constructor injection) — never on the domain implementation.

This module does NOT implement the port (``services/reporting_analytics/analytics_port.py``
is the CONTRACT, the domain agent / ``data_aggregator`` / ``report_builder`` /
``export_engine`` / ``scheduled_reports`` / ``dashboard_metrics`` are UNTOUCHED), the
LLM-orchestration / routing layer (``AGENT_ROUTING_ENABLED`` stays out of scope — Terminal
A infra, ADR-049 §D6/§D7), or the ClickHouse lineage sink. The shared cost / lineage
primitives live in the canonical ``services/agents/_lineage.py`` and are imported, never
redefined (DRY / IL-135).

The Analytics (C7) mask (ADR-054), enforced here in the fixed ADR-049 §D2 chain order
(process_ref → scope → band → cost_cap → compliance(PII + data-egress) →
[step-up N/A] → port call; biometric step-up is N/A — no read / report / export moves
client funds, ADR-054 §D1):

* ``scope``               — ``AnalyticsPort`` operations only (the allow-list:
                            get_spending_summary / get_portfolio_view / get_report /
                            list_available_reports / request_export). The port is injected,
                            never implemented here; an op not on the allow-list is refused.
* ``autonomy_level``      — AUTO-biased (ADR-054): a routine read / summary / report
                            proceeds AUTO within cap. Only a large / sensitive export is
                            pulled down to REVIEW (the data-egress gate).
* ``confirmation_policy`` — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047
                            thresholds, ADR-049 §D4). **Override:** ``request_export`` of a
                            large / sensitive dataset (``data_egress_sensitive``) is forced
                            to the REVIEW band and held for a human reviewer regardless of
                            confidence (ADR-054 data-egress gate). NO biometric step-up —
                            data-egress is not a value-bearing action (ADR-054 §D1).
* ``cost_cap``            — per-request AND per-window hard caps, token AND monetary
                            (Decimal) dimensions (ADR-047 §D2). Emphasis on TOKEN caps:
                            analytics aggregation can be compute-heavy and must not run away.
* ``lineage_obligation``  — one ``AgentDecisionRecord`` per action (ADR-046), non-optional,
                            emitted on every exit path.
* ``compliance_gate``     — the PII overlay (ADR-016) + data-egress gate: the L3 check MUST
                            PASS before a port call; a non-PASS verdict halts (BLOCK). A PII
                            failure escalates to the DPO; a data-egress failure escalates to
                            the egress role (config-as-data, DPO by default).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence, large/sensitive
export REVIEW with no reviewer, cost-cap breach, compliance(PII/egress) fail} halts the
action (ADR-049 §D4 — independent halt conditions). The port's own data-egress materiality
guard (``ExportTooLarge``) and PII guard (``ComplianceBlock``) are defense-in-depth: if the
port raises, lineage is emitted (executed=False) and the error re-raised. Mask *values*
(caps, thresholds, scope, gate, escalation roles) are config-as-data (CLAUDE.md §10),
carried on :class:`AnalyticsMask`, never hardcoded in flow logic.

R-SEC (R-SEC-NEW-01, ADR-021): no raw PII ever enters a lineage record. Every entity /
report reference crossing this agent is an opaque ``entity_id`` / ``report_id``; the
triggering_event is keyed on those opaque handles only, and the port's PII-bearing return
value rides on ``AgentOutcome.result`` (the functional return) — NEVER on the recorded
``AgentDecisionRecord``.

LARGE / SENSITIVE EXPORT DETECTION (assumption, documented):
The "is this export large / sensitive?" classification is performed **upstream** (the
intent-resolution layer) and carried into the agent as a single structured boolean —
:attr:`RequestExportIntent.data_egress_sensitive`. The agent HONORS that signal and never
parses free text for size / sensitivity (fragile-regex detection is out of scope,
config-as-data per CLAUDE.md §10). The port enforces the same materiality as
defense-in-depth (``ExportTooLarge`` when the produced artefact crosses the configured
size), surfaced verbatim by re-raise.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
import uuid

from services.agents._lineage import (
    AgentDecisionRecord,
    AgentOutcome,
    BudgetBreach,
    ComplianceResult,
    ConfirmationDecision,
    CostCap,
    CostWindow,
    DecisionRecorder,
    ProcessRef,
    RequestCost,
)
from services.reporting_analytics.analytics_port import (
    AnalyticsPort,
    AnalyticsPortError,
    EntityId,
    ExportRequest,
    ReportFormat,
    ReportId,
    SpendPeriod,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3 / ADR-054). Analytics is AUTO-biased: routine
    reads / summaries / reports are AUTO-eligible within cap; only a large / sensitive
    export is forced down to REVIEW (the data-egress gate)."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


class ComplianceOverlay(StrEnum):
    """Which arm of the PII + data-egress gate is the primary escalation route for an
    action (ADR-054 compliance_gate). Both overlays gate every action; this selects the
    role a non-PASS verdict escalates to: PII → DPO, data-egress → the egress role."""

    PII = "PII"
    DATA_EGRESS = "DATA_EGRESS"


# ---------------------------------------------------------------------------
# Value types — mask config (the shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AnalyticsMask:
    """Config-as-data Analytics / Reporting (C7) mask (ADR-054). Values are governed
    config, not hardcoded flow logic; the AUTO/REVIEW/BLOCK *scale* is ADR-047 canon. The
    mask is the allow-list and the gate posture for the capability."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.AUTO_BIASED
    lineage_obligation: bool = True
    # Escalation roles (config-as-data, never hardcoded in flow logic): a PII-overlay
    # failure escalates to the DPO (ADR-016); a data-egress failure escalates to the
    # egress role (data-protection owner of the egress decision — DPO by default).
    dpo_role: str = "DPO"
    egress_role: str = "DPO"
    agent_id: str = "analytics_client_agent"

    # The mask scope (ADR-054 §D1 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "AnalyticsPort.get_spending_summary",
        "AnalyticsPort.get_portfolio_view",
        "AnalyticsPort.get_report",
        "AnalyticsPort.list_available_reports",
        "AnalyticsPort.request_export",
    )

    # L3 compliance contour required before any port call: PII + data-egress overlay.
    compliance_gate: tuple[str, ...] = ("PII", "DATA_EGRESS")


@dataclass
class SpendingSummaryIntent:
    """A resolved low-consequence read intent (``get_spending_summary``) — the mask's
    "reads are AUTO-eligible within cap" path (ADR-054). A read below the AUTO band halts
    for a re-check, not a HITL hold. The PII overlay (ADR-016) MUST PASS before the summary
    is returned; a non-PASS verdict blocks and escalates to the DPO. Aggregation can be
    token-heavy — the cost-cap bounds it (ADR-047)."""

    intent_text: str
    process_ref: ProcessRef
    entity_id: EntityId
    period: SpendPeriod
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class PortfolioViewIntent:
    """A resolved portfolio-read intent (``get_portfolio_view``) — AUTO-eligible within
    cap. The PII overlay (ADR-016) MUST PASS before the view is returned; a non-PASS verdict
    blocks and escalates to the DPO. A read below the AUTO band halts for a re-check."""

    intent_text: str
    process_ref: ProcessRef
    entity_id: EntityId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetReportIntent:
    """A resolved single-report read intent (``get_report``) — AUTO-eligible within cap.
    Report rows are PII-redacted by the adapter behind the port; the PII overlay still gates
    the read. An unknown report_id raises ``ReportNotFound`` from the port (recorded then
    re-raised). A read below the AUTO band halts for a re-check."""

    intent_text: str
    process_ref: ProcessRef
    report_id: ReportId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ListReportsIntent:
    """A resolved listing read intent (``list_available_reports``) — AUTO-eligible within
    cap. The PII overlay gates the read; a read below the AUTO band halts for a re-check."""

    intent_text: str
    process_ref: ProcessRef
    entity_id: EntityId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class RequestExportIntent:
    """A resolved client intent to export a report / dataset (``request_export``).

    AUTO-biased (ADR-054): a small / in-cap export proceeds AUTO. **Override:** when
    :attr:`data_egress_sensitive` is True the export is large / sensitive, so the action is
    forced to the REVIEW band (the data-egress gate) and held for a human reviewer regardless
    of confidence; supply ``human_reviewed_by`` to proceed. The large/sensitive classification
    is an upstream, structured signal — the agent honors it and never regex-parses text (see
    module docstring). NO biometric step-up applies — data-egress is not a value-bearing
    action (ADR-054 §D1). The PII + data-egress overlay (``compliance_result``) must PASS
    before the port is called; a non-PASS verdict blocks and escalates. The port's own
    materiality guard raises ``ExportTooLarge`` (recorded then re-raised) as defense-in-depth.
    """

    intent_text: str
    process_ref: ProcessRef
    entity_id: EntityId
    report_id: ReportId
    format: ReportFormat
    actor: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    include_pii: bool = False
    data_egress_sensitive: bool = False


# ---------------------------------------------------------------------------
# Internal evaluation
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
    """All inputs a single masked action evaluates against."""

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    triggering_event: str
    success_action: str
    op: str
    request_cost: RequestCost
    compliance_result: ComplianceResult
    # Which arm of the PII + data-egress gate is the primary escalation route on a
    # non-PASS verdict (PII → DPO, data-egress → egress role).
    compliance_overlay: ComplianceOverlay
    human_reviewed_by: str | None
    # An export supports a REVIEW-band HITL hold; a read is AUTO-only and instead halts
    # below the AUTO band. Defaults False so the read path is unchanged.
    supports_review_hitl: bool = False
    # Data-egress override: a large / sensitive export is forced to the REVIEW band and
    # held for a reviewer regardless of confidence (ADR-054 data-egress gate).
    force_review: bool = False


@dataclass
class _Evaluation:
    decision: ConfirmationDecision
    proceed: bool
    action_taken: str
    reasoning_summary: str
    policies: list[str]
    compliance_result: ComplianceResult
    budget_breach: BudgetBreach
    halt_reason: str | None = None
    requires_hitl: bool = False
    escalated_to: str | None = None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class AnalyticsClientAgent:
    """L2 client-facing analytics agent enforcing the ADR-054 Analytics (C7) mask.

    The :class:`AnalyticsPort` and the lineage recorder are injected as interfaces
    (constructor injection); the agent contains pure governance logic and is unit-testable
    without any live infra. It depends only on the AnalyticsPort CONTRACT, never on the
    domain ``reporting_analytics`` implementation behind it.
    """

    def __init__(
        self,
        *,
        analytics_port: AnalyticsPort,
        recorder: DecisionRecorder,
        mask: AnalyticsMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = analytics_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def get_spending_summary(
        self,
        intent: SpendingSummaryIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Aggregated spend read via ``AnalyticsPort.get_spending_summary`` — AUTO-eligible
        within cap (ADR-054). The PII overlay (``compliance_result``) must PASS before the
        summary is returned; a non-PASS verdict blocks and escalates to the DPO. A read below
        the AUTO band halts for a re-check, not a HITL hold. Aggregation is token-heavy — the
        cost-cap bounds it (ADR-047)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_spending_summary:{intent.entity_id}:{intent.period.value}",
            success_action="GET_SPENDING_SUMMARY",
            op="AnalyticsPort.get_spending_summary",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(
            ctx, lambda: self._port.get_spending_summary(intent.entity_id, intent.period)
        )

    async def get_portfolio_view(
        self,
        intent: PortfolioViewIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Portfolio read via ``AnalyticsPort.get_portfolio_view`` — AUTO-eligible within
        cap. The PII overlay must PASS before the view is returned; a non-PASS verdict blocks
        and escalates to the DPO. A read below the AUTO band halts for a re-check."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_portfolio_view:{intent.entity_id}",
            success_action="GET_PORTFOLIO_VIEW",
            op="AnalyticsPort.get_portfolio_view",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.get_portfolio_view(intent.entity_id))

    async def get_report(
        self,
        intent: GetReportIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Single-report read via ``AnalyticsPort.get_report`` — AUTO-eligible within cap.
        Report rows are PII-redacted behind the port; the PII overlay still gates the read.
        An unknown report_id raises ``ReportNotFound`` from the port (recorded then re-raised).
        A read below the AUTO band halts for a re-check."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_report:{intent.report_id}",
            success_action="GET_REPORT",
            op="AnalyticsPort.get_report",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.get_report(intent.report_id))

    async def list_available_reports(
        self,
        intent: ListReportsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Report listing via ``AnalyticsPort.list_available_reports`` — AUTO-eligible within
        cap. The PII overlay must PASS before the listing is returned; a read below the AUTO
        band halts for a re-check."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"list_available_reports:{intent.entity_id}",
            success_action="LIST_AVAILABLE_REPORTS",
            op="AnalyticsPort.list_available_reports",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(
            ctx, lambda: self._port.list_available_reports(intent.entity_id)
        )

    async def request_export(
        self,
        intent: RequestExportIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Request an export via ``AnalyticsPort.request_export`` under the mask (the only
        non-AUTO operation, ADR-054 data-egress gate).

        AUTO-biased: a small / in-cap export proceeds AUTO. If ``intent.data_egress_sensitive``
        is set the export is large / sensitive, so the action is forced to the REVIEW band and
        held for a human reviewer regardless of confidence; supply ``human_reviewed_by`` to
        proceed. NO biometric step-up applies — data-egress is not a value-bearing action. The
        PII + data-egress overlay (``compliance_result``) must PASS before the port is called;
        a non-PASS verdict blocks and escalates (data-egress → egress role). The port's
        materiality guard raises ``ExportTooLarge`` (recorded then re-raised) as
        defense-in-depth.
        """
        request = ExportRequest(
            entity_id=intent.entity_id,
            report_id=intent.report_id,
            format=intent.format,
            actor=intent.actor,
            correlation_id=intent.correlation_id,
            include_pii=intent.include_pii,
        )
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"request_export:{intent.report_id}",
            success_action="REQUEST_EXPORT",
            op="AnalyticsPort.request_export",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.DATA_EGRESS,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            force_review=intent.data_egress_sensitive,
        )
        return await self._run_action(ctx, lambda: self._port.request_export(request))

    # -- governance engine ---------------------------------------------------

    def _band(self, confidence: float) -> ConfirmationDecision:
        if confidence > self._mask.auto_threshold:
            return ConfirmationDecision.AUTO
        if confidence >= self._mask.review_floor:
            return ConfirmationDecision.REVIEW
        return ConfirmationDecision.BLOCK

    def _cost_breaches(self, cost: RequestCost) -> bool:
        cap = self._mask.cost_cap
        return (
            cost.tokens > cap.max_request_tokens
            or cost.cost > cap.max_request_cost
            or self._window.used_tokens + cost.tokens > cap.max_window_tokens
            or self._window.used_cost + cost.cost > cap.max_window_cost
        )

    def _compliance_role(self, overlay: ComplianceOverlay) -> str:
        # PII failures route to the DPO (ADR-016); data-egress failures route to the egress
        # role (ADR-054 data-egress gate). Roles are config-as-data.
        return self._mask.dpo_role if overlay is ComplianceOverlay.PII else self._mask.egress_role

    def _evaluate(self, ctx: _ActionContext) -> _Evaluation:
        if not 0.0 <= ctx.confidence_score <= 1.0:
            raise ValueError("confidence_score must be in [0.0, 1.0]")
        policies = ["ADR-048-process-resolution"]

        # 1. ADR-048 — no port call without a resolved process_ref.
        if not ctx.process_ref.resolved:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_UNRESOLVED_PROCESS",
                "Intent has no resolved process_ref; governance event, never improvised.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="unresolved_process_ref",
                requires_hitl=True,
            )

        # 2. ADR-054 §D1 — mask scope allow-list; an off-list op is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the Analytics (C7) mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70)
        #    + ADR-054 data-egress override (force REVIEW regardless of confidence).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            # Large / sensitive export: an otherwise-AUTO action is pulled down to REVIEW so
            # a human confirms the data-egress (ADR-054 data-egress gate).
            policies.append("ADR-054-data-egress-REVIEW")
            band = ConfirmationDecision.REVIEW

        if band is ConfirmationDecision.BLOCK:
            return _Evaluation(
                band,
                False,
                "BLOCK_LOW_CONFIDENCE",
                "Confidence < 0.70: full stop, human confirmation mandatory (ADR-049 §D4).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
            )
        if band is ConfirmationDecision.REVIEW:
            # Read path: reads are AUTO-only, so a below-AUTO read halts for a re-check at
            # higher confidence, not a HITL hold (ADR-054).
            if not ctx.supports_review_hitl:
                return _Evaluation(
                    band,
                    False,
                    "HALT_REVIEW_DEFERRED",
                    "Read intent below AUTO band; reads are AUTO-only, no HITL hold (ADR-054).",
                    policies,
                    ctx.compliance_result,
                    BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )
            # Export in the REVIEW band (low confidence OR large/sensitive) holds for HITL.
            if ctx.human_reviewed_by is None:
                reason = (
                    "Large / sensitive export pulled to REVIEW (data-egress gate); paused for "
                    "HITL regardless of confidence (ADR-054)."
                    if ctx.force_review
                    else "Export in REVIEW band; paused for HITL confirmation (ADR-049 §D4)."
                )
                return _Evaluation(
                    band,
                    False,
                    "HOLD_FOR_REVIEW",
                    reason,
                    policies,
                    ctx.compliance_result,
                    BudgetBreach.NONE,
                    halt_reason="hitl_review_required",
                    requires_hitl=True,
                )

        # 4. ADR-047 — hard cost cap (per-request AND per-window). Analytics aggregation can
        #    be token-heavy; the token cap is the primary runaway guard.
        policies.append("ADR-047-cost-cap")
        if self._cost_breaches(ctx.request_cost):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COST_CAP_BREACH",
                "Cost-cap breach (per-request or per-window tokens/cost); action refused (ADR-047).",
                policies,
                ComplianceResult.NA,
                BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        # 5. L3 compliance gate — PII + data-egress overlay. A non-PASS verdict halts AND
        #    escalates (PII → DPO, data-egress → egress role).
        policies.append("ADR-054-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            escalated = self._compliance_role(ctx.compliance_overlay)
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"{ctx.compliance_overlay.value} overlay returned {ctx.compliance_result}; "
                f"action blocked and escalated to {escalated}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=escalated,
            )

        # Biometric step-up: N/A for analytics (no money movement, ADR-054 §D1).
        # All gates satisfied — clear to commit the action.
        reviewer = (
            "" if ctx.human_reviewed_by is None else f" (reviewed by {ctx.human_reviewed_by})"
        )
        return _Evaluation(
            band,
            True,
            ctx.success_action,
            f"All mask gates satisfied at {band.value} confidence{reviewer}; committing within scope.",
            policies,
            ctx.compliance_result,
            BudgetBreach.NONE,
        )

    async def _run_action(
        self,
        ctx: _ActionContext,
        port_call: Callable[[], Awaitable[object]] | None,
    ) -> AgentOutcome:
        ev = self._evaluate(ctx)
        result: object | None = None
        executed = False
        action_taken = ev.action_taken

        if ev.proceed:
            if port_call is not None:
                try:
                    result = await port_call()
                except AnalyticsPortError as exc:
                    # Defense-in-depth: the port's own materiality / PII guard
                    # (ExportTooLarge / ComplianceBlock / ReportNotFound) fired. Emit one
                    # lineage record (executed=False) then re-raise — no raw PII recorded.
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=ev.compliance_result,
                        reasoning=f"Port rejected the action: {exc}",
                        escalated_to=ev.escalated_to,
                    )
                    raise
            executed = True
            self._window.add(ctx.request_cost)

        record = await self._emit(
            ctx,
            ev,
            action_taken,
            executed=executed,
            compliance_result=ev.compliance_result,
            reasoning=ev.reasoning_summary,
            escalated_to=ev.escalated_to,
        )
        return AgentOutcome(
            decision=ev.decision,
            executed=executed,
            record=record,
            result=result,
            halt_reason=ev.halt_reason,
            requires_hitl=ev.requires_hitl,
            escalated_to=ev.escalated_to,
        )

    async def _emit(
        self,
        ctx: _ActionContext,
        ev: _Evaluation,
        action_taken: str,
        *,
        executed: bool,
        compliance_result: ComplianceResult,
        reasoning: str,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        return await self._record(
            triggering_event=ctx.triggering_event,
            intent=ctx.intent_text,
            policies=ev.policies,
            compliance_result=compliance_result,
            reasoning=reasoning,
            confidence_score=ctx.confidence_score,
            action_taken=action_taken,
            human_reviewed_by=ctx.human_reviewed_by,
            correlation_id=ctx.correlation_id,
            request_cost=ctx.request_cost,
            budget_breach=ev.budget_breach,
            escalated_to=escalated_to,
        )

    async def _record(
        self,
        *,
        triggering_event: str,
        intent: str,
        policies: list[str],
        compliance_result: ComplianceResult,
        reasoning: str,
        confidence_score: float,
        action_taken: str,
        human_reviewed_by: str | None,
        correlation_id: str,
        request_cost: RequestCost,
        budget_breach: BudgetBreach,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        """Build, persist, and return exactly one ADR-046 lineage record (the single
        producer→sink seam used by every exit path). R-SEC: only opaque handles
        (entity_id / report_id via triggering_event) ever reach a record — never raw PII."""
        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            agent_id=self._mask.agent_id,
            triggering_event=triggering_event,
            intent=intent,
            policies_evaluated=policies,
            compliance_result=compliance_result,
            reasoning_summary=reasoning,
            confidence_score=confidence_score,
            action_taken=action_taken,
            human_reviewed_by=human_reviewed_by,
            correlation_id=correlation_id,
            cost_tokens=request_cost.tokens,
            cost_amount=request_cost.cost,
            budget_window_ref=self._window.window_ref,
            budget_breach_flag=budget_breach,
            escalated_to=escalated_to,
        )
        await self._recorder.record(record)
        return record


__all__ = [
    "AgentDecisionRecord",
    "AgentOutcome",
    "AnalyticsClientAgent",
    "AnalyticsMask",
    "AutonomyLevel",
    "BudgetBreach",
    "ComplianceOverlay",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "GetReportIntent",
    "ListReportsIntent",
    "PortfolioViewIntent",
    "ProcessRef",
    "RequestCost",
    "RequestExportIntent",
    "SpendingSummaryIntent",
]
