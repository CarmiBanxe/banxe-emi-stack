"""FPAAgent — L1-Auto FP&A GL read agent (ADR-049 §D2 / ORG-STRUCTURE §2.5.2).

WHY: ORG-STRUCTURE §2.5.2 defines the FP&A (Financial Planning & Analysis) agent as the
governed surface through which a resolved budget-vs-actuals read intent becomes a bounded
General Ledger read action. This module is the emi-stack FP&A sibling of
``services/agents/analytics_agent.py``, ``kyc_onboarding_agent.py``, and
``notification_agent.py`` — it implements the agent *logic* and *governance enforcement*
of the FP&A mask in front of the LedgerPort CONTRACT.

The FP&A agent (ORG-STRUCTURE §2.5.2, soul: budget-agent) provides budget-vs-actuals
reporting and GL-variance drill-down by reading account balances and journal entries.
It annotates data with [FACT]/[CALCULATION]/[ASSUMPTION] labels and NEVER submits a
budget without Head-of-FP&A approval — but budget submission is out of scope here.
This module is the read-only governance layer only.

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band → cost_cap → compliance(FINANCIAL_DATA) → port call

* ``scope``              — LedgerPort read ops only (allow-list:
                           get_account_balance / get_journal_entry). Off-list ops
                           are refused outright (ADR-054 §D1 pattern applied here).
* ``autonomy_level``     — L1-Auto: every read is AUTO-eligible within cap. NO REVIEW
                           HITL hold, NO biometric step-up (no money movement). A read
                           that falls below the AUTO band halts for a re-check at higher
                           confidence (HALT_REVIEW_DEFERRED, requires_hitl=True); there
                           is no HITL hold path in this agent.
* ``confirmation_policy``— AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70 (ADR-047
                           thresholds). REVIEW band → HALT_REVIEW_DEFERRED (re-check
                           required, not a hold): reads are AUTO-only for this agent.
* ``cost_cap``           — per-request AND per-window hard caps in both token and
                           monetary (Decimal) dimensions (ADR-047 §D2).
* ``lineage_obligation`` — one ``AgentDecisionRecord`` per action on every exit path
                           (ADR-046), non-optional.
* ``compliance_gate``    — FINANCIAL_DATA overlay: the L3 check MUST PASS before a
                           port call; a non-PASS verdict halts (BLOCK) and escalates
                           to the CFO (config-as-data on the mask).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence, cost-cap
breach, compliance(FINANCIAL_DATA) fail} halts the action (ADR-049 §D4 — independent
halt conditions). The port's own validation (e.g., account not found) is
defense-in-depth: if the port raises LedgerPortError, lineage is emitted
(executed=False) and the error is re-raised. Mask values (caps, thresholds, scope,
gate, escalation role) are config-as-data, carried on :class:`FPAMask`, never
hardcoded in flow logic.

R-SEC (R-SEC-NEW-01, ADR-021): no raw GL balance, amount, or PII ever enters a lineage
record. Every account / entry reference crossing this agent is an opaque ``account_id``
/ ``entry_id``; the triggering_event is keyed on those opaque handles only. The port's
balance / entry return value rides on ``AgentOutcome.result`` (the functional return) —
NEVER on the recorded ``AgentDecisionRecord``.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
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
from services.ledger.ledger_port import LedgerPort

# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class LedgerPortError(Exception):
    """Base error for LedgerPort GL-read failures.

    LedgerPort adapters raise this (or a subclass) when a GL read fails.
    FPAAgent catches it, emits one lineage record (executed=False), then
    re-raises — defense-in-depth: the port's own data validation is the
    last guard (ADR-046 / ADR-027). Correlate failures via
    ``AgentDecisionRecord.correlation_id``.
    """


# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class FPAMask:
    """Config-as-data FP&A (ORG-STRUCTURE §2.5.2) mask.

    All gate values are governed config, not hardcoded flow logic. The
    AUTO/REVIEW/BLOCK scale is ADR-047 canon. The mask is the allow-list and
    the gate posture for the FP&A read capability.
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "fpa_agent"
    # The mask scope (allow-list): the only LedgerPort ops this mask may reach.
    scope: tuple[str, ...] = (
        "LedgerPort.get_account_balance",
        "LedgerPort.get_journal_entry",
    )
    # L3 compliance contour required before any port call.
    compliance_gate: tuple[str, ...] = ("FINANCIAL_DATA",)
    # Escalation role for a compliance non-PASS verdict (config-as-data).
    cfo_role: str = "CFO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass
class GetBudgetActualsIntent:
    """A resolved GL-balance read intent (``LedgerPort.get_account_balance``) —
    the actuals leg of a budget-vs-actuals comparison (ADR-049 §D2 / ORG-STRUCTURE
    §2.5.2). A read below the AUTO band halts for a re-check, not a HITL hold.
    The FINANCIAL_DATA compliance overlay MUST PASS before the balance is returned;
    a non-PASS verdict blocks and escalates to the CFO. The balance rides on
    ``AgentOutcome.result`` ONLY — never on the lineage record (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    account_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetJournalEntryIntent:
    """A resolved journal-entry read intent (``LedgerPort.get_journal_entry``) —
    the variance drill-down path (ORG-STRUCTURE §2.5.2). A read below the AUTO band
    halts for a re-check. The FINANCIAL_DATA overlay MUST PASS; a non-PASS verdict
    blocks and escalates to the CFO. The entry object rides on ``AgentOutcome.result``
    ONLY — never on the lineage record (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    entry_id: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


# ---------------------------------------------------------------------------
# Internal evaluation types
# ---------------------------------------------------------------------------


@dataclass
class _ActionContext:
    """All inputs a single masked FPA action evaluates against."""

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


class FPAAgent:
    """L1-Auto FP&A GL read agent enforcing the ADR-049 §D2 gate chain.

    The :class:`LedgerPort` and the lineage recorder are injected as interfaces
    (constructor injection); the agent contains pure governance logic and is
    unit-testable without any live infra. It depends only on the LedgerPort
    CONTRACT, never on the domain GL adapter behind it.
    """

    def __init__(
        self,
        *,
        ledger_port: LedgerPort,
        recorder: DecisionRecorder,
        mask: FPAMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = ledger_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def get_budget_actuals(
        self,
        intent: GetBudgetActualsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """GL account-balance read via ``LedgerPort.get_account_balance`` — the actuals
        leg of budget-vs-actuals (ORG-STRUCTURE §2.5.2). AUTO-eligible within cap. The
        FINANCIAL_DATA overlay (``compliance_result``) must PASS before the balance is
        returned; a non-PASS verdict blocks and escalates to the CFO. A read below the
        AUTO band halts for a re-check, not a HITL hold (L1-Auto)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_budget_actuals:{intent.account_id}",
            success_action="GET_BUDGET_ACTUALS",
            op="LedgerPort.get_account_balance",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )

        async def _call() -> object:
            return self._port.get_account_balance(intent.account_id)

        return await self._run_action(ctx, _call)

    async def get_journal_entry(
        self,
        intent: GetJournalEntryIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Journal-entry read via ``LedgerPort.get_journal_entry`` — variance drill-down
        (ORG-STRUCTURE §2.5.2). AUTO-eligible within cap. The FINANCIAL_DATA overlay must
        PASS before the entry is returned; a non-PASS verdict blocks and escalates to the
        CFO. A read below the AUTO band halts for a re-check (L1-Auto)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_journal_entry:{intent.entry_id}",
            success_action="GET_JOURNAL_ENTRY",
            op="LedgerPort.get_journal_entry",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )

        async def _call() -> object:
            return self._port.get_journal_entry(intent.entry_id)

        return await self._run_action(ctx, _call)

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

        # 2. Scope allow-list — an off-list op is refused outright.
        policies.append("ADR-049-scope-allow-list")
        if ctx.op not in self._mask.scope:
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "REJECT_OUT_OF_SCOPE",
                f"Operation {ctx.op} is not on the FPA mask scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        # 3. ADR-047 confidence band. REVIEW → HALT_REVIEW_DEFERRED: reads are
        #    AUTO-only (L1-Auto); there is no HITL hold path in this agent.
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

        # 5. FINANCIAL_DATA compliance gate. A non-PASS verdict halts AND escalates to CFO.
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            escalated = self._mask.cfo_role
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"FINANCIAL_DATA overlay returned {ctx.compliance_result}; "
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
            f"All FPA mask gates satisfied at {band.value} confidence; committing within scope.",
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
                except LedgerPortError as exc:
                    # Defense-in-depth: the port's own data guard fired. Emit one
                    # lineage record (executed=False) then re-raise — no raw balance
                    # or PII recorded.
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
        producer→sink seam used by every exit path). R-SEC: only opaque handles
        (account_id / entry_id via triggering_event) ever reach a record — never raw
        GL balances, amounts, or PII."""
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
    "BudgetBreach",
    "ComplianceResult",
    "ConfirmationDecision",
    "CostCap",
    "CostWindow",
    "DecisionRecorder",
    "FPAAgent",
    "FPAMask",
    "GetBudgetActualsIntent",
    "GetJournalEntryIntent",
    "LedgerPortError",
    "ProcessRef",
    "RequestCost",
]
