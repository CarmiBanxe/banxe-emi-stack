"""
services/transaction_monitor/scoring/feature_extractor.py — Feature Extractor
IL-RTM-01 | banxe-emi-stack

Extracts 10 AML features from a TransactionEvent for ML scoring and rules.
All features are non-monetary floats (0-1 normalised or counts).
"""

from __future__ import annotations

import logging
from decimal import Decimal
from typing import Protocol, runtime_checkable

from services.transaction_monitor.config import get_config
from services.transaction_monitor.models.transaction import TransactionEvent

logger = logging.getLogger("banxe.transaction_monitor.features")


# ── Velocity port (Protocol DI) ────────────────────────────────────────────


@runtime_checkable
class VelocityPort(Protocol):
    """Interface for velocity counter reads (injected, no direct Redis dep)."""

    def get_count(self, customer_id: str, window: str) -> int: ...
    def get_cumulative_amount(self, customer_id: str, window: str) -> Decimal: ...


class InMemoryVelocityPort:
    """Test stub — returns deterministic low velocity counts."""

    def get_count(self, customer_id: str, window: str) -> int:
        return 3  # Low velocity for most tests

    def get_cumulative_amount(self, customer_id: str, window: str) -> Decimal:
        return Decimal("2500.00")


# ── Feature Extractor ──────────────────────────────────────────────────────


class FeatureExtractor:
    """Extracts 10 AML risk features from a TransactionEvent.

    Feature names and weights are aligned with the scoring pipeline.
    All feature values are non-monetary floats (0-1 or counts).
    """

    def __init__(self, velocity_port: VelocityPort | None = None) -> None:
        self._velocity = velocity_port or InMemoryVelocityPort()
        self._config = get_config()

    def extract(self, event: TransactionEvent) -> dict[str, float]:
        """Extract all 10 features. Returns a flat dict.

        Feature values are non-monetary floats — Semgrep banxe-float-money
        does not apply here (these are rates/indicators, not monetary amounts).
        """
        return {
            "velocity_1h": self._velocity_feature(event.sender_id, "1h"),
            "velocity_24h": self._velocity_feature(event.sender_id, "24h"),
            "amount_deviation": self._amount_deviation(event),
            "jurisdiction_risk": self._jurisdiction_risk(event),
            "new_counterparty": self._new_counterparty(event),
            "round_amount": self._round_amount(event),
            "time_anomaly": self._time_anomaly(event),
            "crypto_flag": self._crypto_flag(event),
            "cross_border": self._cross_border(event),
            "pep_proximity": self._pep_proximity(event),
        }

    # ── Individual feature computations ───────────────────────────────────

    def _velocity_feature(
        self, customer_id: str, window: str
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary rate
        """Velocity ratio: actual count / threshold (capped at 1.0)."""
        count = self._velocity.get_count(customer_id, window)
        threshold = (
            self._config.velocity_1h_threshold
            if window == "1h"
            else self._config.velocity_24h_threshold
        )
        ratio = count / max(threshold, 1)
        return min(ratio, 1.0)  # nosemgrep: banxe-float-money — non-monetary ratio

    def _amount_deviation(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary deviation score
        """How many times above the customer's average (normalised to 0-1)."""
        avg = event.customer_avg_amount
        if avg is None or avg == 0:
            return 0.3  # nosemgrep: banxe-float-money — neutral default score
        deviation = float(event.amount) / float(
            avg
        )  # nosemgrep: banxe-float-money — non-monetary ratio
        return min(
            deviation / self._config.amount_deviation_threshold, 1.0
        )  # nosemgrep: banxe-float-money — non-monetary

    def _jurisdiction_risk(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary risk score
        """1.0 if hard-blocked, 0.7 if greylist, 0.0 otherwise."""
        jurisdictions = {j for j in [event.sender_jurisdiction, event.receiver_jurisdiction] if j}
        if jurisdictions & self._config.blocked_jurisdictions:
            return 1.0  # nosemgrep: banxe-float-money — non-monetary score
        if jurisdictions & self._config.greylist_jurisdictions:
            return 0.7  # nosemgrep: banxe-float-money — non-monetary score
        return 0.0  # nosemgrep: banxe-float-money — non-monetary score

    def _new_counterparty(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary flag
        """1.0 if first-time counterparty (from metadata), else 0.0."""
        return (
            1.0 if event.metadata.get("first_time_receiver") else 0.0
        )  # nosemgrep: banxe-float-money — binary flag

    def _round_amount(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary structuring flag
        """1.0 if amount is a round number (structuring pattern detection)."""
        modulus = self._config.round_amount_modulus
        amount_int = int(event.amount)
        return (
            1.0 if (amount_int > 0 and amount_int % modulus == 0) else 0.0
        )  # nosemgrep: banxe-float-money — binary flag

    def _time_anomaly(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary anomaly score
        """0.8 if transaction is between 00:00–05:00 UTC (unusual hours)."""
        hour = event.timestamp.hour
        return 0.8 if 0 <= hour < 5 else 0.0  # nosemgrep: banxe-float-money — non-monetary score

    def _crypto_flag(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — binary flag
        """1.0 if crypto on/off ramp transaction."""
        from services.transaction_monitor.models.transaction import TransactionType

        crypto_types = {TransactionType.CRYPTO_ONRAMP, TransactionType.CRYPTO_OFFRAMP}
        return (
            1.0 if event.transaction_type in crypto_types else 0.0
        )  # nosemgrep: banxe-float-money — binary flag

    def _cross_border(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — binary flag
        """1.0 if sender and receiver jurisdictions differ."""
        if event.receiver_jurisdiction is None:
            return 0.0  # nosemgrep: banxe-float-money — binary flag
        return (
            1.0 if event.sender_jurisdiction != event.receiver_jurisdiction else 0.0
        )  # nosemgrep: banxe-float-money — binary flag

    def _pep_proximity(
        self, event: TransactionEvent
    ) -> float:  # nosemgrep: banxe-float-money — non-monetary proximity score
        """0.9 if transaction metadata indicates PEP connection."""
        return (
            0.9 if event.metadata.get("pep_connection") else 0.0
        )  # nosemgrep: banxe-float-money — non-monetary score
