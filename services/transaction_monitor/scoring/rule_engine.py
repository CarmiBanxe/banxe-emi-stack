"""
services/transaction_monitor/scoring/rule_engine.py — Rule Engine
IL-RTM-01 | banxe-emi-stack

Integrates with Jube rules engine (existing :5001) via Protocol DI.
Returns a rules-based risk score 0-1 for the scoring pipeline.
"""

from __future__ import annotations

import logging
from typing import Any, Protocol, runtime_checkable

from services.transaction_monitor.models.risk_score import RiskFactor
from services.transaction_monitor.models.transaction import TransactionEvent

logger = logging.getLogger("banxe.transaction_monitor.rules")


@runtime_checkable
class JubePort(Protocol):
    """Interface for Jube rules engine."""

    def evaluate(self, transaction_data: dict[str, Any]) -> dict[str, Any]: ...


class InMemoryJubePort:
    """Test stub — returns deterministic rule results."""

    def evaluate(self, transaction_data: dict[str, Any]) -> dict[str, Any]:
        return {
            "score": 0.35,
            "triggered_rules": [
                {
                    "rule_id": "R001",
                    "name": "velocity_24h",
                    "score": 0.35,
                    "explanation": "Transaction count in 24h is within acceptable range.",
                }
            ],
        }


class HTTPJubePort:
    """Production Jube HTTP port."""

    def __init__(self, jube_url: str = "http://localhost:5001") -> None:
        self._url = jube_url

    def evaluate(self, transaction_data: dict[str, Any]) -> dict[str, Any]:
        import httpx

        with httpx.Client(base_url=self._url, timeout=10.0) as client:
            r = client.post("/api/v1/classify", json=transaction_data)
            r.raise_for_status()
            return r.json()


class RuleEngine:
    """Evaluates AML rules via Jube and returns risk factors.

    Returns a rules_score (0-1, non-monetary) and a list of triggered factors.
    """

    def __init__(self, jube_port: JubePort | None = None) -> None:
        self._jube = jube_port or InMemoryJubePort()

    def evaluate(
        self, event: TransactionEvent, features: dict[str, float]
    ) -> tuple[float, list[RiskFactor]]:
        """Evaluate rules and return (rules_score, factors).

        rules_score is non-monetary float 0-1.
        """
        # Hard-block: jurisdiction-based immediate critical score (I-02)
        if features.get("jurisdiction_risk", 0) >= 1.0:
            factor = RiskFactor(
                name="jurisdiction_hard_block",
                weight=1.0,
                value=1.0,
                contribution=1.0,
                explanation=f"Transaction involves sanctioned jurisdiction (I-02). Sender: {event.sender_jurisdiction}",
                regulation_ref="MLR 2017 Reg.18 / I-02 banxe invariant",
            )
            return 1.0, [factor]

        # Evaluate via Jube
        try:
            result = self._jube.evaluate(self._to_jube_payload(event, features))
        except Exception as exc:
            logger.warning("Jube evaluation failed: %s — using feature-based fallback", exc)
            return self._fallback_score(features), []

        score = float(result.get("score", 0.0))  # nosemgrep: banxe-float-money — non-monetary score
        factors = [
            RiskFactor(
                name=r.get("name", r.get("rule_id", "unknown")),
                weight=0.40,
                value=float(
                    r.get("score", 0.0)
                ),  # nosemgrep: banxe-float-money — non-monetary score
                contribution=float(r.get("score", 0.0))
                * 0.40,  # nosemgrep: banxe-float-money — non-monetary
                explanation=r.get("explanation", ""),
                regulation_ref=r.get("regulation_ref"),
            )
            for r in result.get("triggered_rules", [])
        ]
        return score, factors

    @staticmethod
    def _to_jube_payload(event: TransactionEvent, features: dict[str, float]) -> dict[str, Any]:
        return {
            "transaction_id": event.transaction_id,
            "amount": str(event.amount),
            "currency": event.currency,
            "sender_id": event.sender_id,
            "sender_jurisdiction": event.sender_jurisdiction,
            "transaction_type": event.transaction_type.value,
            "features": features,
        }

    @staticmethod
    def _fallback_score(
        features: dict[str, float],
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary fallback score
        """Compute rules score from features without Jube."""
        score = 0.0  # nosemgrep: banxe-float-money — non-monetary score init
        if features.get("jurisdiction_risk", 0) > 0.5:
            score += 0.4
        if features.get("velocity_24h", 0) > 0.7:
            score += 0.3
        if features.get("amount_deviation", 0) > 0.8:
            score += 0.2
        if features.get("round_amount", 0) > 0.5:
            score += 0.1
        return min(score, 1.0)  # nosemgrep: banxe-float-money — non-monetary
