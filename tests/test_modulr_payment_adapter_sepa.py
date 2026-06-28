"""SEPA input-validation tests for the LIVE Modulr rail (ModulrPaymentAdapter).

Validation runs BEFORE any network call, so invalid SEPA input returns a FAILED PaymentResult
with no HTTP request. No live API calls; no secrets.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.payment.modulr_client import ModulrPaymentAdapter
from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentStatus,
)


def _intent(
    *,
    rail: PaymentRail = PaymentRail.SEPA_CT,
    iban: str = "DE89370400440532013000",
    bic: str = "DEUTDEFF",
    amount: str = "100.00",
) -> PaymentIntent:
    return PaymentIntent(
        idempotency_key="idem-1",
        rail=rail,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal(amount),
        currency="EUR",
        debtor_account=BankAccount(account_holder_name="Banxe EUR", iban="DE89370400440532013000"),
        creditor_account=BankAccount(account_holder_name="Jane Doe", iban=iban, bic=bic),
        reference="ref",
        end_to_end_id="e2e-1",
        requested_at=datetime.now(UTC),
    )


@pytest.fixture
def adapter() -> ModulrPaymentAdapter:
    return ModulrPaymentAdapter()


def test_sepa_invalid_iban_rejected_before_network(adapter: ModulrPaymentAdapter) -> None:
    result = adapter.submit_payment(_intent(iban="DE00INVALID0000000000"))
    assert result.status is PaymentStatus.FAILED
    assert result.error_code == "invalid_iban"
    assert result.provider_payment_id == ""


def test_sepa_invalid_bic_rejected(adapter: ModulrPaymentAdapter) -> None:
    result = adapter.submit_payment(_intent(bic="BAD"))
    assert result.status is PaymentStatus.FAILED
    assert result.error_code == "invalid_bic"


def test_sepa_instant_over_cap_rejected(adapter: ModulrPaymentAdapter) -> None:
    result = adapter.submit_payment(_intent(rail=PaymentRail.SEPA_INSTANT, amount="100000.01"))
    assert result.status is PaymentStatus.FAILED
    assert result.error_code == "amount_exceeds_sct_inst_max"


def test_valid_sepa_input_passes_validation_gate(adapter: ModulrPaymentAdapter) -> None:
    # SCT (non-instant) has no €100k cap and the IBAN/BIC are valid → the validation gate
    # returns None (would proceed to the network call, which we do not exercise here).
    assert adapter._validate_sepa(_intent(rail=PaymentRail.SEPA_CT, amount="250000.00")) is None
    assert (
        adapter._validate_sepa(_intent(rail=PaymentRail.SEPA_INSTANT, amount="100000.00")) is None
    )
