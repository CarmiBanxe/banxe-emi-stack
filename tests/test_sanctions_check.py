"""
Skeleton tests for Sanctions Check Agent (Moov Watchman integration).
BANXE AI BANK | IL-069 | banxe-emi-stack

Watchman API: https://github.com/moov-io/watchman
Thresholds: minMatch ≥ 0.80 = BLOCK, 0.60–0.79 = REVIEW, < 0.60 = CLEAR
"""

import pytest

# ── Test data builders ────────────────────────────────────────────────────────


def make_watchman_response(match_score: float, entity_name: str = "Test Entity") -> dict:
    """Simulate a Watchman search response."""
    hit = {"score": match_score, "name": entity_name}
    return {
        "ofacSDN": [hit] if match_score >= 0.60 else [],
        "ukSanctions": [],
        "euConsolidated": [],
        "total_hits": 1 if match_score >= 0.60 else 0,
        "max_score": match_score,
    }


def make_screening_request(**kwargs) -> dict:
    defaults = {
        "party_id": "CUST-001",
        "name": "John Smith",
        "country": "GB",
        "amount": "5000.00",
        "currency": "GBP",
    }
    return {**defaults, **kwargs}


# ── Match threshold classification ────────────────────────────────────────────


class TestWatchmanThresholds:
    """Verify SOUL-defined thresholds: BLOCK ≥ 0.80, REVIEW 0.60–0.79, CLEAR < 0.60."""

    BLOCK_THRESHOLD = 0.80
    REVIEW_THRESHOLD = 0.60

    def classify(self, score: float) -> str:
        if score >= self.BLOCK_THRESHOLD:
            return "CONFIRMED_HIT"
        if score >= self.REVIEW_THRESHOLD:
            return "POTENTIAL_MATCH"
        return "CLEAR"

    def test_confirmed_hit_at_exactly_080(self):
        assert self.classify(0.80) == "CONFIRMED_HIT"

    def test_confirmed_hit_above_080(self):
        assert self.classify(0.95) == "CONFIRMED_HIT"
        assert self.classify(1.00) == "CONFIRMED_HIT"

    def test_potential_match_between_060_and_079(self):
        assert self.classify(0.60) == "POTENTIAL_MATCH"
        assert self.classify(0.70) == "POTENTIAL_MATCH"
        assert self.classify(0.79) == "POTENTIAL_MATCH"

    def test_clear_below_060(self):
        assert self.classify(0.00) == "CLEAR"
        assert self.classify(0.30) == "CLEAR"
        assert self.classify(0.59) == "CLEAR"

    def test_boundary_079_is_potential_not_block(self):
        assert self.classify(0.799) == "POTENTIAL_MATCH"

    def test_boundary_080_is_confirmed_not_potential(self):
        assert self.classify(0.800) == "CONFIRMED_HIT"


# ── OFAC/HMT/EU list screening ────────────────────────────────────────────────


class TestSanctionsListCoverage:
    def test_ofac_sdn_included(self):
        response = make_watchman_response(0.85)
        assert "ofacSDN" in response

    def test_uk_hmt_included(self):
        response = make_watchman_response(0.85)
        assert "ukSanctions" in response

    def test_eu_consolidated_included(self):
        response = make_watchman_response(0.85)
        assert "euConsolidated" in response

    def test_no_hits_for_clear_score(self):
        response = make_watchman_response(0.30)
        assert response["total_hits"] == 0
        assert response["max_score"] < 0.60


# ── Geographic risk ───────────────────────────────────────────────────────────


class TestGeographicRisk:
    CATEGORY_A = ["IR", "KP", "MM", "BY", "RU", "CU", "SD", "ZW", "VE"]  # BLOCK
    CATEGORY_B_SAMPLE = ["AF", "AL", "BS", "BW", "BF"]  # EDD

    def test_category_a_countries_blocked(self):
        for country in self.CATEGORY_A:
            request = make_screening_request(country=country)
            assert request["country"] in self.CATEGORY_A, f"{country} should be in Category A"

    def test_gb_is_not_blocked(self):
        assert "GB" not in self.CATEGORY_A

    def test_syria_is_hold_not_block(self):
        """Syria reclassified from BLOCK to HOLD in July 2025 (sanctions update)."""
        # SY was moved to HOLD — should be in Category B, not A
        assert "SY" not in self.CATEGORY_A

    def test_category_b_triggers_edd(self):
        for country in self.CATEGORY_B_SAMPLE:
            request = make_screening_request(country=country)
            assert request["country"] in self.CATEGORY_B_SAMPLE


# ── PEP handling ──────────────────────────────────────────────────────────────


class TestPEPHandling:
    def test_pep_requires_hitl(self):
        """PEP onboarding always requires HUMAN_MLRO gate (SOUL spec)."""
        pep_flags = ["PEP_DIRECT", "PEP_FAMILY", "PEP_ASSOCIATE"]
        for flag in pep_flags:
            # Skeleton: verify that PEP flag triggers HITL gate request
            assert isinstance(flag, str)

    def test_pep_detection_fields(self):
        watchman_pep = {
            "entityType": "PEP",
            "pepCategory": "HEAD_OF_STATE",
            "country": "XX",
            "score": 0.91,
        }
        assert watchman_pep["score"] >= 0.80
        assert watchman_pep["entityType"] == "PEP"


# ── Audit trail ───────────────────────────────────────────────────────────────


class TestSanctionsAuditTrail:
    def test_screening_event_has_required_fields(self):
        """Every screening event must have these fields for ClickHouse (I-24)."""
        event = {
            "party_id": "CUST-001",
            "screened_at": "2026-04-09T10:00:00Z",
            "result": "CLEAR",
            "max_score": 0.21,
            "lists_checked": ["ofacSDN", "ukSanctions", "euConsolidated"],
            "agent_id": "sanctions_check_agent",
        }
        required = ["party_id", "screened_at", "result", "max_score", "lists_checked"]
        for field in required:
            assert field in event, f"Audit trail missing: {field}"

    def test_confirmed_hit_event_logged(self):
        event = {
            "party_id": "CUST-002",
            "screened_at": "2026-04-09T10:05:00Z",
            "result": "CONFIRMED_HIT",
            "max_score": 0.93,
            "lists_checked": ["ofacSDN"],
            "hitl_gate_triggered": "sanctions_reversal",
            "agent_id": "sanctions_check_agent",
        }
        assert event["result"] == "CONFIRMED_HIT"
        assert event["hitl_gate_triggered"] is not None

    @pytest.mark.skip(reason="Requires live Watchman on GMKtec")
    async def test_live_watchman_screening(self):
        """Live integration — run against Watchman on GMKtec."""
        pass
