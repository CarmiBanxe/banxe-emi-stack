"""CRMAgent — L2 client-facing referral/CRM agent (ADR-049 Referral / CRM mask).

WHY: ADR-049 (Intent Layer & Client-Facing Agent Masks) specifies the
client-facing **Referral / CRM mask** (§D3 row "Referral / CRM"): the governed
surface through which a resolved client intent becomes a bounded referral or CRM
profile action. This module is the emi-stack sibling of
``services/agents/kyc_onboarding_agent.py`` and
``services/agents/notification_agent.py`` and the analogue of banxe-payment-core's
``src/agents/payments_agent.py`` / ``fx_exchange_agent.py`` — it implements the
agent *logic* and *governance enforcement* of the Referral / CRM mask; it does
NOT implement the port (``services/crm/crm_provider_port.py`` is UNTOUCHED), the
legacy referral domain (``services/referral/*`` is UNTOUCHED), the
LLM-orchestration/routing layer (``AGENT_ROUTING_ENABLED`` stays out of scope —
Terminal A infra, ADR-049 §D6/§D7), or the ClickHouse sink.

The Referral / CRM mask (ADR-049 §D3 row "Referral / CRM"), enforced here in the
fixed §D2 chain order (process_ref → scope → band → cost_cap →
compliance(PII + anti-abuse) → [step-up N/A] → port call; biometric step-up is
N/A — a referral/CRM update never moves client funds):

* ``scope``                — ``CRMProviderPort`` operations only (the allow-list:
                             register_referral / resolve_referral_code / get_user
                             / update_user_tier). The port is injected, never
                             implemented here; an op not on the allow-list is
                             rejected outright.
* ``autonomy_level``       — AUTO-biased (ADR-049 §D3): a routine referral
                             registration or tier update proceeds AUTO within cap
                             and a code-resolution/profile read is AUTO-eligible.
* ``confirmation_policy``  — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70
                             (ADR-047 thresholds, ADR-049 §D4). **Override:** an
                             incentive/payout-linked action (register_referral or
                             update_user_tier carrying ``payout_linked``) is forced
                             to the REVIEW band and held for a human reviewer
                             *regardless of confidence* (ADR-049 §D3 "REVIEW for
                             incentive/payout-linked actions"). No biometric
                             step-up (not money movement, ADR-049 §D4).
* ``cost_cap``             — per-request AND per-window hard caps, token AND
                             monetary (Decimal) dimensions (ADR-047 §D2, ADR-049 §D3).
* ``lineage_obligation``   — one ``AgentDecisionRecord`` per action (ADR-046),
                             non-optional, emitted on every exit path.
* ``compliance_gate``      — the PII + anti-abuse overlay (ADR-016 PII-handling +
                             referral anti-abuse, R-COMP-FCA-03): the L3 check MUST
                             pass before a port call; a non-PASS verdict halts
                             (BLOCK). A PII failure escalates to the DPO; an
                             anti-abuse failure (self-referral / duplicate pair,
                             defined by the CONTRACT) escalates to AML.

Any one of {unresolved process_ref, out-of-scope op, below-band confidence,
payout-linked REVIEW with no reviewer, cost-cap breach, compliance(PII/anti-abuse)
fail} halts the action (ADR-049 §D4 — independent halt conditions). Mask *values*
(caps, thresholds, scope, gate, escalation roles) are config-as-data (CLAUDE.md
§10), carried on :class:`CRMMask`, never hardcoded in flow logic.

PAYOUT / INCENTIVE DETECTION (assumption, documented):
The "is this referral/tier action incentive- or payout-linked?" classification is
performed **upstream** (the intent-resolution layer) and carried into the agent as
a single structured boolean — :attr:`RegisterReferralIntent.payout_linked` /
:attr:`UpdateTierIntent.payout_linked`. The agent HONORS that signal and never
parses free text for amounts/incentives (fragile-regex detection is explicitly out
of scope, config-as-data per CLAUDE.md §10). When the upstream layer marks an
action payout-linked it sets ``payout_linked=True`` at the call site; the agent
then forces REVIEW.

ANTI-ABUSE (assumption, documented):
Self-referral and duplicate-pair are CONTRACT-defined abuse conditions
(``crm_provider_port.py``: SelfReferral / AlreadyRegistered). The L3 anti-abuse
overlay classifies them upstream and the verdict is carried in as the
``compliance_result`` (PII + anti-abuse net verdict); a non-PASS verdict BLOCKs
the action before the port is ever called and escalates to AML. The port enforces
the same conditions as defense-in-depth (a CONTRACT ``RegisterReferralResult`` with
``accepted=False`` / ``reason`` is surfaced verbatim on the outcome).
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
from services.crm.crm_provider_port import (
    CRMProviderError,
    CRMProviderPort,
    CRMUserId,
    ReferralCode,
    ReferralEvent,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3). Referral / CRM is AUTO-biased: routine
    referral/tier updates and reads are AUTO-eligible within cap; only an
    incentive/payout-linked action is forced down to REVIEW."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


class ComplianceOverlay(StrEnum):
    """Which arm of the PII + anti-abuse gate is the primary escalation route for an
    action (ADR-049 §D3 compliance_gate). Both overlays gate every action; this
    selects the role a non-PASS verdict escalates to: PII → DPO, anti-abuse → AML."""

    PII = "PII"
    ANTI_ABUSE = "ANTI_ABUSE"


# ---------------------------------------------------------------------------
# Value types — mask config (the shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CRMMask:
    """Config-as-data Referral / CRM mask (ADR-049 §D3 row "Referral / CRM"). Values
    are governed config, not hardcoded flow logic; the AUTO/REVIEW/BLOCK *scale* is
    ADR-047 canon. The mask is the allow-list and the gate posture for the capability."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.AUTO_BIASED
    lineage_obligation: bool = True
    # Escalation roles (config-as-data, never hardcoded in flow logic): a PII-overlay
    # failure escalates to the DPO (ADR-016); an anti-abuse failure (self-referral /
    # duplicate pair) escalates to AML (R-COMP-FCA-03 referral fraud analysis).
    dpo_role: str = "DPO"
    abuse_role: str = "AML"
    agent_id: str = "crm_agent"

    # The mask scope (ADR-049 §D3 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "CRMProviderPort.register_referral",
        "CRMProviderPort.resolve_referral_code",
        "CRMProviderPort.get_user",
        "CRMProviderPort.update_user_tier",
    )

    # L3 compliance contour required before any port call: PII + anti-abuse overlay.
    compliance_gate: tuple[str, ...] = ("PII", "ANTI_ABUSE")


@dataclass
class RegisterReferralIntent:
    """A resolved client intent to register a referral (``register_referral``).

    AUTO-biased (ADR-049 §D3): a routine referral registration proceeds AUTO within
    cap. **Override:** when :attr:`payout_linked` is True the registration is tied to
    an incentive/payout, so the action is forced to the REVIEW band and held for a
    human reviewer regardless of confidence (ADR-049 §D3). The payout classification
    is an upstream, structured signal — the agent honors it and never regex-parses
    free text (see module docstring). Self-referral / duplicate-pair anti-abuse is
    carried in via the ``compliance_result`` verdict (CONTRACT-defined conditions).
    """

    intent_text: str
    process_ref: ProcessRef
    referrer: CRMUserId
    referee: CRMUserId
    code: ReferralCode
    occurred_at: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    payout_linked: bool = False
    metadata: dict[str, object] | None = None


@dataclass
class ResolveCodeIntent:
    """A resolved low-consequence read intent (``resolve_referral_code``) — the
    mask's "reads are AUTO-eligible within cap" path (ADR-049 §D3). A read below the
    AUTO band halts for a re-check, not a HITL hold; never carries a payout signal."""

    intent_text: str
    process_ref: ProcessRef
    code: ReferralCode
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetUserIntent:
    """A resolved profile-read intent (``get_user``) — AUTO-eligible within cap. The
    PII overlay (ADR-016) MUST pass before the profile is returned; a non-PASS PII
    verdict blocks the read and escalates to the DPO (ADR-049 §D3 compliance_gate)."""

    intent_text: str
    process_ref: ProcessRef
    user_id: CRMUserId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class UpdateTierIntent:
    """A resolved client intent to change a user's tier (``update_user_tier``).

    AUTO-biased (ADR-049 §D3): a routine tier update proceeds AUTO within cap.
    **Override:** when :attr:`payout_linked` is True the tier change is tied to an
    incentive/payout, so the action is forced to the REVIEW band and held for a human
    reviewer regardless of confidence (ADR-049 §D3). The payout classification is an
    upstream, structured signal — the agent honors it and never regex-parses text.
    """

    intent_text: str
    process_ref: ProcessRef
    user_id: CRMUserId
    tier: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    payout_linked: bool = False


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
    # Which arm of the PII + anti-abuse gate is the primary escalation route on a
    # non-PASS verdict (PII → DPO, anti-abuse → AML).
    compliance_overlay: ComplianceOverlay
    human_reviewed_by: str | None
    # A register/tier update supports a REVIEW-band HITL hold; a read is AUTO-only and
    # instead halts below the AUTO band. Defaults False so the read path is unchanged.
    supports_review_hitl: bool = False
    # Payout/incentive override: a payout-linked action is forced to the REVIEW band
    # and held for a reviewer regardless of confidence (ADR-049 §D3).
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


class CRMAgent:
    """L2 referral/CRM agent enforcing the ADR-049 Referral / CRM mask.

    The provider port and the lineage recorder are injected as interfaces
    (constructor injection); the agent contains pure governance logic and is
    unit-testable without any live infra.
    """

    def __init__(
        self,
        *,
        provider_port: CRMProviderPort,
        recorder: DecisionRecorder,
        mask: CRMMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._provider = provider_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def register_referral(
        self,
        intent: RegisterReferralIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Register a referral via ``CRMProviderPort.register_referral`` under the mask.

        AUTO-biased (ADR-049 §D3): a routine registration within cap proceeds AUTO.
        If ``intent.payout_linked`` is set the registration is incentive/payout-linked,
        so the action is forced to the REVIEW band and held for a human reviewer
        regardless of confidence; supply ``human_reviewed_by`` to proceed. The PII +
        anti-abuse overlay (``compliance_result``) must PASS before the port is called;
        a non-PASS verdict blocks and escalates (anti-abuse → AML). The provider's
        CONTRACT result (``accepted`` / ``reason`` for self-referral or duplicate
        pair) is surfaced verbatim on the outcome.
        """
        event = ReferralEvent(
            referrer=intent.referrer,
            referee=intent.referee,
            code=intent.code,
            occurred_at=intent.occurred_at,
            correlation_id=intent.correlation_id,
            metadata=intent.metadata,
        )
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"register_referral:{intent.referrer}->{intent.referee}",
            success_action="REGISTER_REFERRAL",
            op="CRMProviderPort.register_referral",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.ANTI_ABUSE,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            force_review=intent.payout_linked,
        )
        return await self._run_action(ctx, lambda: self._provider.register_referral(event))

    async def resolve_referral_code(
        self,
        intent: ResolveCodeIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Low-consequence read via ``CRMProviderPort.resolve_referral_code`` —
        AUTO-eligible, no HITL hold (the mask's within-cap read path, ADR-049 §D3).
        A read below the AUTO band halts for a re-check, not a HITL hold."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"resolve_referral_code:{intent.code}",
            success_action="RESOLVE_REFERRAL_CODE",
            op="CRMProviderPort.resolve_referral_code",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.ANTI_ABUSE,
            human_reviewed_by=None,
        )
        return await self._run_action(
            ctx, lambda: self._provider.resolve_referral_code(intent.code)
        )

    async def get_user(
        self,
        intent: GetUserIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Profile read via ``CRMProviderPort.get_user`` — AUTO-eligible within cap.

        The PII overlay (ADR-016) gate (``compliance_result``) must PASS before the
        profile is returned; a non-PASS PII verdict blocks the read and escalates to
        the DPO (ADR-049 §D3 compliance_gate). A read below the AUTO band halts for a
        re-check, not a HITL hold."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_user:{intent.user_id}",
            success_action="GET_USER",
            op="CRMProviderPort.get_user",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._provider.get_user(intent.user_id))

    async def update_user_tier(
        self,
        intent: UpdateTierIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Apply a tier change via ``CRMProviderPort.update_user_tier`` under the mask.

        AUTO-biased (ADR-049 §D3): a routine tier change within cap proceeds AUTO.
        If ``intent.payout_linked`` is set the tier change is incentive/payout-linked,
        so the action is forced to the REVIEW band and held for a human reviewer
        regardless of confidence; supply ``human_reviewed_by`` to proceed. The PII +
        anti-abuse overlay (``compliance_result``) must PASS before the port is called.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"update_user_tier:{intent.user_id}:{intent.tier}",
            success_action="UPDATE_USER_TIER",
            op="CRMProviderPort.update_user_tier",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.ANTI_ABUSE,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            force_review=intent.payout_linked,
        )
        return await self._run_action(
            ctx,
            lambda: self._provider.update_user_tier(
                intent.user_id, intent.tier, intent.correlation_id
            ),
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

    def _compliance_role(self, overlay: ComplianceOverlay) -> str:
        # PII failures route to the DPO (ADR-016); anti-abuse failures route to AML
        # (R-COMP-FCA-03 referral fraud analysis). Roles are config-as-data.
        return self._mask.dpo_role if overlay is ComplianceOverlay.PII else self._mask.abuse_role

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
                f"Operation {ctx.op} is not on the Referral / CRM mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70)
        #    + ADR-049 §D3 payout-linked override (force REVIEW regardless of confidence).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            # Payout/incentive-linked: an otherwise-AUTO action is pulled down to
            # REVIEW so a human confirms anything tied to a payout (ADR-049 §D3).
            policies.append("ADR-049-D3-payout-linked-REVIEW")
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
            # Register/tier in the REVIEW band (low confidence OR payout-linked) holds.
            if ctx.human_reviewed_by is None:
                reason = (
                    "Payout-linked action pulled to REVIEW; paused for HITL regardless "
                    "of confidence (ADR-049 §D3)."
                    if ctx.force_review
                    else "Action in REVIEW band; paused for HITL confirmation (ADR-049 §D4)."
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

        # 5. L3 compliance gate — PII + anti-abuse overlay. A non-PASS verdict halts
        #    AND escalates (PII → DPO, anti-abuse → AML).
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
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

        # Biometric step-up: N/A for referral/CRM (no money movement, ADR-049 §D4).
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
                except CRMProviderError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=ev.compliance_result,
                        reasoning=f"Provider rejected the action: {exc}",
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
        producer→sink seam used by every exit path)."""
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
    "CRMAgent",
    "CRMMask",
    "ComplianceOverlay",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "GetUserIntent",
    "ProcessRef",
    "RegisterReferralIntent",
    "RequestCost",
    "ResolveCodeIntent",
    "UpdateTierIntent",
]
