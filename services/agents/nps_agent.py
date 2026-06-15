"""NPSAgent — L1-Auto §D2 mask over support feedback domain (MASK_ONLY).

WHY: ORG §2.8 (Front Office, CRO quarterly review §2.8.1) defines NPSAgent as the
governed client-facing surface through which a resolved NPS/CSAT read intent becomes
a bounded FeedbackAnalyticsAgent.get_metrics action. This module enforces the ADR-049
§D2 gate chain in front of the support feedback domain.

NPSAgent is READ-ONLY reporting. It DOES NOT submit or record feedback.
submit_csat is NOT in scope — any attempt is REJECT_OUT_OF_SCOPE (INVARIANT).

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band → cost_cap → compliance(CONSUMER_DUTY) → handle call

* ``scope``          — FeedbackAnalyticsAgent READ ops only (1-op allow-list:
                       get_metrics). submit_csat is out-of-scope (ADR-054 §D1 pattern).
* ``autonomy_level`` — L1-Auto: every read is AUTO-eligible within cap. Below-AUTO →
                       HALT_REVIEW_DEFERRED (domain NOT called). No HITL hold path.
* ``cost_cap``       — per-request AND per-window hard caps (ADR-047 §D2).
* ``lineage``        — one AgentDecisionRecord per action, every exit path (ADR-046).
* ``compliance``     — CONSUMER_DUTY overlay; non-PASS → BLOCK + escalate to CRO.

INVARIANT (L1 read-only): mask scope contains ONLY get_metrics. The write op
submit_csat is NOT present. Any attempt to call an off-list op is REJECT_OUT_OF_SCOPE
before the handle is ever reached. I-27: PROPOSES findings only, never applies.

Provider-error: if the handle raises ValueError, one lineage record is emitted
(executed=False, action_taken=HALT_PROVIDER_ERROR:ValueError) then re-raised.

R-SEC (ADR-021): triggering_event is keyed on OPAQUE handles only (period_days /
survey_id / cohort). Raw customer feedback text, CSAT comments, and PII MUST NEVER
appear in any AgentDecisionRecord field. FeedbackMetrics aggregate rides on
AgentOutcome.result ONLY — never on the lineage record.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
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

# ---------------------------------------------------------------------------
# Narrow DI Protocol (typing only — not a new heavy port)
# ---------------------------------------------------------------------------


class FeedbackHandle(Protocol):
    """Narrow typing Protocol for the injected support feedback domain handle.

    Matches FeedbackAnalyticsAgent.get_metrics (the read op) only.
    The write op submit_csat is intentionally absent — NPSAgent is read-only.
    """

    async def get_metrics(self, period_days: int = 30) -> object: ...


# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class NPSMask:
    """Config-as-data CRO-reviewed NPS/CSAT reporting mask (ORG §2.8 / §2.8.1).

    scope contains ONLY get_metrics (the read op). submit_csat is not present
    (INVARIANT: see module docstring). All gate values are governed config.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "nps_agent"
    # INVARIANT: only the read op. submit_csat MUST NOT appear here.
    scope: tuple[str, ...] = ("FeedbackAnalyticsAgent.get_metrics",)
    compliance_gate: tuple[str, ...] = ("CONSUMER_DUTY",)
    cro_role: str = "CRO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class GetFeedbackMetricsIntent:
    """Resolved NPS/CSAT metrics read intent (FeedbackAnalyticsAgent.get_metrics).

    R-SEC: triggering_event keyed on opaque handles only (period_days / survey_id /
    cohort). Raw feedback text and PII MUST NOT appear on any intent field used in
    the lineage record. FeedbackMetrics rides on AgentOutcome.result ONLY.
    """

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    period_days: int = 30
    survey_id: str = ""
    cohort: str = ""


# ---------------------------------------------------------------------------
# Internal evaluation types (private)
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
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


class NPSAgent:
    """L1-Auto CRO NPS/CSAT reporting agent enforcing the ADR-049 §D2 gate chain.

    READ-ONLY: delegates get_feedback_metrics to the injected FeedbackHandle.
    DOES NOT submit or record feedback — submit_csat is REJECT_OUT_OF_SCOPE.
    I-27: PROPOSES findings only, never applies changes autonomously.
    """

    def __init__(
        self,
        *,
        feedback_handle: FeedbackHandle,
        recorder: DecisionRecorder,
        mask: NPSMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._handle = feedback_handle
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def get_feedback_metrics(
        self,
        intent: GetFeedbackMetricsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """NPS/CSAT aggregate read via FeedbackAnalyticsAgent.get_metrics.

        AUTO-eligible within cap. CONSUMER_DUTY overlay MUST PASS; non-PASS blocks
        and escalates to CRO. A read below the AUTO band halts (L1-Auto: no HITL hold).
        FeedbackMetrics rides on AgentOutcome.result ONLY (R-SEC — no metric values
        or PII in lineage).
        """
        # Build opaque triggering_event — no feedback text or PII (R-SEC).
        parts: list[str] = [f"period={intent.period_days}"]
        if intent.survey_id:
            parts.append(f"survey={intent.survey_id}")
        if intent.cohort:
            parts.append(f"cohort={intent.cohort}")

        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="get_feedback_metrics:" + ":".join(parts),
            success_action="REPORT_FEEDBACK_METRICS",
            op="FeedbackAnalyticsAgent.get_metrics",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._handle.get_metrics(intent.period_days))

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

    def _evaluate(self, ctx: _ActionContext) -> _Evaluation:  # noqa: PLR0911
        if not 0.0 <= ctx.confidence_score <= 1.0:
            raise ValueError(f"confidence_score {ctx.confidence_score!r} must be in [0.0, 1.0]")

        policies: list[str] = ["ADR-048-process-resolution"]

        # 1. ADR-048 — no handle call without a resolved process_ref.
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

        # 2. Scope allow-list — submit_csat and all off-list ops are refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op!r} is not on the NPS mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band. REVIEW → HALT_REVIEW_DEFERRED (L1-Auto: no HITL hold).
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
                "Cost-cap breach (per-request or per-window tokens/cost); refused (ADR-047).",
                policies,
                ComplianceResult.NA,
                BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        # 5. CONSUMER_DUTY compliance gate. Non-PASS → block AND escalate to CRO.
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            escalated = self._mask.cro_role
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"CONSUMER_DUTY overlay returned {ctx.compliance_result}; "
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
            f"All NPS mask gates satisfied at {band.value} confidence; committing read.",
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
                except ValueError as exc:
                    # Handle raises ValueError; emit lineage (executed=False), re-raise.
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=ev.compliance_result,
                        reasoning=f"Handle raised {type(exc).__name__}: {exc}",
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
        executed: bool,  # noqa: ARG002
        compliance_result: ComplianceResult,
        reasoning: str,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            agent_id=self._mask.agent_id,
            triggering_event=ctx.triggering_event,
            intent=ctx.intent_text,
            policies_evaluated=list(ev.policies),
            compliance_result=compliance_result,
            reasoning_summary=reasoning,
            confidence_score=ctx.confidence_score,
            action_taken=action_taken,
            human_reviewed_by=None,
            correlation_id=ctx.correlation_id,
            cost_tokens=ctx.request_cost.tokens,
            cost_amount=ctx.request_cost.cost,
            budget_window_ref=self._window.window_ref,
            budget_breach_flag=ev.budget_breach,
            escalated_to=escalated_to,
        )
        await self._recorder.record(record)
        return record


__all__ = [
    "FeedbackHandle",
    "GetFeedbackMetricsIntent",
    "NPSAgent",
    "NPSMask",
]
