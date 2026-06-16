"""CampaignAgent — L2 Marketing campaign agent (ORG §2.8.2, COBS 4 MLRO mask).

WHY: ORG-STRUCTURE §2.8.2 (Marketing & Growth) specifies the `CampaignAgent`
(L2 Review; gate **MLRO for financial promotions**; Listmonk). This module is the
emi-stack analogue of the §D2 client-facing masks (``kyc_onboarding_agent.py`` /
``crm_agent.py``): it implements the agent *logic* and *governance enforcement* of
the campaign mask over :class:`~services.campaign.campaign_port.CampaignPort`; it
does NOT implement the port, the Listmonk adapter, the LLM-orchestration/routing
layer (``AGENT_ROUTING_ENABLED`` stays out of scope), or any lineage sink. The
referral domain (``services/referral/campaign_manager.py``) is NOT touched.

THE REGULATORY INVARIANT (COBS 4 — enforced in code AND test)
-------------------------------------------------------------
"All marketing content involving financial products MUST be reviewed by MLRO
before publication. AI may draft but NEVER auto-publish." Therefore a campaign
action that PUBLISHES financial-promotion content can NEVER be executed
autonomously — it is a **mandatory step-up to MLRO regardless of confidence**: the
publish proceeds only with a valid, campaign-bound :class:`MlroReviewToken`; with
no/invalid token the action HALTS, the domain publish is NEVER called, and the
action escalates to the MLRO. Drafting (``prepare_campaign``) is free.

The campaign mask (ORG §2.8.2), enforced in the fixed §D2 chain order
(process_ref → scope → band → cost_cap → compliance → step-up → port call):

* ``scope``               — :class:`CampaignPort` ops only (the allow-list:
                            prepare_campaign / publish_campaign / list_campaigns).
* ``autonomy_level``      — REVIEW (L2). Reads (list) are AUTO-eligible within cap;
                            drafting is REVIEW-biased; publishing a financial promo
                            is a mandatory MLRO step-up regardless of confidence.
* ``confirmation_policy`` — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047).
* ``cost_cap``            — per-request AND per-window hard caps, token AND monetary.
* ``lineage_obligation``  — one ``AgentDecisionRecord`` per action (ADR-046), on
                            every exit path.
* ``compliance_gate``     — COBS 4 + Consumer Duty; a non-PASS result halts AND
                            escalates to the MLRO.
* ``mlro_publish_gate``   — COBS 4: financial-promotion publish requires a valid
                            MLRO review token (mandatory step-up, never autonomous).

Mask *values* (caps, thresholds, scope, gate, MLRO role) are config-as-data,
carried on :class:`CampaignMask`, never hardcoded in flow logic — EXCEPT the COBS 4
financial-promotion token requirement, which is a hard regulatory floor that mask
config can only *strengthen*, never disable.

R-SEC (ADR-021): the lineage record carries opaque metadata ONLY —
``campaign_id``/``segment``/``channel``, never the marketing content (subject/body)
or recipient PII. Content rides on the intent's :class:`CampaignDraft` straight to
the port and is returned on ``AgentOutcome.result``, never recorded.
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
from services.campaign.campaign_port import (
    CampaignDraft,
    CampaignPort,
    CampaignPortError,
    MlroReviewToken,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture. Campaign is REVIEW-biased: drafting is L2 HITL-capable,
    reads are AUTO-eligible, publishing a financial promo is mandatory MLRO step-up."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


# ---------------------------------------------------------------------------
# Value types — mask config (shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CampaignMask:
    """Config-as-data campaign mask (ORG §2.8.2). The COBS 4 financial-promotion
    publish gate is a regulatory floor: ``require_mlro_for_publish`` may force MLRO
    review on EVERY publish, but a financial promotion ALWAYS requires it regardless
    of this flag (it can only be strengthened, never disabled)."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.REVIEW_BIASED
    lineage_obligation: bool = True
    # COBS 4: when True, EVERY publish requires an MLRO token (not just financial
    # promotions). A financial promotion requires one irrespective of this flag.
    require_mlro_for_publish: bool = True
    # The human double notified/escalated to for campaign sign-off (ORG §2.8.2).
    mlro_role: str = "MLRO"
    agent_id: str = "campaign_agent"

    # The mask scope (ADR-049 §D3 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "CampaignPort.prepare_campaign",
        "CampaignPort.publish_campaign",
        "CampaignPort.list_campaigns",
    )

    # Compliance contour required before any campaign action.
    compliance_gate: tuple[str, ...] = ("COBS4", "CONSUMER_DUTY")


@dataclass
class PrepareCampaignIntent:
    """A resolved intent to DRAFT a marketing campaign (``prepare_campaign``).

    REVIEW-biased: the REVIEW band holds for a human reviewer and proceeds once one
    is supplied; AUTO proceeds within cap. Drafting is free of the COBS 4 publish
    gate — composing content is never a publication."""

    intent_text: str
    process_ref: ProcessRef
    draft: CampaignDraft
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class PublishCampaignIntent:
    """A resolved intent to PUBLISH/SEND a marketing campaign (``publish_campaign``).

    COBS 4 mandatory step-up: a financial-promotion publish is NEVER autonomous —
    it requires a valid, campaign-bound :class:`MlroReviewToken` regardless of the
    confidence band. With no/invalid token the publish HALTS and the domain publish
    is never called."""

    intent_text: str
    process_ref: ProcessRef
    draft: CampaignDraft
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ListCampaignsIntent:
    """A resolved low-consequence read intent (``list_campaigns``) — AUTO-eligible;
    a read below the AUTO band halts for a re-check, not a HITL hold."""

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


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
    # COBS 4 publish gate: True when this action needs a valid MLRO token to proceed.
    requires_mlro_token: bool = False
    mlro_token_valid: bool = False
    human_reviewed_by: str | None = None
    # REVIEW-biased actions (drafting) hold for HITL in the REVIEW band; pure reads
    # instead halt below AUTO. Defaults False so the read path is unchanged.
    supports_review_hitl: bool = False


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
    requires_step_up: bool = False
    requires_hitl: bool = False
    escalated_to: str | None = None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class CampaignAgent:
    """L2 marketing campaign agent enforcing the ORG §2.8.2 / COBS 4 campaign mask.

    The campaign port and the lineage recorder are injected as interfaces; the agent
    contains pure governance logic and is unit-testable without any live infra.
    """

    def __init__(
        self,
        *,
        campaign_port: CampaignPort,
        recorder: DecisionRecorder,
        mask: CampaignMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = campaign_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def prepare_campaign(
        self,
        intent: PrepareCampaignIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Draft a campaign via ``CampaignPort.prepare_campaign`` under the mask.

        Free of the COBS 4 publish gate (drafting is not publication). REVIEW-biased:
        the REVIEW band holds for HITL and proceeds once a human reviewer is supplied.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"prepare_campaign:{intent.draft.campaign_id}:{intent.draft.segment}",
            success_action="PREPARE_CAMPAIGN",
            op="CampaignPort.prepare_campaign",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
        )
        return await self._run_action(ctx, lambda: self._port.prepare_campaign(intent.draft))

    async def publish_campaign(
        self,
        intent: PublishCampaignIntent,
        *,
        mlro_token: MlroReviewToken | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Publish/send a campaign — the regulated COBS 4 path.

        A financial-promotion publish is NEVER autonomous: it forces a step-up to
        the MLRO and proceeds only with a valid, campaign-bound ``mlro_token``,
        regardless of the confidence band. With no/invalid token the action HALTS,
        ``CampaignPort.publish_campaign`` is NEVER called, and the action escalates
        to the MLRO. The mask may additionally require a token on every publish; a
        financial promotion requires one irrespective of that flag.
        """
        draft = intent.draft
        requires_token = draft.is_financial_promotion or self._mask.require_mlro_for_publish
        token_valid = mlro_token is not None and mlro_token.is_valid_for(draft.campaign_id)
        # A valid token is MLRO sign-off — record who reviewed (opaque metadata).
        reviewer = mlro_token.reviewed_by if token_valid and mlro_token is not None else None
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=(
                f"publish_campaign:{draft.campaign_id}:{draft.segment}:{draft.channel.value}"
            ),
            success_action="PUBLISH_CAMPAIGN",
            op="CampaignPort.publish_campaign",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            requires_mlro_token=requires_token,
            mlro_token_valid=token_valid,
            human_reviewed_by=reviewer,
            supports_review_hitl=True,
        )
        # The port is reached ONLY when the step-up gate has passed (token valid),
        # so a non-None token is guaranteed here; the port re-checks (defence in depth).
        return await self._run_action(
            ctx,
            lambda: self._port.publish_campaign(draft, mlro_token),  # type: ignore[arg-type]
        )

    async def list_campaigns(
        self,
        intent: ListCampaignsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Low-consequence read via ``CampaignPort.list_campaigns`` — AUTO-eligible,
        no HITL hold and no step-up (the mask's within-cap read path)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="list_campaigns",
            success_action="LIST_CAMPAIGNS",
            op="CampaignPort.list_campaigns",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.list_campaigns())

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

        # 2. ADR-049 §D3 — mask scope allow-list; an off-list op is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the campaign mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if band is ConfirmationDecision.BLOCK:
            # Low confidence on a publish escalates to the MLRO.
            escalated = self._mask.mlro_role if ctx.requires_mlro_token else None
            return _Evaluation(
                band,
                False,
                "BLOCK_LOW_CONFIDENCE",
                "Confidence < 0.70: full stop, human confirmation mandatory.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
                escalated_to=escalated,
            )
        if band is ConfirmationDecision.REVIEW and not ctx.supports_review_hitl:
            # Read path: reads are AUTO-only, so a below-AUTO read halts for a
            # re-check at higher confidence, not a HITL hold.
            return _Evaluation(
                band,
                False,
                "HALT_REVIEW_DEFERRED",
                "Read intent below AUTO band; reads are AUTO-only, no HITL hold.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="review_deferred",
                requires_hitl=True,
            )

        # REVIEW-biased drafting requires a human reviewer in the REVIEW band; the
        # publish path is gated by the COBS 4 step-up below, not by this HITL hold.
        needs_reviewer = (
            ctx.supports_review_hitl
            and not ctx.requires_mlro_token
            and band is ConfirmationDecision.REVIEW
        )
        if needs_reviewer and ctx.human_reviewed_by is None:
            policies.append("ADR-049-D3-review-HITL")
            return _Evaluation(
                band,
                False,
                "HOLD_FOR_REVIEW",
                "REVIEW-band drafting paused for HITL; proceeds once a reviewer is supplied.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="hitl_review_required",
                requires_hitl=True,
            )

        # 4. ADR-047 — hard cost cap (per-request AND per-window).
        policies.append("ADR-047-cost-cap")
        if self._cost_breaches(ctx.request_cost):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COST_CAP_BREACH",
                "Cost-cap breach (per-request or per-window); action refused (ADR-047).",
                policies,
                ComplianceResult.NA,
                BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        # 5. Compliance gate (COBS 4 + Consumer Duty). A non-PASS result halts AND
        #    escalates to the MLRO.
        policies.append("COBS4-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"Compliance gate returned {ctx.compliance_result}; "
                f"action blocked and escalated to {self._mask.mlro_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.mlro_role,
            )

        # 6. COBS 4 MANDATORY MLRO STEP-UP — a financial-promotion publish can NEVER
        #    be autonomous: it requires a valid MLRO review token regardless of the
        #    confidence band, else HALT and escalate to the MLRO (publish NOT called).
        if ctx.requires_mlro_token and not ctx.mlro_token_valid:
            policies.append("COBS4-MLRO-publish-step-up")
            return _Evaluation(
                band,
                False,
                "HALT_MLRO_REVIEW_REQUIRED",
                "Financial-promotion publish requires MLRO sign-off (COBS 4): no valid "
                "review token — forced step-up, nothing sent, escalated to MLRO.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="mlro_review_required",
                requires_step_up=True,
                requires_hitl=True,
                escalated_to=self._mask.mlro_role,
            )

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
        compliance_result = ev.compliance_result
        escalated_to = ev.escalated_to

        if ev.proceed:
            if port_call is not None:
                try:
                    result = await port_call()
                except CampaignPortError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=compliance_result,
                        reasoning=f"Campaign port rejected the action: {exc}",
                        escalated_to=escalated_to,
                    )
                    raise
            executed = True
            self._window.add(ctx.request_cost)

        record = await self._emit(
            ctx,
            ev,
            action_taken,
            executed=executed,
            compliance_result=compliance_result,
            reasoning=ev.reasoning_summary,
            escalated_to=escalated_to,
        )
        return AgentOutcome(
            decision=ev.decision,
            executed=executed,
            record=record,
            result=result,
            halt_reason=ev.halt_reason,
            requires_step_up=ev.requires_step_up,
            requires_hitl=ev.requires_hitl,
            escalated_to=escalated_to,
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
        producer→sink seam used by every exit path). R-SEC: opaque metadata only —
        ``intent``/``triggering_event`` carry campaign_id/segment, never content/PII."""
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
    "AutonomyLevel",
    "BudgetBreach",
    "CampaignAgent",
    "CampaignMask",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "ListCampaignsIntent",
    "PrepareCampaignIntent",
    "ProcessRef",
    "PublishCampaignIntent",
    "RequestCost",
]
