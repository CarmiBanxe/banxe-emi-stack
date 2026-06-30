"""
test_sandbox_service.py — Tests for sandbox service (InMemorySandboxService)
GAP-042 M-sandbox: Sandbox Mock Rails Service
banxe-emi-stack
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from services.sandbox.sandbox_service import InMemorySandboxService


@pytest.fixture
def service() -> InMemorySandboxService:
    """Create a fresh sandbox service for each test."""
    svc = InMemorySandboxService()
    yield svc
    svc.reset()


def test_seed_account_creates_account(service: InMemorySandboxService) -> None:
    account = service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    assert account.account_id == "ACC001"
    assert account.holder_name == "John Doe"
    assert account.currency == "GBP"
    assert account.balance == Decimal("1000")


def test_seed_account_overwrite_updates_balance(
    service: InMemorySandboxService,
) -> None:
    service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    account = service.seed_account("ACC001", "John Doe", "GBP", Decimal("2000"))
    assert account.balance == Decimal("2000")


def test_seed_account_negative_balance_raises(
    service: InMemorySandboxService,
) -> None:
    with pytest.raises(ValueError, match="balance must be >= 0"):
        service.seed_account("ACC001", "John Doe", "GBP", Decimal("-100"))


def test_seed_account_zero_balance_allowed(
    service: InMemorySandboxService,
) -> None:
    account = service.seed_account("ACC001", "John Doe", "GBP", Decimal("0"))
    assert account.balance == Decimal("0")


def test_get_account_existing(service: InMemorySandboxService) -> None:
    service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    account = service.get_account("ACC001")
    assert account is not None
    assert account.account_id == "ACC001"


def test_get_account_missing_returns_none(
    service: InMemorySandboxService,
) -> None:
    account = service.get_account("NONEXISTENT")
    assert account is None


def test_list_accounts_empty(service: InMemorySandboxService) -> None:
    accounts = service.list_accounts()
    assert accounts == []


def test_list_accounts_multiple(service: InMemorySandboxService) -> None:
    service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    service.seed_account("ACC002", "Jane Smith", "EUR", Decimal("2000"))
    service.seed_account("ACC003", "Bob Brown", "GBP", Decimal("3000"))
    accounts = service.list_accounts()
    assert len(accounts) == 3
    ids = {acc.account_id for acc in accounts}
    assert ids == {"ACC001", "ACC002", "ACC003"}


def test_advance_payment_pending_to_processing(
    service: InMemorySandboxService,
) -> None:
    service.register_payment("PAY001", "PENDING")
    transition = service.advance_payment("PAY001", "PROCESSING")
    assert transition.payment_id == "PAY001"
    assert transition.from_status == "PENDING"
    assert transition.to_status == "PROCESSING"


def test_advance_payment_processing_to_completed(
    service: InMemorySandboxService,
) -> None:
    service.register_payment("PAY001", "PROCESSING")
    transition = service.advance_payment("PAY001", "COMPLETED")
    assert transition.from_status == "PROCESSING"
    assert transition.to_status == "COMPLETED"


def test_advance_payment_processing_to_failed(
    service: InMemorySandboxService,
) -> None:
    service.register_payment("PAY001", "PROCESSING")
    transition = service.advance_payment("PAY001", "FAILED")
    assert transition.from_status == "PROCESSING"
    assert transition.to_status == "FAILED"


def test_advance_payment_invalid_transition_raises(
    service: InMemorySandboxService,
) -> None:
    service.register_payment("PAY001", "PENDING")
    with pytest.raises(ValueError, match="invalid transition"):
        service.advance_payment("PAY001", "FAILED")


def test_advance_payment_unknown_payment_raises(
    service: InMemorySandboxService,
) -> None:
    service.register_payment("PAY001", "PENDING")
    with pytest.raises(ValueError, match="payment PAY002 not registered"):
        service.advance_payment("PAY002", "PROCESSING")


def test_reset_clears_state(service: InMemorySandboxService) -> None:
    service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    service.register_payment("PAY001", "PENDING")
    service.reset()
    assert service.account_count() == 0
    assert service.get_account("ACC001") is None


def test_account_count(service: InMemorySandboxService) -> None:
    assert service.account_count() == 0
    service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    assert service.account_count() == 1
    service.seed_account("ACC002", "Jane Smith", "EUR", Decimal("2000"))
    assert service.account_count() == 2


def test_decimal_precision_preserved(service: InMemorySandboxService) -> None:
    balance = Decimal("1234.567890")
    account = service.seed_account("ACC001", "John Doe", "GBP", balance)
    assert account.balance == Decimal("1234.567890")
    assert str(account.balance) == "1234.567890"


def test_seed_multiple_currencies(service: InMemorySandboxService) -> None:
    service.seed_account("ACC001", "John Doe", "GBP", Decimal("1000"))
    service.seed_account("ACC002", "Jane Smith", "EUR", Decimal("2000"))
    service.seed_account("ACC003", "Bob Brown", "USD", Decimal("3000"))
    accounts = service.list_accounts()
    assert len(accounts) == 3
    currencies = {acc.currency for acc in accounts}
    assert currencies == {"GBP", "EUR", "USD"}
