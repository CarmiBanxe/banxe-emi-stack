"""MLPipelineAgent — L3 ML-pipeline agent (ORG §2.7.1, I-27 dual CRO+CTO sign-off).

WHY: ORG-STRUCTURE §2.7.1 Data & ML Engineering lists ``MLPipelineAgent`` (L3, gate
**CRO + CTO**) — the **LAST** agent in the org chart, completing the catalogue. This module
implements the agent *logic* and *governance enforcement* of the MLPipeline mask in front of
the :class:`MLSignalPort` CONTRACT. It is the emi-stack sibling of ``cards_agent.py`` /
``statement_agent.py`` / ``hr_agent.py`` and fuses two prior patterns: the AUTO-biased read
posture of the statements/analytics masks (for ``get_drift_signals`` / ``propose_retraining``)
with the **mandatory step-up** posture of ``cards_agent`` / the credit-scoring mandatory-gate
invariant — STRENGTHENED to a *dual* human sign-off (CRO **and** CTO) on ``apply_model_update``.

REGULATORY INVARIANT (I-27 — STRICTEST, enforced in code AND test):
The agent may ONLY PROPOSE model retraining / threshold changes. It can NEVER apply a model
update autonomously. Applying requires DUAL human sign-off — a valid CRO token AND a valid CTO
token.
  * ``get_drift_signals``  — read-only; AUTO-eligible within cap.
  * ``propose_retraining`` — prepares a RetrainingProposal (a recommendation, applies NOTHING);
                             AUTO-eligible within cap. The proposal is flagged as requiring the
                             downstream CRO+CTO sign-off to ever become a change.
  * ``apply_model_update`` — the commit seam. MANDATORY dual sign-off regardless of confidence
                             (even at confidence 1.0): the update commits ONLY with BOTH a CRO
                             token AND a CTO token. With either missing the action HALTS
                             (``HALT_DUAL_SIGN_OFF_REQUIRED``), the update is NEVER applied
                             (``MLSignalPort.apply_model_update`` is never called), and it
                             escalates to **CRO+CTO**. The requirement is NOT waivable by mask
                             config — a permissive ``auto_threshold`` cannot turn it off.

This module does NOT implement the port (``services/ml_pipeline/ml_signal_port.py`` is the
CONTRACT; the read-only signal sources ``services/ci_governance/*`` / ``experiment_copilot/*``
/ ``reasoning_bank/*`` are UNTOUCHED, fronted read-only behind the port), nor the
LLM-orchestration / routing layer, nor the lineage sink. The shared cost / lineage primitives
live in the canonical ``services/agents/_lineage.py`` and are imported, never redefined.

The MLPipeline mask, enforced here in the fixed ADR-049 §D2 chain order
(process_ref → scope → band → cost_cap → compliance → dual-sign-off step-up → port call):

* ``scope``               — ``MLSignalPort`` operations only (the allow-list: get_drift_signals
                            / propose_retraining / apply_model_update). An off-list op — e.g. an
                            attempt to apply outside the governed seam — is refused outright.
* ``autonomy_level``      — read/propose are AUTO-biased within cap; ``apply_model_update`` can
                            NEVER be autonomous — it forces the dual CRO+CTO sign-off step-up.
* ``confirmation_policy`` — AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047 / ADR-049
                            §D4). A read/propose below the AUTO band halts for a re-check
                            (AUTO-only, no HITL hold). Apply additionally requires the dual
                            sign-off regardless of confidence.
* ``cost_cap``            — per-request AND per-window hard caps, token AND monetary (Decimal)
                            dimensions (ADR-047 §D2).
* ``lineage_obligation``  — one ``AgentDecisionRecord`` per action (ADR-046), emitted on every
                            exit path.
* ``compliance_gate``     — the MODEL_RISK overlay: the L3 check MUST PASS before a port call;
                            a non-PASS verdict halts (BLOCK) and escalates to the CRO.

R-SEC (ADR-021): no model internals or sign-off tokens ever enter a lineage record. Every
handle crossing this agent is the opaque ``model_id`` / ``proposal_id``; the triggering_event
is keyed on those handles only; the CRO/CTO tokens are routed straight to the port and are
NEVER recorded (a completed dual sign-off is recorded as the opaque roles ``"CRO+CTO"``, never
the token values). Training data, weights, hyper-parameters, datasets and PII stay behind the
port and never reach a record.
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
from services.ml_pipeline.ml_signal_port import (
    MLSignalPort,
    MLSignalPortError,
    ModelId,
    RetrainingProposal,
)

# ---------------------------------------------------------------------------
# Mask vocabulary
# ---------------------------------------------------------------------------


class AutonomyLevel(StrEnum):
    """Mask autonomy posture (ADR-049 §D3). MLPipeline is read/propose-AUTO-biased: routine
    signal reads and proposal generation are AUTO-eligible within cap; ``apply_model_update``
    is NEVER autonomous (mandatory dual CRO+CTO sign-off, I-27)."""

    PROPOSE_AUTO_APPLY_GATED = "propose_auto_apply_gated"


# ---------------------------------------------------------------------------
# Value types — mask config (the shared cost/lineage primitives live in ``_lineage``)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MLPipelineMask:
    """Config-as-data MLPipeline mask (ORG §2.7.1, I-27). Values are governed config, not
    hardcoded flow logic; the AUTO/REVIEW/BLOCK scale is ADR-047 canon. The mask is the
    allow-list and the gate posture for the capability.

    NOTE (I-27 invariant): the dual CRO+CTO sign-off on ``apply_model_update`` is NOT waivable
    by config — ``apply`` always requires both tokens regardless of these thresholds. The
    roles below name *who* must sign off / who an escalation routes to (config-as-data); they
    do not switch the requirement off.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    autonomy_level: AutonomyLevel = AutonomyLevel.PROPOSE_AUTO_APPLY_GATED
    lineage_obligation: bool = True
    # Dual-sign-off roles (config-as-data): apply requires BOTH; a model-risk compliance
    # failure escalates to the CRO (model-risk owner).
    cro_role: str = "CRO"
    cto_role: str = "CTO"
    model_risk_role: str = "CRO"
    agent_id: str = "ml_pipeline_agent"

    # The mask scope (ORG §2.7.1 allow-list): the only port ops this mask may reach.
    scope: tuple[str, ...] = (
        "MLSignalPort.get_drift_signals",
        "MLSignalPort.propose_retraining",
        "MLSignalPort.apply_model_update",
    )

    # L3 compliance contour required before any port call: model-risk overlay.
    compliance_gate: tuple[str, ...] = ("MODEL_RISK",)

    @property
    def dual_sign_off_roles(self) -> str:
        """The opaque dual-sign-off marker recorded / escalated to (never a token value)."""
        return f"{self.cro_role}+{self.cto_role}"


@dataclass
class DriftSignalIntent:
    """A resolved drift-signal read intent (``get_drift_signals``) — AUTO-eligible within cap.
    The MODEL_RISK overlay gates the read; a read below the AUTO band halts for a re-check,
    not a HITL hold. R-SEC: ``model_id`` is an opaque handle, never model internals/PII."""

    intent_text: str
    process_ref: ProcessRef
    model_id: ModelId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ProposeRetrainingIntent:
    """A resolved retraining-proposal intent (``propose_retraining``) — AUTO-eligible within
    cap (I-27: proposing is the agent's only autonomous output; it applies NOTHING). A propose
    below the AUTO band halts for a re-check. The emitted proposal still requires the
    downstream dual CRO+CTO sign-off to ever become a change."""

    intent_text: str
    process_ref: ProcessRef
    model_id: ModelId
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ApplyModelUpdateIntent:
    """A resolved intent to apply a model update (``apply_model_update``) — the commit seam.

    NEVER autonomous (I-27): MANDATORY dual sign-off regardless of confidence. The update
    commits ONLY when BOTH a CRO token AND a CTO token are supplied to
    :meth:`MLPipelineAgent.apply_model_update`; with either missing the action HALTS and the
    port is never called. R-SEC: the proposal carries opaque handles only; the tokens are
    method arguments routed straight to the port, never stored on the intent or recorded."""

    intent_text: str
    process_ref: ProcessRef
    proposal: RetrainingProposal
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
    human_reviewed_by: str | None
    # apply_model_update requires the dual CRO+CTO sign-off (I-27); reads/propose do not.
    # Defaults False so the read/propose path is unchanged.
    requires_dual_sign_off: bool = False
    # The CRO/CTO sign-off tokens for apply (routed to the port, NEVER recorded). Presence of
    # BOTH is the dual sign-off; either missing → HALT (the update is never applied).
    cro_token: str | None = None
    cto_token: str | None = None


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


class MLPipelineAgent:
    """L3 ML-pipeline agent enforcing the MLPipeline mask (ORG §2.7.1, I-27).

    The :class:`MLSignalPort` and the lineage recorder are injected as interfaces (constructor
    injection); the agent contains pure governance logic and is unit-testable without any live
    infra or ML framework. It depends only on the MLSignalPort CONTRACT, never on the read-only
    signal-source domains behind it.
    """

    def __init__(
        self,
        *,
        ml_signal_port: MLSignalPort,
        recorder: DecisionRecorder,
        mask: MLPipelineMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = ml_signal_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions: read / propose (AUTO-eligible within cap) -------

    async def get_drift_signals(
        self,
        intent: DriftSignalIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Read drift / retraining-need signals via ``MLSignalPort.get_drift_signals`` —
        AUTO-eligible within cap. Read-only; the MODEL_RISK overlay must PASS before the
        signals are returned (a non-PASS verdict blocks and escalates to the CRO). A read below
        the AUTO band halts for a re-check, not a HITL hold."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_drift_signals:{intent.model_id}",
            success_action="GET_DRIFT_SIGNALS",
            op="MLSignalPort.get_drift_signals",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
        )
        return await self._run_action(ctx, lambda: self._port.get_drift_signals(intent.model_id))

    async def propose_retraining(
        self,
        intent: ProposeRetrainingIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Prepare a retraining proposal via ``MLSignalPort.propose_retraining`` — AUTO-eligible
        within cap (I-27: proposing applies NOTHING; it is the agent's only autonomous output).
        The MODEL_RISK overlay must PASS before the proposal is returned. A propose below the
        AUTO band halts for a re-check. The emitted proposal still requires the downstream dual
        CRO+CTO sign-off (``requires_step_up`` is carried on the outcome to signal that)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"propose_retraining:{intent.model_id}",
            success_action="PROPOSE_RETRAINING",
            op="MLSignalPort.propose_retraining",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
        )
        return await self._run_action(
            ctx,
            lambda: self._port.propose_retraining(intent.model_id),
            signals_step_up_on_success=True,
        )

    # -- public mask action: apply (NEVER autonomous; mandatory dual CRO+CTO) -

    async def apply_model_update(
        self,
        intent: ApplyModelUpdateIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        cro_token: str | None = None,
        cto_token: str | None = None,
    ) -> AgentOutcome:
        """Apply a model update via ``MLSignalPort.apply_model_update`` — the commit seam,
        NEVER autonomous (I-27).

        MANDATORY dual sign-off regardless of confidence (even at confidence 1.0): the update
        commits ONLY when BOTH a valid CRO token AND a valid CTO token are supplied; with either
        missing the action HALTS (``HALT_DUAL_SIGN_OFF_REQUIRED``), the port is NEVER called, and
        it escalates to CRO+CTO. The requirement is NOT waivable by mask config. The MODEL_RISK
        overlay must PASS before the dual-sign-off gate is reached. R-SEC: the cro_token /
        cto_token are routed straight to the port and are NEVER recorded — a completed dual
        sign-off is recorded as the opaque roles ``"CRO+CTO"``."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"apply_model_update:{intent.proposal.proposal_id}:{intent.proposal.model_id}",
            success_action="APPLY_MODEL_UPDATE",
            op="MLSignalPort.apply_model_update",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            # A completed dual sign-off is recorded as the opaque roles, never the token values.
            human_reviewed_by=self._mask.dual_sign_off_roles if (cro_token and cto_token) else None,
            requires_dual_sign_off=True,
            cro_token=cro_token,
            cto_token=cto_token,
        )
        return await self._run_action(
            ctx,
            lambda: self._port.apply_model_update(
                intent.proposal,
                cro_token or "",
                cto_token or "",
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

    def _dual_sign_off_satisfied(self, ctx: _ActionContext) -> bool:
        # I-27: BOTH the CRO token AND the CTO token must be present (truthy). Either missing →
        # the model update is NEVER applied. NOT waivable by mask config.
        return bool(ctx.cro_token) and bool(ctx.cto_token)

    def _missing_sign_off(self, ctx: _ActionContext) -> str:
        missing = []
        if not ctx.cro_token:
            missing.append(self._mask.cro_role)
        if not ctx.cto_token:
            missing.append(self._mask.cto_role)
        return " and ".join(missing)

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

        # 2. ORG §2.7.1 — mask scope allow-list; an off-list op (e.g. an ungoverned autonomous
        #    apply) is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the MLPipeline mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band (AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70).
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if band is ConfirmationDecision.BLOCK:
            # Low confidence on apply escalates to the dual sign-off; reads/propose do not.
            escalated = self._mask.dual_sign_off_roles if ctx.requires_dual_sign_off else None
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
            # Read/propose are AUTO-only: a below-AUTO confidence halts for a re-check at higher
            # confidence, not a HITL hold. Apply in the REVIEW band still falls through to the
            # mandatory dual-sign-off gate below (its hard stop is the tokens, not a HITL hold).
            if not ctx.requires_dual_sign_off:
                return _Evaluation(
                    band,
                    False,
                    "HALT_REVIEW_DEFERRED",
                    "Read/propose intent below AUTO band; AUTO-only, no HITL hold — re-check at "
                    "higher confidence (ADR-049 §D4).",
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
                "Cost-cap breach (per-request or per-window tokens/cost); action refused (ADR-047).",
                policies,
                ComplianceResult.NA,
                BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        # 5. L3 compliance gate — MODEL_RISK overlay. A non-PASS verdict halts AND escalates to
        #    the CRO (model-risk owner).
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"MODEL_RISK overlay returned {ctx.compliance_result}; action blocked and "
                f"escalated to {self._mask.model_risk_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.model_risk_role,
            )

        # 6. I-27 — MANDATORY dual CRO+CTO sign-off for apply_model_update, regardless of
        #    confidence and NOT waivable by config. Missing either token → HALT, the update is
        #    NEVER applied (the port is never called), escalate to CRO+CTO.
        if ctx.requires_dual_sign_off and not self._dual_sign_off_satisfied(ctx):
            policies.append("I-27-dual-sign-off-CRO+CTO")
            return _Evaluation(
                band,
                False,
                "HALT_DUAL_SIGN_OFF_REQUIRED",
                f"Model update requires dual sign-off; {self._missing_sign_off(ctx)} sign-off "
                "token missing — update NOT applied, autonomous apply refused (I-27).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="dual_sign_off_required",
                requires_step_up=True,
                escalated_to=self._mask.dual_sign_off_roles,
            )

        # All gates satisfied — clear to commit the action. A successful propose still signals
        # the downstream dual sign-off on its outcome (requires_step_up, set in _run_action).
        signoff = f" (signed off by {ctx.human_reviewed_by})" if ctx.human_reviewed_by else ""
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
        *,
        signals_step_up_on_success: bool = False,
    ) -> AgentOutcome:
        ev = self._evaluate(ctx)
        result: object | None = None
        executed = False
        action_taken = ev.action_taken

        if ev.proceed:
            if port_call is not None:
                try:
                    result = await port_call()
                except MLSignalPortError as exc:
                    # Defense-in-depth: the port's own guard (DualSignOffRequired / ModelNotFound
                    # / MLSignalSourceUnavailable) fired. Emit one lineage record (executed=False)
                    # then re-raise — no model internals or tokens recorded.
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
        # A successful proposal carries requires_step_up to signal the downstream CRO+CTO
        # sign-off needed before it can ever become a change (I-27); a failed dual-sign-off gate
        # carries it as the halt reason.
        requires_step_up = ev.requires_step_up or (executed and signals_step_up_on_success)
        return AgentOutcome(
            decision=ev.decision,
            executed=executed,
            record=record,
            result=result,
            halt_reason=ev.halt_reason,
            requires_step_up=requires_step_up,
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
        producer→sink seam used by every exit path). R-SEC: only opaque handles (model_id /
        proposal_id via triggering_event) and governance metadata ever reach a record — never
        training data, weights, hyper-parameters, datasets, PII, or the CRO/CTO sign-off tokens
        (a completed dual sign-off is recorded as the opaque roles ``"CRO+CTO"`` only)."""
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
    "ApplyModelUpdateIntent",
    "AutonomyLevel",
    "BudgetBreach",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "DriftSignalIntent",
    "MLPipelineAgent",
    "MLPipelineMask",
    "ProcessRef",
    "ProposeRetrainingIntent",
    "RequestCost",
    "RetrainingProposal",
]
