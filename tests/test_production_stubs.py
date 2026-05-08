"""
tests/test_production_stubs.py — Sanity tests for Phase 5 production wiring stubs.

Verifies:
  1. Each stub raises NotImplementedError on network-touching methods (not silently no-ops).
  2. Each stub class exists and can be instantiated.
  3. OTP stubs satisfy OtpDeliveryPort (runtime_checkable via inherited LegacyOtpAdapter).

Tests: 10  |  No external deps.
Canon: PORT-CONTRACTS-FREEZE-2026-05-08 + ADR-025 §15-16
"""

from __future__ import annotations

import pytest

from services.auth.otp_delivery_port import OtpDeliveryPort
from services.auth.production.twilio_otp_stub import SendGridOtpStub, TwilioOtpStub
from services.compliance.production.sumsub_http_stub import SumsubHttpStub
from services.ledger.production.midaz_crypto_stub import MidazCryptoStub
from services.payment.production.modulr_sepa_stub import ModulrSepaStub

# ── TwilioOtpStub ─────────────────────────────────────────────────────────────


def test_twilio_otp_stub_raises_not_implemented_on_send() -> None:
    stub = TwilioOtpStub()
    with pytest.raises(NotImplementedError, match="TWILIO_ACCOUNT_SID"):
        stub.send_otp(channel="sms", target="+447700900001", code="123456", ttl_seconds=300)


def test_twilio_otp_stub_satisfies_otp_port() -> None:
    assert isinstance(TwilioOtpStub(), OtpDeliveryPort)


def test_twilio_otp_stub_inherits_generate_otp() -> None:
    stub = TwilioOtpStub()
    code = stub.generate_otp()
    assert len(code) == 6
    assert code.isdigit()


# ── SendGridOtpStub ───────────────────────────────────────────────────────────


def test_sendgrid_otp_stub_raises_not_implemented_on_send() -> None:
    stub = SendGridOtpStub()
    with pytest.raises(NotImplementedError, match="SENDGRID_API_KEY"):
        stub.send_otp(channel="email", target="user@banxe.com", code="654321", ttl_seconds=600)


def test_sendgrid_otp_stub_satisfies_otp_port() -> None:
    assert isinstance(SendGridOtpStub(), OtpDeliveryPort)


# ── ModulrSepaStub ────────────────────────────────────────────────────────────


def test_modulr_sepa_stub_raises_not_implemented_on_submit() -> None:
    from unittest.mock import Mock

    stub = ModulrSepaStub()
    with pytest.raises(NotImplementedError, match="MODULR_API_KEY"):
        stub.submit_payment(Mock())  # stub raises before inspecting intent


def test_modulr_sepa_stub_raises_not_implemented_on_get_status() -> None:
    stub = ModulrSepaStub()
    with pytest.raises(NotImplementedError, match="MODULR_API_KEY"):
        stub.get_payment_status("pay-001")


# ── MidazCryptoStub ───────────────────────────────────────────────────────────


def test_midaz_crypto_stub_raises_not_implemented_on_create_tx() -> None:
    from unittest.mock import Mock

    stub = MidazCryptoStub()
    with pytest.raises(NotImplementedError, match="MIDAZ_API_KEY"):
        stub.create_tx(Mock())  # stub raises before inspecting request


def test_midaz_crypto_stub_raises_not_implemented_on_get_balance() -> None:
    from services.ledger.crypto_ledger_port import SupportedBlockchain

    stub = MidazCryptoStub()
    with pytest.raises(NotImplementedError, match="MIDAZ_API_KEY"):
        stub.get_balance("wallet-001", SupportedBlockchain.BTC)


# ── SumsubHttpStub ────────────────────────────────────────────────────────────


def test_sumsub_http_stub_raises_not_implemented_on_create_workflow() -> None:
    from decimal import Decimal

    from services.kyc.kyc_port import KYCType, KYCWorkflowRequest

    stub = SumsubHttpStub()
    with pytest.raises(NotImplementedError, match="SUMSUB_APP_TOKEN"):
        stub.create_workflow(
            KYCWorkflowRequest(
                customer_id="cust-001",
                kyc_type=KYCType.INDIVIDUAL,
                first_name="Jane",
                last_name="Doe",
                date_of_birth="1990-01-01",
                nationality="GB",
                country_of_residence="GB",
                expected_transaction_volume=Decimal("5000"),
                is_pep=False,
            )
        )


def test_sumsub_http_stub_raises_not_implemented_on_approve_edd() -> None:
    stub = SumsubHttpStub()
    with pytest.raises(NotImplementedError, match="I-27"):
        stub.approve_edd("wf-001", "mlro-user-001")
