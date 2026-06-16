"""HRAgent — L1-Auto People/HR agent with a mandatory CEO gate on SMF hires
(ORG-STRUCTURE §2.9, FCA SM&CR mask).

WHY: ORG-STRUCTURE §2.9 (People / HR) specifies the ``HRAgent`` (L1 Auto; gate **CEO on
hiring an SMF holder**). This module is the emi-stack analogue of the §D2 masks
(``churn_prediction_agent.py`` for the L1-Auto routine path; ``credit_scoring_agent.py``
for the mandatory-gate invariant): it implements the agent *logic* and *governance
enforcement* of the HR mask over :class:`~services.hr.hr_port.HRPort`. It does NOT
implement the port, any HRIS adapter, the LLM-orchestration/routing layer, or any lineage
sink. The SM&CR registry (``services/compliance_automation``) is NOT touched — SMF/role
data is read through the injected read-only :class:`~services.hr.hr_port.SMCRReadHandle`.

THE REGULATORY INVARIANT (FCA SM&CR — enforced in code AND test)
---------------------------------------------------------------
Routine people-ops (training tracking, conduct-rule attestations, headcount reporting)
are L1 AUTO. BUT hiring / appointing / changing a holder of a Senior Management Function
(SMF) can NEVER be done autonomously: it MUST force a step-up to the **CEO regardless of
confidence** (even at confidence 1.0). The appointment commits ONLY with a valid CEO
authorization token; with no token the action HALTS, the appointment is NEVER applied
(``apply_smf_appointment`` is never called), and the action escalates to the CEO. The port
itself refuses an SMF appointment without a CEO token (it raises) — so auto-appointment is
impossible by construction beneath this gate (defence-in-depth).

The HR mask (ORG §2.9), enforced in the fixed §D2 chain order
(process_ref → scope → band → cost_cap → compliance → CEO-step-up → port call):

* ``scope``               — :class:`HRPort` ops only (the allow-list: get_training_status /
                            record_conduct_attestation / apply_smf_appointment).
* ``autonomy_level``      — AUTO (L1). Routine ops are AUTO-eligible within cap; a routine
                            op below the AUTO band halts for a re-check (no HITL hold). An
                            SMF appointment is a mandatory CEO step-up regardless of band.
* ``confirmation_policy`` — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047).
* ``cost_cap``            — per-request AND per-window hard caps, token AND monetary.
* ``lineage_obligation``  — one ``AgentDecisionRecord`` per action (ADR-046), every exit.
* ``compliance_gate``     — SM&CR + conduct; a non-PASS result halts AND escalates to CEO.
* ``smf_step_up``         — SM&CR: an SMF appointment requires a CEO authorization token
                            (mandatory step-up, never autonomous, regardless of band).

Mask *values* (caps, thresholds, scope, gate, escalation role) are config-as-data, carried
on :class:`HRMask`, never hardcoded in flow logic — EXCEPT the SM&CR CEO step-up, which is
a hard regulatory floor mask config can only *strengthen*, never disable.

R-SEC (ADR-021): the lineage record carries opaque metadata ONLY — ``employee_id`` /
``role`` / ``candidate_id``, never names, salary, performance data, or any PII. The CEO
authorization token is routed straight to the port and is NEVER recorded.
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
from services.hr.hr_port import (
    ConductRuleTier,
    HRPort,
    HRPortError,
    SMCRReadHandle,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture. HR routine ops are AUTO-biased (L1): within-cap ops are
    AUTO-eligible; an SMF appointment is gated by the mandatory CEO step-up."""

    AUTO_BIASED = "auto_biased"
    REVIEW_BIASED = "review_biased"


# ---------------------------------------------------------------------------
# Value types — mask config (shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class HRMask:
    """Config-as-data HR mask (ORG §2.9). The SM&CR CEO step-up is a regulatory floor: an
    SMF appointment ALWAYS forces a CEO sign-off (a valid ``ceo_token``) regardless of the
    confidence band — config can strengthen the escalation role but can never disable the
    step-up."""

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.AUTO_BIASED
    lineage_obligation: bool = True
    # The human authority an SMF appointment (and any compliance escalation) is forced up
    # to — FCA SM&CR / ORG §2.9 line 361: the CEO (for hiring SMF holders).
    ceo_escalation_role: str = "CEO"
    agent_id: str = "hr_agent"

    # The mask scope (ADR-049 §D3 allow-list): the only port ops this mask may reach. The
    # token-less ``propose_smf_appointment`` is an internal prep step, not a gated commit —
    # only the CEO-token-gated ``apply_smf_appointment`` appears here.
    scope: tuple[str, ...] = (
        "HRPort.get_training_status",
        "HRPort.record_conduct_attestation",
        "HRPort.apply_smf_appointment",
    )

    # Compliance contour required before any committing op.
    compliance_gate: tuple[str, ...] = ("SMCR", "CONDUCT")


@dataclass
class CheckTrainingIntent:
    """A resolved ROUTINE read intent (``get_training_status``) — L1 AUTO-eligible; a read
    below the AUTO band halts for a re-check, not a HITL hold."""

    intent_text: str
    process_ref: ProcessRef
    employee_id: str
    course_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class AttestConductIntent:
    """A resolved ROUTINE conduct-attestation intent (``record_conduct_attestation``) — L1
    AUTO bookkeeping (not an appointment), so it never trips the SMF gate."""

    intent_text: str
    process_ref: ProcessRef
    employee_id: str
    tier: ConductRuleTier
    attested: bool
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class AppointSMFIntent:
    """A resolved intent to APPOINT an SMF holder — the regulated SM&CR path.

    SM&CR mandatory step-up: an SMF appointment is NEVER autonomous — it forces a CEO
    step-up regardless of the confidence band (even at confidence 1.0) and commits ONLY
    with a valid ``ceo_token``. With no token the action HALTS, the appointment is never
    applied, and the action escalates to the CEO. ``role`` is the FCA SMF function code
    (e.g. ``"SMF1"``); ``candidate`` is an opaque person handle.

    R-SEC: ``ceo_token`` is routed straight to the port and is NEVER recorded."""

    intent_text: str
    process_ref: ProcessRef
    role: str
    candidate: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost
    ceo_token: str | None = None


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
    # SM&CR CEO step-up: True when this action appoints an SMF holder and therefore needs a
    # valid CEO token to proceed (mandatory, regardless of band).
    requires_smf_step_up: bool = False
    ceo_token: str | None = None
    human_reviewed_by: str | None = None


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


class HRAgent:
    """L1-Auto People/HR agent enforcing the ORG §2.9 / SM&CR mask.

    The HR port, the read-only SM&CR handle, and the lineage recorder are injected as
    interfaces; the agent contains pure governance logic and is unit-testable without any
    live infra.
    """

    def __init__(
        self,
        *,
        port: HRPort,
        smcr_handle: SMCRReadHandle,
        recorder: DecisionRecorder,
        mask: HRMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = port
        self._smcr = smcr_handle
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def check_training(
        self,
        intent: CheckTrainingIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Routine training-status read via ``HRPort.get_training_status`` — L1 AUTO,
        no HITL hold and no step-up (the mask's within-cap routine path)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"check_training:{intent.employee_id}:{intent.course_id}",
            success_action="CHECK_TRAINING",
            op="HRPort.get_training_status",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(
            ctx, lambda: self._port.get_training_status(intent.employee_id, intent.course_id)
        )

    async def attest_conduct(
        self,
        intent: AttestConductIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Routine conduct-rule attestation via ``HRPort.record_conduct_attestation`` — L1
        AUTO bookkeeping; not an appointment, so the SMF gate never fires."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"attest_conduct:{intent.employee_id}:{intent.tier.value}",
            success_action="ATTEST_CONDUCT",
            op="HRPort.record_conduct_attestation",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(
            ctx,
            lambda: self._port.record_conduct_attestation(
                intent.employee_id, intent.tier, attested=intent.attested
            ),
        )

    async def appoint_smf(
        self,
        intent: AppointSMFIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Appoint an SMF holder — the regulated SM&CR path.

        An SMF appointment is NEVER autonomous: it forces a step-up to the CEO and commits
        ONLY with a valid ``ceo_token``, regardless of the confidence band (even at
        confidence 1.0). With no token the action HALTS, the appointment is never applied
        (``apply_smf_appointment`` is never called), and the action escalates to the CEO.

        The current incumbent (if any) is read through the read-only SM&CR handle to label
        the appointment new-vs-change for the audit trail (opaque: role / candidate only).
        """
        # Read SMF/role data through the read-only SM&CR handle — never mutates the
        # registry; only reads the current holder to label the appointment.
        incumbent = self._smcr.get_senior_manager(intent.candidate)
        change_kind = "change" if incumbent is not None else "new"
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"appoint_smf:{intent.role}:{intent.candidate}:{change_kind}",
            success_action="APPOINT_SMF",
            op="HRPort.apply_smf_appointment",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            requires_smf_step_up=True,
            ceo_token=intent.ceo_token,
            # A valid CEO token IS the CEO sign-off; record the role (opaque), never the token.
            human_reviewed_by=self._mask.ceo_escalation_role if intent.ceo_token else None,
        )

        async def _apply() -> object:
            # Prepare-only proposal (no token), then commit with the CEO token. Reached
            # only on the proceed path — never when the SMF gate HALTs.
            proposal = self._port.propose_smf_appointment(
                intent.role,
                intent.candidate,
                incumbent_id=getattr(incumbent, "person_id", None),
            )
            return self._port.apply_smf_appointment(proposal, intent.ceo_token or "")

        return await self._run_action(ctx, _apply)

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
                f"Operation {ctx.op} is not on the HR mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if band is ConfirmationDecision.BLOCK:
            # Low confidence on an SMF appointment still escalates to the CEO.
            escalated = self._mask.ceo_escalation_role if ctx.requires_smf_step_up else None
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
        if band is ConfirmationDecision.REVIEW and not ctx.requires_smf_step_up:
            # Routine L1 path: ops are AUTO-only, so a below-AUTO routine op halts for a
            # re-check at higher confidence, not a HITL hold.
            return _Evaluation(
                band,
                False,
                "HALT_REVIEW_DEFERRED",
                "Routine HR op below AUTO band; L1 ops are AUTO-only, no HITL hold.",
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
                "Cost-cap breach (per-request or per-window); action refused (ADR-047).",
                policies,
                ComplianceResult.NA,
                BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        # 5. Compliance gate (SM&CR + conduct). A non-PASS result halts AND escalates to CEO.
        policies.append("SMCR-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"Compliance gate returned {ctx.compliance_result}; action blocked and "
                f"escalated to {self._mask.ceo_escalation_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.ceo_escalation_role,
            )

        # 6. SM&CR MANDATORY CEO STEP-UP — an SMF appointment can NEVER be autonomous: it
        #    requires a valid CEO authorization token regardless of the confidence band,
        #    else HALT and escalate to the CEO (the appointment is never applied).
        if ctx.requires_smf_step_up and not ctx.ceo_token:
            policies.append("SMCR-SMF-CEO-step-up")
            return _Evaluation(
                band,
                False,
                "HALT_SMF_CEO_STEP_UP_REQUIRED",
                "SMF appointment requires a CEO authorization token (FCA SM&CR): no token "
                "— forced step-up, never autonomous, escalated to the CEO; not applied.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="smf_ceo_step_up_required",
                requires_step_up=True,
                requires_hitl=True,
                escalated_to=self._mask.ceo_escalation_role,
            )

        # All gates satisfied — clear to commit within scope.
        signoff = " (CEO sign-off via token)" if ctx.requires_smf_step_up else ""
        return _Evaluation(
            band,
            True,
            ctx.success_action,
            f"All mask gates satisfied at {band.value} confidence{signoff}; committing within scope.",
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
                except HRPortError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=compliance_result,
                        reasoning=f"HR port rejected the action: {exc}",
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
        ``intent``/``triggering_event`` carry employee_id/role/candidate, never PII,
        salary, or the CEO token."""
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
    "AppointSMFIntent",
    "AttestConductIntent",
    "AutonomyLevel",
    "BudgetBreach",
    "CheckTrainingIntent",
    "ComplianceResult",
    "ConductRuleTier",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "HRAgent",
    "HRMask",
    "ProcessRef",
    "RequestCost",
]
