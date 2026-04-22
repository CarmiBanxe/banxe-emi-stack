"""Tests for adorsys_client.py — create_consent, get_accounts, transactions, I-02, BT-007.

IL-PSD2GW-01 | Phase 52B | Sprint 37
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.psd2_gateway.adorsys_client import AdorsysClient
from services.psd2_gateway.psd2_models import (
    ConsentRequest,
    InMemoryConsentStore,
    InMemoryTransactionStore,
)

_GB_IBAN = "GB29NWBK60161331926819"
_DE_IBAN = "DE89370400440532013000"
_VALID_UNTIL = "2027-01-01"


def _make_client() -> tuple[AdorsysClient, InMemoryConsentStore, InMemoryTransactionStore]:
    consent_store = InMemoryConsentStore()
    txn_store = InMemoryTransactionStore()
    client = AdorsysClient(consent_store=consent_store, txn_store=txn_store)
    return client, consent_store, txn_store


def _req(iban: str = _GB_IBAN, valid_until: str = _VALID_UNTIL) -> ConsentRequest:
    """Helper: build ConsentRequest with short variable references."""
    return ConsentRequest(iban=iban, access_type="allAccounts", valid_until=valid_until)


# ── _check_iban (I-02) ─────────────────────────────────────────────────────


def test_check_iban_blocked_ru() -> None:
    """I-02: Russian IBAN must raise ValueError."""
    client, _, _ = _make_client()
    with pytest.raises(ValueError, match="I-02"):
        client._check_iban("RU1234567890")


def test_check_iban_blocked_by() -> None:
    """I-02: Belarusian IBAN."""
    client, _, _ = _make_client()
    with pytest.raises(ValueError, match="I-02"):
        client._check_iban("BY20NBRB3600900000002Z00AB00")


def test_check_iban_blocked_ir() -> None:
    """I-02: Iranian IBAN."""
    client, _, _ = _make_client()
    with pytest.raises(ValueError, match="I-02"):
        client._check_iban("IR800570029971601460641001")


def test_check_iban_gb_passes() -> None:
    client, _, _ = _make_client()
    client._check_iban(_GB_IBAN)  # must not raise


def test_check_iban_de_passes() -> None:
    client, _, _ = _make_client()
    client._check_iban(_DE_IBAN)  # must not raise


# ── create_consent ─────────────────────────────────────────────────────────


def test_create_consent_returns_consent_response() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    assert consent.consent_id.startswith("cns_")
    assert consent.status == "valid"
    assert consent.iban == _GB_IBAN


def test_create_consent_appends_to_store() -> None:
    """I-24: create_consent must append to store."""
    client, consent_store, _ = _make_client()
    client.create_consent(_req())
    assert len(consent_store.list_active()) == 1


def test_create_consent_blocked_iban_raises() -> None:
    """I-02: Create consent with blocked IBAN raises ValueError."""
    client, _, _ = _make_client()
    with pytest.raises(ValueError, match="I-02"):
        client.create_consent(_req(iban="RU1234567890"))


def test_create_consent_deterministic_id() -> None:
    """Same IBAN + date = same consent_id."""
    client1, _, _ = _make_client()
    client2, _, _ = _make_client()
    c1 = client1.create_consent(_req())
    c2 = client2.create_consent(_req())
    assert c1.consent_id == c2.consent_id


def test_create_consent_valid_until_preserved() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req(valid_until="2027-06-30"))
    assert consent.valid_until == "2027-06-30"


def test_create_consent_has_created_at() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    assert "T" in consent.created_at  # ISO format


# ── get_accounts ───────────────────────────────────────────────────────────


def test_get_accounts_returns_list() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    assert len(accounts) == 1


def test_get_accounts_account_id_not_empty() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    assert accounts[0].account_id.startswith("acc_")


def test_get_accounts_currency_gbp() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    assert accounts[0].currency == "GBP"


def test_get_accounts_missing_consent_raises() -> None:
    client, _, _ = _make_client()
    with pytest.raises(KeyError):
        client.get_accounts("nonexistent_consent")


# ── get_transactions ───────────────────────────────────────────────────────


def test_get_transactions_returns_list() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    txns = client.get_transactions(
        consent.consent_id, accounts[0].account_id, "2026-01-01", "2026-01-31"
    )
    assert len(txns) >= 1


def test_get_transactions_amount_is_decimal() -> None:
    """I-01: Transaction amounts must be Decimal."""
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    txns = client.get_transactions(
        consent.consent_id, accounts[0].account_id, "2026-01-01", "2026-01-31"
    )
    for txn in txns:
        assert isinstance(txn.amount, Decimal)
        assert not isinstance(txn.amount, float)


def test_get_transactions_appends_to_store() -> None:
    """I-24: Transactions must be appended."""
    client, consent_store, txn_store = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    client.get_transactions(consent.consent_id, accounts[0].account_id, "2026-01-01", "2026-01-31")
    assert len(txn_store.list_by_account(accounts[0].account_id)) >= 1


def test_get_transactions_missing_consent_raises() -> None:
    client, _, _ = _make_client()
    with pytest.raises(KeyError):
        client.get_transactions("nonexistent", "acc_001", "2026-01-01", "2026-01-31")


# ── get_balances ───────────────────────────────────────────────────────────


def test_get_balances_returns_response() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    bal = client.get_balances(consent.consent_id, accounts[0].account_id)
    assert bal.balance_amount > 0


def test_get_balances_amount_is_decimal() -> None:
    """I-01: Balance must be Decimal."""
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    bal = client.get_balances(consent.consent_id, accounts[0].account_id)
    assert isinstance(bal.balance_amount, Decimal)
    assert not isinstance(bal.balance_amount, float)


def test_get_balances_currency_gbp() -> None:
    client, _, _ = _make_client()
    consent = client.create_consent(_req())
    accounts = client.get_accounts(consent.consent_id)
    bal = client.get_balances(consent.consent_id, accounts[0].account_id)
    assert bal.currency == "GBP"


def test_get_balances_missing_consent_raises() -> None:
    client, _, _ = _make_client()
    with pytest.raises(KeyError):
        client.get_balances("nonexistent", "acc_001")


# ── BT-007: initiate_payment_via_psd2 ─────────────────────────────────────


def test_initiate_payment_raises_not_implemented() -> None:
    """BT-007: PISP payment stub must raise NotImplementedError."""
    client, _, _ = _make_client()
    with pytest.raises(NotImplementedError, match="BT-007"):
        client.initiate_payment_via_psd2()
