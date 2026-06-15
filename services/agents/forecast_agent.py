from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
import datetime
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
from services.treasury.liquidity_forecast_port import (
    LiquidityForecastPort,
    LiquidityForecastPortError,
)


@dataclass(frozen=True)
class ForecastMask:
    cost_cap: CostCap
    auto_threshold: float = 0.90
    review_floor: float = 0.70
    lineage_obligation: bool = True
    agent_id: str = "forecast_agent"
    scope: tuple[str, ...] = (
        "LiquidityForecastPort.get_forecast_inputs",
        "LiquidityForecastPort.get_current_position",
    )
    compliance_gate: tuple[str, ...] = ("FINANCIAL_DATA",)
    review_role: str = "HEAD_OF_FPA"


@dataclass(frozen=True)
class BuildLiquidityForecastIntent:
    intent_text: str
    process_ref: ProcessRef
    horizon_days: int
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class GetLiquidityPositionIntent:
    intent_text: str
    process_ref: ProcessRef
    as_of: str
    correlation_id: str
    confidence_score: float
    request_cost: RequestCost


@dataclass(frozen=True)
class _Evaluation:
    decision: ConfirmationDecision
    proceed: bool
    action_taken: str
    reasoning_summary: str
    policies_evaluated: list[str]
    compliance_result: ComplianceResult
    budget_breach: BudgetBreach
    halt_reason: str | None = None
    requires_step_up: bool = False
    requires_hitl: bool = False
    escalated_to: str | None = None


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


class ForecastAgent:
    """L2 Review agent for liquidity forecast inputs and current position reads.

    Band thresholds: AUTO >= 0.90; REVIEW 0.70–0.90; BLOCK < 0.70.
    REVIEW band with no reviewer → HOLD_FOR_REVIEW escalated to HEAD_OF_FPA.
    soul: forecast-agent — read-only inputs only; no modelling or distribution.
    """

    def __init__(
        self,
        port: LiquidityForecastPort,
        recorder: DecisionRecorder,
        mask: ForecastMask,
        window: CostWindow | None = None,
    ) -> None:
        self._port = port
        self._recorder = recorder
        self._mask = mask
        self._window = window if window is not None else CostWindow()

    # ------------------------------------------------------------------ public

    async def build_liquidity_forecast(
        self,
        intent: BuildLiquidityForecastIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"build_liquidity_forecast:{intent.horizon_days}",
            success_action="BUILD_LIQUIDITY_FORECAST",
            op="LiquidityForecastPort.get_forecast_inputs",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
        )
        return await self._run_action(
            ctx, lambda: self._port.get_forecast_inputs(intent.horizon_days)
        )

    async def get_liquidity_position(
        self,
        intent: GetLiquidityPositionIntent,
        *,
        compliance_result: ComplianceResult = ComplianceResult.PASS,
        human_reviewed_by: str | None = None,
    ) -> AgentOutcome:
        ctx = _ActionContext(
            intent_text=intent.intent_text,
            process_ref=intent.process_ref,
            correlation_id=intent.correlation_id,
            confidence_score=intent.confidence_score,
            triggering_event=f"get_liquidity_position:{intent.as_of}",
            success_action="GET_LIQUIDITY_POSITION",
            op="LiquidityForecastPort.get_current_position",
            request_cost=intent.request_cost,
            compliance_result=compliance_result,
            human_reviewed_by=human_reviewed_by,
        )
        return await self._run_action(ctx, lambda: self._port.get_current_position(intent.as_of))

    # ---------------------------------------------------------------- internals

    def _band(self, score: float) -> ConfirmationDecision:
        if score >= self._mask.auto_threshold:
            return ConfirmationDecision.AUTO
        if score >= self._mask.review_floor:
            return ConfirmationDecision.REVIEW
        return ConfirmationDecision.BLOCK

    def _cost_breaches(self, cost: RequestCost) -> bool:
        cap = self._mask.cost_cap
        if cost.tokens > cap.max_request_tokens:
            return True
        if cost.cost > cap.max_request_cost:
            return True
        if self._window.used_tokens + cost.tokens > cap.max_window_tokens:
            return True
        if self._window.used_cost + cost.cost > cap.max_window_cost:
            return True
        return False

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
                f"Operation {ctx.op!r} not on forecast scope allow-list; refused.",
                policies,
                ComplianceResult.NA,
                BudgetBreach.NONE,
                halt_reason="out_of_scope",
            )

        policies.append("ADR-047-HITL-AUTO-REVIEW-BLOCK")
        band = self._band(ctx.confidence_score)

        if band is ConfirmationDecision.BLOCK:
            return _Evaluation(
                band,
                False,
                "BLOCK_LOW_CONFIDENCE",
                "Confidence < 0.70; human confirmation mandatory (ADR-049 §D4).",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="low_confidence",
                requires_hitl=True,
            )

        if band is ConfirmationDecision.REVIEW and ctx.human_reviewed_by is None:
            return _Evaluation(
                band,
                False,
                "HOLD_FOR_REVIEW",
                f"Forecast action in REVIEW band; HITL hold — escalated to {self._mask.review_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="hitl_review_required",
                requires_hitl=True,
                escalated_to=self._mask.review_role,
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
                f"FINANCIAL_DATA overlay {ctx.compliance_result}; "
                f"blocked, escalated to {self._mask.review_role}.",
                policies,
                ctx.compliance_result,
                BudgetBreach.NONE,
                halt_reason="compliance_block",
                requires_hitl=True,
                escalated_to=self._mask.review_role,
            )

        note = f" (reviewed by {ctx.human_reviewed_by})" if ctx.human_reviewed_by else ""
        return _Evaluation(
            band,
            True,
            ctx.success_action,
            f"All forecast gates satisfied at {band.value} confidence{note}.",
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
        executed: bool,
        compliance_result: ComplianceResult,
        reasoning: str,
        escalated_to: str | None,
    ) -> AgentDecisionRecord:
        record = AgentDecisionRecord(
            record_id=str(uuid.uuid4()),
            timestamp=datetime.datetime.utcnow().isoformat(),
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
                except LiquidityForecastPortError as exc:
                    action_taken = f"HALT_PROVIDER_ERROR:{type(exc).__name__}"
                    await self._emit(
                        ctx,
                        ev,
                        action_taken,
                        executed=False,
                        compliance_result=ev.compliance_result,
                        reasoning=f"Port raised {type(exc).__name__}: {exc}",
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
            requires_step_up=ev.requires_step_up,
            requires_hitl=ev.requires_hitl,
            escalated_to=ev.escalated_to,
        )
