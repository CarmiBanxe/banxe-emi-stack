"""
services/transaction_monitor/scoring/risk_scorer.py — Risk Scoring Pipeline
IL-RTM-01 | banxe-emi-stack

Aggregates rules (40%) + ML (30%) + velocity (30%) into a composite risk score.
All scores are non-monetary floats 0-1 (I-01 does not apply).
"""

from __future__ import annotations

import logging
from typing import Protocol, runtime_checkable

from services.transaction_monitor.config import get_config
from services.transaction_monitor.models.risk_score import (
    RiskFactor,
    RiskScore,
)
from services.transaction_monitor.models.transaction import TransactionEvent
from services.transaction_monitor.scoring.feature_extractor import (
    FeatureExtractor,
    InMemoryVelocityPort,
    VelocityPort,
)
from services.transaction_monitor.scoring.rule_engine import InMemoryJubePort, JubePort, RuleEngine
from services.transaction_monitor.scoring.velocity_tracker import (
    InMemoryVelocityTracker,
    VelocityTrackerPort,
)

logger = logging.getLogger("banxe.transaction_monitor.scorer")


# ── ML Model Port (Protocol DI) ────────────────────────────────────────────


@runtime_checkable
class MLModelPort(Protocol):
    """Interface for ML scoring model."""

    def score(self, features: dict[str, float]) -> float: ...  # returns 0-1


class InMemoryMLModel:
    """Test stub — simple weighted sum for deterministic scoring."""

    def score(
        self, features: dict[str, float]
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary score
        """Return a score based on key features — no external deps."""
        base = 0.2  # nosemgrep: banxe-float-money — non-monetary base score
        base += features.get("velocity_24h", 0) * 0.3
        base += features.get("amount_deviation", 0) * 0.25
        base += features.get("jurisdiction_risk", 0) * 0.3
        base += features.get("round_amount", 0) * 0.1
        base += features.get("crypto_flag", 0) * 0.05
        return min(base, 1.0)  # nosemgrep: banxe-float-money — non-monetary


class IsolationForestModel:
    """Production IsolationForest ML model (deferred import)."""

    def __init__(self, model_path: str | None = None) -> None:
        self._model_path = model_path or get_config().ml_model_path
        self._model = None

    def _load(self) -> None:
        if self._model is None:
            import joblib

            try:
                self._model = joblib.load(self._model_path)
            except FileNotFoundError:
                logger.warning("ML model not found at %s — using fallback", self._model_path)
                self._model = None

    def score(
        self, features: dict[str, float]
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary score
        self._load()
        if self._model is None:
            return InMemoryMLModel().score(features)
        import numpy as np

        feature_vector = np.array([[features.get(k, 0.0) for k in sorted(features)]])
        raw = self._model.decision_function(feature_vector)[0]
        # Convert isolation forest score (-1 to 1) to 0-1 (higher = more anomalous)
        normalised = max(
            0.0, min(1.0, (1.0 - raw) / 2.0)
        )  # nosemgrep: banxe-float-money — non-monetary normalisation
        return normalised


# ── Risk Scorer ────────────────────────────────────────────────────────────


class RiskScorer:
    """Composite risk scoring pipeline: rules (40%) + ML (30%) + velocity (30%).

    Weights from config. All scores are non-monetary floats 0-1.
    """

    def __init__(
        self,
        jube_port: JubePort | None = None,
        ml_model: MLModelPort | None = None,
        velocity_tracker: VelocityTrackerPort | None = None,
        velocity_port: VelocityPort | None = None,
    ) -> None:
        self._config = get_config()
        self._velocity_tracker = velocity_tracker or InMemoryVelocityTracker()
        self._rule_engine = RuleEngine(jube_port=jube_port or InMemoryJubePort())
        self._ml_model = ml_model or InMemoryMLModel()
        self._features = FeatureExtractor(velocity_port=velocity_port or InMemoryVelocityPort())

    def score(self, event: TransactionEvent) -> RiskScore:
        """Score a transaction event.

        Steps:
        1. Check hard-block jurisdictions (immediate CRITICAL)
        2. Extract 10 features
        3. Rules scoring via Jube (40%)
        4. ML scoring via IsolationForest (30%)
        5. Velocity scoring (30%)
        6. Weighted aggregate → classification
        7. Record in velocity tracker
        """
        # Step 1: Hard-block (I-02)
        if self._velocity_tracker.is_hard_blocked(event):
            factor = RiskFactor(
                name="jurisdiction_hard_block",
                weight=1.0,
                value=1.0,
                contribution=1.0,
                explanation=f"Hard-blocked jurisdiction detected (I-02). "
                f"Sender: {event.sender_jurisdiction}, "
                f"Receiver: {event.receiver_jurisdiction}",
                regulation_ref="MLR 2017 Reg.18 / Banxe I-02",
            )
            rs = RiskScore(
                score=1.0,
                classification="critical",
                factors=[factor],
                rules_score=1.0,
                ml_score=1.0,
                velocity_score=1.0,
            )
            self._velocity_tracker.record(event)
            return rs

        # Step 2: Extract features
        features = self._features.extract(event)

        # Step 3: Rules score
        rules_score, rule_factors = self._rule_engine.evaluate(event, features)

        # Step 4: ML score
        ml_score = self._ml_model.score(features)

        # Step 5: Velocity score
        velocity_score = self._compute_velocity_score(event, features)

        # Step 6: Weighted aggregate
        composite = (
            rules_score * self._config.rules_weight
            + ml_score * self._config.ml_weight
            + velocity_score * self._config.velocity_weight
        )
        composite = max(
            0.0, min(1.0, composite)
        )  # nosemgrep: banxe-float-money — non-monetary clamp

        # Step 7: Build velocity factor
        velocity_factor = RiskFactor(
            name="velocity_composite",
            weight=self._config.velocity_weight,
            value=velocity_score,
            contribution=velocity_score * self._config.velocity_weight,
            explanation=self._velocity_explanation(event, features),
            regulation_ref="EBA GL/2021/02 §4.2 — ongoing monitoring",
        )

        ml_factor = RiskFactor(
            name="ml_isolation_forest",
            weight=self._config.ml_weight,
            value=ml_score,
            contribution=ml_score * self._config.ml_weight,
            explanation=f"ML anomaly score: {ml_score:.2f} (IsolationForest v1)",
        )

        all_factors = rule_factors + [ml_factor, velocity_factor]
        all_factors.sort(key=lambda f: f.contribution, reverse=True)

        rs = RiskScore(
            score=composite,
            factors=all_factors,
            rules_score=rules_score,
            ml_score=ml_score,
            velocity_score=velocity_score,
        )

        # Step 7: Record in velocity tracker
        self._velocity_tracker.record(event)
        logger.info(
            "Scored transaction %s: %.2f (%s)",
            event.transaction_id,
            composite,
            rs.classification,
        )
        return rs

    def _compute_velocity_score(
        self, event: TransactionEvent, features: dict[str, float]
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary score
        """Velocity score from feature ratios."""
        v1h = features.get("velocity_1h", 0)
        v24h = features.get("velocity_24h", 0)
        return min((v1h * 0.4 + v24h * 0.6), 1.0)  # nosemgrep: banxe-float-money — non-monetary

    def _velocity_explanation(self, event: TransactionEvent, features: dict[str, float]) -> str:
        count_24h = self._velocity_tracker.get_count(event.sender_id, "24h")
        threshold = self._config.velocity_24h_threshold
        return (
            f"Transaction velocity: {count_24h} transactions in 24h "
            f"(threshold: {threshold}). "
            f"Velocity ratio: {features.get('velocity_24h', 0):.2f}."
        )
