"""ChurnPredictionAgent — L1-Auto Customer-Operations churn / at-risk detection agent
(ORG-STRUCTURE §2.6.3, IL-188).

WHY: ORG-STRUCTURE §2.6.3 (Customer Operations) defines ``ChurnPredictionAgent`` (L1 Auto,
"At-risk customer alerts") as the governed surface through which a resolved churn-read
intent becomes a bounded ChurnSignalPort read action. This module implements the agent
*logic* and *governance enforcement* of the churn mask in front of the ChurnSignalPort
CONTRACT. It is the sibling of ``services/agents/data_quality_agent.py`` and
``services/agents/risk_oversight_agent.py`` (the L1-Auto read-only pattern).

The agent DETECTS and REPORTS at-risk customers (derived, read-only, from the existing
``services/customer_lifecycle/`` customer-state domain BEHIND the port). It operates
READ-ONLY: it NEVER modifies customer state, NEVER triggers a retention campaign or
action, NEVER writes to the lifecycle FSM, and NEVER makes an autonomous decision.

INVARIANT (CRITICAL — enforced in code):
    ChurnPredictionAgent is detection/reporting only. It MUST NEVER modify customer state
    or trigger retention actions autonomously. Enforced by three independent mechanisms:
      (1) the mask scope allow-list contains ONLY the 2 read ops:
          get_at_risk_customers, get_churn_signals;
      (2) ChurnSignalPort has NO mutate / trigger / retention / write method — calling one
          would require a method that does not exist on the port;
      (3) every ``success_action`` in this module is a DETECT/REPORT verb
          (REPORT_AT_RISK, DETECT_CHURN_SIGNALS) — the strings RETENTION, TRIGGER, WRITE,
          UPDATE, SUSPEND do not appear as success actions.

    I-27 (CLAUDE.md): this agent PROPOSES alerts only; it never applies a retention action
    or customer-state change autonomously (out-of-scope ops are refused).

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band → cost_cap → compliance(PII) → port call

* ``scope``              — ChurnSignalPort READ ops only (allow-list:
                           get_at_risk_customers / get_churn_signals). Off-list ops
                           (any retention / write / state-change op) are refused outright.
* ``autonomy_level``     — L1-Auto: every read is AUTO-eligible within cap. NO REVIEW HITL
                           hold, NO biometric step-up. A read below the AUTO band halts for
                           a re-check (HALT_REVIEW_DEFERRED, requires_hitl=True).
* ``confirmation_policy``— AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047).
                           REVIEW band → HALT_REVIEW_DEFERRED.
* ``cost_cap``           — per-request AND per-window hard caps in both token and monetary
                           (Decimal) dimensions (ADR-047 §D2).
* ``lineage_obligation`` — one ``AgentDecisionRecord`` per action on every exit path
                           (ADR-046), non-optional.
* ``compliance_gate``    — PII overlay (ADR-016): the L3 check MUST PASS before a port call;
                           a non-PASS verdict halts (BLOCK) and escalates to the DPO
                           (config-as-data on the mask).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence, cost-cap breach,
compliance(PII) fail} halts the action (ADR-049 §D4). The port's own validation is
defense-in-depth: if the port raises ChurnSignalPortError, lineage is emitted
(executed=False) and the error is re-raised. Mask values are config-as-data, carried on
:class:`ChurnPredictionMask`.

R-SEC (R-SEC-NEW-01, ADR-021): no raw risk score, signal weight, or PII ever enters a
lineage record. triggering_event is keyed on opaque handles ONLY (cohort / customer_id) —
never risk scores or signal values. The port's return value (list[AtRiskCustomer] /
ChurnSignalSet) rides on ``AgentOutcome.result`` ONLY — NEVER on the recorded
``AgentDecisionRecord``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
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
from services.churn.churn_signal_port import ChurnSignalPort, ChurnSignalPortError

# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChurnPredictionMask:
    """Config-as-data Customer-Operations churn-prediction (ORG-STRUCTURE §2.6.3) mask.

    All gate values are governed config, not hardcoded flow logic. The AUTO/REVIEW/BLOCK
    scale is ADR-047 canon. The scope is the exclusive read-only allow-list — no retention /
    trigger / write / state-change op is present (INVARIANT: see module docstring).
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "churn_prediction_agent"
    # The mask scope (allow-list): ONLY the 2 ChurnSignalPort READ ops.
    # INVARIANT: no retention / trigger / write / update op is present in this tuple.
    # Any attempt to call one is REJECT_OUT_OF_SCOPE.
    scope: tuple[str, ...] = (
        "ChurnSignalPort.get_at_risk_customers",
        "ChurnSignalPort.get_churn_signals",
    )
    # L3 compliance contour required before any port call: PII overlay (ADR-016).
    compliance_gate: tuple[str, ...] = ("PII",)
    # Escalation role for a compliance non-PASS verdict (config-as-data).
    dpo_role: str = "DPO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass
class AtRiskScanIntent:
    """A resolved at-risk scan intent (``ChurnSignalPort.get_at_risk_customers``) — the
    primary churn alert read op (ORG §2.6.3). Returns the at-risk customers at or above a
    risk ``threshold`` for a cohort. A read below the AUTO band halts for a re-check, not a
    HITL hold. The PII overlay MUST PASS; a non-PASS verdict blocks and escalates to the DPO.
    The list[AtRiskCustomer] rides on ``AgentOutcome.result`` ONLY (R-SEC)."""

    cohort: str
    threshold: Decimal
    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ChurnSignalsIntent:
    """A resolved per-customer churn-signal read intent (``ChurnSignalPort.get_churn_signals``)
    — the derived signals for one customer (ORG §2.6.3). A read below the AUTO band halts for
    a re-check. The PII overlay MUST PASS; non-PASS escalates to the DPO. The ChurnSignalSet
    rides on ``AgentOutcome.result`` ONLY (R-SEC)."""

    customer_id: str
    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


# ---------------------------------------------------------------------------
# Internal evaluation types
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
    """All inputs a single masked churn action evaluates against."""

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    triggering_event: str
    success_action: str
    op: str
    request_cost: RequestCost
    compliance_result: ComplianceResult


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


class ChurnPredictionAgent:
    """L1-Auto Customer-Operations churn / at-risk detection agent enforcing the
    ADR-049 §D2 gate chain.

    The :class:`~services.churn.churn_signal_port.ChurnSignalPort` and the lineage recorder
    are injected as interfaces (constructor injection); the agent contains pure governance
    logic and is unit-testable without any live infra.

    INVARIANT: DETECTION/REPORTING ONLY. This agent MUST NEVER modify customer state or
    trigger retention actions. See module docstring for the three independent enforcement
    mechanisms. I-27: PROPOSES alerts only, never applies autonomously.
    """

    def __init__(
        self,
        *,
        churn_signal_port: ChurnSignalPort,
        recorder: DecisionRecorder,
        mask: ChurnPredictionMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = churn_signal_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def report_at_risk_customers(
        self,
        intent: AtRiskScanIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """At-risk scan via ``ChurnSignalPort.get_at_risk_customers`` (ORG §2.6.3).

        AUTO-eligible within cap. The PII overlay (``compliance_result``) MUST PASS; a
        non-PASS verdict blocks and escalates to the DPO. A read below the AUTO band halts
        for a re-check (L1-Auto). The list[AtRiskCustomer] rides on ``AgentOutcome.result``
        ONLY (R-SEC — no risk score in lineage; triggering_event keyed on the opaque cohort)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_at_risk_customers:{intent.cohort}",
            success_action="REPORT_AT_RISK",
            op="ChurnSignalPort.get_at_risk_customers",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(
            ctx, lambda: self._port.get_at_risk_customers(intent.threshold)
        )

    async def get_churn_signals(
        self,
        intent: ChurnSignalsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Per-customer churn-signal read via ``ChurnSignalPort.get_churn_signals`` (ORG §2.6.3).

        AUTO-eligible within cap. The PII overlay MUST PASS; non-PASS blocks and escalates to
        the DPO. A read below the AUTO band halts for a re-check (L1-Auto). The ChurnSignalSet
        rides on ``AgentOutcome.result`` ONLY (R-SEC — no risk score or signal weight in
        lineage; triggering_event keyed on the opaque customer_id)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_churn_signals:{intent.customer_id}",
            success_action="DETECT_CHURN_SIGNALS",
            op="ChurnSignalPort.get_churn_signals",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_churn_signals(intent.customer_id))

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

        # 2. Scope allow-list — an off-list op (any retention / write / state-change) is
        #    refused outright. INVARIANT: the mask scope has read ops only.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the churn mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band. REVIEW → HALT_REVIEW_DEFERRED: reads are AUTO-only
        #    (L1-Auto); there is no HITL hold path in this agent.
        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)

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
            return _Evaluation(
                band,
                False,
                "HALT_REVIEW_DEFERRED",
                "Read intent below AUTO band; reads are AUTO-only, no HITL hold (L1-Auto).",
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

        # 5. PII compliance gate (ADR-016). A non-PASS verdict halts AND escalates to the DPO.
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            escalated = self._mask.dpo_role
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"PII overlay returned {ctx.compliance_result}; "
                f"action blocked and escalated to {escalated}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=escalated,
            )

        # All gates satisfied — clear to commit the read.
        return _Evaluation(
            band,
            True,
            ctx.success_action,
            f"All churn mask gates satisfied at {band.value} confidence; committing within scope.",
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
                except ChurnSignalPortError as exc:
                    # Defense-in-depth: the port's own read guard fired. Emit one lineage
                    # record (executed=False) then re-raise — no raw risk score, signal
                    # weight, or PII recorded.
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
        correlation_id: str,
        request_cost: RequestCost,
        budget_breach: BudgetBreach,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        """Build, persist, and return exactly one ADR-046 lineage record (the single
        producer→sink seam used by every exit path). R-SEC: triggering_event uses opaque
        cohort / customer_id labels only — never risk scores, signal weights, or PII. Port
        return values ride on AgentOutcome.result, never on this record."""
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
            human_reviewed_by=None,
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
    "AtRiskScanIntent",
    "BudgetBreach",
    "ChurnPredictionAgent",
    "ChurnPredictionMask",
    "ChurnSignalPortError",
    "ChurnSignalsIntent",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "ProcessRef",
    "RequestCost",
]
