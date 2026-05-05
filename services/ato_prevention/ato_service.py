"""
services/ato_prevention/ato_service.py
ATOPreventionService — velocity checks + session anomaly response (IL-FRAUD-02).

Orchestrates velocity checking, session management, and HITL escalation.
I-01: Decimal risk scores.
I-02: Blocked jurisdictions → BLOCK.
I-24: Immutable audit trail.
I-27: Account lock → HITL notification.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Protocol

from services.ato_prevention.session_manager import (
    InMemorySessionManager,
    SessionManagerPort,
    SessionState,
)
from services.ato_prevention.velocity_checker import (
    VelocityAction,
    VelocityChecker,
)

BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {
        "RU",
        "BY",
        "IR",
        "KP",
        "CU",
        "MM",
        "AF",
        "VE",
        "SY",
    }
)


# ── Result types ─────────────────────────────────────────────────────────────


class SessionAction(str):
    """Session action constants."""

    ALLOW = "ALLOW"
    STEP_UP = "STEP_UP"
    LOCK = "LOCK"
    BLOCK = "BLOCK"


@dataclass(frozen=True)
class ATOResult:
    """Immutable ATO assessment result (I-24)."""

    customer_id: str
    session_id: str
    action: str  # ALLOW / STEP_UP / LOCK / BLOCK
    risk_score: Decimal  # I-01
    reason: str
    ip_hash: str
    geo_country: str
    assessed_at: str = field(default_factory=lambda: datetime.now(UTC).isoformat())

    def __post_init__(self) -> None:
        if not isinstance(self.risk_score, Decimal):
            raise TypeError(
                f"risk_score must be Decimal, got {type(self.risk_score).__name__} (I-01)"
            )


@dataclass(frozen=True)
class ATOHITLProposal:
    """Account lock requires HITL escalation (I-27)."""

    customer_id: str
    session_id: str
    risk_score: str  # Decimal as string
    reason: str
    requires_approval_from: str = "SECURITY_OFFICER"


# ── Audit Port ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class ATOAuditEntry:
    """Immutable audit entry for ATO checks (I-24)."""

    customer_id: str
    action: str
    risk_score: str
    session_action: str
    ip_hash: str
    geo_country: str
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class ATOAuditPort(Protocol):
    """Port for recording ATO audit entries (I-24)."""

    def record(self, entry: ATOAuditEntry) -> None: ...


class InMemoryATOAuditPort:
    """In-memory audit for tests."""

    def __init__(self) -> None:
        self._entries: list[ATOAuditEntry] = []

    def record(self, entry: ATOAuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[ATOAuditEntry]:
        return list(self._entries)


# ── ATO Prevention Service ───────────────────────────────────────────────────


class ATOPreventionService:
    """
    Account Takeover Prevention Service.

    Orchestrates velocity checking, session management, HITL escalation.
    I-01: Decimal risk scores.
    I-02: Blocked jurisdictions → immediate BLOCK.
    I-24: Every assessment logged.
    I-27: LOCK actions → HITL proposal for SECURITY_OFFICER.
    """

    def __init__(
        self,
        velocity: VelocityChecker | None = None,
        sessions: SessionManagerPort | None = None,
        audit: ATOAuditPort | None = None,
    ) -> None:
        self._velocity = velocity or VelocityChecker()
        self._sessions: SessionManagerPort = sessions or InMemorySessionManager()
        self._audit: ATOAuditPort = audit or InMemoryATOAuditPort()

    def assess_login(
        self,
        customer_id: str,
        session_id: str,
        ip_address: str,
        geo_country: str,
        login_success: bool,
    ) -> ATOResult | ATOHITLProposal:
        """
        Assess a login attempt for ATO risk.

        Returns ATOResult for ALLOW/STEP_UP.
        Returns ATOHITLProposal for LOCK/BLOCK (I-27).
        """
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]

        # I-02: blocked jurisdiction → immediate BLOCK.
        if geo_country.upper() in BLOCKED_JURISDICTIONS:
            result = ATOResult(
                customer_id=customer_id,
                session_id=session_id,
                action=SessionAction.BLOCK,
                risk_score=Decimal("100"),
                reason=f"Login from blocked jurisdiction {geo_country.upper()} (I-02)",
                ip_hash=ip_hash,
                geo_country=geo_country.upper(),
            )
            self._sessions.set_state(session_id, customer_id, SessionState.BLOCKED, result.reason)
            self._record_audit(result)
            return ATOHITLProposal(
                customer_id=customer_id,
                session_id=session_id,
                risk_score=str(result.risk_score),
                reason=result.reason,
            )

        # Record attempt in velocity checker.
        self._velocity.record_attempt(customer_id, ip_hash, login_success)

        # Run velocity check.
        vel_result = self._velocity.check(customer_id)

        # Map velocity action to session action.
        if vel_result.action == VelocityAction.LOCK:
            session_action = SessionAction.LOCK
            session_state = SessionState.LOCKED
        elif vel_result.action == VelocityAction.STEP_UP:
            session_action = SessionAction.STEP_UP
            session_state = SessionState.STEP_UP_REQUIRED
        else:
            session_action = SessionAction.ALLOW
            session_state = SessionState.ACTIVE

        # Update session state.
        self._sessions.set_state(session_id, customer_id, session_state, vel_result.reason)

        result = ATOResult(
            customer_id=customer_id,
            session_id=session_id,
            action=session_action,
            risk_score=vel_result.risk_score,
            reason=vel_result.reason,
            ip_hash=ip_hash,
            geo_country=geo_country.upper(),
        )

        self._record_audit(result)

        # I-27: LOCK → HITL escalation.
        if session_action == SessionAction.LOCK:
            return ATOHITLProposal(
                customer_id=customer_id,
                session_id=session_id,
                risk_score=str(vel_result.risk_score),
                reason=vel_result.reason,
            )

        return result

    def _record_audit(self, result: ATOResult) -> None:
        entry = ATOAuditEntry(
            customer_id=result.customer_id,
            action="ATO_ASSESSMENT",
            risk_score=str(result.risk_score),
            session_action=result.action,
            ip_hash=result.ip_hash,
            geo_country=result.geo_country,
        )
        self._audit.record(entry)
