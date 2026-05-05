"""
tests/test_ato_prevention.py
Tests for ATOPreventionService + VelocityChecker (IL-FRAUD-02).

Acceptance criteria:
- test_ato_normal_login_allowed
- test_ato_velocity_exceeded_step_up
- test_ato_brute_force_lock
- test_ato_ip_rotation_detection
- test_ato_blocked_jurisdiction_login (I-02)
- test_ato_hitl_escalation_on_lock (I-27)
- test_ato_audit_trail (I-24)
- test_ato_decimal_risk_scores (I-01)
"""

from decimal import Decimal

import pytest

from services.ato_prevention.ato_service import (
    ATOHITLProposal,
    ATOPreventionService,
    ATOResult,
    InMemoryATOAuditPort,
    SessionAction,
)
from services.ato_prevention.session_manager import (
    InMemorySessionManager,
    SessionEvent,
    SessionState,
)
from services.ato_prevention.velocity_checker import (
    VelocityAction,
    VelocityChecker,
    VelocityResult,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def velocity():
    return VelocityChecker()


@pytest.fixture
def sessions():
    return InMemorySessionManager()


@pytest.fixture
def audit():
    return InMemoryATOAuditPort()


@pytest.fixture
def service(velocity, sessions, audit):
    return ATOPreventionService(velocity=velocity, sessions=sessions, audit=audit)


# ── Normal Login Tests ───────────────────────────────────────────────────────


class TestNormalLogin:
    def test_ato_normal_login_allowed(self, service):
        """AC: single login = ALLOW."""
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=True,
        )
        assert isinstance(result, ATOResult)
        assert result.action == SessionAction.ALLOW
        assert result.risk_score == Decimal("0")

    def test_successful_login_sets_active(self, service, sessions):
        """Successful login sets session to ACTIVE."""
        service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=True,
        )
        assert sessions.get_state("sess-001") == SessionState.ACTIVE

    def test_decimal_risk_scores(self, service):
        """AC: risk scores as Decimal (I-01)."""
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=True,
        )
        assert isinstance(result.risk_score, Decimal)


# ── Velocity Step-Up Tests ───────────────────────────────────────────────────


class TestVelocityStepUp:
    def test_ato_velocity_exceeded_step_up(self, service):
        """AC: >3 failed in 5min = STEP_UP auth."""
        for i in range(3):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
                login_success=False,
            )
        # 4th attempt triggers step-up.
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-final",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=False,
        )
        assert isinstance(result, ATOResult)
        assert result.action == SessionAction.STEP_UP

    def test_step_up_sets_session_state(self, service, sessions):
        """Step-up sets session to STEP_UP_REQUIRED."""
        for i in range(4):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
                login_success=False,
            )
        assert sessions.get_state("sess-3") == SessionState.STEP_UP_REQUIRED


# ── Brute Force Lock Tests ───────────────────────────────────────────────────


class TestBruteForceLock:
    def test_ato_brute_force_lock(self, service):
        """AC: >10 failed in 15min = LOCK account."""
        for i in range(10):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
                login_success=False,
            )
        # 11th triggers lock → HITL.
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-lock",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=False,
        )
        assert isinstance(result, ATOHITLProposal)
        assert result.requires_approval_from == "SECURITY_OFFICER"

    def test_lock_sets_session_state(self, service, sessions):
        """Lock sets session to LOCKED."""
        for i in range(11):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
                login_success=False,
            )
        assert sessions.get_state("sess-10") == SessionState.LOCKED


# ── IP Rotation Tests ────────────────────────────────────────────────────────


class TestIPRotation:
    def test_ato_ip_rotation_detection(self, service):
        """AC: >5 different IPs in 10min = high risk → HITL."""
        for i in range(5):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address=f"10.0.0.{i}",
                geo_country="GB",
                login_success=True,
            )
        # 6th IP triggers lock.
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-final",
            ip_address="10.0.0.99",
            geo_country="GB",
            login_success=True,
        )
        assert isinstance(result, ATOHITLProposal)


# ── Blocked Jurisdiction Tests ───────────────────────────────────────────────


class TestBlockedJurisdiction:
    def test_ato_blocked_jurisdiction_login_ru(self, service):
        """AC: login from RU → BLOCK + HITL (I-02)."""
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="RU",
            login_success=True,
        )
        assert isinstance(result, ATOHITLProposal)
        assert "blocked jurisdiction" in result.reason.lower()

    def test_blocked_jurisdiction_ir(self, service):
        """IR → BLOCK (I-02)."""
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="IR",
            login_success=True,
        )
        assert isinstance(result, ATOHITLProposal)

    def test_blocked_jurisdiction_sets_blocked_state(self, service, sessions):
        """Blocked jurisdiction sets session to BLOCKED."""
        service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="KP",
            login_success=True,
        )
        assert sessions.get_state("sess-001") == SessionState.BLOCKED

    def test_blocked_jurisdiction_case_insensitive(self, service):
        """Case-insensitive check."""
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="ru",
            login_success=True,
        )
        assert isinstance(result, ATOHITLProposal)


# ── HITL Escalation Tests ────────────────────────────────────────────────────


class TestHITLEscalation:
    def test_ato_hitl_escalation_on_lock(self, service):
        """AC: account lock → HITL notification (I-27)."""
        for i in range(11):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
                login_success=False,
            )
        result = service.assess_login(
            customer_id="cust-001",
            session_id="sess-hitl",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=False,
        )
        assert isinstance(result, ATOHITLProposal)
        assert result.requires_approval_from == "SECURITY_OFFICER"
        assert result.customer_id == "cust-001"

    def test_hitl_proposal_immutable(self):
        """ATOHITLProposal is frozen (I-24)."""
        proposal = ATOHITLProposal(
            customer_id="c-001",
            session_id="s-001",
            risk_score="90",
            reason="test",
        )
        with pytest.raises(AttributeError):
            proposal.reason = "modified"  # type: ignore[misc]


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_ato_audit_trail(self, service, audit):
        """AC: all decisions logged (I-24)."""
        service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
            login_success=True,
        )
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.customer_id == "cust-001"
        assert entry.action == "ATO_ASSESSMENT"
        assert entry.geo_country == "GB"

    def test_audit_no_raw_ip(self, service, audit):
        """No raw IP in audit — hash only."""
        service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="192.168.1.100",
            geo_country="GB",
            login_success=True,
        )
        entry = audit.entries[0]
        assert "192.168.1.100" not in entry.ip_hash

    def test_multiple_assessments_produce_entries(self, service, audit):
        """Each assessment produces an audit entry."""
        for i in range(3):
            service.assess_login(
                customer_id="cust-001",
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
                login_success=True,
            )
        assert len(audit.entries) == 3

    def test_blocked_jurisdiction_audited(self, service, audit):
        """Blocked jurisdiction assessment also audited."""
        service.assess_login(
            customer_id="cust-001",
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="RU",
            login_success=True,
        )
        assert len(audit.entries) == 1
        assert audit.entries[0].session_action == SessionAction.BLOCK


# ── Velocity Checker Unit Tests ──────────────────────────────────────────────


class TestVelocityChecker:
    def test_no_activity_allows(self, velocity):
        """No activity → ALLOW."""
        result = velocity.check("cust-001")
        assert result.action == VelocityAction.ALLOW
        assert result.risk_score == Decimal("0")

    def test_velocity_result_decimal(self, velocity):
        """VelocityResult risk_score is Decimal (I-01)."""
        result = velocity.check("cust-001")
        assert isinstance(result.risk_score, Decimal)

    def test_velocity_result_immutable(self, velocity):
        """VelocityResult is frozen (I-24)."""
        result = velocity.check("cust-001")
        with pytest.raises(AttributeError):
            result.action = VelocityAction.LOCK  # type: ignore[misc]

    def test_velocity_result_rejects_float(self):
        """VelocityResult rejects float score (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            VelocityResult(
                customer_id="c-001",
                action=VelocityAction.ALLOW,
                risk_score=0.5,  # type: ignore[arg-type]
                failed_count=0,
                unique_ips=0,
                reason="test",
            )

    def test_velocity_audit_log(self, velocity):
        """Velocity checker maintains audit log."""
        velocity.check("cust-001")
        assert len(velocity.audit_log) == 1


# ── Session Manager Tests ────────────────────────────────────────────────────


class TestSessionManager:
    def test_session_state_tracking(self, sessions):
        """Session state transitions tracked."""
        sessions.set_state("s-001", "c-001", SessionState.ACTIVE, "login")
        assert sessions.get_state("s-001") == SessionState.ACTIVE

    def test_session_events_recorded(self, sessions):
        """Session events recorded (I-24)."""
        sessions.set_state("s-001", "c-001", SessionState.ACTIVE, "login")
        sessions.set_state("s-001", "c-001", SessionState.LOCKED, "brute force")
        events = sessions.get_events("c-001")
        assert len(events) == 2
        assert events[1].old_state == SessionState.ACTIVE
        assert events[1].new_state == SessionState.LOCKED

    def test_session_event_immutable(self):
        """SessionEvent is frozen (I-24)."""
        event = SessionEvent(
            session_id="s-001",
            customer_id="c-001",
            old_state=None,
            new_state=SessionState.ACTIVE,
            reason="test",
        )
        with pytest.raises(AttributeError):
            event.reason = "modified"  # type: ignore[misc]

    def test_unknown_session_returns_none(self, sessions):
        """Unknown session returns None."""
        assert sessions.get_state("nonexistent") is None
