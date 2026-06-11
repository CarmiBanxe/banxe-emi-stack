"""DeployAgent — L2/L3 CTO deploy governance (ADR-081 / ORG §2.7.2).

SAFETY INVARIANT (CRITICAL — enforced in code AND tests):
    DeployAgent MUST NEVER autonomously execute a PRODUCTION deployment.
    Production execute is reachable ONLY when a non-empty approval_token is
    supplied AND the gate-chain proceeds. Three independent enforcement mechanisms:
      (1) deploy_production always sets force_review=True regardless of confidence,
          pulling any AUTO band down to REVIEW;
      (2) REVIEW band with human_reviewed_by=None → HOLD_FOR_REVIEW (proceed=False,
          port.execute_deployment NEVER called);
      (3) InMemoryDeployPort.execute_deployment raises DeployPortError when the
          approval_token is None or unrecognised (defense-in-depth).
    There is NO scope op that bypasses CTO approval. ``DeployPort.autonomous_execute``
    is not on the allow-list and would be REJECT_OUT_OF_SCOPE.

R-SEC (ADR-081 / R-SEC-NEW-01): the approval_token is credential-like.
    It MUST NOT appear in ANY AgentDecisionRecord field (not in triggering_event,
    reasoning, intent, human_reviewed_by, or anywhere else). Only the presence
    marker ``_TOKEN_PRESENT_MARKER`` is stored in ``human_reviewed_by`` when a
    token is supplied. The raw token is captured only in the port-call lambda
    closure and is never persisted to _ActionContext, _Evaluation, or
    AgentDecisionRecord.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import datetime
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
from services.deploy.deploy_port import DeployEnv, DeploymentPlan, DeployPort, DeployPortError

# R-SEC: non-secret presence marker recorded in human_reviewed_by when a
# CTO approval_token is supplied. The raw token is never stored here.
_TOKEN_PRESENT_MARKER = "CTO:approval-token:present"  # noqa: S105


# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DeployMask:
    """Config-as-data CTO deploy governance (ORG §2.7.2 / ADR-081) mask.

    All gate values are governed config, not hardcoded flow logic.
    The scope allow-list is the exclusive operation boundary; any op not listed
    is REJECT_OUT_OF_SCOPE — there is no ``autonomous_execute`` entry.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "deploy_agent"
    scope: tuple[str, ...] = (
        "DeployPort.prepare_deployment",
        "DeployPort.request_approval",
        "DeployPort.execute_deployment",
    )
    compliance_gate: tuple[str, ...] = ("DEPLOY_SAFETY",)
    cto_role: str = "CTO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PrepareDeploymentIntent:
    """A resolved prepare-deployment read intent (``DeployPort.prepare_deployment``).

    L1-Auto read: below AUTO band → HALT_REVIEW_DEFERRED (no HITL hold path).
    No approval_token; no side effect on the target environment.
    """

    intent_text: str
    process_ref: ProcessRef
    target_env: DeployEnv
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class DeployStagingIntent:
    """A resolved staging deploy intent (``DeployPort.execute_deployment`` / staging).

    L2 Review: always requires CTO approval_token (force_review=True).
    Without a token → HOLD_FOR_REVIEW; port.execute NOT called.
    plan is obtained from a prior prepare_deployment action.
    """

    intent_text: str
    process_ref: ProcessRef
    plan: DeploymentPlan
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class DeployProductionIntent:
    """A resolved production deploy intent (``DeployPort.execute_deployment`` / prod).

    L3 SAFETY-CRITICAL: force_review=True ALWAYS (regardless of confidence),
    requires_step_up=True. Without a token → HOLD_FOR_REVIEW; port.execute
    NEVER called. See module docstring for the safety invariant.
    plan is obtained from a prior prepare_deployment action.
    """

    intent_text: str
    process_ref: ProcessRef
    plan: DeploymentPlan
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


# ---------------------------------------------------------------------------
# Internal evaluation types
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
    """All inputs a single masked deploy action evaluates against."""

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    triggering_event: str  # opaque handle only (plan_id:target_env) — no token, no artifact
    success_action: str
    op: str
    request_cost: RequestCost
    compliance_result: ComplianceResult
    human_reviewed_by: str | None  # redacted marker only, NEVER the raw approval_token
    force_review: bool = False
    review_escalate_to: str | None = None
    requires_step_up: bool = False  # L3 production: force mandatory step-up signal
    auto_only: bool = False  # L1 reads: REVIEW band → HALT_REVIEW_DEFERRED, not HOLD


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


class DeployAgent:
    """L2/L3 CTO deploy governance agent (ADR-081 / ORG §2.7.2).

    Enforces the ADR-049 §D2 gate-chain (process_ref → scope → band → cost_cap
    → compliance) for all deployment operations. The DeployPort and recorder are
    injected as interfaces; the agent contains pure governance logic only.

    Band thresholds: AUTO >= 0.90; REVIEW 0.70–0.90; BLOCK < 0.70.
    prepare_deployment: L1-Auto read (auto_only=True → REVIEW → HALT_REVIEW_DEFERRED).
    deploy_staging:     L2 Review (force_review=True always → CTO sign-off required).
    deploy_production:  L3 SAFETY-CRITICAL (force_review=True + requires_step_up=True
                        always — see module docstring safety invariant).
    """

    def __init__(
        self,
        *,
        deploy_port: DeployPort,
        recorder: DecisionRecorder,
        mask: DeployMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._deploy_port = deploy_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def prepare_deployment(
        self,
        intent: PrepareDeploymentIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Prepare/validate a deployment plan (L1-Auto read, no side effect).

        AUTO-eligible within cap. REVIEW band → HALT_REVIEW_DEFERRED (reads are
        AUTO-only; there is no HITL hold on prepare). The DEPLOY_SAFETY compliance
        overlay must PASS; a non-PASS verdict blocks and escalates to the CTO.
        Result (DeploymentPlan) rides on AgentOutcome.result ONLY (R-SEC).
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"prepare_deployment:{intent.target_env}",
            success_action="PREPARE_DEPLOYMENT",
            op="DeployPort.prepare_deployment",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
            auto_only=True,
        )
        return await self._run_action(
            ctx,
            lambda: self._deploy_port.prepare_deployment(intent.target_env),
        )

    async def deploy_staging(
        self,
        intent: DeployStagingIntent,
        *,
        approval_token: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Deploy to staging (L2 Review — CTO approval always required).

        force_review=True always: even AUTO-band confidence is pulled to REVIEW.
        Without approval_token → HOLD_FOR_REVIEW (proceed=False, escalate→CTO,
        port.execute NOT called). With approval_token → port.execute_deployment
        called; port re-validates the token (defense-in-depth).

        R-SEC: approval_token is credential-like and MUST NOT appear in any
        AgentDecisionRecord field. Only ``_TOKEN_PRESENT_MARKER`` is recorded.
        """
        reviewer_marker = _TOKEN_PRESENT_MARKER if approval_token else None
        plan = intent.plan
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"deploy_staging:{plan.plan_id}:{plan.target_env}",
            success_action="DEPLOY_STAGING",
            op="DeployPort.execute_deployment",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=reviewer_marker,
            force_review=True,
            review_escalate_to=self._mask.cto_role,
        )
        return await self._run_action(
            ctx,
            lambda: self._deploy_port.execute_deployment(plan, approval_token),
        )

    async def deploy_production(
        self,
        intent: DeployProductionIntent,
        *,
        approval_token: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Deploy to production (L3 SAFETY-CRITICAL — CTO approval ALWAYS mandatory).

        SAFETY INVARIANT: production deployment is NEVER autonomous. force_review=True
        ALWAYS pulls any confidence band to REVIEW regardless of score. Without a
        valid approval_token, HOLD_FOR_REVIEW halts (proceed=False, port.execute
        NEVER called, escalate→CTO). Even with a token, the port re-validates it
        and raises DeployPortError if invalid (defense-in-depth). There is NO code
        path that executes a production deployment without a CTO approval token.

        R-SEC: approval_token is credential-like — NEVER appears in any
        AgentDecisionRecord field. Only ``_TOKEN_PRESENT_MARKER`` is recorded in
        human_reviewed_by. The raw token is captured only in the port-call lambda
        closure and is never stored on _ActionContext, _Evaluation, or the record.
        """
        reviewer_marker = _TOKEN_PRESENT_MARKER if approval_token else None
        plan = intent.plan
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"deploy_production:{plan.plan_id}:{plan.target_env}",
            success_action="DEPLOY_PRODUCTION",
            op="DeployPort.execute_deployment",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=reviewer_marker,
            force_review=True,
            review_escalate_to=self._mask.cto_role,
            requires_step_up=True,
        )
        return await self._run_action(
            ctx,
            lambda: self._deploy_port.execute_deployment(plan, approval_token),
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
        if cost.tokens > cap.max_request_tokens:
            return True
        if cost.cost > cap.max_request_cost:
            return True
        if self._window.used_tokens + cost.tokens > cap.max_window_tokens:
            return True
        if self._window.used_cost + cost.cost > cap.max_window_cost:
            return True
        return False

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
                reasoning_summary=f"Operation {ctx.op!r} not on deploy scope allow-list; refused.",
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            policies.append("ADR-081-CTO-step-up")
            band = ConfirmationDecision.REVIEW

        if band is ConfirmationDecision.BLOCK:
            return _Evaluation(
                decision=band,
                proceed=False,
                action_taken="BLOCK_LOW_CONFIDENCE",
                reasoning_summary="Confidence < 0.70; human confirmation mandatory (ADR-049 §D4).",
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
            )

        # L1 reads (prepare_deployment): REVIEW band → deferred, no HITL hold.
        if ctx.auto_only and band is ConfirmationDecision.REVIEW:
            return _Evaluation(
                decision=band,
                proceed=False,
                action_taken="HALT_REVIEW_DEFERRED",
                reasoning_summary="Prepare read below AUTO band; reads are AUTO-only (L1), no HITL hold.",
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="review_deferred",
                requires_hitl=True,
            )

        # L2/L3 deploy: REVIEW band + no CTO reviewer marker → HOLD for sign-off.
        if band is ConfirmationDecision.REVIEW and ctx.human_reviewed_by is None:
            reason = (
                "Production deploy: CTO approval required (ADR-081 §L3). "
                "No approval_token supplied — HOLD, escalated to CTO."
                if ctx.requires_step_up
                else "Staging deploy: CTO review required (ADR-081 §L2). "
                "No approval_token supplied — HOLD, escalated to CTO."
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
                    f"DEPLOY_SAFETY overlay {ctx.compliance_result}; "
                    f"blocked, escalated to {self._mask.cto_role}."
                ),
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.cto_role,
            )

        note = f" (reviewed by {ctx.human_reviewed_by})" if ctx.human_reviewed_by else ""
        return _Evaluation(
            decision=band,
            proceed=True,
            action_taken=ctx.success_action,
            reasoning_summary=f"All deploy gates satisfied at {band.value} confidence{note}.",
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
        executed: bool,
        compliance_result: ComplianceResult,
        reasoning: str,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.datetime.utcnow().isoformat(),
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
                except DeployPortError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=ev.compliance_result,
                        reasoning=f"Port raised {type(exc).__name__}: {exc}",
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
