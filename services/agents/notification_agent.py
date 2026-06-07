"""NotificationAgent — L2 client-facing notification agent (ADR-049 Notifications mask).

WHY: ADR-049 (Intent Layer & Client-Facing Agent Masks) specifies the
client-facing **Notifications mask** (§D3 row "Notifications"): the governed
surface through which a resolved client intent becomes a bounded, multi-channel
notification dispatch. This module is the emi-stack sibling of
``services/agents/kyc_onboarding_agent.py`` and the analogue of
banxe-payment-core's ``src/agents/payments_agent.py`` / ``fx_exchange_agent.py``
— it implements the agent *logic* and *governance enforcement* of the
Notifications mask; it does NOT implement the port, the LLM-orchestration/routing
layer (``AGENT_ROUTING_ENABLED`` stays out of scope — Terminal A infra,
ADR-049 §D6/§D7), or the ClickHouse sink.

The Notifications mask (ADR-049 §D3 row 178), enforced here in the fixed §D2
chain order (process_ref → scope → band → cost_cap → compliance(PII) → port call;
biometric step-up is N/A — a notification never moves client funds):

* ``scope``                — ``NotificationProviderPort`` operations only (the
                             allow-list: send / is_channel_available). The port
                             is injected, never implemented here; an op not on the
                             allow-list is rejected outright.
* ``autonomy_level``       — AUTO-biased (low consequence, ADR-049 §D3): an
                             INFORMATIONAL send defaults to AUTO within cap and a
                             channel-availability read is AUTO-eligible.
* ``confirmation_policy``  — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70
                             (ADR-047 thresholds, ADR-049 §D4). **Override:** a
                             message that templates CLIENT FUNDS DATA
                             (amounts/balances/transactions) is forced to the
                             REVIEW band and held for a human reviewer
                             *regardless of confidence* (ADR-049 §D3). No
                             biometric step-up (not money movement, ADR-049 §D4).
* ``cost_cap``             — per-request AND per-window hard caps, token AND
                             monetary (Decimal) dimensions (ADR-047 §D2, ADR-049 §D3).
* ``lineage_obligation``   — one ``AgentDecisionRecord`` per action (ADR-046),
                             non-optional, emitted on every exit path.
* ``compliance_gate``      — the PII-handling overlay (ADR-016): the L3 PII check
                             MUST pass before a send; a non-PASS PII verdict halts
                             (BLOCK) and escalates to the DPO.

Any one of {unresolved process_ref, out-of-scope op, below-band confidence,
funds-data REVIEW with no reviewer, cost-cap breach, PII-gate fail} halts the
action (ADR-049 §D4 — independent halt conditions). Mask *values* (caps,
thresholds, scope, gate, DPO role) are config-as-data (CLAUDE.md §10), carried on
:class:`NotificationMask`, never hardcoded in flow logic.

FUNDS-DATA DETECTION (assumption, documented):
The "does this message template client funds data?" classification is performed
**upstream** (the intent-resolution / templating layer) and carried into the agent
as a single structured boolean — :attr:`NotificationSendIntent.contains_funds_data`.
The agent HONORS that signal and never parses free text for amounts/balances
(fragile-regex detection is explicitly out of scope, config-as-data per CLAUDE.md
§10). A template that renders amounts, balances, or transaction lines sets
``contains_funds_data=True`` at the call site; the agent then forces REVIEW.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from enum import StrEnum
import uuid

from services.notifications.notification_provider_port import (
    NotificationChannel,
    NotificationError,
    NotificationMessage,
    NotificationProviderPort,
    Recipient,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class ConfirmationDecision(StrEnum):
    """HITL band selected by the confirmation_policy (ADR-047 / ADR-049 §D4)."""

    AUTO = "auto"
    REVIEW = "review"
    BLOCK = "block"


class ComplianceResult(StrEnum):
    """Net L3 compliance-gate (PII overlay, ADR-016) outcome on the lineage record."""

    PASS = "PASS"  # nosec B105 # noqa: S105 — compliance verdict, not a credential
    FAIL = "FAIL"
    ESCALATE = "ESCALATE"
    NA = "N/A"


class BudgetBreach(StrEnum):
    """Cost-cap breach flag for the lineage record (ADR-047 §D2/§D4)."""

    NONE = "NONE"
    WARN = "WARN"
    BREACH = "BREACH"


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3). Notifications are AUTO-biased:
    informational sends and channel reads are AUTO-eligible within cap; only a
    funds-data send is forced down to REVIEW."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


# ---------------------------------------------------------------------------
# Value types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ProcessRef:
    """ADR-048 intent→process handle. Both fields required for a resolved intent."""

    process_id: str
    version: str

    @property
    def resolved(self) -> bool:
        return bool(self.process_id) and bool(self.version)


@dataclass(frozen=True)
class RequestCost:
    """Estimated cost of a single agent invocation (ADR-047 per-request dimensions)."""

    tokens: int
    cost: Decimal


@dataclass(frozen=True)
class CostCap:
    """Hard caps in both token and monetary (Decimal) dimensions (ADR-047 §D2)."""

    max_request_tokens: int
    max_request_cost: Decimal
    max_window_tokens: int
    max_window_cost: Decimal


@dataclass
class CostWindow:
    """Rolling per-window usage accumulator (ADR-047 §D2 per-window budget)."""

    used_tokens: int = 0
    used_cost: Decimal = Decimal("0")
    window_ref: str = "notification_agent:default"

    def add(self, cost: RequestCost) -> None:
        self.used_tokens += cost.tokens
        self.used_cost += cost.cost


@dataclass(frozen=True)
class NotificationMask:
    """Config-as-data Notifications mask (ADR-049 §D3 row 178). Values are governed
    config, not hardcoded flow logic; the AUTO/REVIEW/BLOCK *scale* is ADR-047
    canon. The mask is the allow-list and the gate posture for the capability."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.AUTO_BIASED
    lineage_obligation: bool = True
    # The data-protection role notified/escalated to on a PII-gate failure
    # (ADR-016 PII-handling overlay). Config-as-data, never hardcoded in flow logic.
    dpo_role: str = "DPO"
    agent_id: str = "notification_agent"

    # The mask scope (ADR-049 §D3 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "NotificationProviderPort.send",
        "NotificationProviderPort.is_channel_available",
    )

    # L3 compliance contour required before any send: the PII overlay (ADR-016).
    compliance_gate: tuple[str, ...] = ("PII",)


@dataclass
class NotificationSendIntent:
    """A resolved client intent to dispatch a notification (``send``).

    AUTO-biased (ADR-049 §D3): an informational send proceeds AUTO within cap.
    **Override:** when :attr:`contains_funds_data` is True the message templates
    client funds data (amounts/balances/transactions), so the action is forced to
    the REVIEW band and held for a human reviewer regardless of confidence
    (ADR-049 §D3). The funds-data classification is an upstream, structured signal
    — the agent honors it and never regex-parses free text (see module docstring).
    """

    intent_text: str
    process_ref: ProcessRef
    recipient: Recipient
    message: NotificationMessage
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    contains_funds_data: bool = False


@dataclass
class ChannelCheckIntent:
    """A resolved low-consequence read intent (``is_channel_available``) — the
    mask's "reads are AUTO-eligible within cap" path (ADR-049 §D3). A read below
    the AUTO band halts for a re-check, not a HITL hold; never carries funds data."""

    intent_text: str
    process_ref: ProcessRef
    channel: NotificationChannel
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class AgentDecisionRecord:
    """Decision-lineage record emitted per action (ADR-046 schema + ADR-047 cost)."""

    record_id: str
    timestamp: datetime
    agent_id: str
    triggering_event: str
    intent: str
    policies_evaluated: list[str]
    compliance_result: ComplianceResult
    reasoning_summary: str
    confidence_score: float
    action_taken: str
    human_reviewed_by: str | None
    correlation_id: str
    # ADR-047 cost lineage (cost is a first-class lineage dimension).
    cost_tokens: int = 0
    cost_amount: Decimal = Decimal("0")
    budget_window_ref: str = ""
    budget_breach_flag: BudgetBreach = BudgetBreach.NONE
    # DPO escalation marker (ADR-016); set on a PII-gate fail/escalate.
    escalated_to: str | None = None


@dataclass
class AgentOutcome:
    """Result of a masked action: the decision, whether a port was called, and the
    lineage record that was emitted (always non-None — lineage is non-optional).

    ``requires_step_up`` is carried for shape-parity with the sibling agents'
    outcome; the Notifications mask never sets it (biometric step-up is N/A, a
    notification never moves client funds — ADR-049 §D4)."""

    decision: ConfirmationDecision
    executed: bool
    record: AgentDecisionRecord
    result: object | None = None
    halt_reason: str | None = None
    requires_step_up: bool = False
    requires_hitl: bool = False
    escalated_to: str | None = None


class DecisionRecorder(ABC):
    """Sink for :class:`AgentDecisionRecord` (ADR-046 producer→sink seam).

    Injected, not implemented here: the ClickHouse/lineage wiring is out of scope
    (ADR-049 §D7). The agent depends only on this interface.
    """

    @abstractmethod
    async def record(self, record: AgentDecisionRecord) -> None:
        """Persist one decision-lineage record. Must be durable before the action
        is considered complete (ADR-046 §D4 producer obligation)."""


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
    human_reviewed_by: str | None
    # A send supports a REVIEW-band HITL hold; a channel read is AUTO-only and
    # instead halts below the AUTO band. Defaults False so the read path is unchanged.
    supports_review_hitl: bool = False
    # Funds-data override: a send templating client funds data is forced to the
    # REVIEW band and held for a reviewer regardless of confidence (ADR-049 §D3).
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


class NotificationAgent:
    """L2 notification agent enforcing the ADR-049 Notifications mask.

    The provider port and the lineage recorder are injected as interfaces
    (constructor injection); the agent contains pure governance logic and is
    unit-testable without any live infra.
    """

    def __init__(
        self,
        *,
        provider_port: NotificationProviderPort,
        recorder: DecisionRecorder,
        mask: NotificationMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._provider = provider_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def send_notification(
        self,
        intent: NotificationSendIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        """Dispatch a notification via ``NotificationProviderPort.send`` under the mask.

        AUTO-biased (ADR-049 §D3): an informational send within cap proceeds AUTO.
        If ``intent.contains_funds_data`` is set the message templates client funds
        data, so the action is forced to the REVIEW band and held for a human
        reviewer regardless of confidence; supply ``human_reviewed_by`` to proceed.
        The PII overlay (ADR-016) gate (``compliance_result``) must PASS before the
        port is called; a non-PASS PII verdict blocks and escalates to the DPO.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=(
                f"send_notification:{intent.recipient.user_id}:{intent.message.severity.value}"
            ),
            success_action="SEND_NOTIFICATION",
            op="NotificationProviderPort.send",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
            force_review=intent.contains_funds_data,
        )
        return await self._run_action(
            ctx,
            lambda: self._provider.send(intent.recipient, intent.message),
        )

    async def check_channel(
        self,
        intent: ChannelCheckIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Low-consequence read via ``NotificationProviderPort.is_channel_available``
        — AUTO-eligible, no HITL hold (the mask's within-cap read path, ADR-049 §D3).
        A read below the AUTO band halts for a re-check, not a HITL hold."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"check_channel:{intent.channel.value}",
            success_action="CHECK_CHANNEL_AVAILABLE",
            op="NotificationProviderPort.is_channel_available",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
        )
        return await self._run_action(
            ctx, lambda: self._provider.is_channel_available(intent.channel)
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
                f"Operation {ctx.op} is not on the Notifications mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70)
        #    + ADR-049 §D3 funds-data override (force REVIEW regardless of confidence).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            # Funds-data send: an otherwise-AUTO send is pulled down to REVIEW so a
            # human confirms anything templating client funds (ADR-049 §D3).
            policies.append("ADR-049-D3-funds-data-REVIEW")
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
            # Send in the REVIEW band (low confidence OR funds-data) holds for HITL.
            if ctx.human_reviewed_by is None:
                reason = (
                    "Funds-data send pulled to REVIEW; paused for HITL regardless of confidence."
                    if ctx.force_review
                    else "Send in REVIEW band; paused for HITL confirmation (ADR-049 §D4)."
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

        # 5. L3 compliance gate — PII-handling overlay (ADR-016). A non-PASS PII
        #    verdict halts AND escalates to the DPO.
        policies.append("ADR-016-PII-overlay:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"PII overlay returned {ctx.compliance_result}; "
                f"send blocked and escalated to {self._mask.dpo_role} (ADR-016).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.dpo_role,
            )

        # Biometric step-up: N/A for notifications (no money movement, ADR-049 §D4).
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
                except NotificationError as exc:
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
    "ChannelCheckIntent",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "NotificationAgent",
    "NotificationMask",
    "NotificationSendIntent",
    "ProcessRef",
    "RequestCost",
]
