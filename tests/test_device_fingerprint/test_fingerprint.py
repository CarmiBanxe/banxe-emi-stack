"""Tests for Device Fingerprinting (IL-DFP-01)."""

from __future__ import annotations

from decimal import Decimal

from services.device_fingerprint.fingerprint_engine import (
    MAX_DEVICES_PER_CUSTOMER,
    SCORE_KNOWN_DEVICE,
    SCORE_NEW_DEVICE,
    SCORE_SUSPICIOUS,
    FingerprintEngine,
    InMemoryDeviceStore,
    _compute_hash,
)
from services.device_fingerprint.fingerprint_models import FingerprintData, MatchResult


def _make_fp(**kwargs) -> FingerprintData:
    defaults = {"user_agent": "Mozilla/5.0", "canvas_hash": "abc123"}
    defaults.update(kwargs)
    return FingerprintData(**defaults)


class TestFingerprintEngine:
    def test_register_device_returns_profile(self):
        engine = FingerprintEngine()
        fp = _make_fp()
        profile = engine.register_device("CUST001", fp)
        assert profile.device_id is not None
        assert profile.customer_id == "CUST001"

    def test_device_id_starts_with_dev(self):
        engine = FingerprintEngine()
        profile = engine.register_device("CUST001", _make_fp())
        assert profile.device_id.startswith("dev_")

    def test_device_log_append_only(self):
        """I-24: device_log grows."""
        engine = FingerprintEngine()
        engine.register_device("CUST001", _make_fp(user_agent="UA1"))
        engine.register_device("CUST001", _make_fp(user_agent="UA2"))
        assert len(engine.device_log) >= 2

    def test_known_device_score_zero(self):
        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        result = engine.match_device("CUST001", fp)
        assert result.match_type == "known"
        assert Decimal(result.risk_score) == SCORE_KNOWN_DEVICE

    def test_new_device_score_03(self):
        engine = FingerprintEngine()
        fp = _make_fp(canvas_hash="NEW_CANVAS")
        result = engine.match_device("CUST001", fp)
        assert result.match_type == "new"
        assert Decimal(result.risk_score) == SCORE_NEW_DEVICE

    def test_suspicious_device_cross_customer(self):
        """Device known for CUST001 presented by CUST002 → suspicious."""
        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        result = engine.match_device("CUST002", fp)
        assert result.match_type == "suspicious"
        assert Decimal(result.risk_score) == SCORE_SUSPICIOUS

    def test_score_is_decimal_string(self):
        """I-01: risk_score is string parseable as Decimal."""
        engine = FingerprintEngine()
        result = engine.match_device("CUST001", _make_fp())
        assert isinstance(result.risk_score, str)
        Decimal(result.risk_score)  # must parse

    def test_score_not_float(self):
        engine = FingerprintEngine()
        result = engine.match_device("CUST001", _make_fp())
        assert not isinstance(result.risk_score, float)

    def test_max_devices_triggers_suspicious(self):
        """6th device → suspicious (max=5)."""
        engine = FingerprintEngine()
        for i in range(MAX_DEVICES_PER_CUSTOMER):
            engine.register_device("CUST001", _make_fp(user_agent=f"UA{i}", canvas_hash=f"HASH{i}"))
        # 6th new device
        result = engine.match_device(
            "CUST001", _make_fp(user_agent="UA_NEW", canvas_hash="HASH_NEW")
        )
        assert result.match_type == "suspicious"

    def test_hash_deterministic(self):
        fp = _make_fp()
        assert _compute_hash(fp) == _compute_hash(fp)

    def test_hash_differs_for_different_ua(self):
        fp1 = _make_fp(user_agent="UA1")
        fp2 = _make_fp(user_agent="UA2")
        assert _compute_hash(fp1) != _compute_hash(fp2)

    def test_score_constants_are_decimal(self):
        assert isinstance(SCORE_NEW_DEVICE, Decimal)
        assert isinstance(SCORE_KNOWN_DEVICE, Decimal)
        assert isinstance(SCORE_SUSPICIOUS, Decimal)

    def test_score_constants_not_float(self):
        assert not isinstance(SCORE_NEW_DEVICE, float)
        assert not isinstance(SCORE_SUSPICIOUS, float)

    def test_get_by_customer_returns_registered(self):
        store = InMemoryDeviceStore()
        engine = FingerprintEngine(store)
        engine.register_device("CUST001", _make_fp())
        devices = store.get_by_customer("CUST001")
        assert len(devices) == 1


class TestFingerprintAgent:
    def test_known_device_returns_match_result(self):
        from services.device_fingerprint.fingerprint_agent import FingerprintAgent

        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        agent = FingerprintAgent(engine)
        result = agent.assess_device("CUST001", fp)
        assert isinstance(result, MatchResult)

    def test_suspicious_device_returns_hitl(self):
        from services.device_fingerprint.fingerprint_agent import (
            DeviceHITLProposal,
            FingerprintAgent,
        )

        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        agent = FingerprintAgent(engine)
        result = agent.assess_device("CUST002", fp)  # cross-customer
        assert isinstance(result, DeviceHITLProposal)

    def test_hitl_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.device_fingerprint.fingerprint_agent import (
            DeviceHITLProposal,
            FingerprintAgent,
        )

        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        agent = FingerprintAgent(engine)
        result = agent.assess_device("CUST002", fp)
        assert isinstance(result, DeviceHITLProposal)
        assert result.approved is False

    def test_hitl_requires_fraud_analyst(self):
        from services.device_fingerprint.fingerprint_agent import (
            DeviceHITLProposal,
            FingerprintAgent,
        )

        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        agent = FingerprintAgent(engine)
        result = agent.assess_device("CUST002", fp)
        assert isinstance(result, DeviceHITLProposal)
        assert result.requires_approval_from == "FRAUD_ANALYST"

    def test_proposals_accumulate(self):
        from services.device_fingerprint.fingerprint_agent import FingerprintAgent

        engine = FingerprintEngine()
        fp = _make_fp()
        engine.register_device("CUST001", fp)
        agent = FingerprintAgent(engine)
        agent.assess_device("CUST002", fp)
        agent.assess_device("CUST003", fp)
        assert len(agent.proposals) == 2
