"""RiskOversightAgent — L1-Auto CRO risk dashboard read agent
(ADR-079 / ORG-STRUCTURE §2.2).

WHY: ORG-STRUCTURE §2.2 defines the CRO risk-oversight agent as the governed surface
through which a resolved risk-data read intent becomes a bounded RiskMetricsPort
read action. This module is the emi-stack CRO sibling of
``services/agents/bi_agent.py`` and ``services/agents/fpa_agent.py`` — it implements
the agent *logic* and *governance enforcement* of the risk oversight mask in front
of the RiskMetricsPort CONTRACT.

The CRO risk oversight agent provides aggregate exposure, monitoring counters,
and Consumer Duty signal reads for the CRO dashboard. It operates READ-ONLY
over the risk metrics layer and NEVER modifies source data, NEVER approves models,
NEVER changes risk thresholds, and NEVER makes risk decisions.

INVARIANT (CRITICAL — enforced in code):
    RiskOversightAgent is READ-ONLY DASHBOARD. It MUST NEVER emit an approve /
    threshold-change / model-approval / risk-decision action. Enforced by three
    independent mechanisms:
      (1) the mask scope allow-list contains ONLY the 4 read ops:
          get_risk_dashboard, get_aggregate_exposure, get_monitoring_counters,
          get_consumer_duty_signals;
      (2) RiskMetricsPort has NO mutating / approve / threshold method — calling
          one would require a method that does not exist on the port;
      (3) every ``success_action`` in this module is a DASHBOARD/READ verb
          (GET_RISK_DASHBOARD, GET_AGGREGATE_EXPOSURE, GET_MONITORING_COUNTERS,
          GET_CONSUMER_DUTY_SIGNALS) — the strings APPROVE, THRESHOLD, DECISION,
          MODEL_APPROVAL do not appear as success actions here.

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band → cost_cap → compliance(RISK_DATA) → port call

* ``scope``              — RiskMetricsPort READ ops only (allow-list:
                           get_risk_dashboard / get_aggregate_exposure /
                           get_monitoring_counters / get_consumer_duty_signals).
                           Off-list ops are refused outright (ADR-054 §D1 pattern).
* ``autonomy_level``     — L1-Auto: every read is AUTO-eligible within cap. NO
                           REVIEW HITL hold, NO biometric step-up (no money
                           movement). A read below the AUTO band halts for a
                           re-check (HALT_REVIEW_DEFERRED, requires_hitl=True);
                           there is no HITL hold path in this agent.
* ``confirmation_policy``— AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70
                           (ADR-047 thresholds). REVIEW band → HALT_REVIEW_DEFERRED
                           (re-check required, not a hold): reads are AUTO-only.
* ``cost_cap``           — per-request AND per-window hard caps in both token and
                           monetary (Decimal) dimensions (ADR-047 §D2).
* ``lineage_obligation`` — one ``AgentDecisionRecord`` per action on every exit
                           path (ADR-046), non-optional.
* ``compliance_gate``    — RISK_DATA overlay: the L3 check MUST PASS before a
                           port call; a non-PASS verdict halts (BLOCK) and
                           escalates to the CRO (config-as-data on the mask).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence,
cost-cap breach, compliance(RISK_DATA) fail} halts the action (ADR-049 §D4).
The port's own validation is defense-in-depth: if the port raises
RiskMetricsPortError, lineage is emitted (executed=False) and the error is
re-raised. Mask values are config-as-data, carried on :class:`RiskOversightMask`.

R-SEC (R-SEC-NEW-01, ADR-021): no raw metric value, exposure amount, alert
counter, or PII ever enters a lineage record. triggering_event is keyed on
static op labels only — never metric values or amounts. The port's return value
(RiskDashboard / AggregateExposure / MonitoringCounters / list[ConsumerDutySignal])
rides on ``AgentOutcome.result`` ONLY — NEVER on the recorded
``AgentDecisionRecord``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
from services.risk.risk_metrics_port import RiskMetricsPort, RiskMetricsPortError

# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RiskOversightMask:
    """Config-as-data CRO risk oversight (ORG-STRUCTURE §2.2) mask.

    All gate values are governed config, not hardcoded flow logic. The
    AUTO/REVIEW/BLOCK scale is ADR-047 canon. The scope is the exclusive
    read-only allow-list — no approve / threshold / decision op is present
    (INVARIANT: see module docstring).
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "risk_oversight_agent"
    # The mask scope (allow-list): ONLY the 4 RiskMetricsPort READ ops.
    # INVARIANT: no approve / threshold / model-approval / risk-decision op
    # is present in this tuple. Any attempt to call one is REJECT_OUT_OF_SCOPE.
    scope: tuple[str, ...] = (
        "RiskMetricsPort.get_risk_dashboard",
        "RiskMetricsPort.get_aggregate_exposure",
        "RiskMetricsPort.get_monitoring_counters",
        "RiskMetricsPort.get_consumer_duty_signals",
    )
    # L3 compliance contour required before any port call.
    compliance_gate: tuple[str, ...] = ("RISK_DATA",)
    # Escalation role for a compliance non-PASS verdict (config-as-data).
    cro_role: str = "CRO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass
class GetRiskDashboardIntent:
    """A resolved risk-dashboard read intent
    (``RiskMetricsPort.get_risk_dashboard``) — the primary CRO read op
    (ADR-079 / ORG-STRUCTURE §2.2). A read below the AUTO band halts for a
    re-check, not a HITL hold. The RISK_DATA compliance overlay MUST PASS;
    a non-PASS verdict blocks and escalates to the CRO. The dashboard rides
    on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetAggregateExposureIntent:
    """A resolved aggregate-exposure read intent
    (``RiskMetricsPort.get_aggregate_exposure``) — the EMI-wide exposure
    leg of CRO oversight (ADR-079). A read below the AUTO band halts for a
    re-check. The RISK_DATA overlay MUST PASS; non-PASS escalates to CRO.
    The AggregateExposure rides on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetMonitoringCountersIntent:
    """A resolved monitoring-counters read intent
    (``RiskMetricsPort.get_monitoring_counters``) — fraud/AML alert counts
    for CRO situational awareness (ADR-079). A read below the AUTO band halts
    for a re-check. The RISK_DATA overlay MUST PASS; non-PASS escalates to CRO.
    The MonitoringCounters rides on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetConsumerDutySignalsIntent:
    """A resolved Consumer Duty signals read intent
    (``RiskMetricsPort.get_consumer_duty_signals``) — outcome metric signals
    for CRO Consumer Duty oversight (ADR-079). A read below the AUTO band halts
    for a re-check. The RISK_DATA overlay MUST PASS; non-PASS escalates to CRO.
    The signal list rides on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


# ---------------------------------------------------------------------------
# Internal evaluation types
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
    """All inputs a single masked risk oversight action evaluates against."""

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    triggering_event: str
    success_action: str
    op: str
    request_cost: RequestCost
    compliance_result: ComplianceResult


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


class RiskOversightAgent:
    """L1-Auto CRO risk dashboard read agent enforcing the ADR-049 §D2 gate chain.

    The :class:`~services.risk.risk_metrics_port.RiskMetricsPort` and the lineage
    recorder are injected as interfaces (constructor injection); the agent contains
    pure governance logic and is unit-testable without any live infra.

    INVARIANT: READ-ONLY DASHBOARD. This agent MUST NEVER emit an approve /
    threshold-change / model-approval / risk-decision action. See module docstring
    for the three independent enforcement mechanisms.
    """

    def __init__(
        self,
        *,
        risk_metrics_port: RiskMetricsPort,
        recorder: DecisionRecorder,
        mask: RiskOversightMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = risk_metrics_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def get_risk_dashboard(
        self,
        intent: GetRiskDashboardIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """CRO dashboard read via ``RiskMetricsPort.get_risk_dashboard`` — the
        primary risk oversight op (ADR-079 / ORG-STRUCTURE §2.2). AUTO-eligible
        within cap. The RISK_DATA overlay (``compliance_result``) must PASS before
        the dashboard is returned; a non-PASS verdict blocks and escalates to the
        CRO. A read below the AUTO band halts for a re-check, not a HITL hold
        (L1-Auto). Dashboard rides on ``AgentOutcome.result`` ONLY (R-SEC)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="get_risk_dashboard",
            success_action="GET_RISK_DASHBOARD",
            op="RiskMetricsPort.get_risk_dashboard",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_risk_dashboard())

    async def get_aggregate_exposure(
        self,
        intent: GetAggregateExposureIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Aggregate exposure read via ``RiskMetricsPort.get_aggregate_exposure``
        (ADR-079). AUTO-eligible within cap. The RISK_DATA overlay must PASS;
        non-PASS blocks and escalates to CRO. A read below the AUTO band halts
        for a re-check (L1-Auto). Result rides on ``AgentOutcome.result`` ONLY
        (R-SEC — never expose total_gbp in a lineage record)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="get_aggregate_exposure",
            success_action="GET_AGGREGATE_EXPOSURE",
            op="RiskMetricsPort.get_aggregate_exposure",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_aggregate_exposure())

    async def get_monitoring_counters(
        self,
        intent: GetMonitoringCountersIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Monitoring counters read via ``RiskMetricsPort.get_monitoring_counters``
        (ADR-079). AUTO-eligible within cap. The RISK_DATA overlay must PASS;
        non-PASS blocks and escalates to CRO. A read below the AUTO band halts
        for a re-check (L1-Auto). Result rides on ``AgentOutcome.result`` ONLY
        (R-SEC — never expose counter values in a lineage record)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="get_monitoring_counters",
            success_action="GET_MONITORING_COUNTERS",
            op="RiskMetricsPort.get_monitoring_counters",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_monitoring_counters())

    async def get_consumer_duty_signals(
        self,
        intent: GetConsumerDutySignalsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Consumer Duty signals read via ``RiskMetricsPort.get_consumer_duty_signals``
        (ADR-079). AUTO-eligible within cap. The RISK_DATA overlay must PASS;
        non-PASS blocks and escalates to CRO. A read below the AUTO band halts
        for a re-check (L1-Auto). Result rides on ``AgentOutcome.result`` ONLY
        (R-SEC)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="get_consumer_duty_signals",
            success_action="GET_CONSUMER_DUTY_SIGNALS",
            op="RiskMetricsPort.get_consumer_duty_signals",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_consumer_duty_signals())

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

        # 2. Scope allow-list — an off-list op is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the risk oversight mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band. REVIEW → HALT_REVIEW_DEFERRED: reads are
        #    AUTO-only (L1-Auto); there is no HITL hold path in this agent.
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)

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
            return _Evaluation(
                band,
                False,
                "HALT_REVIEW_DEFERRED",
                "Read intent below AUTO band; reads are AUTO-only, no HITL hold (L1-Auto).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="review_deferred",
                requires_hitl=True,
            )

        # 4. ADR-047 — hard cost cap (per-request AND per-window).
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

        # 5. RISK_DATA compliance gate. A non-PASS verdict halts AND escalates to CRO.
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            escalated = self._mask.cro_role
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"RISK_DATA overlay returned {ctx.compliance_result}; "
                f"action blocked and escalated to {escalated}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=escalated,
            )

        # All gates satisfied — clear to commit the read.
        return _Evaluation(
            band,
            True,
            ctx.success_action,
            f"All risk oversight mask gates satisfied at {band.value} confidence; committing within scope.",
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
                except RiskMetricsPortError as exc:
                    # Defense-in-depth: the port's own data guard fired. Emit one
                    # lineage record (executed=False) then re-raise — no raw metric
                    # value, exposure amount, or PII recorded.
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
        correlation_id: str,
        request_cost: RequestCost,
        budget_breach: BudgetBreach,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        """Build, persist, and return exactly one ADR-046 lineage record (the single
        producer→sink seam used by every exit path). R-SEC: triggering_event uses
        static op labels only — never metric values, exposure amounts, alert counters,
        or PII. Port return values ride on AgentOutcome.result, never on this record."""
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
            human_reviewed_by=None,
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
    "BudgetBreach",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "GetAggregateExposureIntent",
    "GetConsumerDutySignalsIntent",
    "GetMonitoringCountersIntent",
    "GetRiskDashboardIntent",
    "ProcessRef",
    "RequestCost",
    "RiskMetricsPortError",
    "RiskOversightAgent",
    "RiskOversightMask",
]
