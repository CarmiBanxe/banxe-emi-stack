"""
tests/test_consent_management/test_consent_validator.py
Tests for ConsentValidator: scope coverage, transaction limit, expiry.
IL-CNS-01 | Phase 49 | Sprint 35

≥20 tests covering:
- check_scope_coverage (full, partial, empty, unknown)
- check_transaction_limit (within, over, no limit, I-01 Decimal)
- is_consent_valid (active, revoked, expired, unknown)
- get_consent_summary (counts by status)
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from services.consent_management.consent_validator import ConsentValidator
from services.consent_management.models import (
    ConsentGrant,
    ConsentScope,
    ConsentStatus,
    ConsentType,
    InMemoryConsentStore,
)


def make_store_with_consent(
    consent_id: str = "cns_001",
    customer_id: str = "cust_001",
    scopes: list[ConsentScope] | None = None,
    status: ConsentStatus = ConsentStatus.ACTIVE,
    expires_in_days: int = 90,
    transaction_limit: Decimal | None = None,
) -> tuple[ConsentValidator, InMemoryConsentStore]:
    store = InMemoryConsentStore()
    validator = ConsentValidator(store)
    now = datetime.now(UTC)
    consent = ConsentGrant(
        consent_id=consent_id,
        customer_id=customer_id,
        tpp_id="tpp_test",
        consent_type=ConsentType.AISP,
        scopes=scopes or [ConsentScope.ACCOUNTS, ConsentScope.BALANCES],
        granted_at=now.isoformat(),
        expires_at=(now + timedelta(days=expires_in_days)).isoformat(),
        status=status,
        transaction_limit=transaction_limit,
        redirect_uri="https://example.com",
    )
    store.save(consent)
    return validator, store


# ── check_scope_coverage tests ────────────────────────────────────────────────


def test_check_scope_coverage_all_covered_returns_true() -> None:
    """Test scope coverage returns True when all scopes present."""
    validator, _ = make_store_with_consent(
        scopes=[ConsentScope.ACCOUNTS, ConsentScope.BALANCES, ConsentScope.TRANSACTIONS]
    )
    assert (
        validator.check_scope_coverage("cns_001", [ConsentScope.ACCOUNTS, ConsentScope.BALANCES])
        is True
    )


def test_check_scope_coverage_missing_scope_returns_false() -> None:
    """Test scope coverage returns False when scope not in consent."""
    validator, _ = make_store_with_consent(scopes=[ConsentScope.ACCOUNTS])
    assert validator.check_scope_coverage("cns_001", [ConsentScope.PAYMENTS]) is False


def test_check_scope_coverage_empty_requested_returns_true() -> None:
    """Test empty requested scopes returns True (vacuously true)."""
    validator, _ = make_store_with_consent()
    assert validator.check_scope_coverage("cns_001", []) is True


def test_check_scope_coverage_unknown_consent_returns_false() -> None:
    """Test unknown consent_id returns False."""
    validator, _ = make_store_with_consent()
    assert validator.check_scope_coverage("cns_unknown", [ConsentScope.ACCOUNTS]) is False


def test_check_scope_coverage_single_scope() -> None:
    """Test single scope check passes when present."""
    validator, _ = make_store_with_consent(scopes=[ConsentScope.TRANSACTIONS])
    assert validator.check_scope_coverage("cns_001", [ConsentScope.TRANSACTIONS]) is True


# ── check_transaction_limit tests ─────────────────────────────────────────────


def test_check_transaction_limit_no_limit_returns_true() -> None:
    """Test check_transaction_limit returns True when no limit set."""
    validator, _ = make_store_with_consent(transaction_limit=None)
    assert validator.check_transaction_limit("cns_001", Decimal("9999.99")) is True


def test_check_transaction_limit_within_limit_returns_true() -> None:
    """Test check_transaction_limit returns True when amount <= limit (I-01: Decimal)."""
    validator, _ = make_store_with_consent(transaction_limit=Decimal("500.00"))
    assert validator.check_transaction_limit("cns_001", Decimal("499.99")) is True


def test_check_transaction_limit_at_limit_returns_true() -> None:
    """Test check_transaction_limit returns True when amount == limit exactly."""
    validator, _ = make_store_with_consent(transaction_limit=Decimal("500.00"))
    assert validator.check_transaction_limit("cns_001", Decimal("500.00")) is True


def test_check_transaction_limit_over_limit_returns_false() -> None:
    """Test check_transaction_limit returns False when amount > limit (I-01)."""
    validator, _ = make_store_with_consent(transaction_limit=Decimal("500.00"))
    assert validator.check_transaction_limit("cns_001", Decimal("500.01")) is False


def test_check_transaction_limit_decimal_precision() -> None:
    """Test transaction limit comparison uses Decimal precision (I-01)."""
    validator, _ = make_store_with_consent(transaction_limit=Decimal("100.001"))
    assert validator.check_transaction_limit("cns_001", Decimal("100.001")) is True
    assert validator.check_transaction_limit("cns_001", Decimal("100.002")) is False


def test_check_transaction_limit_unknown_consent_returns_false() -> None:
    """Test check_transaction_limit returns False for unknown consent."""
    validator, _ = make_store_with_consent()
    assert validator.check_transaction_limit("cns_unknown", Decimal("100")) is False


# ── is_consent_valid tests ────────────────────────────────────────────────────


def test_is_consent_valid_active_returns_true() -> None:
    """Test is_consent_valid returns True for active, non-expired consent."""
    validator, _ = make_store_with_consent(status=ConsentStatus.ACTIVE)
    assert validator.is_consent_valid("cns_001") is True


def test_is_consent_valid_revoked_returns_false() -> None:
    """Test is_consent_valid returns False for REVOKED consent."""
    validator, _ = make_store_with_consent(status=ConsentStatus.REVOKED)
    assert validator.is_consent_valid("cns_001") is False


def test_is_consent_valid_pending_returns_false() -> None:
    """Test is_consent_valid returns False for PENDING consent."""
    validator, _ = make_store_with_consent(status=ConsentStatus.PENDING)
    assert validator.is_consent_valid("cns_001") is False


def test_is_consent_valid_expired_returns_false() -> None:
    """Test is_consent_valid returns False for expired consent."""
    store = InMemoryConsentStore()
    validator = ConsentValidator(store)
    now = datetime.now(UTC)
    # Expired consent: granted 2 days ago, expires 1 day ago
    consent = ConsentGrant(
        consent_id="cns_expired",
        customer_id="c1",
        tpp_id="tpp_test",
        consent_type=ConsentType.AISP,
        scopes=[ConsentScope.ACCOUNTS],
        granted_at=(now - timedelta(days=2)).isoformat(),
        expires_at=(now - timedelta(days=1)).isoformat(),
        status=ConsentStatus.ACTIVE,
        redirect_uri="https://example.com",
    )
    store.save(consent)
    assert validator.is_consent_valid("cns_expired") is False


def test_is_consent_valid_unknown_returns_false() -> None:
    """Test is_consent_valid returns False for unknown consent."""
    validator, _ = make_store_with_consent()
    assert validator.is_consent_valid("cns_unknown") is False


# ── get_consent_summary tests ─────────────────────────────────────────────────


def test_get_consent_summary_active_count() -> None:
    """Test get_consent_summary counts active consents."""
    validator, _ = make_store_with_consent(status=ConsentStatus.ACTIVE)
    summary = validator.get_consent_summary("cust_001")
    assert summary["active_count"] == 1


def test_get_consent_summary_revoked_count() -> None:
    """Test get_consent_summary counts revoked consents."""
    validator, _ = make_store_with_consent(status=ConsentStatus.REVOKED)
    summary = validator.get_consent_summary("cust_001")
    assert summary["revoked_count"] == 1


def test_get_consent_summary_empty_for_unknown() -> None:
    """Test get_consent_summary returns zeros for unknown customer."""
    validator, _ = make_store_with_consent()
    summary = validator.get_consent_summary("cust_unknown")
    assert summary["active_count"] == 0
    assert summary["total_count"] == 0
