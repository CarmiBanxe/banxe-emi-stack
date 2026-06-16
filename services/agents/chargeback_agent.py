"""ChargebackAgent — L2 Review mask for dispute chargeback operations.

WHY: ORG §2.6 defines the chargeback agent as the governed surface through
which a resolved chargeback intent becomes a bounded ChargebackHandle action.
This module is the emi-stack COO-gated sibling of treasury_agent — it enforces
the ADR-049 §D2 gate chain in front of the dispute_resolution domain.

The chargeback agent operates over initiate_chargeback (L2, COO gate),
submit_representment (L2, COO gate), and get_chargeback_status (L1 AUTO read).
It DELEGATES to the injected ChargebackHandle and NEVER reimplements dispute logic.

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band [+COO step-up] → cost_cap → compliance(DISPUTE) → handle call

* ``scope``          — ChargebackHandle ops only (3-op allow-list).
* ``autonomy_level`` — L2 for initiate/submit (force_review=True, COO sign-off);
                       L1-Auto for get_status (AUTO-only read).
* ``cost_cap``       — per-request AND per-window hard caps (ADR-047 §D2).
* ``lineage``        — one AgentDecisionRecord per action, every exit path (ADR-046).
* ``compliance``     — DISPUTE overlay; non-PASS → BLOCK + escalate to COO.

R-SEC (ADR-021): triggering_event is keyed on opaque handles (dispute_id /
chargeback_id) ONLY — never amounts, PII, or customer data. The handle's dict
return rides on AgentOutcome.result ONLY, never on AgentDecisionRecord.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
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

# ---------------------------------------------------------------------------
# Narrow DI Protocol (typing only — not a new heavy port)
# ---------------------------------------------------------------------------


class ChargebackHandle(Protocol):
    """Narrow typing Protocol for the injected chargeback domain handle.

    Matches ChargebackBridge's three public method signatures exactly.
    """

    def initiate_chargeback(
        self,
        dispute_id: str,
        scheme: str,
        amount: Decimal,
        reason_code: str,
    ) -> dict[str, str]: ...

    def submit_representment(
        self,
        chargeback_id: str,
        evidence_hashes: list[str],
    ) -> dict[str, object]: ...

    def get_chargeback_status(self, chargeback_id: str) -> dict[str, str]: ...


# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChargebackMask:
    """Config-as-data COO-gated chargeback mask (ORG §2.6).

    All gate values are governed config. scope is the exclusive allow-list.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "chargeback_agent"
    scope: tuple[str, ...] = (
        "ChargebackHandle.initiate_chargeback",
        "ChargebackHandle.submit_representment",
        "ChargebackHandle.get_chargeback_status",
    )
    compliance_gate: tuple[str, ...] = ("DISPUTE",)
    coo_role: str = "COO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class InitiateChargebackIntent:
    """Resolved initiate-chargeback intent (L2 COO gate).

    R-SEC: amount (Decimal, I-01) is passed to the handle but NEVER recorded
    in the lineage record. triggering_event uses dispute_id (opaque) only.
    """

    intent_text: str
    process_ref: ProcessRef
    dispute_id: str
    scheme: str
    amount: Decimal  # I-01: Decimal for money, never float
    reason_code: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class SubmitRepresentmentIntent:
    """Resolved submit-representment intent (L2 COO gate).

    R-SEC: triggering_event uses chargeback_id (opaque) only.
    evidence_hashes is a tuple to keep the frozen dataclass hashable.
    """

    intent_text: str
    process_ref: ProcessRef
    chargeback_id: str
    evidence_hashes: tuple[str, ...]
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class GetChargebackStatusIntent:
    """Resolved get-chargeback-status intent (L1 AUTO read).

    A read below the AUTO band halts with HALT_REVIEW_DEFERRED; there is
    no HITL hold path for status reads. R-SEC: triggering_event uses
    chargeback_id (opaque) only.
    """

    intent_text: str
    process_ref: ProcessRef
    chargeback_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


# ---------------------------------------------------------------------------
# Internal evaluation types (private)
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
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
    force_review: bool = False
    review_escalate_to: str | None = None


@dataclass
class _Evaluation:
    decision: ConfirmationDecision
    proceed: bool
    action_taken: str
    reasoning_summary: str
    policies_evaluated: list[str]
    compliance_result: ComplianceResult
    budget_breach: BudgetBreach
    halt_reason: str | None = None
    requires_hitl: bool = False
    escalated_to: str | None = None


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------


class ChargebackAgent:
    """L2 Review COO-gated chargeback mask enforcing the ADR-049 §D2 gate chain.

    initiate_chargeback and submit_representment always force REVIEW (COO gate).
    get_chargeback_status is L1-Auto: AUTO-eligible within cap; REVIEW band →
    HALT_REVIEW_DEFERRED (no HITL hold for reads).

    The ChargebackHandle and recorder are injected; this class contains pure
    governance logic and is unit-testable without any live infrastructure.
    """

    def __init__(
        self,
        *,
        chargeback_handle: ChargebackHandle,
        recorder: DecisionRecorder,
        mask: ChargebackMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._handle = chargeback_handle
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def initiate_chargeback(
        self,
        intent: InitiateChargebackIntent,
        *,
        human_reviewed_by: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Initiate a chargeback via the handle (L2, COO gate).

        force_review=True: AUTO confidence is stepped up to REVIEW.
        No reviewer → HOLD_FOR_REVIEW (handle NOT called, escalate→COO).
        With reviewer → delegate to handle.initiate_chargeback(…).
        R-SEC: triggering_event uses dispute_id only — never amount or PII.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"initiate_chargeback:{intent.dispute_id}",
            success_action="INITIATE_CHARGEBACK",
            op="ChargebackHandle.initiate_chargeback",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            force_review=True,
            review_escalate_to=self._mask.coo_role,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.initiate_chargeback(
                intent.dispute_id, intent.scheme, intent.amount, intent.reason_code
            ),
        )

    async def submit_representment(
        self,
        intent: SubmitRepresentmentIntent,
        *,
        human_reviewed_by: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Submit representment evidence via the handle (L2, COO gate).

        force_review=True: same COO gate as initiate_chargeback.
        R-SEC: triggering_event uses chargeback_id only.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"submit_representment:{intent.chargeback_id}",
            success_action="SUBMIT_REPRESENTMENT",
            op="ChargebackHandle.submit_representment",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            force_review=True,
            review_escalate_to=self._mask.coo_role,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.submit_representment(
                intent.chargeback_id, list(intent.evidence_hashes)
            ),
        )

    async def get_chargeback_status(
        self,
        intent: GetChargebackStatusIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Read chargeback status via the handle (L1 AUTO read).

        AUTO-eligible within cap. REVIEW band → HALT_REVIEW_DEFERRED (no HITL hold
        for reads). DISPUTE overlay must PASS; non-PASS blocks and escalates to COO.
        R-SEC: result rides on AgentOutcome.result ONLY — never in the lineage record.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_chargeback_status:{intent.chargeback_id}",
            success_action="GET_CHARGEBACK_STATUS",
            op="ChargebackHandle.get_chargeback_status",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
            force_review=False,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.get_chargeback_status(intent.chargeback_id),
        )

    # -- governance engine ---------------------------------------------------

    def _band(self, score: float) -> ConfirmationDecision:
        if score >= self._mask.auto_threshold:
            return ConfirmationDecision.AUTO
        if score >= self._mask.review_floor:
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

    def _evaluate(self, ctx: _ActionContext) -> _Evaluation:  # noqa: PLR0911
        if not 0.0 <= ctx.confidence_score <= 1.0:
            raise ValueError(f"confidence_score {ctx.confidence_score!r} must be in [0.0, 1.0]")

        policies: list[str] = ["ADR-048-process-resolution"]

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

        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op!r} not on chargeback scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            policies.append("ADR-046-COO-step-up")
            band = ConfirmationDecision.REVIEW

        if band is ConfirmationDecision.BLOCK:
            return _Evaluation(
                band,
                False,
                "BLOCK_LOW_CONFIDENCE",
                "Confidence below 0.70; human confirmation mandatory (ADR-049 §D4).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
            )

        if band is ConfirmationDecision.REVIEW:
            if ctx.force_review:
                # L2 write path: COO sign-off required.
                if ctx.human_reviewed_by is None:
                    return _Evaluation(
                        band,
                        False,
                        "HOLD_FOR_REVIEW",
                        "Consequential chargeback op: COO sign-off required (ADR-046).",
                        policies,
                        ctx.compliance_result,
                        BudgetBreach.NONE,
                        halt_reason="hitl_review_required",
                        requires_hitl=True,
                        escalated_to=ctx.review_escalate_to,
                    )
                # reviewer present → fall through to cost/compliance gates
            else:
                # L1 read path: reads are AUTO-only; no HITL hold.
                return _Evaluation(
                    band,
                    False,
                    "HALT_REVIEW_DEFERRED",
                    "Status read below AUTO band; reads are AUTO-only, no HITL hold.",
                    policies,
                    ctx.compliance_result,
                    BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )

        policies.append("ADR-047-cost-cap")
        if self._cost_breaches(ctx.request_cost):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COST_CAP_BREACH",
                "Per-request or per-window cost-cap breach; action refused (ADR-047).",
                policies,
                ComplianceResult.NA,
                BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"DISPUTE overlay {ctx.compliance_result!r}; blocked, escalated to {self._mask.coo_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.coo_role,
            )

        note = f" (reviewed by {ctx.human_reviewed_by})" if ctx.human_reviewed_by else ""
        return _Evaluation(
            band,
            True,
            ctx.success_action,
            f"All chargeback gates satisfied at {band.value} confidence{note}.",
            policies,
            ctx.compliance_result,
            BudgetBreach.NONE,
        )

    async def _emit(
        self,
        ctx: _ActionContext,
        ev: _Evaluation,
        action_taken: str,
        *,
        executed: bool,  # noqa: ARG002
        compliance_result: ComplianceResult,
        reasoning: str,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.now(UTC),
            agent_id=self._mask.agent_id,
            triggering_event=ctx.triggering_event,
            intent=ctx.intent_text,
            policies_evaluated=list(ev.policies_evaluated),
            compliance_result=compliance_result,
            reasoning_summary=reasoning,
            confidence_score=ctx.confidence_score,
            action_taken=action_taken,
            human_reviewed_by=ctx.human_reviewed_by,
            correlation_id=ctx.correlation_id,
            cost_tokens=ctx.request_cost.tokens,
            cost_amount=ctx.request_cost.cost,
            budget_window_ref=self._window.window_ref,
            budget_breach_flag=ev.budget_breach,
            escalated_to=escalated_to,
        )
        await self._recorder.record(record)
        return record

    async def _run_action(
        self,
        ctx: _ActionContext,
        port_call: Callable[[], object],
    ) -> AgentOutcome:
        ev = self._evaluate(ctx)
        result: object | None = None
        executed = False
        action_taken = ev.action_taken

        if ev.proceed:
            try:
                result = port_call()
            except ValueError as exc:
                # Domain raises ValueError for unknown scheme / non-positive amount / not-found.
                action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                await self._emit(
                    ctx,
                    ev,
                    action_taken,
                    executed=False,
                    compliance_result=ev.compliance_result,
                    reasoning=f"Handle raised {type(exc).__name__}: {exc}",
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


__all__ = [
    "ChargebackAgent",
    "ChargebackHandle",
    "ChargebackMask",
    "GetChargebackStatusIntent",
    "InitiateChargebackIntent",
    "SubmitRepresentmentIntent",
]
