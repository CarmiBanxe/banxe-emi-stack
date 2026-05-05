"""
tests/test_gl_service.py
Tests for GLService — double-entry bookkeeping (IL-FIN-01).

Acceptance criteria:
- test_double_entry_debit_credit_balanced (Decimal, I-01)
- test_journal_entry_immutable (I-24)
- test_multi_currency_posting (GBP/EUR/USD)
- test_blocked_jurisdiction_account_rejected (I-02)
- test_high_value_posting_flagged (I-04)
- test_gl_audit_trail_complete (I-24)
"""

from decimal import Decimal

import pytest

from services.ledger.gl_service import (
    GLService,
    HighValueHITLProposal,
    InMemoryGLAuditPort,
    JurisdictionBlockedError,
    UnbalancedEntryError,
)
from services.ledger.inmemory_ledger import InMemoryLedger
from services.ledger.ledger_models import (
    BLOCKED_JURISDICTIONS,
    HIGH_VALUE_THRESHOLD,
    SUPPORTED_CURRENCIES,
    Account,
    AccountType,
    GLAuditEntry,
    JournalEntry,
    Posting,
    PostingDirection,
    PostingStatus,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def ledger():
    return InMemoryLedger()


@pytest.fixture
def audit():
    return InMemoryGLAuditPort()


@pytest.fixture
def service(ledger, audit):
    return GLService(ledger=ledger, audit=audit)


def _create_two_accounts(service, currency="GBP"):
    """Helper: create a debit and credit account."""
    cash = service.create_account("Cash", AccountType.ASSET, currency)
    revenue = service.create_account("Revenue", AccountType.REVENUE, currency)
    return cash, revenue


# ── Double-Entry Balance Tests ───────────────────────────────────────────────


class TestDoubleEntry:
    def test_double_entry_debit_credit_balanced(self, service):
        """AC: balanced journal entry posts successfully (Decimal, I-01)."""
        cash, revenue = _create_two_accounts(service)
        result = service.post_journal_entry(
            description="Sale revenue",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("500.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("500.00"), "GBP"),
            ],
        )
        assert isinstance(result, JournalEntry)
        assert result.status == PostingStatus.POSTED
        assert len(result.postings) == 2

    def test_unbalanced_entry_rejected(self, service):
        """Unbalanced journal entry raises UnbalancedEntryError."""
        cash, revenue = _create_two_accounts(service)
        with pytest.raises(UnbalancedEntryError, match="Unbalanced"):
            service.post_journal_entry(
                description="Bad entry",
                postings=[
                    (cash.account_id, PostingDirection.DEBIT, Decimal("500.00"), "GBP"),
                    (revenue.account_id, PostingDirection.CREDIT, Decimal("499.99"), "GBP"),
                ],
            )

    def test_balance_updated_after_posting(self, service):
        """Account balances reflect posted entries."""
        cash, revenue = _create_two_accounts(service)
        service.post_journal_entry(
            description="Sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("1000.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("1000.00"), "GBP"),
            ],
        )
        assert service.get_balance(cash.account_id) == Decimal("1000.00")
        assert service.get_balance(revenue.account_id) == Decimal("-1000.00")

    def test_multiple_postings_accumulate(self, service):
        """Multiple journal entries accumulate balances."""
        cash, revenue = _create_two_accounts(service)
        for i in range(3):
            service.post_journal_entry(
                description=f"Sale {i}",
                postings=[
                    (cash.account_id, PostingDirection.DEBIT, Decimal("100.00"), "GBP"),
                    (revenue.account_id, PostingDirection.CREDIT, Decimal("100.00"), "GBP"),
                ],
            )
        assert service.get_balance(cash.account_id) == Decimal("300.00")

    def test_three_leg_entry(self, service):
        """Three-posting entry (split) must still balance."""
        cash = service.create_account("Cash", AccountType.ASSET, "GBP")
        tax = service.create_account("Tax", AccountType.LIABILITY, "GBP")
        revenue = service.create_account("Revenue", AccountType.REVENUE, "GBP")

        result = service.post_journal_entry(
            description="Sale with tax",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("120.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("100.00"), "GBP"),
                (tax.account_id, PostingDirection.CREDIT, Decimal("20.00"), "GBP"),
            ],
        )
        assert isinstance(result, JournalEntry)
        assert result.status == PostingStatus.POSTED


# ── Immutability Tests ───────────────────────────────────────────────────────


class TestImmutability:
    def test_journal_entry_immutable(self, service):
        """AC: JournalEntry is frozen (I-24)."""
        cash, revenue = _create_two_accounts(service)
        result = service.post_journal_entry(
            description="Test",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("100.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("100.00"), "GBP"),
            ],
        )
        with pytest.raises(AttributeError):
            result.status = PostingStatus.REVERSED  # type: ignore[misc]

    def test_account_immutable(self, service):
        """Account is frozen (I-24)."""
        account = service.create_account("Cash", AccountType.ASSET, "GBP")
        with pytest.raises(AttributeError):
            account.name = "Modified"  # type: ignore[misc]

    def test_posting_immutable(self):
        """Posting is frozen (I-24)."""
        posting = Posting(
            posting_id="p-001",
            account_id="acc-001",
            direction=PostingDirection.DEBIT,
            amount=Decimal("100"),
            currency="GBP",
        )
        with pytest.raises(AttributeError):
            posting.amount = Decimal("200")  # type: ignore[misc]

    def test_gl_audit_entry_immutable(self):
        """GLAuditEntry is frozen (I-24)."""
        entry = GLAuditEntry(
            entry_id="je-001",
            action="TEST",
            status=PostingStatus.POSTED,
            total_amount=Decimal("100"),
            currency="GBP",
            actor="test",
        )
        with pytest.raises(AttributeError):
            entry.action = "MODIFIED"  # type: ignore[misc]


# ── Multi-Currency Tests ─────────────────────────────────────────────────────


class TestMultiCurrency:
    def test_multi_currency_posting_gbp(self, service):
        """AC: GBP posting works."""
        cash, revenue = _create_two_accounts(service, "GBP")
        result = service.post_journal_entry(
            description="GBP sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("100.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("100.00"), "GBP"),
            ],
        )
        assert isinstance(result, JournalEntry)

    def test_multi_currency_posting_eur(self, service):
        """AC: EUR posting works."""
        cash, revenue = _create_two_accounts(service, "EUR")
        result = service.post_journal_entry(
            description="EUR sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("250.50"), "EUR"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("250.50"), "EUR"),
            ],
        )
        assert isinstance(result, JournalEntry)

    def test_multi_currency_posting_usd(self, service):
        """AC: USD posting works."""
        cash, revenue = _create_two_accounts(service, "USD")
        result = service.post_journal_entry(
            description="USD sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("500.00"), "USD"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("500.00"), "USD"),
            ],
        )
        assert isinstance(result, JournalEntry)

    def test_unsupported_currency_rejected(self, service):
        """Unsupported currency raises ValueError."""
        with pytest.raises(ValueError, match="Unsupported currency"):
            service.create_account("Cash", AccountType.ASSET, "CHF")

    def test_supported_currencies_set(self):
        """Verify supported currencies include GBP, EUR, USD."""
        assert frozenset({"GBP", "EUR", "USD"}) == SUPPORTED_CURRENCIES


# ── Jurisdiction Blocking Tests ──────────────────────────────────────────────


class TestJurisdictionBlocking:
    def test_blocked_jurisdiction_account_rejected_ru(self, service):
        """AC: RU jurisdiction account rejected (I-02)."""
        with pytest.raises(JurisdictionBlockedError, match="sanctioned"):
            service.create_account("Bad Account", AccountType.ASSET, "GBP", "RU")

    def test_blocked_jurisdiction_ir(self, service):
        """IR jurisdiction blocked (I-02)."""
        with pytest.raises(JurisdictionBlockedError):
            service.create_account("Bad", AccountType.ASSET, "GBP", "IR")

    def test_blocked_jurisdiction_kp(self, service):
        """KP jurisdiction blocked (I-02)."""
        with pytest.raises(JurisdictionBlockedError):
            service.create_account("Bad", AccountType.ASSET, "GBP", "KP")

    def test_blocked_jurisdiction_case_insensitive(self, service):
        """Jurisdiction check is case-insensitive."""
        with pytest.raises(JurisdictionBlockedError):
            service.create_account("Bad", AccountType.ASSET, "GBP", "ru")

    def test_all_blocked_jurisdictions(self):
        """Verify all I-02 blocked countries."""
        expected = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
        assert expected == BLOCKED_JURISDICTIONS

    def test_gb_jurisdiction_allowed(self, service):
        """GB jurisdiction is allowed."""
        account = service.create_account("Cash", AccountType.ASSET, "GBP", "GB")
        assert account.jurisdiction == "GB"


# ── High-Value Posting Tests ─────────────────────────────────────────────────


class TestHighValue:
    def test_high_value_posting_flagged(self, service):
        """AC: posting >= £50k returns HighValueHITLProposal (I-04)."""
        cash, revenue = _create_two_accounts(service)
        result = service.post_journal_entry(
            description="Large sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("50000.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("50000.00"), "GBP"),
            ],
        )
        assert isinstance(result, HighValueHITLProposal)
        assert result.requires_approval_from == "MLRO"
        assert result.total_amount == "50000.00"

    def test_below_threshold_posts_normally(self, service):
        """Posting below threshold posts without HITL."""
        cash, revenue = _create_two_accounts(service)
        result = service.post_journal_entry(
            description="Normal sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("49999.99"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("49999.99"), "GBP"),
            ],
        )
        assert isinstance(result, JournalEntry)

    def test_high_value_approved_posts(self, service):
        """Pre-approved high-value posting succeeds."""
        cash, revenue = _create_two_accounts(service)
        result = service.post_journal_entry(
            description="Approved large sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("100000.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("100000.00"), "GBP"),
            ],
            high_value_approved=True,
        )
        assert isinstance(result, JournalEntry)
        assert result.status == PostingStatus.POSTED

    def test_high_value_threshold(self):
        """HIGH_VALUE_THRESHOLD is £50,000."""
        assert Decimal("50000") == HIGH_VALUE_THRESHOLD


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_gl_audit_trail_complete_account_creation(self, service, audit):
        """AC: audit entry for account creation (I-24)."""
        service.create_account("Cash", AccountType.ASSET, "GBP")
        assert len(audit.entries) == 1
        entry = audit.entries[0]
        assert entry.action == "CREATE_ACCOUNT"
        assert entry.status == PostingStatus.POSTED
        assert isinstance(entry.total_amount, Decimal)

    def test_gl_audit_trail_journal_entry(self, service, audit):
        """AC: audit entry for journal entry posting (I-24)."""
        cash, revenue = _create_two_accounts(service)
        service.post_journal_entry(
            description="Sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("100.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("100.00"), "GBP"),
            ],
        )
        # 2 account creations + 1 journal entry = 3 audit entries
        assert len(audit.entries) == 3
        je_entry = audit.entries[-1]
        assert je_entry.action == "POST_JOURNAL_ENTRY"
        assert je_entry.total_amount == Decimal("100.00")

    def test_audit_includes_details(self, service, audit):
        """Audit entry includes posting details."""
        cash, revenue = _create_two_accounts(service)
        service.post_journal_entry(
            description="Test sale",
            postings=[
                (cash.account_id, PostingDirection.DEBIT, Decimal("100.00"), "GBP"),
                (revenue.account_id, PostingDirection.CREDIT, Decimal("100.00"), "GBP"),
            ],
        )
        je_entry = audit.entries[-1]
        assert "postings=2" in je_entry.details
        assert "Test sale" in je_entry.details


# ── Model Validation Tests ───────────────────────────────────────────────────


class TestModels:
    def test_posting_decimal_only(self):
        """Posting rejects non-Decimal amount (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            Posting(
                posting_id="p-001",
                account_id="acc-001",
                direction=PostingDirection.DEBIT,
                amount=100.0,  # type: ignore[arg-type]
                currency="GBP",
            )

    def test_posting_positive_amount(self):
        """Posting rejects non-positive amount."""
        with pytest.raises(ValueError, match="positive"):
            Posting(
                posting_id="p-001",
                account_id="acc-001",
                direction=PostingDirection.DEBIT,
                amount=Decimal("-10"),
                currency="GBP",
            )

    def test_journal_entry_min_postings(self):
        """JournalEntry requires at least 2 postings."""
        with pytest.raises(ValueError, match="at least 2"):
            JournalEntry(
                entry_id="je-001",
                description="Bad",
                postings=(
                    Posting("p-001", "acc-001", PostingDirection.DEBIT, Decimal("100"), "GBP"),
                ),
            )

    def test_account_unsupported_currency(self):
        """Account rejects unsupported currency."""
        with pytest.raises(ValueError, match="Unsupported currency"):
            Account(
                account_id="acc-001",
                name="Bad",
                account_type=AccountType.ASSET,
                currency="JPY",
            )

    def test_get_account(self, service):
        """get_account returns created account."""
        account = service.create_account("Cash", AccountType.ASSET, "GBP")
        found = service.get_account(account.account_id)
        assert found is not None
        assert found.account_id == account.account_id

    def test_get_account_not_found(self, service):
        """get_account returns None for unknown ID."""
        assert service.get_account("nonexistent") is None

    def test_non_decimal_amount_rejected(self, service):
        """Non-Decimal amount in posting rejected (I-01)."""
        cash, revenue = _create_two_accounts(service)
        with pytest.raises(TypeError, match="Decimal"):
            service.post_journal_entry(
                description="Bad",
                postings=[
                    (cash.account_id, PostingDirection.DEBIT, 100.0, "GBP"),  # type: ignore[list-item]
                    (revenue.account_id, PostingDirection.CREDIT, Decimal("100"), "GBP"),
                ],
            )
