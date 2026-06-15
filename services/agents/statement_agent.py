"""StatementClientAgent — L2 client-facing Statements agent (ADR-055 Statements mask).

WHY: ADR-055 (Statements client-facing mask — the THIRD extended-catalogue entry added
via ADR-053 over ADR-049, after Cards C22 / ADR-053 and Analytics C7 / ADR-054) specifies
the governed surface through which a resolved client intent becomes a bounded
read / generate / deliver action over the client's OWN statements. This module is the
emi-stack sibling of ``services/agents/analytics_agent.py``,
``services/agents/cards_agent.py``, ``kyc_onboarding_agent.py``, ``notification_agent.py``
and ``crm_agent.py`` and the analogue of banxe-payment-core's ``src/agents/payments_agent.py`` —
it implements the agent *logic* and *governance enforcement* of the Statements mask in front
of the StatementPort CONTRACT.

NAME COLLISION (intentional, documented): the *domain* statement agent lives at
``services/client_statements/statement_agent.py`` and sits BEHIND ``StatementPort`` as the
adapter (untouched here, ADR-055 §D2 boundary). THIS module is the *client-facing* agent in a
different package (``services/agents``); its class is :class:`StatementClientAgent` to keep
the two unambiguous. The client agent depends only on the ``StatementPort`` INTERFACE
(constructor injection) — never on the domain implementation behind it.

This module does NOT implement the port (``services/client_statements/statement_port.py`` is
the CONTRACT, the domain ``statement_agent`` / ``statement_generator`` / ``statement_models``
collaborators are UNTOUCHED), the LLM-orchestration / routing layer
(``AGENT_ROUTING_ENABLED`` stays out of scope — Terminal A infra, ADR-049 §D6/§D7), or the
ClickHouse lineage sink. The shared cost / lineage primitives live in the canonical
``services/agents/_lineage.py`` and are imported, never redefined (DRY / IL-135).

The Statements mask (ADR-055), enforced here in the fixed ADR-049 §D2 chain order
(process_ref → scope → band → cost_cap → compliance(PII + data-egress) →
[step-up N/A] → port call; biometric step-up is N/A — no read / generate / deliver moves
client funds, ADR-055 §D1):

* ``scope``               — ``StatementPort`` operations only (the allow-list:
                            get_statement / list_statements / generate_statement /
                            deliver_statement). The port is injected, never implemented here;
                            an op not on the allow-list is refused.
* ``autonomy_level``      — AUTO-biased (ADR-055): a routine read / generate of the client's
                            OWN statements proceeds AUTO within cap. Only delivery to an
                            EXTERNAL channel (EMAIL / EXPORT) is pulled down to REVIEW (the
                            data-egress gate); in-boundary delivery (IN_APP) stays AUTO.
* ``confirmation_policy`` — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047
                            thresholds, ADR-049 §D4). **Override:** ``deliver_statement`` to an
                            external channel (EMAIL / EXPORT = PII data-egress) is forced to
                            the REVIEW band and held for a human reviewer regardless of
                            confidence (ADR-055 data-egress gate). NO biometric step-up —
                            data-egress is not a value-bearing action (ADR-055 §D1).
* ``cost_cap``            — per-request AND per-window hard caps, token AND monetary (Decimal)
                            dimensions (ADR-047 §D2). Emphasis on TOKEN caps: statement
                            generation can be document-heavy and must not run away.
* ``lineage_obligation``  — one ``AgentDecisionRecord`` per action (ADR-046), non-optional,
                            emitted on every exit path.
* ``compliance_gate``     — the PII overlay (ADR-016) + data-egress gate: the L3 check MUST
                            PASS before a port call; a non-PASS verdict halts (BLOCK). A PII
                            failure escalates to the DPO; a data-egress failure escalates to
                            the egress role (config-as-data, DPO by default).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence, external-delivery
REVIEW with no reviewer, cost-cap breach, compliance(PII/egress) fail} halts the action
(ADR-049 §D4 — independent halt conditions). The port's own data-egress guard
(``DeliveryEgressBlocked``), not-found guard (``StatementNotFound``) and PII guard
(``ComplianceBlock``) are defense-in-depth: if the port raises, lineage is emitted
(executed=False) and the error re-raised. Mask *values* (caps, thresholds, scope, gate,
escalation roles) are config-as-data (CLAUDE.md §10), carried on :class:`StatementMask`, never
hardcoded in flow logic.

R-SEC (R-SEC-NEW-01, ADR-021): no raw PII ever enters a lineage record. Every entity /
statement reference crossing this agent is an opaque ``entity_id`` / ``statement_id``; the
triggering_event is keyed on those opaque handles only, and the port's PII-bearing return
value (the itemised statement behind the port) rides on ``AgentOutcome.result`` (the
functional return) — NEVER on the recorded ``AgentDecisionRecord``.

EXTERNAL-DELIVERY DETECTION (channel-keyed, config-as-data):
The "is this delivery an external data-egress?" classification is a property of the
``DeliveryChannel`` itself — ``IN_APP`` keeps the artefact inside the application boundary
(AUTO posture); ``EMAIL`` / ``EXPORT`` egress a PII-bearing funds artefact OUTSIDE the
application and therefore force ``deliver_statement`` to the REVIEW band (ADR-055 data-egress
gate). The set of in-boundary channels is carried on the mask
(:attr:`StatementMask.in_boundary_channels`), never hardcoded in flow logic. The port enforces
the same posture as defense-in-depth (``DeliveryEgressBlocked`` when the gate forbids the
egress), surfaced verbatim by re-raise.
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
from services.client_statements.statement_port import (
    DeliveryChannel,
    EntityId,
    GenerateStatementRequest,
    StatementFormat,
    StatementId,
    StatementPeriod,
    StatementPort,
    StatementPortError,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3 / ADR-055). Statements is AUTO-biased: routine
    reads / generation of the client's OWN statements are AUTO-eligible within cap; only
    delivery to an EXTERNAL channel is forced down to REVIEW (the data-egress gate)."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


class ComplianceOverlay(StrEnum):
    """Which arm of the PII + data-egress gate is the primary escalation route for an
    action (ADR-055 compliance_gate). Both overlays gate every action; this selects the
    role a non-PASS verdict escalates to: PII → DPO, data-egress → the egress role."""

    PII = "PII"
    DATA_EGRESS = "DATA_EGRESS"


# ---------------------------------------------------------------------------
# Value types — mask config (the shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StatementMask:
    """Config-as-data Statements mask (ADR-055). Values are governed config, not hardcoded
    flow logic; the AUTO/REVIEW/BLOCK *scale* is ADR-047 canon. The mask is the allow-list and
    the gate posture for the capability."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.AUTO_BIASED
    lineage_obligation: bool = True
    # Escalation roles (config-as-data, never hardcoded in flow logic): a PII-overlay failure
    # escalates to the DPO (ADR-016); a data-egress failure escalates to the egress role
    # (data-protection owner of the egress decision — DPO by default).
    dpo_role: str = "DPO"
    egress_role: str = "DPO"
    agent_id: str = "statement_client_agent"

    # The mask scope (ADR-055 §D1 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "StatementPort.get_statement",
        "StatementPort.list_statements",
        "StatementPort.generate_statement",
        "StatementPort.deliver_statement",
    )

    # L3 compliance contour required before any port call: PII + data-egress overlay.
    compliance_gate: tuple[str, ...] = ("PII", "DATA_EGRESS")

    # Delivery channels that keep the artefact INSIDE the application boundary (AUTO posture).
    # Any channel NOT in this set is an external data-egress that forces deliver_statement to
    # the REVIEW band (ADR-055 data-egress gate). Channel-keyed, never hardcoded in flow logic.
    in_boundary_channels: tuple[DeliveryChannel, ...] = (DeliveryChannel.IN_APP,)


@dataclass
class GetStatementIntent:
    """A resolved single-statement read intent (``get_statement``) — AUTO-eligible within cap
    (ADR-055). The statement's raw itemised PII stays behind the port; the PII overlay
    (ADR-016) MUST PASS before the summary view is returned, and a non-PASS verdict blocks and
    escalates to the DPO. An unknown statement_id raises ``StatementNotFound`` from the port
    (recorded then re-raised). A read below the AUTO band halts for a re-check, not a HITL
    hold."""

    intent_text: str
    process_ref: ProcessRef
    statement_id: StatementId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ListStatementsIntent:
    """A resolved listing read intent (``list_statements``) — AUTO-eligible within cap. The
    PII overlay gates the read; a read below the AUTO band halts for a re-check."""

    intent_text: str
    process_ref: ProcessRef
    entity_id: EntityId
    period: StatementPeriod
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GenerateStatementIntent:
    """A resolved statement-generation intent (``generate_statement``) — AUTO-eligible within
    cap (ADR-055 AUTO-with-cap). Generation derives a statement artefact from reads — it does
    NOT move money or mutate funds. Generation can be document-heavy, so the ADR-047
    per-request / per-window token caps bound it; a cap breach halts the action. The PII
    overlay (ADR-016) MUST PASS before the view is returned. A generate below the AUTO band
    halts for a re-check."""

    intent_text: str
    process_ref: ProcessRef
    entity_id: EntityId
    period: StatementPeriod
    format: StatementFormat
    actor: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class DeliverStatementIntent:
    """A resolved client intent to deliver a statement (``deliver_statement``) — the only
    egress operation (ADR-055 data-egress gate).

    AUTO-biased: in-boundary delivery (``DeliveryChannel.IN_APP``) proceeds AUTO within cap.
    **Override:** delivery to an EXTERNAL channel (``EMAIL`` / ``EXPORT`` = PII data-egress) is
    forced to the REVIEW band (the data-egress gate) and held for a human reviewer regardless
    of confidence; supply ``human_reviewed_by`` to proceed. The external-vs-in-boundary
    classification is a property of the channel (config-as-data on the mask), never a
    free-text parse. NO biometric step-up applies — data-egress is not a value-bearing action
    (ADR-055 §D1). The PII + data-egress overlay (``compliance_result``) must PASS before the
    port is called; a non-PASS verdict blocks and escalates. The port's own data-egress guard
    raises ``DeliveryEgressBlocked`` (recorded then re-raised) as defense-in-depth."""

    intent_text: str
    process_ref: ProcessRef
    statement_id: StatementId
    channel: DeliveryChannel
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
    # Which arm of the PII + data-egress gate is the primary escalation route on a non-PASS
    # verdict (PII → DPO, data-egress → egress role).
    compliance_overlay: ComplianceOverlay
    human_reviewed_by: str | None
    # A delivery supports a REVIEW-band HITL hold; a read / generate is AUTO-only and instead
    # halts below the AUTO band. Defaults False so the read/generate path is unchanged.
    supports_review_hitl: bool = False
    # Data-egress override: delivery to an external channel is forced to the REVIEW band and
    # held for a reviewer regardless of confidence (ADR-055 data-egress gate).
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


class StatementClientAgent:
    """L2 client-facing statements agent enforcing the ADR-055 Statements mask.

    The :class:`StatementPort` and the lineage recorder are injected as interfaces
    (constructor injection); the agent contains pure governance logic and is unit-testable
    without any live infra. It depends only on the StatementPort CONTRACT, never on the domain
    ``client_statements`` implementation behind it.
    """

    def __init__(
        self,
        *,
        statement_port: StatementPort,
        recorder: DecisionRecorder,
        mask: StatementMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = statement_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def get_statement(
        self,
        intent: GetStatementIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Single-statement read via ``StatementPort.get_statement`` — AUTO-eligible within cap
        (ADR-055). The raw itemised PII stays behind the port; the PII overlay
        (``compliance_result``) must PASS before the summary view is returned, and a non-PASS
        verdict blocks and escalates to the DPO. An unknown statement_id raises
        ``StatementNotFound`` from the port (recorded then re-raised). A read below the AUTO
        band halts for a re-check, not a HITL hold."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_statement:{intent.statement_id}",
            success_action="GET_STATEMENT",
            op="StatementPort.get_statement",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.get_statement(intent.statement_id))

    async def list_statements(
        self,
        intent: ListStatementsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Statement listing via ``StatementPort.list_statements`` — AUTO-eligible within cap.
        The PII overlay must PASS before the listing is returned; a read below the AUTO band
        halts for a re-check."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"list_statements:{intent.entity_id}:{intent.period.value}",
            success_action="LIST_STATEMENTS",
            op="StatementPort.list_statements",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(
            ctx, lambda: self._port.list_statements(intent.entity_id, intent.period)
        )

    async def generate_statement(
        self,
        intent: GenerateStatementIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Generate a statement via ``StatementPort.generate_statement`` — AUTO-eligible within
        cap (ADR-055 AUTO-with-cap). Generation derives a statement artefact from reads — it
        does NOT move money or mutate funds. Generation is document-heavy, so the ADR-047
        token cost-cap is the primary runaway guard; a cap breach halts the action. The PII
        overlay must PASS before the view is returned. A generate below the AUTO band halts for
        a re-check."""
        request = GenerateStatementRequest(
            entity_id=intent.entity_id,
            period=intent.period,
            format=intent.format,
            actor=intent.actor,
            correlation_id=intent.correlation_id,
        )
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"generate_statement:{intent.entity_id}:{intent.period.value}",
            success_action="GENERATE_STATEMENT",
            op="StatementPort.generate_statement",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.PII,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.generate_statement(request))

    async def deliver_statement(
        self,
        intent: DeliverStatementIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Deliver a statement via ``StatementPort.deliver_statement`` under the mask (the only
        non-AUTO-by-default operation, ADR-055 data-egress gate).

        AUTO-biased: in-boundary delivery (``DeliveryChannel.IN_APP``) proceeds AUTO within
        cap. **Override:** delivery to an EXTERNAL channel (``EMAIL`` / ``EXPORT`` = PII
        data-egress) is forced to the REVIEW band and held for a human reviewer regardless of
        confidence; supply ``human_reviewed_by`` to proceed. The external-vs-in-boundary
        classification is channel-keyed config-as-data (:attr:`StatementMask.in_boundary_channels`),
        never a free-text parse. NO biometric step-up applies — data-egress is not a
        value-bearing action (ADR-055 §D1). The PII + data-egress overlay
        (``compliance_result``) must PASS before the port is called; a non-PASS verdict blocks
        and escalates (data-egress → egress role). The port's own data-egress guard raises
        ``DeliveryEgressBlocked`` (recorded then re-raised) as defense-in-depth."""
        external_egress = intent.channel not in self._mask.in_boundary_channels
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"deliver_statement:{intent.statement_id}:{intent.channel.value}",
            success_action="DELIVER_STATEMENT",
            op="StatementPort.deliver_statement",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            compliance_overlay=ComplianceOverlay.DATA_EGRESS,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            force_review=external_egress,
        )
        return await self._run_action(
            ctx, lambda: self._port.deliver_statement(intent.statement_id, intent.channel)
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
        # PII failures route to the DPO (ADR-016); data-egress failures route to the egress
        # role (ADR-055 data-egress gate). Roles are config-as-data.
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

        # 2. ADR-055 §D1 — mask scope allow-list; an off-list op is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the Statements mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70)
        #    + ADR-055 data-egress override (force REVIEW regardless of confidence).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            # External delivery: an otherwise-AUTO action is pulled down to REVIEW so a human
            # confirms the data-egress of the PII-bearing statement (ADR-055 data-egress gate).
            policies.append("ADR-055-data-egress-REVIEW")
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
            # Read / generate path: these are AUTO-only, so a below-AUTO read/generate halts
            # for a re-check at higher confidence, not a HITL hold (ADR-055).
            if not ctx.supports_review_hitl:
                return _Evaluation(
                    band,
                    False,
                    "HALT_REVIEW_DEFERRED",
                    "Read/generate intent below AUTO band; AUTO-only, no HITL hold (ADR-055).",
                    policies,
                    ctx.compliance_result,
                    BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )
            # Delivery in the REVIEW band (low confidence OR external egress) holds for HITL.
            if ctx.human_reviewed_by is None:
                reason = (
                    "External delivery (EMAIL / EXPORT) pulled to REVIEW (data-egress gate); "
                    "paused for HITL regardless of confidence (ADR-055)."
                    if ctx.force_review
                    else "Delivery in REVIEW band; paused for HITL confirmation (ADR-049 §D4)."
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

        # 4. ADR-047 — hard cost cap (per-request AND per-window). Statement generation can be
        #    document-heavy; the token cap is the primary runaway guard.
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
        policies.append("ADR-055-compliance-gate:" + "+".join(self._mask.compliance_gate))
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

        # Biometric step-up: N/A for statements (no money movement, ADR-055 §D1).
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
                except StatementPortError as exc:
                    # Defense-in-depth: the port's own guard (DeliveryEgressBlocked /
                    # ComplianceBlock / StatementNotFound) fired. Emit one lineage record
                    # (executed=False) then re-raise — no raw PII recorded.
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
        (entity_id / statement_id via triggering_event) ever reach a record — never raw PII."""
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
    "ComplianceOverlay",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "DeliverStatementIntent",
    "GenerateStatementIntent",
    "GetStatementIntent",
    "ListStatementsIntent",
    "ProcessRef",
    "RequestCost",
    "StatementClientAgent",
    "StatementMask",
]
