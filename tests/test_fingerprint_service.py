"""
tests/test_fingerprint_service.py
Tests for FingerprintService + AnomalyDetector (IL-FRAUD-01).

Acceptance criteria:
- test_fingerprint_session_binding
- test_fingerprint_known_device_low_risk
- test_fingerprint_new_device_medium_risk
- test_fingerprint_impossible_travel_high_risk
- test_fingerprint_blocked_jurisdiction_device (I-02)
- test_fingerprint_audit_trail (I-24)
- test_fingerprint_no_pii_in_logs
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from services.device_fingerprint.anomaly_detector import (
    AnomalyDetector,
    AnomalyResult,
    JurisdictionBlockedError,
    RiskLevel,
)
from services.device_fingerprint.fingerprint_engine import (
    FingerprintEngine,
    InMemoryDeviceStore,
)
from services.device_fingerprint.fingerprint_models import FingerprintData
from services.device_fingerprint.fingerprint_service import (
    FingerprintHITLProposal,
    FingerprintService,
    InMemoryFingerprintAuditPort,
)
from services.device_fingerprint.fingerprint_store import (
    InMemoryFingerprintStore,
    SessionBinding,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def device_store():
    return InMemoryDeviceStore()


@pytest.fixture
def session_store():
    return InMemoryFingerprintStore()


@pytest.fixture
def audit():
    return InMemoryFingerprintAuditPort()


@pytest.fixture
def engine(device_store):
    return FingerprintEngine(store=device_store)


@pytest.fixture
def anomaly_detector():
    return AnomalyDetector()


@pytest.fixture
def service(engine, session_store, anomaly_detector, audit):
    return FingerprintService(
        engine=engine,
        store=session_store,
        anomaly_detector=anomaly_detector,
        audit=audit,
    )


def _fp_data(ua: str = "Mozilla/5.0 Chrome/120") -> FingerprintData:
    return FingerprintData(user_agent=ua)


# ── Session Binding Tests ────────────────────────────────────────────────────


class TestSessionBinding:
    def test_fingerprint_session_binding(self, service, session_store):
        """AC: device → session association created."""
        service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data(),
            session_id="sess-001",
            ip_address="192.168.1.1",
            geo_country="GB",
        )
        bindings = session_store.get_session_bindings("cust-001")
        assert len(bindings) == 1
        assert bindings[0].session_id == "sess-001"
        assert bindings[0].customer_id == "cust-001"
        assert bindings[0].geo_country == "GB"

    def test_multiple_sessions_bound(self, service, session_store):
        """Multiple sessions create multiple bindings."""
        for i in range(3):
            service.check_device(
                customer_id="cust-001",
                fingerprint_data=_fp_data(),
                session_id=f"sess-{i}",
                ip_address="192.168.1.1",
                geo_country="GB",
            )
        assert len(session_store.get_session_bindings("cust-001")) == 3

    def test_session_binding_immutable(self):
        """SessionBinding is frozen (I-24)."""
        binding = SessionBinding(
            session_id="s-001",
            device_id="d-001",
            customer_id="c-001",
            ip_address_hash="abc123",
            geo_country="GB",
        )
        with pytest.raises(AttributeError):
            binding.session_id = "modified"  # type: ignore[misc]


# ── Known Device Tests ───────────────────────────────────────────────────────


class TestKnownDevice:
    def test_fingerprint_known_device_low_risk(self, service):
        """AC: returning device = low risk."""
        # First check registers the device.
        service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data(),
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
        )
        # Second check recognizes it.
        result = service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data(),
            session_id="sess-002",
            ip_address="1.2.3.4",
            geo_country="GB",
        )
        assert isinstance(result, AnomalyResult)
        assert result.risk_level == RiskLevel.LOW
        assert result.risk_score == Decimal("0")


# ── New Device Tests ─────────────────────────────────────────────────────────


class TestNewDevice:
    def test_fingerprint_new_device_medium_risk(self, service):
        """AC: unknown device = medium risk + alert."""
        result = service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data("Firefox/119"),
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
        )
        assert isinstance(result, AnomalyResult)
        assert result.risk_level == RiskLevel.MEDIUM
        assert "NEW_DEVICE" in result.anomalies
        assert result.risk_score == Decimal("30")

    def test_new_device_registered(self, service, device_store):
        """New device is auto-registered."""
        service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data("Safari/17"),
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
        )
        devices = device_store.get_by_customer("cust-001")
        assert len(devices) == 1


# ── Impossible Travel Tests ──────────────────────────────────────────────────


class TestImpossibleTravel:
    def test_fingerprint_impossible_travel_high_risk(self, service, session_store):
        """AC: 2 logins < 1h, different geo = high risk → HITL."""
        # Plant a recent session from GB.
        recent_time = (datetime.now(UTC) - timedelta(minutes=30)).isoformat()
        session_store.save_session_binding(
            SessionBinding(
                session_id="sess-prev",
                device_id="dev-001",
                customer_id="cust-001",
                ip_address_hash="hash1",
                geo_country="GB",
                bound_at=recent_time,
            )
        )
        # New login from US — impossible travel.
        result = service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data("Chrome/121"),
            session_id="sess-new",
            ip_address="5.6.7.8",
            geo_country="US",
        )
        # Should be HITL due to HIGH/CRITICAL risk.
        assert isinstance(result, FingerprintHITLProposal)
        assert "IMPOSSIBLE_TRAVEL" in result.anomalies
        assert result.requires_approval_from == "FRAUD_ANALYST"

    def test_location_change_no_impossible_travel(self, service, session_store):
        """Location change > 1h is flagged but not impossible travel."""
        old_time = (datetime.now(UTC) - timedelta(hours=3)).isoformat()
        session_store.save_session_binding(
            SessionBinding(
                session_id="sess-prev",
                device_id="dev-001",
                customer_id="cust-001",
                ip_address_hash="hash1",
                geo_country="GB",
                bound_at=old_time,
            )
        )
        result = service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data("Chrome/121"),
            session_id="sess-new",
            ip_address="5.6.7.8",
            geo_country="DE",
        )
        # New device + location change = HIGH → HITL.
        assert isinstance(result, FingerprintHITLProposal)
        assert "LOCATION_CHANGE" in result.anomalies
        assert "IMPOSSIBLE_TRAVEL" not in result.anomalies


# ── Blocked Jurisdiction Tests ───────────────────────────────────────────────


class TestBlockedJurisdiction:
    def test_fingerprint_blocked_jurisdiction_device_ru(self, service):
        """AC: device from RU → reject (I-02)."""
        with pytest.raises(JurisdictionBlockedError, match="blocked"):
            service.check_device(
                customer_id="cust-001",
                fingerprint_data=_fp_data(),
                session_id="sess-001",
                ip_address="1.2.3.4",
                geo_country="RU",
            )

    def test_fingerprint_blocked_jurisdiction_ir(self, service):
        """Device from IR → reject (I-02)."""
        with pytest.raises(JurisdictionBlockedError):
            service.check_device(
                customer_id="cust-001",
                fingerprint_data=_fp_data(),
                session_id="sess-001",
                ip_address="1.2.3.4",
                geo_country="IR",
            )

    def test_fingerprint_blocked_jurisdiction_kp(self, service):
        """Device from KP → reject (I-02)."""
        with pytest.raises(JurisdictionBlockedError):
            service.check_device(
                customer_id="cust-001",
                fingerprint_data=_fp_data(),
                session_id="sess-001",
                ip_address="1.2.3.4",
                geo_country="KP",
            )

    def test_blocked_jurisdiction_case_insensitive(self, service):
        """Case-insensitive jurisdiction check."""
        with pytest.raises(JurisdictionBlockedError):
            service.check_device(
                customer_id="cust-001",
                fingerprint_data=_fp_data(),
                session_id="sess-001",
                ip_address="1.2.3.4",
                geo_country="ru",
            )


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_fingerprint_audit_trail(self, service, audit):
        """AC: all checks logged immutably (I-24)."""
        service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data(),
            session_id="sess-001",
            ip_address="1.2.3.4",
            geo_country="GB",
        )
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.customer_id == "cust-001"
        assert entry.action == "DEVICE_CHECK"
        assert entry.geo_country == "GB"

    def test_fingerprint_no_pii_in_logs(self, service, audit):
        """AC: no raw IP in audit — hash only."""
        service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data(),
            session_id="sess-001",
            ip_address="192.168.1.100",
            geo_country="GB",
        )
        entry = audit.entries[0]
        # IP hash should NOT contain the raw IP.
        assert "192.168.1.100" not in entry.ip_hash
        assert len(entry.ip_hash) == 16  # SHA256 truncated to 16 chars

    def test_audit_entry_immutable(self):
        """FingerprintAuditEntry is frozen."""
        from services.device_fingerprint.fingerprint_service import (
            FingerprintAuditEntry,
        )

        entry = FingerprintAuditEntry(
            customer_id="c-001",
            action="TEST",
            device_id=None,
            risk_level="LOW",
            risk_score="0",
            geo_country="GB",
            ip_hash="abc",
        )
        with pytest.raises(AttributeError):
            entry.action = "MODIFIED"  # type: ignore[misc]

    def test_multiple_checks_produce_multiple_entries(self, service, audit):
        """Each check produces an audit entry."""
        for i in range(3):
            service.check_device(
                customer_id="cust-001",
                fingerprint_data=_fp_data(),
                session_id=f"sess-{i}",
                ip_address="1.2.3.4",
                geo_country="GB",
            )
        assert len(audit.entries) == 3


# ── Anomaly Detector Unit Tests ──────────────────────────────────────────────


class TestAnomalyDetector:
    def test_known_device_no_anomalies(self, anomaly_detector):
        """Known device, same geo = LOW risk."""
        result = anomaly_detector.check(
            customer_id="c-001",
            device_id="d-001",
            geo_country="GB",
            is_known_device=True,
        )
        assert result.risk_level == RiskLevel.LOW
        assert result.risk_score == Decimal("0")
        assert len(result.anomalies) == 0

    def test_new_device_anomaly(self, anomaly_detector):
        """New device → MEDIUM risk."""
        result = anomaly_detector.check(
            customer_id="c-001",
            device_id=None,
            geo_country="GB",
            is_known_device=False,
        )
        assert result.risk_level == RiskLevel.MEDIUM
        assert "NEW_DEVICE" in result.anomalies
        assert result.risk_score == Decimal("30")

    def test_risk_score_decimal_type(self, anomaly_detector):
        """AC: risk scores as Decimal (I-01)."""
        result = anomaly_detector.check(
            customer_id="c-001",
            device_id=None,
            geo_country="GB",
            is_known_device=False,
        )
        assert isinstance(result.risk_score, Decimal)

    def test_anomaly_result_immutable(self, anomaly_detector):
        """AnomalyResult is frozen (I-24)."""
        result = anomaly_detector.check(
            customer_id="c-001",
            device_id="d-001",
            geo_country="GB",
            is_known_device=True,
        )
        with pytest.raises(AttributeError):
            result.risk_level = RiskLevel.HIGH  # type: ignore[misc]

    def test_anomaly_result_rejects_float_score(self):
        """AnomalyResult rejects float risk_score (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            AnomalyResult(
                customer_id="c-001",
                device_id=None,
                risk_level=RiskLevel.LOW,
                risk_score=0.5,  # type: ignore[arg-type]
                anomalies=(),
                geo_country="GB",
            )

    def test_anomaly_detector_audit_log(self, anomaly_detector):
        """Anomaly detector maintains audit log (I-24)."""
        anomaly_detector.check(
            customer_id="c-001",
            device_id="d-001",
            geo_country="GB",
            is_known_device=True,
        )
        assert len(anomaly_detector.audit_log) == 1
        assert anomaly_detector.audit_log[0].action == "ANOMALY_CHECK"


# ── HITL Proposal Tests ──────────────────────────────────────────────────────


class TestHITLProposal:
    def test_hitl_proposal_for_critical_risk(self, service, session_store):
        """CRITICAL risk → HITL proposal (I-27)."""
        recent_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
        session_store.save_session_binding(
            SessionBinding(
                session_id="sess-old",
                device_id="dev-001",
                customer_id="cust-001",
                ip_address_hash="hash1",
                geo_country="JP",
                bound_at=recent_time,
            )
        )
        result = service.check_device(
            customer_id="cust-001",
            fingerprint_data=_fp_data("Edge/120"),
            session_id="sess-new",
            ip_address="9.8.7.6",
            geo_country="BR",
        )
        assert isinstance(result, FingerprintHITLProposal)
        assert result.requires_approval_from == "FRAUD_ANALYST"

    def test_hitl_proposal_immutable(self):
        """FingerprintHITLProposal is frozen."""
        proposal = FingerprintHITLProposal(
            customer_id="c-001",
            device_id="d-001",
            risk_level="HIGH",
            risk_score="50",
            anomalies=("NEW_DEVICE",),
            reason="test",
        )
        with pytest.raises(AttributeError):
            proposal.reason = "modified"  # type: ignore[misc]
