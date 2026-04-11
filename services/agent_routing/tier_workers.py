"""
services/agent_routing/tier_workers.py — Tier Workers
IL-ARL-01 | banxe-emi-stack

Three tier workers implementing progressively more expensive analysis:
  Tier 1: Rule engine + BM25 (~$0 per decision)
  Tier 2: Mid-tier LLM (Haiku-class)
  Tier 3: Top model (Opus-class) or delegates to SwarmOrchestrator
"""

from __future__ import annotations

import logging
import time

from services.agent_routing.models import AgentTask
from services.agent_routing.schemas import AgentResponse, TierResult

logger = logging.getLogger(__name__)

# Sanctioned jurisdiction codes — I-02
_SANCTIONED_JURISDICTIONS: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)

# Known safe patterns for Tier 1 fast-path
_KNOWN_SAFE_EVENT_TYPES: frozenset[str] = frozenset(
    {"account_balance_check", "fx_rate_lookup", "limit_check_only"}
)


# ── Tier 1: Rule Engine ───────────────────────────────────────────────────────


class Tier1Worker:
    """Rule engine + BM25 pattern matching for routine, low-risk decisions.

    Cost: ~$0 per decision (no LLM calls).
    Suitable for: sanctions list check, limit validation, known-pattern transactions.
    """

    async def process(self, task: AgentTask) -> TierResult:
        t_start = time.monotonic()
        responses: list[AgentResponse] = []

        # Sanctions check (rule-based, no LLM)
        sanctions_resp = self._check_sanctions(task)
        responses.append(sanctions_resp)

        # Limit validation
        limit_resp = self._check_limits(task)
        responses.append(limit_resp)

        # Known-pattern matching
        pattern_resp = self._check_known_patterns(task)
        responses.append(pattern_resp)

        decision = self._aggregate(responses)
        latency_ms = int((time.monotonic() - t_start) * 1000)
        total_tokens = sum(r.token_cost for r in responses)

        return TierResult(
            task_id=task.task_id,
            tier_used=1,
            decision=decision,
            responses=responses,
            total_tokens=total_tokens,
            total_latency_ms=latency_ms,
            reasoning_reused=False,
            playbook_version=task.playbook_id,
        )

    def _check_sanctions(self, task: AgentTask) -> AgentResponse:
        """Hard-block sanctioned jurisdictions (I-02)."""
        ctx = task.risk_context
        jurisdiction = task.jurisdiction.upper()
        sanctions_hit = ctx.get("sanctions_hit", False)
        hard_block = jurisdiction in _SANCTIONED_JURISDICTIONS

        if hard_block or sanctions_hit:
            return AgentResponse(
                agent_name="tier1_sanctions",
                case_id=task.task_id,
                signal_type="sanctions_screening",
                risk_score=1.0,
                confidence=1.0,
                decision_hint="block",
                reason_summary=(
                    f"Sanctioned jurisdiction {jurisdiction!r}"
                    if hard_block
                    else "Sanctions list hit in risk context"
                ),
                evidence_refs=["invariant_I-02"],
                token_cost=0,
                latency_ms=0,
            )
        return AgentResponse(
            agent_name="tier1_sanctions",
            case_id=task.task_id,
            signal_type="sanctions_screening",
            risk_score=0.0,
            confidence=1.0,
            decision_hint="clear",
            reason_summary="No sanctions match",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )

    def _check_limits(self, task: AgentTask) -> AgentResponse:
        """Validate transaction amount against product limits."""
        ctx = task.risk_context
        # Use Decimal for monetary comparison (I-01)
        from decimal import Decimal

        amount = Decimal(str(ctx.get("amount_eur", 0)))

        # I-04: EDD threshold £10k individual, £50k corporate
        customer_type = ctx.get("customer_type", "individual")
        edd_threshold = Decimal("50000") if customer_type == "corporate" else Decimal("10000")

        if amount > edd_threshold:
            return AgentResponse(
                agent_name="tier1_limits",
                case_id=task.task_id,
                signal_type="limit_check",
                risk_score=0.8,
                confidence=1.0,
                decision_hint="warning",
                reason_summary=f"Amount {amount} EUR exceeds EDD threshold {edd_threshold}",
                evidence_refs=["invariant_I-04"],
                token_cost=0,
                latency_ms=0,
            )
        return AgentResponse(
            agent_name="tier1_limits",
            case_id=task.task_id,
            signal_type="limit_check",
            risk_score=0.0,
            confidence=1.0,
            decision_hint="clear",
            reason_summary="Amount within limits",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )

    def _check_known_patterns(self, task: AgentTask) -> AgentResponse:
        """BM25 / rule-based known-safe pattern matching."""
        ctx = task.risk_context
        known_beneficiary = ctx.get("known_beneficiary", False)
        anomaly_count = int(ctx.get("anomaly_count", 0))
        device_risk = ctx.get("device_risk", "medium")

        if known_beneficiary and anomaly_count == 0 and device_risk == "low":
            return AgentResponse(
                agent_name="tier1_pattern",
                case_id=task.task_id,
                signal_type="pattern_matching",
                risk_score=0.05,
                confidence=0.9,
                decision_hint="clear",
                reason_summary="Known beneficiary, no anomalies, low device risk",
                evidence_refs=[],
                token_cost=0,
                latency_ms=0,
            )
        risk_score = min(0.3 + (anomaly_count * 0.1), 0.7)
        return AgentResponse(
            agent_name="tier1_pattern",
            case_id=task.task_id,
            signal_type="pattern_matching",
            risk_score=risk_score,
            confidence=0.75,
            decision_hint="warning" if risk_score >= 0.3 else "clear",
            reason_summary=f"Pattern check: anomaly_count={anomaly_count}, device_risk={device_risk}",
            evidence_refs=[],
            token_cost=0,
            latency_ms=0,
        )

    @staticmethod
    def _aggregate(responses: list[AgentResponse]) -> str:
        """Deterministic aggregation: any block → hold; majority warning → manual_review."""
        if any(r.decision_hint == "block" for r in responses):
            return "hold"
        warnings = sum(1 for r in responses if r.decision_hint == "warning")
        if warnings >= 2:
            return "manual_review"
        max_risk = max((r.risk_score for r in responses), default=0.0)
        if max_risk >= 0.75:
            return "manual_review"
        return "approve"


# ── Tier 2: Mid-Tier LLM ─────────────────────────────────────────────────────


class Tier2Worker:
    """Mid-tier LLM worker (Haiku-class) for moderate-complexity analysis.

    Suitable for: new beneficiary analysis, payment description NLP,
    behavioral anomaly assessment.
    """

    async def process(self, task: AgentTask) -> TierResult:
        t_start = time.monotonic()
        responses: list[AgentResponse] = []

        # New beneficiary analysis
        beneficiary_resp = await self._analyze_beneficiary(task)
        responses.append(beneficiary_resp)

        # Payment description NLP
        description_resp = await self._analyze_description(task)
        responses.append(description_resp)

        # Behavioral anomaly
        behavior_resp = await self._analyze_behavior(task)
        responses.append(behavior_resp)

        decision = self._aggregate(responses)
        latency_ms = int((time.monotonic() - t_start) * 1000)
        total_tokens = sum(r.token_cost for r in responses)

        return TierResult(
            task_id=task.task_id,
            tier_used=2,
            decision=decision,
            responses=responses,
            total_tokens=total_tokens,
            total_latency_ms=latency_ms,
            reasoning_reused=task.reasoning_hint is not None,
            playbook_version=task.playbook_id,
        )

    async def _analyze_beneficiary(self, task: AgentTask) -> AgentResponse:
        """Analyze new beneficiary risk."""
        ctx = task.risk_context
        new_beneficiary = ctx.get("new_beneficiary", False)
        customer_age_days = int(ctx.get("customer_age_days", 365))

        # Simulate mid-tier LLM analysis
        # In production: call Haiku-class LLM with structured prompt
        if new_beneficiary and customer_age_days < 30:
            risk = 0.65
            hint = "warning"
            summary = (
                f"New beneficiary + new customer (age {customer_age_days} days) — elevated risk"
            )
            tokens = 120
        elif new_beneficiary:
            risk = 0.35
            hint = "warning"
            summary = "New beneficiary — standard review required"
            tokens = 80
        else:
            risk = 0.1
            hint = "clear"
            summary = "Known beneficiary, no concerns"
            tokens = 40

        return AgentResponse(
            agent_name="tier2_beneficiary",
            case_id=task.task_id,
            signal_type="beneficiary_analysis",
            risk_score=risk,
            confidence=0.82,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=[],
            token_cost=tokens,
            latency_ms=50,
        )

    async def _analyze_description(self, task: AgentTask) -> AgentResponse:
        """NLP analysis of payment description for suspicious keywords."""
        payload = task.payload
        description = payload.get("description", "").lower()

        # Simplified keyword detection — in production: LLM with prompt
        suspicious_keywords = {"crypto", "gambling", "casino", "anonymous", "offshore"}
        found = [kw for kw in suspicious_keywords if kw in description]

        if found:
            risk = 0.6
            hint = "warning"
            summary = f"Suspicious keywords in description: {found}"
            tokens = 150
        else:
            risk = 0.05
            hint = "clear"
            summary = "No suspicious keywords detected"
            tokens = 60

        return AgentResponse(
            agent_name="tier2_description_nlp",
            case_id=task.task_id,
            signal_type="description_nlp",
            risk_score=risk,
            confidence=0.78,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=[],
            token_cost=tokens,
            latency_ms=80,
        )

    async def _analyze_behavior(self, task: AgentTask) -> AgentResponse:
        """Behavioral anomaly assessment."""
        ctx = task.risk_context
        amount_spike = ctx.get("amount_spike", False)
        velocity_24h = int(ctx.get("velocity_24h", 0))
        cumulative_risk: float = ctx.get("cumulative_risk_score", 0.0)

        risk = cumulative_risk
        if amount_spike:
            risk = min(risk + 0.3, 1.0)
        if velocity_24h > 5:
            risk = min(risk + 0.2, 1.0)

        hint: str
        if risk >= 0.7:
            hint = "block"
            summary = f"High behavioral risk: spike={amount_spike}, velocity={velocity_24h}, cumulative={cumulative_risk:.2f}"
        elif risk >= 0.4:
            hint = "warning"
            summary = f"Elevated behavioral signals: spike={amount_spike}, velocity={velocity_24h}"
        else:
            hint = "clear"
            summary = "Normal behavioral pattern"

        return AgentResponse(
            agent_name="tier2_behavior",
            case_id=task.task_id,
            signal_type="behavioral_anomaly",
            risk_score=risk,
            confidence=0.85,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=[],
            token_cost=200,
            latency_ms=120,
        )

    @staticmethod
    def _aggregate(responses: list[AgentResponse]) -> str:
        """Aggregate Tier 2 responses with LLM confidence weighting."""
        if any(r.decision_hint == "block" for r in responses):
            return "hold"
        high_confidence_warnings = sum(
            1 for r in responses if r.decision_hint == "warning" and r.confidence >= 0.7
        )
        if high_confidence_warnings >= 2:
            return "manual_review"
        avg_risk = sum(r.risk_score for r in responses) / len(responses) if responses else 0.0
        if avg_risk >= 0.55:
            return "manual_review"
        return "approve"


# ── Tier 3: Top Model / Swarm ─────────────────────────────────────────────────


class Tier3Worker:
    """Top model (Opus-class) or Swarm Orchestrator for complex investigations.

    Suitable for: conflicting signals, cross-border high-risk, complex AML/KYC.
    Delegates to SwarmOrchestrator for cases requiring multiple agents.
    """

    async def process(self, task: AgentTask) -> TierResult:
        """Process complex cases with top-tier model or swarm delegation."""
        t_start = time.monotonic()

        # Determine whether to use swarm or single top-tier LLM
        use_swarm = self._should_use_swarm(task)

        if use_swarm:
            return await self._process_with_swarm(task, t_start)
        return await self._process_with_top_model(task, t_start)

    def _should_use_swarm(self, task: AgentTask) -> bool:
        """Use swarm for cases with conflicting signals or high complexity."""
        ctx = task.risk_context
        conflicting = ctx.get("conflicting_signals", False)
        cross_border = ctx.get("cross_border", False)
        risk: float = ctx.get("cumulative_risk_score", 0.0)
        return conflicting or (cross_border and risk >= 0.5)

    async def _process_with_swarm(self, task: AgentTask, t_start: float) -> TierResult:
        """Delegate to SwarmOrchestrator for multi-agent analysis."""
        # Import here to avoid circular imports
        from services.swarm.orchestrator import SwarmOrchestrator

        orchestrator = SwarmOrchestrator()
        result = await orchestrator.launch_swarm(
            task=task,
            topology="star",
            agent_names=["sanctions", "behavior", "geo_risk", "profile_history"],
        )
        result.tier_used = 3
        return result

    async def _process_with_top_model(self, task: AgentTask, t_start: float) -> TierResult:
        """Use top-tier LLM for complex single-agent analysis."""
        # Simulate top-tier LLM analysis
        # In production: call Opus-class LLM with full context
        ctx = task.risk_context
        sanctions_hit = ctx.get("sanctions_hit", False)
        cumulative_risk: float = ctx.get("cumulative_risk_score", 0.0)

        if sanctions_hit:
            risk = 0.95
            hint = "block"
            summary = "Tier 3: Confirmed sanctions hit — decline required"
            tokens = 800
        elif cumulative_risk >= 0.75:
            risk = cumulative_risk
            hint = "manual_review"
            summary = f"Tier 3: High cumulative risk {cumulative_risk:.2f} — mandatory HITL review"
            tokens = 1200
        else:
            risk = max(cumulative_risk, 0.3)
            hint = "warning"
            summary = f"Tier 3: Complex case, risk={risk:.2f} — advisory review recommended"
            tokens = 600

        response = AgentResponse(
            agent_name="tier3_top_model",
            case_id=task.task_id,
            signal_type="complex_analysis",
            risk_score=risk,
            confidence=0.92,
            decision_hint=hint,
            reason_summary=summary,
            evidence_refs=[f"tier3_analysis_{task.task_id}"],
            token_cost=tokens,
            latency_ms=500,
        )

        latency_ms = int((time.monotonic() - t_start) * 1000)
        decision: str
        match hint:
            case "block":
                decision = "decline"
            case "manual_review":
                decision = "manual_review"
            case "warning":
                decision = "manual_review"
            case _:
                decision = "approve"

        return TierResult(
            task_id=task.task_id,
            tier_used=3,
            decision=decision,
            responses=[response],
            total_tokens=tokens,
            total_latency_ms=latency_ms,
            reasoning_reused=task.reasoning_hint is not None,
            playbook_version=task.playbook_id,
        )
