"""
services/device_fingerprint/anomaly_detector.py
Anomaly detection for device fingerprinting (IL-FRAUD-01).

Detects: new device, location change, impossible travel.
I-01: Risk scores as Decimal.
I-02: Blocked jurisdictions → reject.
I-24: All checks logged immutably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum

BLOCKED_JURISDICTIONS: frozenset[str] = frozenset({
    "RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY",
})

# Impossible travel: same customer, different geo, < 1 hour apart.
IMPOSSIBLE_TRAVEL_WINDOW_MINUTES: int = 60


class RiskLevel(str, Enum):
    """Device risk level."""

    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True)
class AnomalyResult:
    """Immutable result of anomaly detection (I-24)."""

    customer_id: str
    device_id: str | None
    risk_level: RiskLevel
    risk_score: Decimal  # I-01
    anomalies: tuple[str, ...]
    geo_country: str
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not isinstance(self.risk_score, Decimal):
            raise TypeError(
                f"risk_score must be Decimal, got {type(self.risk_score).__name__} (I-01)"
            )


@dataclass(frozen=True)
class AnomalyAuditEntry:
    """Immutable audit entry for anomaly checks (I-24)."""

    customer_id: str
    action: str
    risk_level: RiskLevel
    risk_score: Decimal  # I-01
    details: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class JurisdictionBlockedError(ValueError):
    """Device from blocked jurisdiction (I-02)."""


class AnomalyDetector:
    """
    Detects device anomalies: new device, geo change, impossible travel.

    I-01: Decimal risk scores.
    I-02: Blocked jurisdictions → reject.
    I-24: Immutable audit log.
    """

    def __init__(self) -> None:
        self._audit_log: list[AnomalyAuditEntry] = []

    def check(
        self,
        customer_id: str,
        device_id: str | None,
        geo_country: str,
        is_known_device: bool,
        previous_sessions: list[dict[str, str]] | None = None,
    ) -> AnomalyResult:
        """
        Run anomaly detection.

        previous_sessions: list of dicts with 'geo_country' and 'timestamp' keys.
        """
        # I-02: blocked jurisdiction check.
        if geo_country.upper() in BLOCKED_JURISDICTIONS:
            raise JurisdictionBlockedError(
                f"Device from blocked jurisdiction {geo_country!r} (I-02)."
            )

        anomalies: list[str] = []
        score = Decimal("0")

        # New device detection.
        if not is_known_device:
            anomalies.append("NEW_DEVICE")
            score += Decimal("30")

        # Location change detection.
        if previous_sessions:
            last_geo = previous_sessions[-1].get("geo_country", "")
            if last_geo and last_geo.upper() != geo_country.upper():
                anomalies.append("LOCATION_CHANGE")
                score += Decimal("20")

                # Impossible travel detection.
                last_ts = previous_sessions[-1].get("timestamp", "")
                if last_ts:
                    try:
                        last_time = datetime.fromisoformat(last_ts)
                        now = datetime.now(UTC)
                        delta_minutes = (now - last_time).total_seconds() / 60
                        if delta_minutes < IMPOSSIBLE_TRAVEL_WINDOW_MINUTES:
                            anomalies.append("IMPOSSIBLE_TRAVEL")
                            score += Decimal("40")
                    except (ValueError, TypeError):
                        pass

        # Determine risk level.
        if score >= Decimal("70"):
            risk_level = RiskLevel.CRITICAL
        elif score >= Decimal("40"):
            risk_level = RiskLevel.HIGH
        elif score >= Decimal("20"):
            risk_level = RiskLevel.MEDIUM
        else:
            risk_level = RiskLevel.LOW

        result = AnomalyResult(
            customer_id=customer_id,
            device_id=device_id,
            risk_level=risk_level,
            risk_score=score,
            anomalies=tuple(anomalies),
            geo_country=geo_country.upper(),
        )

        # I-24: audit log.
        self._audit_log.append(
            AnomalyAuditEntry(
                customer_id=customer_id,
                action="ANOMALY_CHECK",
                risk_level=risk_level,
                risk_score=score,
                details=f"anomalies={','.join(anomalies) or 'none'}, geo={geo_country.upper()}",
            )
        )

        return result

    @property
    def audit_log(self) -> list[AnomalyAuditEntry]:
        return list(self._audit_log)
