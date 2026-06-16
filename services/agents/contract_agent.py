"""ContractAgent — §D2 MASK_ONLY over agreement domain (Legal; ORG §2.9).

WHY: ORG §2.9 defines the contract agent as the governed surface through
which a resolved agreement intent becomes a bounded AgreementPort action.
This module is the emi-stack Legal-gated sibling of chargeback_agent — it
enforces the ADR-049 §D2 gate chain in front of the agreement domain.

The contract agent operates over create_agreement (L2, Legal Counsel gate),
record_signature (L2, Legal Counsel gate), and get_agreement (L1 AUTO read).
It DELEGATES to the injected AgreementPort and NEVER reimplements agreement logic.

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band [+Legal Counsel step-up] → cost_cap
    → compliance(LEGAL) → handle call

* ``scope``          — AgreementPort ops only (3-op allow-list).
* ``autonomy_level`` — L2 for create/record (force_review=True, Legal Counsel sign-off);
                       L1-Auto for get_agreement (AUTO-only read).
* ``cost_cap``       — per-request AND per-window hard caps (ADR-047 §D2).
* ``lineage``        — one AgentDecisionRecord per action, every exit path (ADR-046).
* ``compliance``     — LEGAL overlay; non-PASS → BLOCK + escalate to LEGAL_COUNSEL.

R-SEC (ADR-021): triggering_event is keyed on opaque handles (agreement_id /
customer_id / product_type) ONLY — never terms content, signature data, or PII.
The Agreement object rides on AgentOutcome.result ONLY, never on AgentDecisionRecord.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
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
from services.agreement.agreement_port import (
    AgreementError,
    AgreementPort,
    CreateAgreementRequest,
    ProductType,
    SignAgreementRequest,
)

# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ContractMask:
    """Config-as-data Legal-Counsel-gated contract mask (ORG §2.9).

    All gate values are governed config. scope is the exclusive allow-list.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "contract_agent"
    scope: tuple[str, ...] = (
        "AgreementPort.create_agreement",
        "AgreementPort.record_signature",
        "AgreementPort.get_agreement",
    )
    compliance_gate: tuple[str, ...] = ("LEGAL",)
    legal_counsel_role: str = "LEGAL_COUNSEL"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CreateAgreementIntent:
    """Resolved create-agreement intent (L2, Legal Counsel gate).

    R-SEC: terms_version is passed to the handle but triggering_event uses
    customer_id and product_type (opaque) only — never terms content.
    """

    intent_text: str
    process_ref: ProcessRef
    customer_id: str
    product_type: ProductType
    terms_version: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class RecordSignatureIntent:
    """Resolved record-signature intent (L2, Legal Counsel gate).

    R-SEC: signature_provider / docusign_envelope_id are passed to the handle
    but triggering_event uses agreement_id (opaque) only — never signature data.
    """

    intent_text: str
    process_ref: ProcessRef
    agreement_id: str
    customer_id: str
    signature_provider: str
    docusign_envelope_id: str | None
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class GetAgreementIntent:
    """Resolved get-agreement intent (L1 AUTO read).

    A read below the AUTO band halts with HALT_REVIEW_DEFERRED; there is no
    HITL hold path for agreement reads. R-SEC: triggering_event uses
    agreement_id (opaque) only.
    """

    intent_text: str
    process_ref: ProcessRef
    agreement_id: str
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


class ContractAgent:
    """L2 Review Legal-Counsel-gated contract mask enforcing the ADR-049 §D2 gate chain.

    create_agreement and record_signature always force REVIEW (Legal Counsel gate).
    get_agreement is L1-Auto: AUTO-eligible within cap; REVIEW band →
    HALT_REVIEW_DEFERRED (no HITL hold for reads).

    AgreementPort and recorder are injected; this class contains pure
    governance logic and is unit-testable without any live infrastructure.
    """

    def __init__(
        self,
        *,
        agreement_handle: AgreementPort,
        recorder: DecisionRecorder,
        mask: ContractMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._handle = agreement_handle
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def create_agreement(
        self,
        intent: CreateAgreementIntent,
        *,
        human_reviewed_by: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Create a customer agreement via the handle (L2, Legal Counsel gate).

        force_review=True: AUTO confidence is stepped up to REVIEW.
        No reviewer → HOLD_FOR_REVIEW (handle NOT called, escalate→LEGAL_COUNSEL).
        With reviewer → delegate to handle.create_agreement(…).
        R-SEC: triggering_event uses customer_id and product_type only.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=(f"create_agreement:{intent.customer_id}:{intent.product_type.value}"),
            success_action="CREATE_AGREEMENT",
            op="AgreementPort.create_agreement",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            force_review=True,
            review_escalate_to=self._mask.legal_counsel_role,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.create_agreement(
                CreateAgreementRequest(
                    customer_id=intent.customer_id,
                    product_type=intent.product_type,
                    terms_version=intent.terms_version,
                )
            ),
        )

    async def record_signature(
        self,
        intent: RecordSignatureIntent,
        *,
        human_reviewed_by: str | None = None,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Record an agreement signature via the handle (L2, Legal Counsel gate).

        force_review=True: same Legal Counsel gate as create_agreement.
        R-SEC: triggering_event uses agreement_id only — never signature data.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"record_signature:{intent.agreement_id}",
            success_action="RECORD_SIGNATURE",
            op="AgreementPort.record_signature",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
            force_review=True,
            review_escalate_to=self._mask.legal_counsel_role,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.record_signature(
                SignAgreementRequest(
                    agreement_id=intent.agreement_id,
                    customer_id=intent.customer_id,
                    signature_provider=intent.signature_provider,
                    docusign_envelope_id=intent.docusign_envelope_id,
                )
            ),
        )

    async def get_agreement(
        self,
        intent: GetAgreementIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Retrieve an agreement via the handle (L1 AUTO read).

        AUTO-eligible within cap. REVIEW band → HALT_REVIEW_DEFERRED (no HITL hold
        for reads). LEGAL overlay must PASS; non-PASS blocks and escalates to
        LEGAL_COUNSEL. R-SEC: Agreement result rides on AgentOutcome.result ONLY.
        """
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_agreement:{intent.agreement_id}",
            success_action="GET_AGREEMENT",
            op="AgreementPort.get_agreement",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=None,
            force_review=False,
        )
        return await self._run_action(
            ctx,
            lambda: self._handle.get_agreement(intent.agreement_id),
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
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="HALT_UNRESOLVED_PROCESS",
                reasoning_summary=(
                    "Intent has no resolved process_ref; governance event, never improvised."
                ),
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.NONE,
                halt_reason="unresolved_process_ref",
                requires_hitl=True,
            )

        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="REJECT_OUT_OF_SCOPE",
                reasoning_summary=(
                    f"Operation {ctx.op!r} not on contract scope allow-list; refused."
                ),
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)
        if ctx.force_review and band is ConfirmationDecision.AUTO:
            policies.append("ADR-046-LEGAL-COUNSEL-step-up")
            band = ConfirmationDecision.REVIEW

        if band is ConfirmationDecision.BLOCK:
            return _Evaluation(
                decision=band,
                proceed=False,
                action_taken="BLOCK_LOW_CONFIDENCE",
                reasoning_summary=(
                    "Confidence below 0.70; human confirmation mandatory (ADR-049 §D4)."
                ),
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
            )

        if band is ConfirmationDecision.REVIEW:
            if ctx.force_review:
                # L2 write path: Legal Counsel sign-off required.
                if ctx.human_reviewed_by is None:
                    return _Evaluation(
                        decision=band,
                        proceed=False,
                        action_taken="HOLD_FOR_REVIEW",
                        reasoning_summary=(
                            "Consequential agreement op: Legal Counsel sign-off required (ADR-046)."
                        ),
                        policies_evaluated=policies,
                        compliance_result=ctx.compliance_result,
                        budget_breach=BudgetBreach.NONE,
                        halt_reason="hitl_review_required",
                        requires_hitl=True,
                        escalated_to=ctx.review_escalate_to,
                    )
                # reviewer present → fall through to cost / compliance gates
            else:
                # L1 read path: reads are AUTO-only; no HITL hold.
                return _Evaluation(
                    decision=band,
                    proceed=False,
                    action_taken="HALT_REVIEW_DEFERRED",
                    reasoning_summary=(
                        "Agreement read below AUTO band; reads are AUTO-only, no HITL hold."
                    ),
                    policies_evaluated=policies,
                    compliance_result=ctx.compliance_result,
                    budget_breach=BudgetBreach.NONE,
                    halt_reason="review_deferred",
                    requires_hitl=True,
                )

        policies.append("ADR-047-cost-cap")
        if self._cost_breaches(ctx.request_cost):
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="HALT_COST_CAP_BREACH",
                reasoning_summary=(
                    "Per-request or per-window cost-cap breach; action refused (ADR-047)."
                ),
                policies_evaluated=policies,
                compliance_result=ComplianceResult.NA,
                budget_breach=BudgetBreach.BREACH,
                halt_reason="cost_cap_breach",
            )

        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            return _Evaluation(
                decision=ConfirmationDecision.BLOCK,
                proceed=False,
                action_taken="HALT_COMPLIANCE_BLOCK",
                reasoning_summary=(
                    f"LEGAL overlay {ctx.compliance_result!r}; "
                    f"blocked, escalated to {self._mask.legal_counsel_role}."
                ),
                policies_evaluated=policies,
                compliance_result=ctx.compliance_result,
                budget_breach=BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.legal_counsel_role,
            )

        note = f" (reviewed by {ctx.human_reviewed_by})" if ctx.human_reviewed_by else ""
        return _Evaluation(
            decision=band,
            proceed=True,
            action_taken=ctx.success_action,
            reasoning_summary=(f"All contract gates satisfied at {band.value} confidence{note}."),
            policies_evaluated=policies,
            compliance_result=ctx.compliance_result,
            budget_breach=BudgetBreach.NONE,
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
            except AgreementError as exc:
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
    "ContractAgent",
    "ContractMask",
    "CreateAgreementIntent",
    "GetAgreementIntent",
    "RecordSignatureIntent",
]
