"""
tests/test_jube_adapter.py — JubeAdapter unit tests (IL-057)
S5-22 (<100ms fraud scoring SLA) | PSR APP 2024 | FCA MLR 2017 Reg.26
banxe-emi-stack

All HTTP calls are mocked by replacing adapter._client after construction.
httpx IS installed — construct JubeAdapter with direct params, then swap _client.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from services.fraud.fraud_port import (
    AppScamIndicator,
    FraudRisk,
    FraudScoringRequest,
)
from services.fraud.jube_adapter import JubeAdapter


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _mock_response(status_code: int, json_data: dict | list | str = "") -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.is_error = status_code >= 400
    resp.json.return_value = json_data
    resp.text = str(json_data)[:200]
    return resp


def _adapter(client: MagicMock | None = None) -> JubeAdapter:
    """
    Construct a JubeAdapter with known params (no env vars needed),
    then replace the internal httpx.Client with a mock.
    """
    adapter = JubeAdapter(
        base_url="http://jube-test:5001",
        username="Administrator",
        password="test-pass",
        model_guid="aaaabbbb-cccc-dddd-eeee-ffffffffffff",
        timeout_ms=90,
    )
    adapter._client = client or MagicMock()
    return adapter


def _req(**kwargs) -> FraudScoringRequest:
    defaults = dict(
        transaction_id="tx-001",
        customer_id="cust-001",
        amount=Decimal("150.00"),
        currency="GBP",
        destination_account="12345678",
        destination_sort_code="20-00-00",
        destination_country="GB",
        payment_rail="fps",
        entity_type="individual",
        first_transaction_to_payee=True,
        amount_unusual=False,
        customer_ip="1.2.3.4",
        customer_device_id="dev-001",
        session_id="sess-001",
    )
    defaults.update(kwargs)
    return FraudScoringRequest(**defaults)


def _auth_response(token: str = "jwt-token", hours: int = 1) -> MagicMock:
    expiry = (datetime.now(timezone.utc) + timedelta(hours=hours)).isoformat()
    return _mock_response(200, {"token": token, "tokenExpiryTime": expiry})


# ─────────────────────────────────────────────────────────────────────────────
# TestJubeAdapterInit
# ─────────────────────────────────────────────────────────────────────────────

class TestJubeAdapterInit:
    def test_direct_params_ok(self):
        adapter = _adapter()
        assert adapter._base_url == "http://jube-test:5001"
        assert adapter._username == "Administrator"
        assert adapter._model_guid == "aaaabbbb-cccc-dddd-eeee-ffffffffffff"
        assert adapter._timeout_s == pytest.approx(0.09)

    def test_missing_base_url_raises(self):
        with patch.dict("os.environ", {}, clear=False):
            import os
            original = os.environ.pop("JUBE_URL", None)
            try:
                with pytest.raises(EnvironmentError, match="JUBE_URL"):
                    JubeAdapter(
                        base_url="",
                        username="Administrator",
                        password="pass",
                        model_guid="guid",
                    )
            finally:
                if original is not None:
                    os.environ["JUBE_URL"] = original

    def test_missing_password_raises(self):
        with pytest.raises(EnvironmentError, match="JUBE_PASSWORD"):
            JubeAdapter(
                base_url="http://jube:5001",
                username="Administrator",
                password="",
                model_guid="guid",
            )

    def test_missing_model_guid_raises(self):
        with pytest.raises(EnvironmentError, match="JUBE_MODEL_GUID"):
            JubeAdapter(
                base_url="http://jube:5001",
                username="Administrator",
                password="pass",
                model_guid="",
            )

    def test_trailing_slash_stripped(self):
        adapter = JubeAdapter(
            base_url="http://jube:5001/",
            username="Administrator",
            password="pass",
            model_guid="guid",
        )
        assert adapter._base_url == "http://jube:5001"

    def test_httpx_not_installed_raises(self):
        import sys
        with patch.dict(sys.modules, {"httpx": None}):
            with pytest.raises(RuntimeError, match="httpx not installed"):
                JubeAdapter(
                    base_url="http://jube:5001",
                    username="Administrator",
                    password="pass",
                    model_guid="guid",
                )


# ─────────────────────────────────────────────────────────────────────────────
# TestAuthenticate
# ─────────────────────────────────────────────────────────────────────────────

class TestAuthenticate:
    def test_success_stores_jwt(self):
        client = MagicMock()
        client.post.return_value = _auth_response("my-jwt")
        adapter = _adapter(client)

        token = adapter._authenticate()

        assert token == "my-jwt"
        assert adapter._jwt == "my-jwt"
        assert adapter._jwt_expires_at is not None

    def test_uses_passcalcase_payload(self):
        client = MagicMock()
        client.post.return_value = _auth_response()
        adapter = _adapter(client)

        adapter._authenticate()

        call_kwargs = client.post.call_args
        body = call_kwargs[1]["json"]
        assert "UserName" in body
        assert "Password" in body

    def test_401_raises_runtime_error(self):
        client = MagicMock()
        client.post.return_value = _mock_response(401, {})
        adapter = _adapter(client)

        with pytest.raises(RuntimeError, match="Jube authentication failed"):
            adapter._authenticate()

    def test_server_error_raises(self):
        client = MagicMock()
        client.post.return_value = _mock_response(500, "Internal Server Error")
        adapter = _adapter(client)

        with pytest.raises(RuntimeError, match="Jube authentication error: 500"):
            adapter._authenticate()

    def test_missing_token_in_response_raises(self):
        client = MagicMock()
        client.post.return_value = _mock_response(200, {"tokenExpiryTime": "2099-01-01T00:00:00Z"})
        adapter = _adapter(client)

        with pytest.raises(RuntimeError, match="missing token"):
            adapter._authenticate()

    def test_expiry_fallback_on_bad_iso(self):
        """If tokenExpiryTime is malformed, falls back to now + 1 hour."""
        client = MagicMock()
        client.post.return_value = _mock_response(200, {"token": "tok", "tokenExpiryTime": "not-a-date"})
        adapter = _adapter(client)

        adapter._authenticate()

        assert adapter._jwt_expires_at is not None
        # Should be roughly now + 1 hour
        diff = adapter._jwt_expires_at - datetime.now(timezone.utc)
        assert timedelta(minutes=50) < diff < timedelta(hours=2)

    def test_token_key_alias_Token(self):
        """Jube may use PascalCase 'Token' key."""
        client = MagicMock()
        expiry = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        client.post.return_value = _mock_response(200, {"Token": "pascal-token", "TokenExpiryTime": expiry})
        adapter = _adapter(client)

        token = adapter._authenticate()
        assert token == "pascal-token"


# ─────────────────────────────────────────────────────────────────────────────
# TestGetJwt
# ─────────────────────────────────────────────────────────────────────────────

class TestGetJwt:
    def test_fetches_new_jwt_when_none(self):
        client = MagicMock()
        client.post.return_value = _auth_response("fresh-token")
        adapter = _adapter(client)

        token = adapter._get_jwt()
        assert token == "fresh-token"
        assert client.post.call_count == 1

    def test_returns_cached_jwt_when_valid(self):
        client = MagicMock()
        adapter = _adapter(client)
        adapter._jwt = "cached-token"
        adapter._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

        token = adapter._get_jwt()
        assert token == "cached-token"
        client.post.assert_not_called()

    def test_refreshes_jwt_near_expiry(self):
        """Token expiring in <60s should trigger re-auth."""
        client = MagicMock()
        client.post.return_value = _auth_response("new-token")
        adapter = _adapter(client)
        adapter._jwt = "old-token"
        adapter._jwt_expires_at = datetime.now(timezone.utc) + timedelta(seconds=30)

        token = adapter._get_jwt()
        assert token == "new-token"
        assert client.post.call_count == 1

    def test_refreshes_jwt_when_expired(self):
        client = MagicMock()
        client.post.return_value = _auth_response("refreshed")
        adapter = _adapter(client)
        adapter._jwt = "old"
        adapter._jwt_expires_at = datetime.now(timezone.utc) - timedelta(hours=1)

        token = adapter._get_jwt()
        assert token == "refreshed"


# ─────────────────────────────────────────────────────────────────────────────
# TestBuildPayload
# ─────────────────────────────────────────────────────────────────────────────

class TestBuildPayload:
    def test_amount_is_string(self):
        """I-05: monetary amounts must be strings, never float."""
        adapter = _adapter()
        req = _req(amount=Decimal("999.99"))

        payload = adapter._build_payload(req)

        assert isinstance(payload["TransactionAmount"], str)
        assert payload["TransactionAmount"] == "999.99"

    def test_all_expected_fields_present(self):
        adapter = _adapter()
        payload = adapter._build_payload(_req())

        required = {
            "TransactionId", "CustomerId", "TransactionAmount", "Currency",
            "DestinationAccount", "DestinationSortCode", "DestinationCountry",
            "PaymentRail", "EntityType", "FirstTransactionToPayee",
            "AmountUnusual", "CustomerIp", "CustomerDeviceId", "SessionId",
        }
        assert required.issubset(payload.keys())

    def test_optional_string_fields_default_to_empty(self):
        adapter = _adapter()
        req = _req(customer_ip=None, customer_device_id=None, session_id=None)

        payload = adapter._build_payload(req)

        assert payload["CustomerIp"] == ""
        assert payload["CustomerDeviceId"] == ""
        assert payload["SessionId"] == ""


# ─────────────────────────────────────────────────────────────────────────────
# TestParseResponse
# ─────────────────────────────────────────────────────────────────────────────

class TestParseResponse:
    def _parse(self, data: dict, latency: float = 10.0):
        adapter = _adapter()
        return adapter._parse_response(_req(), data, latency)

    def test_score_critical_block(self):
        result = self._parse({"responseElevation": 90})
        assert result.risk == FraudRisk.CRITICAL
        assert result.score == 90
        assert result.block is True
        # CRITICAL → blocked outright; hold_for_review is for HIGH/MEDIUM human review
        assert result.hold_for_review is False

    def test_score_high_hold_no_block(self):
        result = self._parse({"responseElevation": 75})
        assert result.risk == FraudRisk.HIGH
        assert result.block is False
        assert result.hold_for_review is True

    def test_score_medium_hold_no_block(self):
        result = self._parse({"responseElevation": 55})
        assert result.risk == FraudRisk.MEDIUM
        assert result.block is False
        assert result.hold_for_review is True

    def test_score_low_no_block_no_hold(self):
        result = self._parse({"responseElevation": 10})
        assert result.risk == FraudRisk.LOW
        assert result.block is False
        assert result.hold_for_review is False

    def test_score_clamped_to_100(self):
        result = self._parse({"responseElevation": 999})
        assert result.score == 100

    def test_score_clamped_to_0(self):
        result = self._parse({"responseElevation": -5})
        assert result.score == 0

    def test_missing_score_defaults_to_0(self):
        result = self._parse({})
        assert result.score == 0
        assert result.risk == FraudRisk.LOW

    def test_case_insensitive_pascal_elevation(self):
        result = self._parse({"ResponseElevation": 85})
        assert result.risk == FraudRisk.CRITICAL

    def test_explicit_block_activation_rule(self):
        """LOW score but BlockTransaction=True → block=True."""
        result = self._parse({"responseElevation": 10, "BlockTransaction": True})
        assert result.block is True

    def test_explicit_hold_activation_rule(self):
        """LOW score but HoldForReview=True → hold=True."""
        result = self._parse({"responseElevation": 10, "HoldTransaction": True})
        assert result.hold_for_review is True

    def test_audit_guid_logged(self, caplog):
        """I-24: entityAnalysisModelInstanceEntryGuid must be logged."""
        with caplog.at_level(logging.INFO, logger="services.fraud.jube_adapter"):
            self._parse({
                "responseElevation": 20,
                "EntityAnalysisModelInstanceEntryGuid": "audit-guid-1234",
            })
        assert "audit-guid-1234" in caplog.text

    def test_factors_extracted_from_bool_rules(self):
        result = self._parse({
            "responseElevation": 80,
            "NewDevice": True,
            "HighRiskCountry": True,
            "SomeNumericField": 42,
        })
        assert "NewDevice" in result.factors
        assert "HighRiskCountry" in result.factors
        assert "SomeNumericField" not in result.factors

    def test_provider_field(self):
        result = self._parse({"responseElevation": 30})
        assert result.provider == "jube"

    def test_latency_passed_through(self):
        result = self._parse({"responseElevation": 30}, latency=42.5)
        assert result.latency_ms == pytest.approx(42.5)


# ─────────────────────────────────────────────────────────────────────────────
# TestDetectAppScam
# ─────────────────────────────────────────────────────────────────────────────

class TestDetectAppScam:
    def _detect(self, normalised: dict) -> AppScamIndicator:
        return _adapter()._detect_app_scam(normalised)

    def test_purchase_scam(self):
        assert self._detect({"purchasescam": True}) == AppScamIndicator.PURCHASE_SCAM

    def test_romance_scam(self):
        assert self._detect({"romancescam": True}) == AppScamIndicator.ROMANCE_SCAM

    def test_investment_scam(self):
        assert self._detect({"investmentscam": True}) == AppScamIndicator.INVESTMENT_SCAM

    def test_impersonation_bank(self):
        assert self._detect({"impersonationbank": True}) == AppScamIndicator.IMPERSONATION_BANK

    def test_impersonation_police(self):
        assert self._detect({"impersonationpolice": True}) == AppScamIndicator.IMPERSONATION_POLICE

    def test_impersonation_hmrc(self):
        assert self._detect({"impersonationhmrc": True}) == AppScamIndicator.IMPERSONATION_HMRC

    def test_ceo_fraud(self):
        assert self._detect({"ceofraud": True}) == AppScamIndicator.CEO_FRAUD

    def test_invoice_redirect(self):
        assert self._detect({"invoiceredirect": True}) == AppScamIndicator.INVOICE_REDIRECT

    def test_advance_fee(self):
        assert self._detect({"advancefee": True}) == AppScamIndicator.ADVANCE_FEE

    def test_no_match_returns_none(self):
        assert self._detect({"unrelatedtag": True}) == AppScamIndicator.NONE

    def test_false_value_returns_none(self):
        assert self._detect({"purchasescam": False}) == AppScamIndicator.NONE

    def test_empty_dict_returns_none(self):
        assert self._detect({}) == AppScamIndicator.NONE


# ─────────────────────────────────────────────────────────────────────────────
# TestScore — full flow
# ─────────────────────────────────────────────────────────────────────────────

class TestScore:
    def _adapter_with_auth(self) -> tuple[JubeAdapter, MagicMock]:
        """Adapter with pre-loaded JWT (skip auth in tests)."""
        client = MagicMock()
        adapter = _adapter(client)
        adapter._jwt = "valid-jwt"
        adapter._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        return adapter, client

    def test_low_risk_score(self):
        adapter, client = self._adapter_with_auth()
        client.post.return_value = _mock_response(200, {"responseElevation": 20})

        result = adapter.score(_req())
        assert result.risk == FraudRisk.LOW
        assert result.block is False
        assert result.hold_for_review is False
        assert result.provider == "jube"

    def test_critical_risk_score(self):
        adapter, client = self._adapter_with_auth()
        client.post.return_value = _mock_response(200, {"responseElevation": 95})

        result = adapter.score(_req())
        assert result.risk == FraudRisk.CRITICAL
        assert result.block is True

    def test_invoke_url_contains_model_guid(self):
        adapter, client = self._adapter_with_auth()
        client.post.return_value = _mock_response(200, {"responseElevation": 10})

        adapter.score(_req())

        call_args = client.post.call_args
        url = call_args[0][0]
        assert "aaaabbbb-cccc-dddd-eeee-ffffffffffff" in url

    def test_bearer_token_in_headers(self):
        adapter, client = self._adapter_with_auth()
        client.post.return_value = _mock_response(200, {"responseElevation": 10})

        adapter.score(_req())

        call_kwargs = client.post.call_args[1]
        assert call_kwargs["headers"]["Authorization"] == "Bearer valid-jwt"

    def test_timeout_fallback_returns_medium_hold(self):
        import httpx
        client = MagicMock()
        adapter = _adapter(client)
        adapter._jwt = "valid-jwt"
        adapter._jwt_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)
        client.post.side_effect = httpx.TimeoutException("timeout")

        result = adapter.score(_req())

        assert result.risk == FraudRisk.MEDIUM
        assert result.hold_for_review is True
        assert result.block is False
        assert result.provider == "jube_timeout_fallback"
        assert "jube_timeout" in result.factors

    def test_error_fallback_on_5xx(self):
        adapter, client = self._adapter_with_auth()
        client.post.return_value = _mock_response(503, "Service Unavailable")

        result = adapter.score(_req())

        assert result.risk == FraudRisk.MEDIUM
        assert result.hold_for_review is True
        assert result.provider == "jube_error_fallback"
        assert "jube_api_error" in result.factors

    def test_401_mid_flight_triggers_reauth(self):
        """On 401 during invoke, adapter clears JWT and re-authenticates."""
        adapter, client = self._adapter_with_auth()
        auth_resp = _auth_response("new-jwt")
        invoke_resp = _mock_response(200, {"responseElevation": 10})

        # First invoke call returns 401, auth returns new token, second invoke succeeds
        client.post.side_effect = [
            _mock_response(401, {}),  # first invoke → 401
            auth_resp,                 # _authenticate() → new JWT
            invoke_resp,               # second invoke → success
        ]

        result = adapter.score(_req())

        assert result.risk == FraudRisk.LOW
        assert client.post.call_count == 3

    def test_transaction_id_in_result(self):
        adapter, client = self._adapter_with_auth()
        client.post.return_value = _mock_response(200, {"responseElevation": 30})

        result = adapter.score(_req(transaction_id="tx-999"))
        assert result.transaction_id == "tx-999"


# ─────────────────────────────────────────────────────────────────────────────
# TestFallbacks
# ─────────────────────────────────────────────────────────────────────────────

class TestFallbacks:
    def test_timeout_fallback_structure(self):
        adapter = _adapter()
        result = adapter._timeout_fallback(_req(), latency_s=0.095)

        assert result.risk == FraudRisk.MEDIUM
        assert result.score == 50
        assert result.block is False
        assert result.hold_for_review is True
        assert result.app_scam_indicator == AppScamIndicator.NONE
        assert result.provider == "jube_timeout_fallback"
        assert result.latency_ms == pytest.approx(95.0)

    def test_error_fallback_structure(self):
        adapter = _adapter()
        result = adapter._error_fallback(_req(), latency_ms=88.0)

        assert result.risk == FraudRisk.MEDIUM
        assert result.score == 50
        assert result.block is False
        assert result.hold_for_review is True
        assert result.provider == "jube_error_fallback"
        assert result.latency_ms == pytest.approx(88.0)


# ─────────────────────────────────────────────────────────────────────────────
# TestHealth
# ─────────────────────────────────────────────────────────────────────────────

class TestHealth:
    def test_health_true_when_auth_succeeds(self):
        client = MagicMock()
        client.post.return_value = _auth_response()
        adapter = _adapter(client)

        assert adapter.health() is True

    def test_health_false_when_auth_fails(self):
        client = MagicMock()
        client.post.return_value = _mock_response(401, {})
        adapter = _adapter(client)

        assert adapter.health() is False

    def test_health_false_on_network_error(self):
        import httpx
        client = MagicMock()
        client.post.side_effect = httpx.ConnectError("refused")
        adapter = _adapter(client)

        assert adapter.health() is False


# ─────────────────────────────────────────────────────────────────────────────
# TestScoreThresholdBoundaries
# ─────────────────────────────────────────────────────────────────────────────

class TestScoreThresholdBoundaries:
    """Verify exact threshold boundaries match spec (I-057)."""

    def _score_only(self, elevation: int) -> tuple:
        adapter = _adapter()
        result = adapter._parse_response(_req(), {"responseElevation": elevation}, 5.0)
        return result.risk, result.score

    def test_boundary_84_is_high(self):
        risk, _ = self._score_only(84)
        assert risk == FraudRisk.HIGH

    def test_boundary_85_is_critical(self):
        risk, _ = self._score_only(85)
        assert risk == FraudRisk.CRITICAL

    def test_boundary_69_is_medium(self):
        risk, _ = self._score_only(69)
        assert risk == FraudRisk.MEDIUM

    def test_boundary_70_is_high(self):
        risk, _ = self._score_only(70)
        assert risk == FraudRisk.HIGH

    def test_boundary_39_is_low(self):
        risk, _ = self._score_only(39)
        assert risk == FraudRisk.LOW

    def test_boundary_40_is_medium(self):
        risk, _ = self._score_only(40)
        assert risk == FraudRisk.MEDIUM

    def test_boundary_0_is_low(self):
        risk, score = self._score_only(0)
        assert risk == FraudRisk.LOW
        assert score == 0

    def test_boundary_100_is_critical(self):
        risk, score = self._score_only(100)
        assert risk == FraudRisk.CRITICAL
        assert score == 100
