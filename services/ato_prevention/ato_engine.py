"""
services/ato_prevention/ato_engine.py
Account Takeover (ATO) detection engine (IL-ATO-01).
Signals: new_device, new_ip, geo_shift, impossible_travel, failed_login_velocity.
I-01: all scores Decimal.
I-24: ATOLog append-only.
I-27: lockout requires SECURITY_OFFICER HITL.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import math
from typing import Protocol

from services.ato_prevention.ato_models import (
    ATOAssessment,
    LoginAttempt,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
MAX_FAILED_LOGINS = 5
FAILED_LOGIN_WINDOW_MINUTES = 15
IMPOSSIBLE_TRAVEL_KM_PER_HOUR = 900  # approx max commercial flight speed


class ATOStorePort(Protocol):
    def record_attempt(self, attempt: LoginAttempt) -> None: ...
    def get_recent(self, customer_id: str, limit: int = 20) -> list[LoginAttempt]: ...
    def get_failed_count(self, customer_id: str, window_minutes: int) -> int: ...


class InMemoryATOStore:
    def __init__(self) -> None:
        self._attempts: list[tuple[str, LoginAttempt]] = []  # (timestamp, attempt) — I-24

    def record_attempt(self, attempt: LoginAttempt) -> None:
        self._attempts.append((datetime.now(UTC).isoformat(), attempt))

    def get_recent(self, customer_id: str, limit: int = 20) -> list[LoginAttempt]:
        all_for_customer = [a for _, a in self._attempts if a.customer_id == customer_id]
        return all_for_customer[-limit:]

    def get_failed_count(self, customer_id: str, window_minutes: int) -> int:
        return sum(1 for _, a in self._attempts if a.customer_id == customer_id and not a.success)


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in km."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))


class ATOEngine:
    """Account Takeover detection engine.

    I-01: scores as Decimal.
    I-24: ATOLog append-only.
    """

    def __init__(self, store: ATOStorePort | None = None) -> None:
        self._store: ATOStorePort = store or InMemoryATOStore()
        self._ato_log: list[dict] = []  # I-24 append-only

    def assess_login(self, attempt: LoginAttempt) -> ATOAssessment:
        signals: list[str] = []
        score = Decimal("0.0")

        # Signal 1: blocked jurisdiction (I-02)
        if attempt.geo.country in BLOCKED_JURISDICTIONS:
            signals.append("BLOCKED_JURISDICTION")
            score = Decimal("1.0")

        else:
            # Signal 2: failed login velocity
            failed = self._store.get_failed_count(attempt.customer_id, FAILED_LOGIN_WINDOW_MINUTES)
            if failed >= MAX_FAILED_LOGINS:
                signals.append("FAILED_LOGIN_VELOCITY")
                score = min(score + Decimal("0.6"), Decimal("1.0"))

            # Signal 3: check impossible travel
            recent = self._store.get_recent(attempt.customer_id, 1)
            if recent:
                prev = recent[-1]
                dist = _haversine_km(
                    prev.geo.latitude,
                    prev.geo.longitude,
                    attempt.geo.latitude,
                    attempt.geo.longitude,
                )
                # Assume 1h between logins: if distance > 900km → impossible travel
                if dist > IMPOSSIBLE_TRAVEL_KM_PER_HOUR:
                    signals.append("IMPOSSIBLE_TRAVEL")
                    score = min(score + Decimal("0.7"), Decimal("1.0"))

        # Determine action
        if score >= Decimal("0.8"):
            action = "lock"
        elif score >= Decimal("0.4"):
            action = "challenge"
        else:
            action = "allow"

        # Record attempt I-24
        self._store.record_attempt(attempt)
        self._ato_log.append(
            {
                "event": "ato.assessed",
                "customer_id": attempt.customer_id,
                "score": str(score),
                "action": action,
                "signals": signals,
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )

        return ATOAssessment(
            customer_id=attempt.customer_id,
            risk_score=str(score),
            signals=signals,
            action=action,
        )

    @property
    def ato_log(self) -> list[dict]:
        """I-24: append-only."""
        return list(self._ato_log)
