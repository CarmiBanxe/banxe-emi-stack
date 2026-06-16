"""IncidentResponseAgent — L2 security-incident triage agent (ORG §2.7.4, SYSC 8.1 mask).

WHY: ORG-STRUCTURE §2.7.4 (Security & Compliance) specifies the
``IncidentResponseAgent`` (L2; gate **CTO + CEO for CRITICAL**). This module is the
emi-stack analogue of the §D2 masks (``campaign_agent.py`` / ``kyc_onboarding_agent.py``):
it implements the agent *logic* and *governance enforcement* of the incident-response
mask over :class:`~services.incident_response.incident_signal_port.IncidentSignalPort`;
it does NOT implement the port, any SIEM/pager adapter, the LLM-orchestration/routing
layer (``AGENT_ROUTING_ENABLED`` stays out of scope), or any lineage sink. The
observability / device-fingerprint / ATO-prevention domains are NOT touched — they are
read-only signal sources the port derives from.

THE REGULATORY INVARIANT (FCA SYSC 8.1 — enforced in code AND test)
-------------------------------------------------------------------
A security incident classified CRITICAL can NEVER be auto-resolved / suppressed /
closed by the agent. It MUST force a step-up escalation to **CTO + CEO regardless of
confidence**, flagged with a ≤2h notification SLA. The agent may triage / classify and
propose, but a CRITICAL disposition proceeds ONLY with a human (CTO + CEO) reviewer:
with no reviewer the action HALTS, the triage disposition is NEVER committed, and the
action escalates to CTO + CEO with ``sla_hours = 2``. The signal port exposes no close
seam at all, so auto-closure is impossible by construction (defence-in-depth).

The incident mask (ORG §2.7.4), enforced in the fixed §D2 chain order
(process_ref → scope → band → cost_cap → compliance → step-up → port call):

* ``scope``               — :class:`IncidentSignalPort` ops only (the allow-list:
                            get_incidents / get_incident / classify_severity).
* ``autonomy_level``      — REVIEW (L2). Reads (list/inspect) are AUTO-eligible within
                            cap; non-critical triage is REVIEW-biased; a CRITICAL triage
                            is a mandatory CTO+CEO step-up regardless of confidence.
* ``confirmation_policy`` — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047).
* ``cost_cap``            — per-request AND per-window hard caps, token AND monetary.
* ``lineage_obligation``  — one ``AgentDecisionRecord`` per action (ADR-046), on every
                            exit path.
* ``compliance_gate``     — SYSC 8.1 + security; a non-PASS result halts AND escalates
                            to CTO + CEO.
* ``critical_step_up``    — SYSC 8.1: a CRITICAL incident closure requires CTO + CEO
                            sign-off (mandatory step-up, never autonomous), ≤2h SLA.

Mask *values* (caps, thresholds, scope, gate, escalation role, SLA) are config-as-data,
carried on :class:`IncidentResponseMask`, never hardcoded in flow logic — EXCEPT the
SYSC 8.1 CRITICAL step-up, which is a hard regulatory floor mask config can only
*strengthen*, never disable.

R-SEC (ADR-021): the lineage record carries opaque metadata ONLY — ``incident_id`` and
the derived severity/source, never raw security payloads, log lines, or PII.
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
from services.incident_response.incident_signal_port import (
    IncidentSeverity,
    IncidentSignalPort,
    IncidentSignalPortError,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture. Incident triage is REVIEW-biased: reads are AUTO-eligible,
    non-critical triage is L2 HITL-capable, a CRITICAL triage is mandatory CTO+CEO."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


# ---------------------------------------------------------------------------
# Value types — mask config (shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class IncidentResponseMask:
    """Config-as-data incident-response mask (ORG §2.7.4). The SYSC 8.1 CRITICAL
    step-up is a regulatory floor: a CRITICAL incident ALWAYS forces a CTO+CEO
    step-up with the ``critical_sla_hours`` deadline — config can strengthen the
    escalation role / SLA but can never disable the step-up."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.REVIEW_BIASED
    lineage_obligation: bool = True
    # The human double a CRITICAL incident (and any compliance/security escalation)
    # is forced up to — FCA SYSC 8.1 / ORG §2.7.4 line 430: CTO + CEO.
    critical_escalation_role: str = "CTO+CEO"
    # FCA SYSC 8.1: CEO must be notified of a CRITICAL security incident within 2h.
    critical_sla_hours: int = 2
    agent_id: str = "incident_response_agent"

    # The mask scope (ADR-049 §D3 allow-list): the only port ops this mask may reach.
    # There is intentionally no close/suppress op — the port exposes none.
    scope: tuple[str, ...] = (
        "IncidentSignalPort.get_incidents",
        "IncidentSignalPort.get_incident",
        "IncidentSignalPort.classify_severity",
    )

    # Compliance contour required before any triage disposition.
    compliance_gate: tuple[str, ...] = ("SYSC8_1", "SECURITY")


@dataclass
class ListIncidentsIntent:
    """A resolved low-consequence read intent (``get_incidents``) — AUTO-eligible; a
    read below the AUTO band halts for a re-check, not a HITL hold."""

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    severity: IncidentSeverity | None = None


@dataclass
class InspectIncidentIntent:
    """A resolved low-consequence read intent (``get_incident``) for one incident."""

    intent_text: str
    process_ref: ProcessRef
    incident_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class TriageIncidentIntent:
    """A resolved intent to TRIAGE / dispose an incident (classify + close-or-escalate).

    SYSC 8.1 mandatory step-up: a CRITICAL ``severity`` triage is NEVER autonomous — it
    forces a CTO+CEO step-up regardless of the confidence band and proceeds only with a
    human reviewer. With no reviewer the disposition HALTS and is never committed; the
    incident is left for CTO+CEO with a ≤2h SLA. Non-critical triage is normal L2."""

    intent_text: str
    process_ref: ProcessRef
    incident_id: str
    severity: IncidentSeverity
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
    # SYSC 8.1 CRITICAL step-up: True when this triage disposes a CRITICAL incident and
    # therefore needs a CTO+CEO reviewer to proceed (mandatory, regardless of band).
    requires_critical_escalation: bool = False
    human_reviewed_by: str | None = None
    # REVIEW-biased triage holds for HITL in the REVIEW band; pure reads instead halt
    # below AUTO. Defaults False so the read path is unchanged.
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
    sla_hours: int | None = None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class IncidentResponseAgent:
    """L2 security-incident triage agent enforcing the ORG §2.7.4 / SYSC 8.1 mask.

    The signal port and the lineage recorder are injected as interfaces; the agent
    contains pure governance logic and is unit-testable without any live infra.
    """

    def __init__(
        self,
        *,
        signal_port: IncidentSignalPort,
        recorder: DecisionRecorder,
        mask: IncidentResponseMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = signal_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def list_incidents(
        self,
        intent: ListIncidentsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Low-consequence read via ``IncidentSignalPort.get_incidents`` — AUTO-eligible,
        no HITL hold and no step-up (the mask's within-cap read path)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"list_incidents:{intent.severity.value if intent.severity else 'all'}",
            success_action="LIST_INCIDENTS",
            op="IncidentSignalPort.get_incidents",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_incidents(intent.severity))

    async def inspect_incident(
        self,
        intent: InspectIncidentIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Low-consequence read of one incident via ``IncidentSignalPort.get_incident``."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"inspect_incident:{intent.incident_id}",
            success_action="INSPECT_INCIDENT",
            op="IncidentSignalPort.get_incident",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_incident(intent.incident_id))

    async def triage_incident(
        self,
        intent: TriageIncidentIntent,
        *,
        human_reviewed_by: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Triage / dispose an incident — the regulated SYSC 8.1 path.

        A CRITICAL incident is NEVER auto-closed: it forces a step-up to CTO+CEO and
        proceeds only with a ``human_reviewed_by`` sign-off, regardless of the
        confidence band (even at confidence 1.0). With no reviewer the action HALTS,
        no disposition is committed (the port has no close seam), and the action
        escalates to CTO+CEO with the ≤2h SLA. Non-critical triage is normal L2.

        The disposition commits no port mutation (the port is read+classify only) — a
        triage verdict is recorded solely as ADR-046 lineage (``port_call=None``).
        """
        is_critical = intent.severity is IncidentSeverity.CRITICAL
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"triage_incident:{intent.incident_id}:{intent.severity.value}",
            success_action="TRIAGE_INCIDENT",
            op="IncidentSignalPort.classify_severity",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            requires_critical_escalation=is_critical,
            human_reviewed_by=human_reviewed_by,
            supports_review_hitl=True,
        )
        return await self._run_action(ctx, port_call=None)

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
        #    A close/suppress op is never on the allow-list → auto-close refused.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the incident mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if band is ConfirmationDecision.BLOCK:
            # Low confidence on a CRITICAL triage still escalates to CTO+CEO.
            escalated = (
                self._mask.critical_escalation_role if ctx.requires_critical_escalation else None
            )
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
                sla_hours=self._mask.critical_sla_hours
                if ctx.requires_critical_escalation
                else None,
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

        # REVIEW-biased non-critical triage requires a human reviewer in the REVIEW
        # band; the CRITICAL path is gated by the mandatory step-up below, not here.
        needs_reviewer = (
            ctx.supports_review_hitl
            and not ctx.requires_critical_escalation
            and band is ConfirmationDecision.REVIEW
        )
        if needs_reviewer and ctx.human_reviewed_by is None:
            policies.append("ADR-049-D3-review-HITL")
            return _Evaluation(
                band,
                False,
                "HOLD_FOR_REVIEW",
                "REVIEW-band triage paused for HITL; proceeds once a reviewer is supplied.",
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

        # 5. Compliance gate (SYSC 8.1 + security). A non-PASS result halts AND
        #    escalates to CTO+CEO.
        policies.append("SYSC8.1-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"Compliance gate returned {ctx.compliance_result}; action blocked and "
                f"escalated to {self._mask.critical_escalation_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.critical_escalation_role,
            )

        # 6. SYSC 8.1 MANDATORY CTO+CEO STEP-UP — a CRITICAL incident can NEVER be
        #    auto-closed: it requires a CTO+CEO reviewer regardless of the confidence
        #    band, else HALT and escalate to CTO+CEO with the ≤2h SLA (no close).
        if ctx.requires_critical_escalation and ctx.human_reviewed_by is None:
            policies.append("SYSC8.1-CRITICAL-CTO-CEO-step-up")
            return _Evaluation(
                band,
                False,
                "HALT_CRITICAL_ESCALATION_REQUIRED",
                "CRITICAL security incident requires CTO+CEO sign-off (FCA SYSC 8.1): no "
                "reviewer — forced step-up, never auto-closed, escalated with a ≤2h SLA.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="critical_escalation_required",
                requires_step_up=True,
                requires_hitl=True,
                escalated_to=self._mask.critical_escalation_role,
                sla_hours=self._mask.critical_sla_hours,
            )

        # All gates satisfied — clear to commit the triage disposition.
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
            # A CRITICAL triage that proceeds did so under CTO+CEO sign-off — surface the
            # SYSC 8.1 SLA for the audit trail; non-critical dispositions carry none.
            sla_hours=self._mask.critical_sla_hours if ctx.requires_critical_escalation else None,
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
                except IncidentSignalPortError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=compliance_result,
                        reasoning=f"Signal port rejected the action: {exc}",
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
            sla_hours=ev.sla_hours,
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
        ``intent``/``triggering_event`` carry incident_id/severity, never raw data/PII."""
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
    "IncidentResponseAgent",
    "IncidentResponseMask",
    "InspectIncidentIntent",
    "ListIncidentsIntent",
    "ProcessRef",
    "RequestCost",
    "TriageIncidentIntent",
]
