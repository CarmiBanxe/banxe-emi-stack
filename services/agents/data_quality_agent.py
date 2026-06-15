"""DataQualityAgent — L1-Auto CTO data quality & drift detection agent
(ADR-080 / ORG-STRUCTURE §2.7.1).

WHY: ORG-STRUCTURE §2.7.1 defines the CTO data-quality agent as the governed surface
through which a resolved data-quality read intent becomes a bounded DataQualityPort
read action. This module implements the agent *logic* and *governance enforcement* of
the data quality mask in front of the DataQualityPort CONTRACT.

The CTO data-quality agent provides drift score detection, quality reports, dataset
discovery, and freshness reads for the CTO data oversight dashboard. It operates
READ-ONLY over the data quality layer and NEVER modifies source data, NEVER triggers
pipeline runs, NEVER updates or retrains models, and NEVER makes autonomous data
decisions.

INVARIANT (CRITICAL — enforced in code):
    DataQualityAgent is detection/reporting only. It MUST NEVER trigger retraining,
    pipeline runs, or data writes. Enforced by three independent mechanisms:
      (1) the mask scope allow-list contains ONLY the 4 read ops:
          get_drift_score, get_quality_report, list_datasets, get_freshness;
      (2) DataQualityPort has NO mutate/trigger/retrain method — calling one would
          require a method that does not exist on the port;
      (3) every ``success_action`` in this module is a DETECT/REPORT verb
          (DETECT_DRIFT_SCORE, REPORT_QUALITY, DETECT_DATASETS, REPORT_FRESHNESS) —
          the strings RETRAIN, TRIGGER, WRITE, UPDATE do not appear as success actions.

    I-27 (CLAUDE.md): Feedback is supervised — this agent PROPOSES findings, never
    applies model updates or triggers retraining autonomously.

GOVERNANCE (ADR-049 §D2 gate-chain, fixed order):
    process_ref → scope → band → cost_cap → compliance(DATA_QUALITY) → port call

* ``scope``              — DataQualityPort READ ops only (allow-list:
                           get_drift_score / get_quality_report /
                           list_datasets / get_freshness).
                           Off-list ops are refused outright (ADR-054 §D1 pattern).
* ``autonomy_level``     — L1-Auto: every read is AUTO-eligible within cap. NO
                           REVIEW HITL hold, NO biometric step-up. A read below
                           the AUTO band halts for a re-check (HALT_REVIEW_DEFERRED,
                           requires_hitl=True); there is no HITL hold path.
* ``confirmation_policy``— AUTO > 0.90 / REVIEW 0.70–0.90 / BLOCK < 0.70
                           (ADR-047 thresholds). REVIEW band → HALT_REVIEW_DEFERRED.
* ``cost_cap``           — per-request AND per-window hard caps in both token and
                           monetary (Decimal) dimensions (ADR-047 §D2).
* ``lineage_obligation`` — one ``AgentDecisionRecord`` per action on every exit
                           path (ADR-046), non-optional.
* ``compliance_gate``    — DATA_QUALITY overlay: the L3 check MUST PASS before a
                           port call; a non-PASS verdict halts (BLOCK) and
                           escalates to the CTO (config-as-data on the mask).

Any one of {unresolved process_ref, out-of-scope op, below-band confidence,
cost-cap breach, compliance(DATA_QUALITY) fail} halts the action (ADR-049 §D4).
The port's own validation is defense-in-depth: if the port raises
DataQualityPortError, lineage is emitted (executed=False) and the error is
re-raised. Mask values are config-as-data, carried on :class:`DataQualityMask`.

R-SEC (R-SEC-NEW-01, ADR-021): no raw metric value, drift score, null rate, or PII
ever enters a lineage record. triggering_event is keyed on opaque labels only (dataset
name + op prefix) — never metric values. The port's return value (DriftSignal /
DataQualityReport / list[str] / int) rides on ``AgentOutcome.result`` ONLY — NEVER
on the recorded ``AgentDecisionRecord``.
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
from services.data_quality.data_quality_port import DataQualityPort, DataQualityPortError

# ---------------------------------------------------------------------------
# Mask (config-as-data)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class DataQualityMask:
    """Config-as-data CTO data quality oversight (ORG-STRUCTURE §2.7.1) mask.

    All gate values are governed config, not hardcoded flow logic. The
    AUTO/REVIEW/BLOCK scale is ADR-047 canon. The scope is the exclusive
    read-only allow-list — no retrain/trigger/write op is present
    (INVARIANT: see module docstring).
    """

    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "data_quality_agent"
    # The mask scope (allow-list): ONLY the 4 DataQualityPort READ ops.
    # INVARIANT: no retrain / trigger / write / update op is present in this tuple.
    # Any attempt to call one is REJECT_OUT_OF_SCOPE.
    scope: tuple[str, ...] = (
        "DataQualityPort.get_drift_score",
        "DataQualityPort.get_quality_report",
        "DataQualityPort.list_datasets",
        "DataQualityPort.get_freshness",
    )
    # L3 compliance contour required before any port call.
    compliance_gate: tuple[str, ...] = ("DATA_QUALITY",)
    # Escalation role for a compliance non-PASS verdict (config-as-data).
    cto_role: str = "CTO"


# ---------------------------------------------------------------------------
# Intent vocabulary
# ---------------------------------------------------------------------------


@dataclass
class GetDriftScoreIntent:
    """A resolved drift-score detection intent
    (``DataQualityPort.get_drift_score``) — the primary data drift read op
    (ADR-080 / ORG-STRUCTURE §2.7.1). A read below the AUTO band halts for a
    re-check, not a HITL hold. The DATA_QUALITY compliance overlay MUST PASS;
    a non-PASS verdict blocks and escalates to the CTO. The DriftSignal rides
    on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    dataset: str
    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetQualityReportIntent:
    """A resolved quality-report read intent
    (``DataQualityPort.get_quality_report``) — full data quality report for
    the CTO dashboard (ADR-080). A read below the AUTO band halts for a
    re-check. The DATA_QUALITY overlay MUST PASS; non-PASS escalates to CTO.
    The DataQualityReport rides on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    dataset: str
    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class ListDatasetsIntent:
    """A resolved dataset-discovery intent
    (``DataQualityPort.list_datasets``) — enumerates monitored datasets
    (ADR-080). A read below the AUTO band halts for a re-check. The
    DATA_QUALITY overlay MUST PASS; non-PASS escalates to CTO. The dataset
    list rides on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    intent_text: str
    process_ref: ProcessRef
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass
class GetFreshnessIntent:
    """A resolved freshness-report intent
    (``DataQualityPort.get_freshness``) — seconds since last data update
    (ADR-080). A read below the AUTO band halts for a re-check. The
    DATA_QUALITY overlay MUST PASS; non-PASS escalates to CTO. The freshness
    value rides on ``AgentOutcome.result`` ONLY (R-SEC).
    """

    dataset: str
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
    """All inputs a single masked data quality action evaluates against."""

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


class DataQualityAgent:
    """L1-Auto CTO data quality & drift detection agent enforcing ADR-049 §D2 gate chain.

    The :class:`~services.data_quality.data_quality_port.DataQualityPort` and the
    lineage recorder are injected as interfaces (constructor injection); the agent
    contains pure governance logic and is unit-testable without any live infra.

    INVARIANT: DETECTION/REPORTING ONLY. This agent MUST NEVER trigger retraining,
    pipeline runs, or data writes. See module docstring for the three independent
    enforcement mechanisms. I-27: PROPOSES findings only, never applies autonomously.
    """

    def __init__(
        self,
        *,
        data_quality_port: DataQualityPort,
        recorder: DecisionRecorder,
        mask: DataQualityMask,
        cost_window: CostWindow | None = None,
    ) -> None:
        self._port = data_quality_port
        self._recorder = recorder
        self._mask = mask
        self._window = cost_window or CostWindow(window_ref=f"{mask.agent_id}:default")

    # -- public mask actions -------------------------------------------------

    async def get_drift_score(
        self,
        intent: GetDriftScoreIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Drift score detection via ``DataQualityPort.get_drift_score`` (ADR-080).

        AUTO-eligible within cap. DATA_QUALITY overlay (``compliance_result``) MUST PASS;
        a non-PASS verdict blocks and escalates to the CTO. A read below the AUTO band
        halts for a re-check (L1-Auto). DriftSignal rides on ``AgentOutcome.result``
        ONLY (R-SEC — no drift score in lineage)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_drift_score:{intent.dataset}",
            success_action="DETECT_DRIFT_SCORE",
            op="DataQualityPort.get_drift_score",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_drift_score(intent.dataset))

    async def get_quality_report(
        self,
        intent: GetQualityReportIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Quality report read via ``DataQualityPort.get_quality_report`` (ADR-080).

        AUTO-eligible within cap. DATA_QUALITY overlay MUST PASS; non-PASS blocks and
        escalates to CTO. A read below the AUTO band halts for a re-check (L1-Auto).
        DataQualityReport rides on ``AgentOutcome.result`` ONLY (R-SEC — no null-rate
        or schema-conformance value in lineage)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_quality_report:{intent.dataset}",
            success_action="REPORT_QUALITY",
            op="DataQualityPort.get_quality_report",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_quality_report(intent.dataset))

    async def list_datasets(
        self,
        intent: ListDatasetsIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Dataset discovery via ``DataQualityPort.list_datasets`` (ADR-080).

        AUTO-eligible within cap. DATA_QUALITY overlay MUST PASS; non-PASS blocks and
        escalates to CTO. A read below the AUTO band halts for a re-check (L1-Auto).
        Dataset list rides on ``AgentOutcome.result`` ONLY (R-SEC)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event="list_datasets",
            success_action="DETECT_DATASETS",
            op="DataQualityPort.list_datasets",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.list_datasets())

    async def get_freshness(
        self,
        intent: GetFreshnessIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
    ) -> AgentOutcome:
        """Freshness report via ``DataQualityPort.get_freshness`` (ADR-080).

        AUTO-eligible within cap. DATA_QUALITY overlay MUST PASS; non-PASS blocks and
        escalates to CTO. A read below the AUTO band halts for a re-check (L1-Auto).
        Freshness value rides on ``AgentOutcome.result`` ONLY (R-SEC — no freshness
        seconds value in lineage)."""
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_freshness:{intent.dataset}",
            success_action="REPORT_FRESHNESS",
            op="DataQualityPort.get_freshness",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
        )
        return await self._run_action(ctx, lambda: self._port.get_freshness(intent.dataset))

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
                f"Operation {ctx.op} is not on the data quality mask scope allow-list; refused.",
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

        # 5. DATA_QUALITY compliance gate. A non-PASS verdict halts AND escalates to CTO.
        policies.append("ADR-049-compliance-gate:" + "+".join(self._mask.compliance_gate))
        if ctx.compliance_result not in (ComplianceResult.PASS, ComplianceResult.NA):
            escalated = self._mask.cto_role
            return _Evaluation(
                ConfirmationDecision.BLOCK,
                False,
                "HALT_COMPLIANCE_BLOCK",
                f"DATA_QUALITY overlay returned {ctx.compliance_result}; "
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
            f"All data quality mask gates satisfied at {band.value} confidence; committing within scope.",
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
                except DataQualityPortError as exc:
                    # Defense-in-depth: the port's own data guard fired. Emit one
                    # lineage record (executed=False) then re-raise — no raw metric
                    # value, drift score, null rate, or PII recorded.
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
        producer→sink seam used by every exit path). R-SEC: triggering_event uses
        opaque dataset/op labels only — never drift scores, null rates, metric values,
        freshness values, or PII. Port return values ride on AgentOutcome.result,
        never on this record."""
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
    "DataQualityAgent",
    "DataQualityMask",
    "DataQualityPortError",
    "DecisionRecorder",
    "GetDriftScoreIntent",
    "GetFreshnessIntent",
    "GetQualityReportIntent",
    "ListDatasetsIntent",
    "ProcessRef",
    "RequestCost",
]
