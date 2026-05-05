"""
services/ato_prevention/velocity_checker.py
Velocity checks for ATO prevention (IL-FRAUD-02).

Tracks failed logins, IP rotation within time windows.
I-01: Decimal for risk scores.
I-24: All checks logged immutably.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from enum import Enum


class VelocityAction(str, Enum):
    """Action based on velocity check result."""

    ALLOW = "ALLOW"
    STEP_UP = "STEP_UP"
    LOCK = "LOCK"
    BLOCK = "BLOCK"


# Thresholds.
FAILED_LOGIN_STEP_UP_THRESHOLD: int = 3
FAILED_LOGIN_STEP_UP_WINDOW_MINUTES: int = 5
FAILED_LOGIN_LOCK_THRESHOLD: int = 10
FAILED_LOGIN_LOCK_WINDOW_MINUTES: int = 15
IP_ROTATION_THRESHOLD: int = 5
IP_ROTATION_WINDOW_MINUTES: int = 10


@dataclass(frozen=True)
class VelocityResult:
    """Immutable velocity check result (I-24)."""

    customer_id: str
    action: VelocityAction
    risk_score: Decimal  # I-01
    failed_count: int
    unique_ips: int
    reason: str
    checked_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not isinstance(self.risk_score, Decimal):
            raise TypeError(
                f"risk_score must be Decimal, got {type(self.risk_score).__name__} (I-01)"
            )


@dataclass
class LoginRecord:
    """A login attempt record for velocity tracking."""

    customer_id: str
    ip_address_hash: str
    success: bool
    timestamp: datetime


class VelocityChecker:
    """
    Velocity-based login anomaly detection.

    Checks:
    - Failed login velocity (>3 in 5min → STEP_UP, >10 in 15min → LOCK)
    - IP rotation (>5 unique IPs in 10min → HIGH risk)

    I-01: Decimal risk scores.
    I-24: Immutable audit log.
    """

    def __init__(self) -> None:
        self._records: list[LoginRecord] = []
        self._audit_log: list[VelocityResult] = []

    def record_attempt(
        self,
        customer_id: str,
        ip_address_hash: str,
        success: bool,
    ) -> None:
        """Record a login attempt."""
        self._records.append(
            LoginRecord(
                customer_id=customer_id,
                ip_address_hash=ip_address_hash,
                success=success,
                timestamp=datetime.now(UTC),
            )
        )

    def check(self, customer_id: str) -> VelocityResult:
        """Run velocity checks for a customer."""
        now = datetime.now(UTC)

        # Failed login count in step-up window (5 min).
        step_up_cutoff = now - timedelta(minutes=FAILED_LOGIN_STEP_UP_WINDOW_MINUTES)
        failed_step_up = sum(
            1
            for r in self._records
            if r.customer_id == customer_id and not r.success and r.timestamp >= step_up_cutoff
        )

        # Failed login count in lock window (15 min).
        lock_cutoff = now - timedelta(minutes=FAILED_LOGIN_LOCK_WINDOW_MINUTES)
        failed_lock = sum(
            1
            for r in self._records
            if r.customer_id == customer_id and not r.success and r.timestamp >= lock_cutoff
        )

        # Unique IPs in rotation window (10 min).
        ip_cutoff = now - timedelta(minutes=IP_ROTATION_WINDOW_MINUTES)
        recent_ips = {
            r.ip_address_hash
            for r in self._records
            if r.customer_id == customer_id and r.timestamp >= ip_cutoff
        }
        unique_ip_count = len(recent_ips)

        # Determine action and score.
        if failed_lock >= FAILED_LOGIN_LOCK_THRESHOLD:
            action = VelocityAction.LOCK
            score = Decimal("90")
            reason = (
                f"Brute force: {failed_lock} failed logins in {FAILED_LOGIN_LOCK_WINDOW_MINUTES}min"
            )
        elif unique_ip_count >= IP_ROTATION_THRESHOLD:
            action = VelocityAction.LOCK
            score = Decimal("80")
            reason = f"IP rotation: {unique_ip_count} unique IPs in {IP_ROTATION_WINDOW_MINUTES}min"
        elif failed_step_up >= FAILED_LOGIN_STEP_UP_THRESHOLD:
            action = VelocityAction.STEP_UP
            score = Decimal("50")
            reason = f"Velocity: {failed_step_up} failed logins in {FAILED_LOGIN_STEP_UP_WINDOW_MINUTES}min"
        else:
            action = VelocityAction.ALLOW
            score = Decimal("0")
            reason = "Normal activity"

        result = VelocityResult(
            customer_id=customer_id,
            action=action,
            risk_score=score,
            failed_count=failed_lock,
            unique_ips=unique_ip_count,
            reason=reason,
        )

        self._audit_log.append(result)
        return result

    @property
    def audit_log(self) -> list[VelocityResult]:
        return list(self._audit_log)
