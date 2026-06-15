"""KYCOnboardingAgent — L2 client-facing KYC onboarding agent (ADR-049 KYC mask).

WHY: ADR-049 (Intent Layer & Client-Facing Agent Masks) specifies the
client-facing **KYC onboarding mask**: the governed surface through which a
resolved client intent becomes a bounded identity-verification action. This
module is the emi-stack analogue of banxe-payment-core's
``src/agents/payments_agent.py`` / ``fx_exchange_agent.py`` — it implements the
agent *logic* and *governance enforcement* of the KYC mask; it does NOT
implement the port, the LLM-orchestration/routing layer (``AGENT_ROUTING_ENABLED``
stays out of scope — Terminal A infra, ADR-049 §D6/§D7), or the ClickHouse sink.

The KYC mask (ADR-049 §D3), enforced here in the fixed §D2 chain order
(process_ref → scope → band → cost_cap → compliance → step-up → port call):

* ``scope``                — ``KYCProviderPort`` operations only (the allow-list:
                             start_session / get_status / handle_webhook /
                             change_level). The port is injected, never implemented
                             here; an op not on the allow-list is rejected outright.
* ``autonomy_level``       — REVIEW (identity decisions are L2 HITL, ADR-049 §D3).
                             Reads (status) are AUTO-eligible within cap; session
                             start is REVIEW-biased; an identity acceptance/decline
                             is a mandatory-HITL decision regardless of confidence.
* ``confirmation_policy``  — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70
                             (ADR-047 thresholds, ADR-049 §D4). Identity decisions
                             additionally require a human reviewer (mandatory HITL)
                             and biometric step-up where the KYC flow requires it.
* ``cost_cap``             — per-request AND per-window hard caps, token AND
                             monetary (Decimal) dimensions (ADR-047 §D2, ADR-049 §D3).
* ``lineage_obligation``   — one ``AgentDecisionRecord`` per action (ADR-046),
                             non-optional, emitted on every exit path.
* ``compliance_gate``      — KYC + sanctions (Ruflo mandatory, L3); a non-PASS
                             result halts AND escalates to the MLRO
                             (``.claude/rules/agents.md`` MLRO escalation).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence,
missing mandatory HITL, cost-cap breach, compliance fail, missing biometric
step-up} halts the action (ADR-049 §D4 — independent halt conditions). Mask
*values* (caps, thresholds, scope, gate, MLRO role) are config-as-data
(CLAUDE.md §10), carried on :class:`KYCOnboardingMask`, never hardcoded in flow
logic.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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
from services.kyc.kyc_provider_port import (
    KYCProviderError,
    KYCProviderPort,
    KYCTier,
    TierDowngradeBlocked,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3). KYC is REVIEW-biased: identity
    decisions are L2 HITL, reads are AUTO-eligible within cap."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


class IdentityDecision(StrEnum):
    """The two terminal identity verdicts a human reviewer commits (ADR-049 §D3)."""

    ACCEPT = "accept"
    DECLINE = "decline"


# ---------------------------------------------------------------------------
# Value types — mask config (the shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class KYCOnboardingMask:
    """Config-as-data KYC onboarding mask (ADR-049 §D3). Values are governed
    config, not hardcoded flow logic; the AUTO/REVIEW/BLOCK *scale* is ADR-047
    canon. The mask is the allow-list and the gate posture for the capability."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.REVIEW_BIASED
    lineage_obligation: bool = True
    # Identity decisions require biometric step-up where the KYC flow requires it
    # (per-intent ``biometric_required``); this mask toggle can disable it entirely.
    require_biometric_for_identity: bool = True
    # The human double notified/escalated to for KYC (`.claude/rules/agents.md`).
    mlro_role: str = "MLRO"
    agent_id: str = "kyc_onboarding_agent"

    # The mask scope (ADR-049 §D3 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "KYCProviderPort.start_session",
        "KYCProviderPort.get_status",
        "KYCProviderPort.handle_webhook",
        "KYCProviderPort.change_level",
    )

    # L3 compliance contour required before any KYC action (Ruflo mandatory).
    compliance_gate: tuple[str, ...] = ("KYC", "SANCTIONS")


@dataclass
class StartOnboardingIntent:
    """A resolved client intent to begin KYC onboarding (``start_session``).

    REVIEW-biased (ADR-049 §D3): a session start in the REVIEW band holds for a
    human reviewer and proceeds only once one is supplied; AUTO proceeds within cap.
    """

    intent_text: str
    process_ref: ProcessRef
    user_id: str
    tier: KYCTier
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class StatusCheckIntent:
    """A resolved low-consequence read intent (``get_status``) — the mask's
    "reads are AUTO-eligible within cap" path (ADR-049 §D3). A read below the AUTO
    band halts for a re-check, not a HITL hold."""

    intent_text: str
    process_ref: ProcessRef
    user_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class IdentityDecisionIntent:
    """A resolved identity acceptance/decline — the mask's mandatory-HITL decision.

    Identity decisions are L2 HITL (ADR-049 §D3): a human reviewer is required
    regardless of the confidence band, and biometric step-up is required where the
    KYC flow demands it (``biometric_required``). On ACCEPT the agent calls
    ``change_level`` to ``target_tier``; on DECLINE no provider mutation is made —
    the declined verdict is recorded as lineage and the tier is left unchanged.
    """

    intent_text: str
    process_ref: ProcessRef
    user_id: str
    decision: IdentityDecision
    target_tier: KYCTier
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    biometric_required: bool = False
    biometric_verified: bool = False


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
    requires_biometric: bool
    biometric_verified: bool
    human_reviewed_by: str | None
    # Money-movement-equivalent for KYC: REVIEW-biased actions (session start,
    # identity decision) hold for HITL in the REVIEW band; pure reads instead halt
    # below AUTO. Defaults False so the read path is unchanged.
    supports_review_hitl: bool = False
    # Identity decisions require a human reviewer regardless of band (mandatory HITL).
    mandatory_hitl: bool = False


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


class KYCOnboardingAgent:
    """L2 KYC onboarding agent enforcing the ADR-049 KYC mask.

    The provider port and the lineage recorder are injected as interfaces
    (constructor injection); the agent contains pure governance logic and is
    unit-testable without any live infra.
    """

    def __init__(
        self,
        *,
        provider_port: KYCProviderPort,
        recorder: DecisionRecorder,
        mask: KYCOnboardingMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._provider = provider_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def start_onboarding(
        self,
        intent: StartOnboardingIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Begin KYC onboarding via ``KYCProviderPort.start_session`` under the mask.

        REVIEW-biased (ADR-049 §D3): the REVIEW band holds for HITL and proceeds
        only once a human reviewer is supplied; not an identity decision, so no
        biometric step-up.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"start_onboarding:{intent.user_id}:{intent.tier.value}",
            success_action="START_KYC_SESSION",
            op="KYCProviderPort.start_session",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            requires_biometric=False,
            biometric_verified=False,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
        )
        return await self._run_action(
            ctx,
            lambda: self._provider.start_session(
                intent.user_id, intent.tier, intent.correlation_id
            ),
        )

    async def check_status(
        self,
        intent: StatusCheckIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Low-consequence read via ``KYCProviderPort.get_status`` — AUTO-eligible,
        no HITL hold and no step-up (the mask's within-cap read path, ADR-049 §D3)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"check_status:{intent.user_id}",
            success_action="CHECK_KYC_STATUS",
            op="KYCProviderPort.get_status",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            requires_biometric=False,
            biometric_verified=False,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._provider.get_status(intent.user_id))

    async def accept_or_decline_identity(
        self,
        intent: IdentityDecisionIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Commit an identity acceptance/decline — the mask's mandatory-HITL decision.

        Identity decisions are L2 HITL (ADR-049 §D3): a human reviewer is required
        regardless of the confidence band, escalating to the MLRO; biometric step-up
        is required where the KYC flow demands it. On ACCEPT, ``change_level`` is
        called to ``target_tier``; on DECLINE no provider mutation is made and the
        declined verdict is recorded as lineage (the tier is left unchanged).
        """
        is_accept = intent.decision is IdentityDecision.ACCEPT
        success_action = "ACCEPT_IDENTITY" if is_accept else "DECLINE_IDENTITY"
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"identity_decision:{intent.decision.value}:{intent.user_id}",
            success_action=success_action,
            op="KYCProviderPort.change_level",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            requires_biometric=intent.biometric_required,
            biometric_verified=intent.biometric_verified,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            mandatory_hitl=True,
        )
        # ACCEPT mutates the provider tier; DECLINE commits the verdict with no
        # provider call (port_call=None) — both still owe exactly one lineage record.
        port_call: Callable[[], Awaitable[object]] | None = (
            (
                lambda: self._provider.change_level(
                    intent.user_id, intent.target_tier, intent.correlation_id
                )
            )
            if is_accept
            else None
        )
        return await self._run_action(ctx, port_call)

    async def handle_provider_webhook(
        self,
        payload: object,
        signature: str,
        *,
        correlation_id: str | None = None,
        request_cost: RequestCost | None = None,
        intent_text: str = "kyc_provider_webhook",
    ) -> AgentOutcome:
        """Process a provider-initiated status webhook via ``KYCProviderPort.handle_webhook``.

        Provider-initiated (not a client intent), so it does not traverse the
        confidence-band chain; it still emits exactly one lineage record (ADR-046)
        on every exit path. The port verifies the HMAC signature BEFORE any
        processing (ADR-034): an invalid signature raises :class:`InvalidSignature`,
        which is recorded as an MLRO-escalated halt and re-raised. Idempotency is the
        port's contract — a duplicate event returns ``deduped=True`` and applies no
        state change; the agent records the de-dup without re-processing.
        """
        cid = correlation_id or str(uuid.uuid4())
        cost = request_cost or RequestCost(tokens=0, cost=Decimal("0"))
        triggering_event = "kyc_provider_webhook"
        policies = ["ADR-034-webhook-hmac-verify", "ADR-046-lineage", "ADR-049-scope-allow-list"]

        try:
            outcome = await self._provider.handle_webhook(payload, signature)
        except KYCProviderError as exc:
            # InvalidSignature (and any provider error) → record then re-raise. A bad
            # signature is a possible attack: escalate to the MLRO (port docstring).
            action_taken = f"HALT_WEBHOOK_ERROR:{type(exc).__name__}"
            await self._record(
                triggering_event=triggering_event,
                intent=intent_text,
                policies=policies,
                compliance_result=ComplianceResult.ESCALATE,
                reasoning=f"Webhook rejected before processing: {exc}",
                confidence_score=1.0,
                action_taken=action_taken,
                human_reviewed_by=None,
                correlation_id=cid,
                request_cost=cost,
                budget_breach=BudgetBreach.NONE,
                escalated_to=self._mask.mlro_role,
            )
            raise
        # Idempotent replay: deduped event applied no state change (ADR-034).
        deduped = outcome.deduped
        action_taken = "WEBHOOK_DEDUPED" if deduped else "WEBHOOK_PROCESSED"
        reasoning = (
            "Duplicate provider event id — idempotent replay, no state change applied."
            if deduped
            else "Provider event verified and applied; status transition persisted."
        )
        record = await self._record(
            triggering_event=triggering_event,
            intent=intent_text,
            policies=policies,
            compliance_result=ComplianceResult.NA,
            reasoning=reasoning,
            confidence_score=1.0,
            action_taken=action_taken,
            human_reviewed_by=None,
            correlation_id=cid,
            request_cost=cost,
            budget_breach=BudgetBreach.NONE,
            escalated_to=None,
        )
        if not deduped:
            self._window.add(cost)
        return AgentOutcome(
            decision=ConfirmationDecision.AUTO,
            executed=not deduped,
            record=record,
            result=outcome,
            halt_reason=None,
        )

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

    def _step_up_required(self, ctx: _ActionContext) -> bool:
        # Biometric step-up is required only for identity decisions whose flow demands
        # it, and only while the mask enables identity step-up (config-as-data).
        return ctx.requires_biometric and self._mask.require_biometric_for_identity

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
                f"Operation {ctx.op} is not on the KYC mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70)
        #    + ADR-049 §D3 mandatory HITL for identity decisions.
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if band is ConfirmationDecision.BLOCK:
            # Low confidence on an identity decision escalates to the MLRO.
            escalated = self._mask.mlro_role if ctx.mandatory_hitl else None
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
                escalated_to=escalated,
            )
        if band is ConfirmationDecision.REVIEW:
            # Read path: reads are AUTO-only, so a below-AUTO read halts for a
            # re-check at higher confidence, not a HITL hold (ADR-049 §D3).
            if not ctx.supports_review_hitl:
                return _Evaluation(
                    band,
                    False,
                    "HALT_REVIEW_DEFERRED",
                    "Read intent below AUTO band; reads are AUTO-only, no HITL hold (ADR-049 §D3).",
                    policies,
                    ctx.compliance_result,
                    BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )

        # ADR-049 §D3 — REVIEW-biased / identity actions require a human reviewer.
        # Reads (no review HITL) skip this; the REVIEW band and every identity
        # decision (mandatory HITL, even at AUTO) hold until a reviewer is supplied.
        needs_reviewer = ctx.supports_review_hitl and (
            band is ConfirmationDecision.REVIEW or ctx.mandatory_hitl
        )
        if needs_reviewer and ctx.human_reviewed_by is None:
            policies.append("ADR-049-D3-identity-HITL")
            return _Evaluation(
                band,
                False,
                "HOLD_FOR_REVIEW",
                "Identity/REVIEW-band action paused for HITL; escalates to MLRO on no response.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="hitl_review_required",
                requires_hitl=True,
                escalated_to=self._mask.mlro_role if ctx.mandatory_hitl else None,
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

        # 5. L3 compliance gate (KYC + sanctions; Ruflo mandatory). A non-PASS
        #    result halts AND escalates to the MLRO (`.claude/rules/agents.md`).
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"L3 compliance gate returned {ctx.compliance_result}; "
                f"action blocked and escalated to {self._mask.mlro_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.mlro_role,
            )

        # 6. ADR-049 §D4 — biometric step-up where the identity flow requires it.
        if self._step_up_required(ctx) and not ctx.biometric_verified:
            policies.append("ADR-049-D4-biometric-step-up")
            return _Evaluation(
                band,
                False,
                "HALT_STEP_UP_REQUIRED",
                "Identity decision requires biometric step-up before commit (ADR-049 §D4).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="step_up_required",
                requires_step_up=True,
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
                except KYCProviderError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    # A regulatory-blocked downgrade is an MLRO escalation (port docstring).
                    if isinstance(exc, TierDowngradeBlocked):
                        compliance_result = ComplianceResult.ESCALATE
                        escalated_to = self._mask.mlro_role
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=compliance_result,
                        reasoning=f"Provider rejected the action: {exc}",
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
        producer→sink seam used by every exit path, including the webhook handler)."""
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
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "IdentityDecision",
    "IdentityDecisionIntent",
    "KYCOnboardingAgent",
    "KYCOnboardingMask",
    "ProcessRef",
    "RequestCost",
    "StartOnboardingIntent",
    "StatusCheckIntent",
]
