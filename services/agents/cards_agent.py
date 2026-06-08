"""CardsAgent — L2 client-facing Cards agent (ADR-053 Cards mask, C22).

WHY: ADR-053 extends the ADR-049 client-facing mask catalogue and adds the
**Cards (C22) mask** as its first new entry. The mask is the governed surface
through which a resolved client intent becomes a bounded card operation. This
module is the emi-stack sibling of ``services/agents/kyc_onboarding_agent.py``,
``notification_agent.py`` and ``crm_agent.py`` and the analogue of
banxe-payment-core's ``src/agents/payments_agent.py`` — it implements the agent
*logic* and *governance enforcement* of the Cards mask; it does NOT implement
the port (``services/card_issuing/card_port.py`` is the CONTRACT, injected as an
interface and never implemented here), it does NOT touch the pre-existing domain
service-agent ``services/card_issuing/card_agent.py`` (ADR-053 D2/D3: that agent
is the adapter BEHIND ``CardPort``, untouched), and it does NOT implement the
LLM-orchestration/routing layer (``AGENT_ROUTING_ENABLED`` stays out of scope —
Terminal A infra, ADR-049 §D6/§D7) or the ClickHouse sink.

The Cards mask (ADR-053 D4), enforced here in the fixed ADR-049 §D2 chain order
(process_ref → scope → band → cost_cap → compliance → step-up → port call):

* ``scope``                — ``CardPort`` operations only (the allow-list:
                             read_card / read_limits / freeze / block / unfreeze /
                             issue_card / change_limit). The port is injected,
                             never implemented here; an op not on the allow-list
                             is rejected outright.
* ``autonomy_level``       — **Mixed** (ADR-053 D4): reads and the protective
                             freeze/block/unfreeze are AUTO-with-cap (a freeze is
                             a *protective*, low-regret action that favours the
                             customer and should fire instantly within cap);
                             issue_card and change_limit are REVIEW-biased
                             (value/credit-affecting).
* ``confirmation_policy``  — AUTO (within cap) for reads and protective
                             freeze/block/unfreeze; **REVIEW + biometric step-up**
                             for issue_card and change_limit — issuance and limit
                             changes move/expose client credit and are critical
                             actions, so biometric step-up is MANDATORY regardless
                             of the confidence band (ADR-049 §D4, ADR-053 D4).
* ``cost_cap``             — per-request AND per-window hard caps, token AND
                             monetary (Decimal) dimensions (ADR-047 §D2, ADR-053 D4).
* ``lineage_obligation``   — one ``AgentDecisionRecord`` per action (ADR-046),
                             non-optional, emitted on every exit path.
* ``compliance_gate``      — **AML + PII** overlay (ADR-016): issuance and limit
                             changes pass the AML contour; all card reads pass the
                             PII overlay; Ruflo mandatory where the action is
                             payment/compliance-classed (`.claude/rules/agents.md`).
                             A non-PASS verdict halts (BLOCK); a PII failure
                             escalates to the DPO, an AML failure to the AML role.

Any one of {unresolved process_ref, out-of-scope op, below-band confidence,
REVIEW-band money-class action with no reviewer, cost-cap breach,
compliance(AML/PII) fail, missing biometric step-up} halts the action (ADR-049
§D4 — independent halt conditions). Mask *values* (caps, thresholds, scope, gate,
escalation roles) are config-as-data (CLAUDE.md §10), carried on
:class:`CardsMask`, never hardcoded in flow logic.

R-SEC / PCI-DSS (R-SEC-PCI-01): the agent NEVER records a full PAN, CVV/CVC, PIN,
or track data in a lineage record. The ``CardPort`` contract already excludes
those values from every CardView / request / result; the agent records only
opaque references (card_id, entity_id, period, status) and the masked-only port
result is returned on ``AgentOutcome.result`` to the caller, NEVER on the record.
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
from services.card_issuing.card_port import (
    CardId,
    CardPort,
    CardPortError,
    IssueCardRequest,
    LimitChange,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3). Cards is **Mixed** (ADR-053 D4): reads
    and protective freeze/block/unfreeze are AUTO-with-cap; issue_card/change_limit
    are REVIEW-biased with mandatory biometric step-up."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"
    MIXED = "mixed"


class ComplianceOverlay(StrEnum):
    """Which arm of the AML + PII gate is the primary escalation route for an action
    (ADR-053 D4 compliance_gate). Both overlays gate every action; this selects the
    role a non-PASS verdict escalates to: card reads → PII → DPO; money-class and
    protective card ops → AML → the AML role (ADR-016)."""

    PII = "PII"
    AML = "AML"


# ---------------------------------------------------------------------------
# Value types — mask config (the shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CardsMask:
    """Config-as-data Cards mask (ADR-053 D4, the C22 catalogue entry). Values are
    governed config, not hardcoded flow logic; the AUTO/REVIEW/BLOCK *scale* is
    ADR-047 canon. The mask is the allow-list and the gate posture for the capability."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.MIXED
    lineage_obligation: bool = True
    # Money-class ops (issue_card / change_limit) require biometric step-up regardless
    # of confidence (ADR-053 D4); this mask toggle can disable it entirely (config-as-data).
    require_biometric_for_money_ops: bool = True
    # Escalation roles (config-as-data, never hardcoded in flow logic): a PII-overlay
    # failure on a read escalates to the DPO (ADR-016); an AML-overlay failure on a
    # money-class / protective op escalates to the AML role.
    dpo_role: str = "DPO"
    aml_role: str = "AML"
    agent_id: str = "cards_agent"

    # The mask scope (ADR-053 D4 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "CardPort.read_card",
        "CardPort.read_limits",
        "CardPort.freeze",
        "CardPort.block",
        "CardPort.unfreeze",
        "CardPort.issue_card",
        "CardPort.change_limit",
    )

    # L3 compliance contour required before any port call: AML + PII overlay (ADR-016).
    compliance_gate: tuple[str, ...] = ("AML", "PII")


@dataclass
class ReadCardIntent:
    """A resolved low-consequence read intent (``read_card``) — the mask's "reads are
    AUTO-eligible within cap" path (ADR-053 D4). The PII overlay (ADR-016) MUST pass
    before the card snapshot is returned; a non-PASS PII verdict blocks the read and
    escalates to the DPO. A read below the AUTO band halts for a re-check, never a
    HITL hold; never carries a biometric/payout signal."""

    intent_text: str
    process_ref: ProcessRef
    card_id: CardId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ReadLimitsIntent:
    """A resolved low-consequence read intent (``read_limits``) — AUTO-eligible within
    cap, PII overlay must PASS (mirrors :class:`ReadCardIntent`)."""

    intent_text: str
    process_ref: ProcessRef
    card_id: CardId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class FreezeIntent:
    """A resolved client intent to freeze a card (``freeze``) — a PROTECTIVE, low-regret
    action that favours the customer, AUTO-with-cap (ADR-053 D4). Passes the AML + PII
    gate; no biometric step-up (not credit-affecting). ``reason`` is a non-PII string."""

    intent_text: str
    process_ref: ProcessRef
    card_id: CardId
    actor: str
    reason: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class BlockIntent:
    """A resolved client intent to block a card (``block``) — PROTECTIVE and TERMINAL
    (irreversible), AUTO-with-cap (ADR-053 D4). Passes the AML + PII gate; no biometric
    step-up. ``reason`` is a non-PII string."""

    intent_text: str
    process_ref: ProcessRef
    card_id: CardId
    actor: str
    reason: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class UnfreezeIntent:
    """A resolved client intent to lift a freeze (``unfreeze``) — protective-reversible,
    AUTO-with-cap (ADR-053 D4): returning a frozen card to ACTIVE favours the customer
    and is low-regret. Passes the AML + PII gate; no biometric step-up."""

    intent_text: str
    process_ref: ProcessRef
    card_id: CardId
    actor: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class IssueCardIntent:
    """A resolved client intent to issue a new card (``issue_card``) — value/credit
    affecting and MONEY-CLASS (ADR-053 D4): REVIEW-biased (pulled to REVIEW and held
    for a human reviewer regardless of confidence) AND biometric step-up MANDATORY
    before commit. Passes the AML contour. ``request`` is the CONTRACT
    :class:`IssueCardRequest` (carries no PAN/CVV/PIN — PCI-DSS); its ``correlation_id``
    threads the lineage."""

    intent_text: str
    process_ref: ProcessRef
    request: IssueCardRequest
    confidence_score: float
    request_cost: RequestCost
    biometric_verified: bool = False


@dataclass
class ChangeLimitIntent:
    """A resolved client intent to change a card's spend limits (``change_limit``) —
    value/credit affecting and MONEY-CLASS (ADR-053 D4): REVIEW-biased + biometric
    step-up MANDATORY (mirrors :class:`IssueCardIntent`). Passes the AML contour.
    ``new_limits`` is the CONTRACT :class:`LimitChange` (Decimal amount; its
    ``correlation_id`` threads the lineage)."""

    intent_text: str
    process_ref: ProcessRef
    card_id: CardId
    new_limits: LimitChange
    confidence_score: float
    request_cost: RequestCost
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
    # Which arm of the AML + PII gate is the primary escalation route on a non-PASS
    # verdict (PII → DPO, AML → the AML role).
    compliance_overlay: ComplianceOverlay
    human_reviewed_by: str | None
    # Money-class ops (issue_card / change_limit) support a REVIEW-band HITL hold; a
    # read or a protective op is AUTO-only and instead halts below the AUTO band.
    # Defaults False so the read/protective path is unchanged.
    supports_review_hitl: bool = False
    # Money-class override: a value/credit action is REVIEW-biased — forced to the
    # REVIEW band and held for a reviewer regardless of confidence (ADR-053 D4).
    force_review: bool = False
    # Money-class biometric step-up (ADR-053 D4): mandatory before commit on
    # issue_card / change_limit; the flag carries whether step-up has been completed.
    requires_biometric: bool = False
    biometric_verified: bool = False


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


class CardsAgent:
    """L2 Cards agent enforcing the ADR-053 Cards mask (C22).

    The card port and the lineage recorder are injected as interfaces (constructor
    injection); the agent contains pure governance logic and is unit-testable without
    any live infra. It NEVER calls the domain ``card_agent.py`` directly — it calls the
    injected :class:`CardPort`, which the domain agent fulfils as an adapter (ADR-053 D2).
    """

    def __init__(
        self,
        *,
        card_port: CardPort,
        recorder: DecisionRecorder,
        mask: CardsMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = card_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions: reads (AUTO-eligible within cap; PII overlay) ---

    async def read_card(
        self,
        intent: ReadCardIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Read a display-safe card snapshot via ``CardPort.read_card`` — AUTO-eligible
        within cap (the mask's read path, ADR-053 D4). The PII overlay (ADR-016)
        ``compliance_result`` MUST PASS before the snapshot is returned; a non-PASS PII
        verdict blocks the read and escalates to the DPO. A read below the AUTO band
        halts for a re-check, not a HITL hold."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"read_card:{intent.card_id}",
            success_action="READ_CARD",
            op="CardPort.read_card",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.read_card(intent.card_id))

    async def read_limits(
        self,
        intent: ReadLimitsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Read a card's spend limits via ``CardPort.read_limits`` — AUTO-eligible within
        cap, PII overlay must PASS (mirrors :meth:`read_card`)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"read_limits:{intent.card_id}",
            success_action="READ_LIMITS",
            op="CardPort.read_limits",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.read_limits(intent.card_id))

    # -- public mask actions: protective (AUTO-with-cap; AML + PII; no step-up) -

    async def freeze(
        self,
        intent: FreezeIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Freeze a card via ``CardPort.freeze`` — a PROTECTIVE, low-regret action that
        favours the customer, AUTO-with-cap (ADR-053 D4). Passes the AML + PII gate (a
        non-PASS verdict blocks and escalates to AML); no biometric step-up. A
        below-AUTO-band confidence halts for a re-check rather than firing on doubt."""
        ctx = self._protective_ctx(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            card_id=intent.card_id,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            triggering_event=f"freeze:{intent.card_id}",
            success_action="FREEZE_CARD",
            op="CardPort.freeze",
        )
        return await self._run_action(
            ctx, lambda: self._port.freeze(intent.card_id, intent.actor, intent.reason)
        )

    async def block(
        self,
        intent: BlockIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Block a card via ``CardPort.block`` — PROTECTIVE and TERMINAL (irreversible),
        AUTO-with-cap (ADR-053 D4). Passes the AML + PII gate; no biometric step-up."""
        ctx = self._protective_ctx(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            card_id=intent.card_id,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            triggering_event=f"block:{intent.card_id}",
            success_action="BLOCK_CARD",
            op="CardPort.block",
        )
        return await self._run_action(
            ctx, lambda: self._port.block(intent.card_id, intent.actor, intent.reason)
        )

    async def unfreeze(
        self,
        intent: UnfreezeIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Lift a freeze via ``CardPort.unfreeze`` — protective-reversible, AUTO-with-cap
        (ADR-053 D4): returning a frozen card to ACTIVE favours the customer and is
        low-regret. Passes the AML + PII gate; no biometric step-up."""
        ctx = self._protective_ctx(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            card_id=intent.card_id,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            triggering_event=f"unfreeze:{intent.card_id}",
            success_action="UNFREEZE_CARD",
            op="CardPort.unfreeze",
        )
        return await self._run_action(
            ctx, lambda: self._port.unfreeze(intent.card_id, intent.actor)
        )

    # -- public mask actions: money-class (REVIEW + mandatory biometric step-up) -

    async def issue_card(
        self,
        intent: IssueCardIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Issue a new card via ``CardPort.issue_card`` — value/credit affecting and
        MONEY-CLASS (ADR-053 D4): REVIEW-biased (forced to REVIEW and held for a human
        reviewer regardless of confidence; supply ``human_reviewed_by`` to proceed) AND
        biometric step-up MANDATORY (``intent.biometric_verified`` must be True) before
        the port is called. Passes the AML contour; a non-PASS verdict blocks and
        escalates to AML. PCI-DSS: the request and the returned CardView carry no
        PAN/CVV/PIN."""
        ctx = self._money_ctx(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.request.correlation_id,
            confidence_score=intent.confidence_score,
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            triggering_event=f"issue_card:{intent.request.entity_id}:{intent.request.card_type.value}",
            success_action="ISSUE_CARD",
            op="CardPort.issue_card",
            human_reviewed_by=human_reviewed_by,
            biometric_verified=intent.biometric_verified,
        )
        return await self._run_action(ctx, lambda: self._port.issue_card(intent.request))

    async def change_limit(
        self,
        intent: ChangeLimitIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Change a card's spend limits via ``CardPort.change_limit`` — value/credit
        affecting and MONEY-CLASS (ADR-053 D4): REVIEW-biased + biometric step-up
        MANDATORY (mirrors :meth:`issue_card`). Passes the AML contour."""
        ctx = self._money_ctx(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.new_limits.correlation_id,
            confidence_score=intent.confidence_score,
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            triggering_event=f"change_limit:{intent.card_id}:{intent.new_limits.period.value}",
            success_action="CHANGE_LIMIT",
            op="CardPort.change_limit",
            human_reviewed_by=human_reviewed_by,
            biometric_verified=intent.biometric_verified,
        )
        return await self._run_action(
            ctx, lambda: self._port.change_limit(intent.card_id, intent.new_limits)
        )

    # -- context builders (protective vs money-class postures) ---------------

    def _protective_ctx(
        self,
        *,
        intent_text: str,
        process_ref: ProcessRef,
        card_id: CardId,
        correlation_id: str,
        confidence_score: float,
        request_cost: RequestCost,
        compliance_result: ComplianceResult,
        triggering_event: str,
        success_action: str,
        op: str,
    ) -> _ActionContext:
        """Protective freeze/block/unfreeze posture: AUTO-with-cap, AML overlay primary,
        no HITL hold and no biometric step-up (ADR-053 D4)."""
        return _ActionContext(
            intent_text=intent_text,
            process_ref=process_ref,
            correlation_id=correlation_id,
            confidence_score=confidence_score,
            triggering_event=triggering_event,
            success_action=success_action,
            op=op,
            request_cost=request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.AML,
            human_reviewed_by=None,
        )

    def _money_ctx(
        self,
        *,
        intent_text: str,
        process_ref: ProcessRef,
        correlation_id: str,
        confidence_score: float,
        request_cost: RequestCost,
        compliance_result: ComplianceResult,
        triggering_event: str,
        success_action: str,
        op: str,
        human_reviewed_by: str | None,
        biometric_verified: bool,
    ) -> _ActionContext:
        """Money-class issue_card/change_limit posture: REVIEW-biased (force_review),
        HITL hold, AML overlay primary, and MANDATORY biometric step-up (ADR-053 D4)."""
        return _ActionContext(
            intent_text=intent_text,
            process_ref=process_ref,
            correlation_id=correlation_id,
            confidence_score=confidence_score,
            triggering_event=triggering_event,
            success_action=success_action,
            op=op,
            request_cost=request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.AML,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            force_review=True,
            requires_biometric=True,
            biometric_verified=biometric_verified,
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
        # PII failures (reads) route to the DPO (ADR-016); AML failures (money-class /
        # protective ops) route to the AML role. Roles are config-as-data.
        return self._mask.dpo_role if overlay is ComplianceOverlay.PII else self._mask.aml_role

    def _step_up_required(self, ctx: _ActionContext) -> bool:
        # Biometric step-up is required only for money-class ops (issue_card /
        # change_limit) and only while the mask enables it (config-as-data).
        return ctx.requires_biometric and self._mask.require_biometric_for_money_ops

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

        # 2. ADR-053 D4 — mask scope allow-list; an off-list op is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the Cards mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70)
        #    + ADR-053 D4 money-class REVIEW-bias (force REVIEW regardless of confidence).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            # Value/credit-affecting: an otherwise-AUTO action is pulled down to REVIEW
            # so a human confirms anything that moves/exposes client credit (ADR-053 D4).
            policies.append("ADR-053-D4-money-class-REVIEW")
            band = ConfirmationDecision.REVIEW

        if band is ConfirmationDecision.BLOCK:
            # Low confidence on a money-class action escalates to the AML role.
            escalated = self._mask.aml_role if ctx.supports_review_hitl else None
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
            # Read / protective path: AUTO-only, so a below-AUTO confidence halts for a
            # re-check at higher confidence, not a HITL hold (ADR-053 D4).
            if not ctx.supports_review_hitl:
                return _Evaluation(
                    band,
                    False,
                    "HALT_REVIEW_DEFERRED",
                    "Action below AUTO band; reads/protective ops are AUTO-only, "
                    "no HITL hold — re-check at higher confidence (ADR-053 D4).",
                    policies,
                    ctx.compliance_result,
                    BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )
            # Money-class in the REVIEW band (low confidence OR REVIEW-biased) holds.
            if ctx.human_reviewed_by is None:
                policies.append("ADR-053-D4-money-class-HITL")
                reason = (
                    "Money-class action (issue_card/change_limit) pulled to REVIEW; "
                    "paused for HITL regardless of confidence (ADR-053 D4)."
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

        # 5. L3 compliance gate — AML + PII overlay. A non-PASS verdict halts AND
        #    escalates (PII → DPO, AML → the AML role) (ADR-016, ADR-053 D4).
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

        # 6. ADR-049 §D4 / ADR-053 D4 — biometric step-up for money-class ops, MANDATORY
        #    before commit regardless of confidence (issue_card / change_limit).
        if self._step_up_required(ctx) and not ctx.biometric_verified:
            policies.append("ADR-049-D4-biometric-step-up")
            return _Evaluation(
                band,
                False,
                "HALT_STEP_UP_REQUIRED",
                "Money-class action requires biometric step-up before commit (ADR-053 D4).",
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

        if ev.proceed:
            if port_call is not None:
                try:
                    result = await port_call()
                except CardPortError as exc:
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
            requires_step_up=ev.requires_step_up,
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
        producer→sink seam used by every exit path).

        R-SEC / PCI-DSS: the record carries only opaque references (triggering_event is
        card_id/entity_id-keyed, never a PAN) and governance metadata — never a full
        PAN, CVV/CVC, or PIN. The masked-only port result is returned on
        ``AgentOutcome.result``, never recorded here."""
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
    "BlockIntent",
    "BudgetBreach",
    "CardsAgent",
    "CardsMask",
    "ChangeLimitIntent",
    "ComplianceOverlay",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "FreezeIntent",
    "IssueCardIntent",
    "ProcessRef",
    "ReadCardIntent",
    "ReadLimitsIntent",
    "RequestCost",
    "UnfreezeIntent",
]
