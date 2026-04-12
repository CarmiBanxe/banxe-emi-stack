"""
Skeleton tests for Jube Adapter Agent integration.
BANXE AI BANK | IL-069 | banxe-emi-stack
"""

from decimal import Decimal
import re

import pytest


def make_midaz_event(**kwargs):
    defaults = {
        "tx_id": "TXN-TEST-001",
        "account_id": "ACC-001",
        "customer_id": "CUST-001",
        "amount": "150.00",
        "currency": "GBP",
        "timestamp": "2026-04-09T10:00:00Z",
        "channel": "ONLINE",
        "country_from": "GB",
        "country_to": "GB",
        "merchant_category": "5411",
    }
    return {**defaults, **kwargs}


def make_jube_response(**kwargs):
    defaults = {
        "tx_id": "TXN-TEST-001",
        "risk_score": 2.1,
        "alert": False,
        "alert_type": None,
        "model_version": "v2.3.1",
        "processing_ms": 45,
    }
    return {**defaults, **kwargs}


class TestJubeAmountHandling:
    def test_amount_is_string_in_event(self):
        event = make_midaz_event(amount="150.00")
        assert isinstance(event["amount"], str)

    def test_amount_not_float(self):
        event = make_midaz_event(amount="150.00")
        assert not isinstance(event["amount"], float)

    def test_decimal_precision_preserved(self):
        amount_str = "1234.56"
        assert str(Decimal(amount_str)) == amount_str

    def test_high_value_no_precision_loss(self):
        assert Decimal("99999.99") == Decimal("99999.99")


class TestJubeEventSchema:
    REQUIRED_FIELDS = [
        "tx_id",
        "account_id",
        "customer_id",
        "amount",
        "currency",
        "timestamp",
        "channel",
        "country_from",
        "country_to",
        "merchant_category",
    ]

    def test_required_fields_present(self):
        event = make_midaz_event()
        for field in self.REQUIRED_FIELDS:
            assert field in event

    def test_currency_is_iso_4217(self):
        event = make_midaz_event(currency="GBP")
        assert len(event["currency"]) == 3
        assert event["currency"].isupper()

    def test_country_codes_are_iso_3166(self):
        event = make_midaz_event(country_from="GB", country_to="DE")
        assert len(event["country_from"]) == 2
        assert len(event["country_to"]) == 2

    def test_timestamp_is_iso8601(self):
        event = make_midaz_event()
        assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", event["timestamp"])

    def test_channel_is_valid(self):
        valid_channels = {"ONLINE", "MOBILE", "BRANCH", "API"}
        event = make_midaz_event(channel="ONLINE")
        assert event["channel"] in valid_channels


class TestJubeAlertRouting:
    def test_aml_alert_has_aml_type(self):
        response = make_jube_response(alert=True, alert_type="AML_VELOCITY")
        assert response["alert"] is True
        assert "AML" in response["alert_type"]

    def test_fraud_alert_has_fraud_type(self):
        response = make_jube_response(alert=True, alert_type="FRAUD_CARD")
        assert "FRAUD" in response["alert_type"]

    def test_no_alert_no_routing(self):
        response = make_jube_response(alert=False, alert_type=None)
        assert response["alert"] is False

    def test_critical_alert_high_score(self):
        response = make_jube_response(alert=True, alert_type="AML_CRITICAL", risk_score=9.5)
        assert response["risk_score"] > 7.0


class TestJubeSLA:
    def test_processing_under_100ms(self):
        response = make_jube_response(processing_ms=45)
        assert response["processing_ms"] < 100

    def test_sla_boundary(self):
        response = make_jube_response(processing_ms=99)
        assert response["processing_ms"] < 100

    @pytest.mark.skip(reason="Requires live Jube instance on GMKtec")
    async def test_live_jube_classification(self):
        pass
