"""Tests for psd2_models.py — frozen dataclasses, Decimal I-01, InMemory stores.

IL-PSD2GW-01 | Phase 52B | Sprint 37
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from services.psd2_gateway.psd2_models import (
    BLOCKED_JURISDICTIONS,
    AccountInfo,
    BalanceResponse,
    ConsentRequest,
    ConsentResponse,
    InMemoryConsentStore,
    InMemoryTransactionStore,
    Transaction,
    _iban_country,
)

# ── _iban_country ──────────────────────────────────────────────────────────


def test_iban_country_gb() -> None:
    assert _iban_country("GB29NWBK60161331926819") == "GB"


def test_iban_country_de() -> None:
    assert _iban_country("DE89370400440532013000") == "DE"


def test_iban_country_ru_detected() -> None:
    assert _iban_country("RU1234567890") == "RU"


def test_iban_country_short() -> None:
    assert _iban_country("X") == ""


def test_iban_country_empty() -> None:
    assert _iban_country("") == ""


# ── BLOCKED_JURISDICTIONS (I-02) ───────────────────────────────────────────


def test_blocked_jurisdictions_contains_ru() -> None:
    assert "RU" in BLOCKED_JURISDICTIONS


def test_blocked_jurisdictions_contains_by() -> None:
    assert "BY" in BLOCKED_JURISDICTIONS


def test_blocked_jurisdictions_contains_ir() -> None:
    assert "IR" in BLOCKED_JURISDICTIONS


def test_blocked_jurisdictions_contains_kp() -> None:
    assert "KP" in BLOCKED_JURISDICTIONS


def test_gb_not_blocked() -> None:
    assert "GB" not in BLOCKED_JURISDICTIONS


# ── ConsentRequest ─────────────────────────────────────────────────────────


def test_consent_request_frozen() -> None:
    req = ConsentRequest(
        iban="GB29NWBK60161331926819",
        access_type="allAccounts",
        valid_until="2027-01-01",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        req.iban = "DE89370400440532013000"  # type: ignore[misc]


def test_consent_request_defaults() -> None:
    req = ConsentRequest(
        iban="GB29NWBK60161331926819",
        access_type="allAccounts",
        valid_until="2027-01-01",
    )
    assert req.recurring_indicator is True
    assert req.frequency_per_day == 4


# ── ConsentResponse ────────────────────────────────────────────────────────


def test_consent_response_frozen() -> None:
    resp = ConsentResponse(
        consent_id="cns_001",
        status="valid",
        valid_until="2027-01-01",
        iban="GB29NWBK60161331926819",
        created_at="2026-01-01T00:00:00Z",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        resp.status = "expired"  # type: ignore[misc]


# ── Transaction ────────────────────────────────────────────────────────────


def test_transaction_frozen() -> None:
    txn = Transaction(
        transaction_id="txn_001",
        amount=Decimal("100.00"),
        currency="GBP",
        creditor_name="Creditor",
        debtor_name=None,
        booking_date="2026-01-01",
        value_date="2026-01-01",
        reference="Test",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        txn.amount = Decimal("200.00")  # type: ignore[misc]


def test_transaction_amount_is_decimal() -> None:
    """I-01: Transaction amount must be Decimal."""
    txn = Transaction(
        transaction_id="txn_001",
        amount=Decimal("1500.00"),
        currency="GBP",
        creditor_name=None,
        debtor_name=None,
        booking_date="2026-01-01",
        value_date="2026-01-01",
        reference=None,
    )
    assert isinstance(txn.amount, Decimal)
    assert not isinstance(txn.amount, float)


def test_transaction_amount_not_float() -> None:
    """I-01: Never use float for money."""
    txn = Transaction(
        transaction_id="txn_001",
        amount=Decimal("50.00"),
        currency="GBP",
        creditor_name=None,
        debtor_name=None,
        booking_date="2026-01-01",
        value_date="2026-01-01",
        reference=None,
    )
    assert not isinstance(txn.amount, float)


# ── BalanceResponse ────────────────────────────────────────────────────────


def test_balance_response_frozen() -> None:
    bal = BalanceResponse(
        account_id="acc_001",
        iban="GB29NWBK60161331926819",
        currency="GBP",
        balance_amount=Decimal("50000.00"),
        balance_type="closingBooked",
        last_change_date_time="2026-01-01T00:00:00Z",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        bal.balance_amount = Decimal("60000.00")  # type: ignore[misc]


def test_balance_response_amount_is_decimal() -> None:
    """I-01: Balance amount must be Decimal."""
    bal = BalanceResponse(
        account_id="acc_001",
        iban="GB29NWBK60161331926819",
        currency="GBP",
        balance_amount=Decimal("50000.00"),
        balance_type="closingBooked",
        last_change_date_time="2026-01-01T00:00:00Z",
    )
    assert isinstance(bal.balance_amount, Decimal)


# ── InMemoryConsentStore ───────────────────────────────────────────────────


def test_in_memory_consent_store_append() -> None:
    """I-24: append-only."""
    store = InMemoryConsentStore()
    consent = ConsentResponse(
        consent_id="cns_001",
        status="valid",
        valid_until="2027-01-01",
        iban="GB29NWBK60161331926819",
        created_at="2026-01-01T00:00:00Z",
    )
    store.append(consent)
    assert store.get("cns_001") is not None


def test_in_memory_consent_store_get_missing() -> None:
    store = InMemoryConsentStore()
    assert store.get("nonexistent") is None


def test_in_memory_consent_store_list_active() -> None:
    store = InMemoryConsentStore()
    consent = ConsentResponse(
        consent_id="cns_valid",
        status="valid",
        valid_until="2027-01-01",
        iban="GB29NWBK60161331926819",
        created_at="2026-01-01T00:00:00Z",
    )
    expired = ConsentResponse(
        consent_id="cns_expired",
        status="expired",
        valid_until="2025-01-01",
        iban="DE89370400440532013000",
        created_at="2025-01-01T00:00:00Z",
    )
    store.append(consent)
    store.append(expired)
    active = store.list_active()
    assert len(active) == 1
    assert active[0].consent_id == "cns_valid"


# ── InMemoryTransactionStore ───────────────────────────────────────────────


def test_in_memory_transaction_store_append() -> None:
    """I-24: append-only."""
    store = InMemoryTransactionStore()
    txn = Transaction(
        transaction_id="txn_001",
        amount=Decimal("100.00"),
        currency="GBP",
        creditor_name=None,
        debtor_name=None,
        booking_date="2026-01-01",
        value_date="2026-01-01",
        reference=None,
    )
    store.append(txn)
    result = store.list_by_account("acc_001")
    assert len(result) == 1


def test_in_memory_transaction_store_multiple() -> None:
    store = InMemoryTransactionStore()
    for i in range(3):
        store.append(
            Transaction(
                transaction_id=f"txn_{i:03d}",
                amount=Decimal("100.00"),
                currency="GBP",
                creditor_name=None,
                debtor_name=None,
                booking_date="2026-01-01",
                value_date="2026-01-01",
                reference=None,
            )
        )
    assert len(store.list_by_account("acc_any")) == 3


# ── AccountInfo ────────────────────────────────────────────────────────────


def test_account_info_frozen() -> None:
    acc = AccountInfo(
        account_id="acc_001",
        iban="GB29NWBK60161331926819",
        currency="GBP",
        account_type="CACC",
        name="Banxe Account",
    )
    with pytest.raises((FrozenInstanceError, AttributeError)):
        acc.account_id = "acc_002"  # type: ignore[misc]


def test_account_info_optional_name() -> None:
    acc = AccountInfo(
        account_id="acc_001",
        iban="GB29NWBK60161331926819",
        currency="GBP",
        account_type="CACC",
        name=None,
    )
    assert acc.name is None
