"""Tests for ATO Prevention (IL-ATO-01)."""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.ato_prevention.ato_engine import (
    BLOCKED_JURISDICTIONS,
    MAX_FAILED_LOGINS,
    ATOEngine,
    InMemoryATOStore,
    _haversine_km,
)
from services.ato_prevention.ato_models import ATOAssessment, GeoLocation, LoginAttempt


def _make_attempt(
    customer_id: str = "CUST001",
    country: str = "GB",
    success: bool = True,
    lat: float = 51.5,
    lon: float = -0.1,
) -> LoginAttempt:
    return LoginAttempt(
        customer_id=customer_id,
        ip_address="1.2.3.4",
        device_fingerprint="abc123",
        geo=GeoLocation(country=country, latitude=lat, longitude=lon),
        success=success,
    )


class TestATOEngine:
    def test_clean_login_returns_allow(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt())
        assert result.action == "allow"

    def test_risk_score_is_string(self):
        """I-01: risk_score is Decimal string."""
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt())
        assert isinstance(result.risk_score, str)
        Decimal(result.risk_score)

    def test_risk_score_not_float(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt())
        assert not isinstance(result.risk_score, float)

    def test_blocked_jurisdiction_ru_locks(self):
        """I-02: RU geo → score 1.0, lock."""
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt(country="RU"))
        assert result.action == "lock"
        assert Decimal(result.risk_score) == Decimal("1.0")
        assert "BLOCKED_JURISDICTION" in result.signals

    def test_blocked_jurisdiction_ir_locks(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt(country="IR"))
        assert result.action == "lock"

    def test_blocked_jurisdiction_kp_locks(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt(country="KP"))
        assert result.action == "lock"

    def test_allowed_jurisdiction_gb_allows(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt(country="GB"))
        assert "BLOCKED_JURISDICTION" not in result.signals

    def test_failed_login_velocity_challenges(self):
        """5+ failed logins → FAILED_LOGIN_VELOCITY signal."""
        store = InMemoryATOStore()
        engine = ATOEngine(store)
        for _ in range(MAX_FAILED_LOGINS):
            engine.assess_login(_make_attempt(success=False))
        result = engine.assess_login(_make_attempt(success=True))
        assert "FAILED_LOGIN_VELOCITY" in result.signals

    def test_ato_log_append_only(self):
        """I-24: ato_log grows."""
        engine = ATOEngine()
        engine.assess_login(_make_attempt(customer_id="C1"))
        engine.assess_login(_make_attempt(customer_id="C2"))
        assert len(engine.ato_log) == 2

    def test_ato_log_has_timestamp(self):
        engine = ATOEngine()
        engine.assess_login(_make_attempt())
        assert "logged_at" in engine.ato_log[0]

    def test_haversine_same_point_zero(self):
        dist = _haversine_km(51.5, -0.1, 51.5, -0.1)
        assert dist == pytest.approx(0.0, abs=0.01)

    def test_haversine_london_paris(self):
        dist = _haversine_km(51.5, -0.1, 48.8, 2.3)  # London to Paris ≈ 340km
        assert 300 < dist < 400

    def test_impossible_travel_detected(self):
        """London → New York in 1 assess → impossible travel."""
        store = InMemoryATOStore()
        engine = ATOEngine(store)
        # First login from London
        engine.assess_login(_make_attempt(lat=51.5, lon=-0.1))
        # Immediate login from New York (≈5500km away)
        result = engine.assess_login(_make_attempt(lat=40.7, lon=-74.0))
        assert "IMPOSSIBLE_TRAVEL" in result.signals

    def test_blocked_jurisdictions_set(self):
        assert "RU" in BLOCKED_JURISDICTIONS
        assert "GB" not in BLOCKED_JURISDICTIONS

    def test_assessment_has_all_fields(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt())
        assert hasattr(result, "customer_id")
        assert hasattr(result, "risk_score")
        assert hasattr(result, "signals")
        assert hasattr(result, "action")

    def test_action_values(self):
        engine = ATOEngine()
        result = engine.assess_login(_make_attempt())
        assert result.action in ("allow", "challenge", "lock")


class TestATOAgent:
    def test_low_risk_returns_assessment(self):
        from services.ato_prevention.ato_agent import ATOAgent

        engine = ATOEngine()
        agent = ATOAgent(engine)
        result = agent.assess_and_act(_make_attempt())
        assert isinstance(result, ATOAssessment)

    def test_high_risk_returns_hitl(self):
        """Blocked jurisdiction → score 1.0 → HITL."""
        from services.ato_prevention.ato_agent import ATOAgent, ATOHITLProposal

        engine = ATOEngine()
        agent = ATOAgent(engine)
        result = agent.assess_and_act(_make_attempt(country="RU"))
        assert isinstance(result, ATOHITLProposal)

    def test_hitl_not_auto_approved(self):
        """I-27: proposals start unapproved."""
        from services.ato_prevention.ato_agent import ATOAgent, ATOHITLProposal

        engine = ATOEngine()
        agent = ATOAgent(engine)
        result = agent.assess_and_act(_make_attempt(country="IR"))
        assert isinstance(result, ATOHITLProposal)
        assert result.approved is False

    def test_hitl_requires_security_officer(self):
        from services.ato_prevention.ato_agent import ATOAgent, ATOHITLProposal

        engine = ATOEngine()
        agent = ATOAgent(engine)
        result = agent.assess_and_act(_make_attempt(country="KP"))
        assert isinstance(result, ATOHITLProposal)
        assert result.requires_approval_from == "SECURITY_OFFICER"

    def test_unlock_returns_hitl(self):
        from services.ato_prevention.ato_agent import ATOAgent, ATOHITLProposal

        agent = ATOAgent()
        proposal = agent.propose_unlock("CUST001", "security_officer@banxe.com")
        assert isinstance(proposal, ATOHITLProposal)
        assert proposal.action == "unlock_account"

    def test_unlock_hitl_not_auto_approved(self):
        from services.ato_prevention.ato_agent import ATOAgent

        agent = ATOAgent()
        proposal = agent.propose_unlock("CUST001", "officer@banxe.com")
        assert proposal.approved is False

    def test_proposals_accumulate(self):
        from services.ato_prevention.ato_agent import ATOAgent

        engine = ATOEngine()
        agent = ATOAgent(engine)
        agent.assess_and_act(_make_attempt(customer_id="C1", country="RU"))
        agent.assess_and_act(_make_attempt(customer_id="C2", country="IR"))
        assert len(agent.proposals) == 2
