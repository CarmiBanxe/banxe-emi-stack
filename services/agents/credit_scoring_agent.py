"""CreditScoringAgent — §D2 MASK_ONLY over lending domain (Credit/Risk; EU AI Act Art.14).

REGULATORY INVARIANT (CRITICAL — enforced in code AND tests):
    If the proposed outcome is a REJECTION (is_rejection=True), the mask sets
    force_review=True + requires_step_up=True regardless of confidence.
    No reviewer supplied → HOLD_FOR_REVIEW (proceed=False, handle.decide NOT called,
    escalate→CREDIT_OFFICER). There is NO code path that passes a rejection
    to the lending domain without a human reviewer present.

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band [+CREDIT_OFFICER step-up] → cost_cap
    → compliance(CREDIT+CONSUMER_DUTY) → handle call

R-SEC (ADR-021): triggering_event uses opaque handles (customer_id / application_id)
ONLY — never income, aml_risk_score, score values, or PII. Domain returns ride on
AgentOutcome.result ONLY, never on AgentDecisionRecord.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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
# Narrow DI Protocol (typing only — avoids cross-service model import)
# ---------------------------------------------------------------------------


class CreditHandle(Protocol):
    """Narrow typing Protocol for the injected credit domain handle.

    Structurally compatible with CreditScorer (score_customer / get_latest_score)
    and LoanOriginator (decide). Return types are `object` to avoid importing
    lending domain models into the mask module.
    """

    def score_customer(
        self,
        customer_id: str,
        income: Decimal,
        account_age_months: int,
        aml_risk_score: Decimal,
    ) -> object: ...

    def get_latest_score(self, customer_id: str) -> object | None: ...

    def decide(self, application_id: str, credit_score: object, actor: str = "system") -> dict: ...


# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreditScoringMask:
    """Config-as-data Credit/Risk mask (EU AI Act Art.14 high-risk; FCA CONC).

    scope is the exclusive allow-list; credit_reviewer_role is the escalation
    target for compliance failures and mandatory rejection step-up.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "credit_scoring_agent"
    scope: tuple[str, ...] = (
        "CreditHandle.score_customer",
        "CreditHandle.get_latest_score",
        "CreditHandle.decide",
    )
    compliance_gate: tuple[str, ...] = ("CREDIT", "CONSUMER_DUTY")
    credit_reviewer_role: str = "CREDIT_OFFICER"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ScoreCustomerIntent:
    """Resolved score-customer intent (L1 AUTO read).

    R-SEC: income / aml_risk_score passed to handle but NEVER recorded.
    triggering_event uses customer_id (opaque) only.
    """

    intent_text: str
    process_ref: ProcessRef
    customer_id: str
    income: Decimal  # I-01: Decimal for money, never float
    account_age_months: int
    aml_risk_score: Decimal  # I-01
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class GetLatestScoreIntent:
    """Resolved get-latest-score intent (L1 AUTO read).

    R-SEC: triggering_event uses customer_id (opaque) only.
    """

    intent_text: str
    process_ref: ProcessRef
    customer_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class DecideIntent:
    """Resolved credit-decision intent (L2 normal; L3 step-up on rejection).

    is_rejection=True activates mandatory HITL step-up (EU AI Act Art.14 / FCA CONC):
    force_review=True + requires_step_up=True regardless of confidence. credit_score
    is an opaque domain object passed through to handle.decide().

    R-SEC: triggering_event uses application_id only — never score values or PII.
    """

    intent_text: str
    process_ref: ProcessRef
    application_id: str
    credit_score: object  # lending domain CreditScore; opaque to this mask
    is_rejection: bool
    actor: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


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
    human_reviewed_by: str | None
    force_review: bool = False
    review_escalate_to: str | None = None
    requires_step_up: bool = False
    auto_only: bool = False


@dataclass(frozen=True)
class _Evaluation:
    decision: ConfirmationDecision
    proceed: bool
    action_taken: str
    reasoning_summary: str
    policies_evaluated: list[str]
    compliance_result: ComplianceResult
    budget_breach: BudgetBreach
    halt_reason: str | None = None
    requires_step_up: bool = False
    requires_hitl: bool = False
    escalated_to: str | None = None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CreditScoringAgent:
    """§D2 MASK_ONLY Credit/Risk agent (EU AI Act Art.14; FCA CONC / ADR-049).

    score_customer and get_latest_score are L1-Auto reads (AUTO-eligible within cap;
    REVIEW band → HALT_REVIEW_DEFERRED, no HITL hold). decide is L2/L3: APPROVED /
    REFERRED proposals follow the normal band; DECLINED (is_rejection=True) always
    forces step-up — no reviewer → HOLD_FOR_REVIEW, handle.decide NEVER called.

    CreditHandle and recorder are injected; this class contains pure governance logic.
    """

    def __init__(
        self,
        *,
        credit_handle: CreditHandle,
        recorder: DecisionRecorder,
        mask: CreditScoringMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._handle = credit_handle
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def score_customer(
        self,
        intent: ScoreCustomerIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Score a customer's creditworthiness (L1 AUTO read).

        REVIEW band → HALT_REVIEW_DEFERRED (reads are AUTO-only; no HITL hold).
        R-SEC: income / aml_risk_score never appear in the lineage record.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"score_customer:{intent.customer_id}",
            success_action="SCORE_CUSTOMER",
            op="CreditHandle.score_customer",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
            auto_only=True,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.score_customer(
                intent.customer_id,
                intent.income,
                intent.account_age_months,
                intent.aml_risk_score,
            ),
        )

    async def get_latest_score(
        self,
        intent: GetLatestScoreIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Retrieve latest credit score (L1 AUTO read).

        REVIEW band → HALT_REVIEW_DEFERRED. R-SEC: customer_id only in record.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_latest_score:{intent.customer_id}",
            success_action="GET_LATEST_SCORE",
            op="CreditHandle.get_latest_score",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
            auto_only=True,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.get_latest_score(intent.customer_id),
        )

    async def decide(
        self,
        intent: DecideIntent,
        *,
        human_reviewed_by: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Apply credit decision governance (L2 normal; L3 rejection step-up).

        REGULATORY INVARIANT: is_rejection=True → force_review=True +
        requires_step_up=True. No reviewer → HOLD_FOR_REVIEW (handle.decide NOT
        called, escalate→CREDIT_OFFICER). Reviewer present → delegate to handle.
        R-SEC: triggering_event uses application_id only — no score/PII.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"decide:{intent.application_id}",
            success_action="CREDIT_DECIDE",
            op="CreditHandle.decide",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            force_review=intent.is_rejection,
            review_escalate_to=self._mask.credit_reviewer_role,
            requires_step_up=intent.is_rejection,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.decide(intent.application_id, intent.credit_score, intent.actor),
        )

    # -- governance engine ---------------------------------------------------

    def _band(self, score: float) -> ConfirmationDecision:
        if score >= self._mask.auto_threshold:
            return ConfirmationDecision.AUTO
        if score >= self._mask.review_floor:
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

        if not ctx.process_ref.resolved:
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="HALT_UNRESOLVED_PROCESS",
                reasoning_summary="Intent has no resolved process_ref; governance event, never improvised.",
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.NONE,
                halt_reason="unresolved_process_ref",
                requires_hitl=True,
            )

        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="REJECT_OUT_OF_SCOPE",
                reasoning_summary=f"Operation {ctx.op!r} not on credit scope allow-list; refused.",
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            policies.append("ADR-046-CREDIT-OFFICER-step-up")
            band = ConfirmationDecision.REVIEW

        if band is ConfirmationDecision.BLOCK:
            return _Evaluation(
                decision=band,
                proceed=False,
                action_taken="BLOCK_LOW_CONFIDENCE",
                reasoning_summary="Confidence below 0.70; human confirmation mandatory (ADR-049 §D4).",
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
            )

        if band is ConfirmationDecision.REVIEW:
            if ctx.force_review:
                if ctx.human_reviewed_by is None:
                    reason = (
                        "Rejection decision: mandatory human review (EU AI Act Art.14 / FCA CONC). "
                        "No reviewer — HOLD, escalated to CREDIT_OFFICER."
                        if ctx.requires_step_up
                        else "Credit decision: CREDIT_OFFICER sign-off required. "
                        "No reviewer — HOLD, escalated to CREDIT_OFFICER."
                    )
                    return _Evaluation(
                        decision=band,
                        proceed=False,
                        action_taken="HOLD_FOR_REVIEW",
                        reasoning_summary=reason,
                        policies_evaluated=policies,
                        compliance_result=ctx.compliance_result,
                        budget_breach=BudgetBreach.NONE,
                        halt_reason="hitl_review_required",
                        requires_step_up=ctx.requires_step_up,
                        requires_hitl=True,
                        escalated_to=ctx.review_escalate_to,
                    )
                # reviewer present → fall through to cost / compliance gates
            else:
                return _Evaluation(
                    decision=band,
                    proceed=False,
                    action_taken="HALT_REVIEW_DEFERRED",
                    reasoning_summary="Credit read below AUTO band; reads are AUTO-only (L1), no HITL hold.",
                    policies_evaluated=policies,
                    compliance_result=ctx.compliance_result,
                    budget_breach=BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )

        policies.append("ADR-047-cost-cap")
        if self._cost_breaches(ctx.request_cost):
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="HALT_COST_CAP_BREACH",
                reasoning_summary="Per-request or per-window cost-cap breach; action refused (ADR-047).",
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="HALT_COMPLIANCE_BLOCK",
                reasoning_summary=(
                    f"CREDIT/CONSUMER_DUTY overlay {ctx.compliance_result!r}; "
                    f"blocked, escalated to {self._mask.credit_reviewer_role}."
                ),
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.credit_reviewer_role,
            )

        note = f" (reviewed by {ctx.human_reviewed_by})" if ctx.human_reviewed_by else ""
        return _Evaluation(
            decision=band,
            proceed=True,
            action_taken=ctx.success_action,
            reasoning_summary=f"All credit gates satisfied at {band.value} confidence{note}.",
            policies_evaluated=policies,
            compliance_result=ctx.compliance_result,
            budget_breach=BudgetBreach.NONE,
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
            policies_evaluated=list(ev.policies_evaluated),
            compliance_result=compliance_result,
            reasoning_summary=reasoning,
            confidence_score=ctx.confidence_score,
            action_taken=action_taken,
            human_reviewed_by=ctx.human_reviewed_by,
            correlation_id=ctx.correlation_id,
            cost_tokens=ctx.request_cost.tokens,
            cost_amount=ctx.request_cost.cost,
            budget_window_ref=self._window.window_ref,
            budget_breach_flag=ev.budget_breach,
            escalated_to=escalated_to,
        )
        await self._recorder.record(record)
        return record

    async def _run_action(
        self,
        ctx: _ActionContext,
        port_call: Callable[[], object],
    ) -> AgentOutcome:
        ev = self._evaluate(ctx)
        result: object | None = None
        executed = False
        action_taken = ev.action_taken

        if ev.proceed:
            try:
                result = port_call()
            except ValueError as exc:
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
            requires_step_up=ev.requires_step_up,
            requires_hitl=ev.requires_hitl,
            escalated_to=ev.escalated_to,
        )


__all__ = [
    "CreditHandle",
    "CreditScoringAgent",
    "CreditScoringMask",
    "DecideIntent",
    "GetLatestScoreIntent",
    "ScoreCustomerIntent",
]
