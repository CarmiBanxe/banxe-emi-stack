"""tests/test_multi_currency/test_models.py — Model, enum, and seed data tests."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.multi_currency.models import (
    _NOSTRO_ACCOUNTS,
    _SUPPORTED_CURRENCIES,
    ConversionRecord,
    ConversionStatus,
    CurrencyBalance,
    LedgerEntry,
    MCEventEntry,
    MultiCurrencyAccount,
    NostroAccount,
    NostroType,
    ReconciliationResult,
    ReconciliationStatus,
    RoutingStrategy,
)

# ── Enum tests ─────────────────────────────────────────────────────────────────


def test_reconciliation_status_values() -> None:
    assert ReconciliationStatus.MATCHED.value == "MATCHED"
    assert ReconciliationStatus.DISCREPANCY.value == "DISCREPANCY"
    assert ReconciliationStatus.PENDING.value == "PENDING"


def test_conversion_status_values() -> None:
    assert ConversionStatus.COMPLETED.value == "COMPLETED"
    assert ConversionStatus.PENDING.value == "PENDING"
    assert ConversionStatus.FAILED.value == "FAILED"


def test_nostro_type_values() -> None:
    assert NostroType.NOSTRO.value == "NOSTRO"
    assert NostroType.VOSTRO.value == "VOSTRO"
    assert NostroType.LORO.value == "LORO"


def test_routing_strategy_values() -> None:
    assert RoutingStrategy.CHEAPEST.value == "CHEAPEST"
    assert RoutingStrategy.FASTEST.value == "FASTEST"
    assert RoutingStrategy.DIRECT.value == "DIRECT"


# ── CurrencyBalance tests ──────────────────────────────────────────────────────


def test_currency_balance_fields() -> None:
    bal = CurrencyBalance(
        currency="GBP",
        amount=Decimal("100.00"),
        available=Decimal("90.00"),
        reserved=Decimal("10.00"),
    )
    assert bal.currency == "GBP"
    assert bal.amount == Decimal("100.00")
    assert bal.available == Decimal("90.00")
    assert bal.reserved == Decimal("10.00")


def test_currency_balance_is_frozen() -> None:
    bal = CurrencyBalance("GBP", Decimal("0"), Decimal("0"), Decimal("0"))
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass
        bal.currency = "EUR"  # type: ignore[misc]


def test_currency_balance_uses_decimal_not_float() -> None:
    bal = CurrencyBalance("EUR", Decimal("50"), Decimal("50"), Decimal("0"))
    assert isinstance(bal.amount, Decimal)
    assert isinstance(bal.available, Decimal)


# ── MultiCurrencyAccount tests ─────────────────────────────────────────────────


def test_multi_currency_account_fields() -> None:
    now = datetime.now(UTC)
    bal = CurrencyBalance("GBP", Decimal("0"), Decimal("0"), Decimal("0"))
    acct = MultiCurrencyAccount(
        account_id="mc-001",
        entity_id="ent-001",
        base_currency="GBP",
        balances=(bal,),
        created_at=now,
    )
    assert acct.account_id == "mc-001"
    assert acct.entity_id == "ent-001"
    assert acct.base_currency == "GBP"
    assert acct.max_currencies == 10
    assert len(acct.balances) == 1


def test_multi_currency_account_is_frozen() -> None:
    now = datetime.now(UTC)
    acct = MultiCurrencyAccount(
        account_id="mc-002",
        entity_id="ent-002",
        base_currency="EUR",
        balances=(),
        created_at=now,
    )
    with pytest.raises(Exception):  # noqa: B017 — frozen dataclass
        acct.entity_id = "other"  # type: ignore[misc]


# ── NostroAccount tests ────────────────────────────────────────────────────────


def test_nostro_account_fields() -> None:
    acct = NostroAccount(
        account_id="nostro-001",
        bank_name="Barclays",
        currency="GBP",
        our_balance=Decimal("1_000_000"),
        their_balance=Decimal("1_000_000"),
        account_type=NostroType.NOSTRO,
    )
    assert acct.account_id == "nostro-001"
    assert acct.our_balance == Decimal("1000000")
    assert acct.last_reconciled is None


def test_nostro_account_last_reconciled_optional() -> None:
    acct = NostroAccount(
        account_id="n-001",
        bank_name="HSBC",
        currency="USD",
        our_balance=Decimal("500000"),
        their_balance=Decimal("500000"),
        account_type=NostroType.VOSTRO,
        last_reconciled=datetime.now(UTC),
    )
    assert acct.last_reconciled is not None


# ── Seed data tests ────────────────────────────────────────────────────────────


def test_supported_currencies_count() -> None:
    assert len(_SUPPORTED_CURRENCIES) == 10


def test_supported_currencies_contains_gbp_eur_usd() -> None:
    assert "GBP" in _SUPPORTED_CURRENCIES
    assert "EUR" in _SUPPORTED_CURRENCIES
    assert "USD" in _SUPPORTED_CURRENCIES


def test_supported_currencies_no_sanctioned() -> None:
    sanctioned = {"RUB", "IRR", "KPW", "BYR", "SYP"}
    assert not sanctioned.intersection(_SUPPORTED_CURRENCIES)


def test_nostro_accounts_seeded() -> None:
    assert len(_NOSTRO_ACCOUNTS) == 2


def test_nostro_gbp_seed() -> None:
    gbp = next(n for n in _NOSTRO_ACCOUNTS if n.account_id == "nostro-gbp-001")
    assert gbp.bank_name == "Barclays"
    assert gbp.currency == "GBP"
    assert gbp.our_balance == Decimal("5000000")


def test_nostro_eur_seed() -> None:
    eur = next(n for n in _NOSTRO_ACCOUNTS if n.account_id == "nostro-eur-001")
    assert eur.bank_name == "BNP Paribas"
    assert eur.currency == "EUR"
    assert eur.our_balance == Decimal("3000000")


# ── LedgerEntry / MCEventEntry / ConversionRecord / ReconciliationResult ───────


def test_ledger_entry_fields() -> None:
    now = datetime.now(UTC)
    entry = LedgerEntry(
        entry_id="e-001",
        account_id="mc-001",
        currency="GBP",
        amount=Decimal("100"),
        direction="CREDIT",
        description="test",
        created_at=now,
    )
    assert entry.direction == "CREDIT"
    assert isinstance(entry.amount, Decimal)


def test_mc_event_entry_fields() -> None:
    now = datetime.now(UTC)
    evt = MCEventEntry(
        event_id="ev-001",
        account_id="mc-001",
        event_type="ACCOUNT_CREATED",
        currency="GBP",
        amount=Decimal("0"),
        created_at=now,
    )
    assert evt.event_type == "ACCOUNT_CREATED"


def test_conversion_record_fields() -> None:
    now = datetime.now(UTC)
    rec = ConversionRecord(
        conversion_id="conv-001",
        account_id="mc-001",
        from_currency="GBP",
        to_currency="EUR",
        from_amount=Decimal("100"),
        to_amount=Decimal("116"),
        rate=Decimal("1.16"),
        fee=Decimal("0.20"),
        status=ConversionStatus.COMPLETED,
        created_at=now,
    )
    assert rec.status == ConversionStatus.COMPLETED
    assert isinstance(rec.fee, Decimal)


def test_reconciliation_result_fields() -> None:
    now = datetime.now(UTC)
    result = ReconciliationResult(
        nostro_id="nostro-001",
        our_balance=Decimal("1000"),
        their_balance=Decimal("999"),
        variance=Decimal("1"),
        status=ReconciliationStatus.MATCHED,
        reconciled_at=now,
    )
    assert result.variance == Decimal("1")
    assert result.status == ReconciliationStatus.MATCHED
