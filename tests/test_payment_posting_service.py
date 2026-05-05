"""
tests/test_payment_posting_service.py
Tests for PaymentPostingService (IL-CBS-01).

Acceptance criteria:
- test_payment_capture_posts_debit_credit (Decimal, I-01)
- test_payment_refund_reversal_posts
- test_payment_settlement_recon
- test_posting_blocked_jurisdiction (I-02)
- test_posting_high_value_flagged (I-04)
- test_posting_audit_trail (I-24)
- test_posting_double_entry_always_balanced
"""

from decimal import Decimal

import pytest

from services.ledger.gl_service import GLService, HighValueHITLProposal, InMemoryGLAuditPort
from services.ledger.inmemory_ledger import InMemoryLedger
from services.ledger.ledger_models import AccountType, JournalEntry, PostingDirection, PostingStatus
from services.ledger.payment_posting_service import (
    AccountRegistry,
    InMemoryPostingAuditPort,
    PaymentPostingService,
)
from services.ledger.posting_models import (
    DEFAULT_POSTING_RULES,
    PaymentEvent,
    PaymentEventType,
)
from services.ledger.posting_rules import (
    JurisdictionBlockedError,
    NoPostingRuleError,
    PostingRuleEngine,
)

# ── Fixtures ─────────────────────────────────────────────────────────────────


@pytest.fixture
def ledger():
    return InMemoryLedger()


@pytest.fixture
def gl_audit():
    return InMemoryGLAuditPort()


@pytest.fixture
def gl(ledger, gl_audit):
    return GLService(ledger=ledger, audit=gl_audit)


@pytest.fixture
def posting_audit():
    return InMemoryPostingAuditPort()


@pytest.fixture
def registry(gl):
    """Create GL accounts and register them."""
    reg = AccountRegistry()
    # Create accounts in GL.
    cf = gl.create_account("Customer Funds", AccountType.LIABILITY, "GBP")
    sp = gl.create_account("Settlement Pending", AccountType.LIABILITY, "GBP")
    mp = gl.create_account("Merchant Payable", AccountType.LIABILITY, "GBP")
    # Register logical types.
    reg.register("CUSTOMER_FUNDS", "GBP", cf.account_id)
    reg.register("SETTLEMENT_PENDING", "GBP", sp.account_id)
    reg.register("MERCHANT_PAYABLE", "GBP", mp.account_id)
    return reg


@pytest.fixture
def service(gl, registry, posting_audit):
    return PaymentPostingService(gl=gl, registry=registry, audit=posting_audit)


def _event(
    event_type: PaymentEventType = PaymentEventType.CAPTURED,
    amount: Decimal = Decimal("500.00"),
    currency: str = "GBP",
    jurisdiction: str = "GB",
    tx_id: str = "tx-001",
) -> PaymentEvent:
    return PaymentEvent(
        event_id=f"evt-{tx_id}",
        transaction_id=tx_id,
        event_type=event_type,
        amount=amount,
        currency=currency,
        customer_id="cust-001",
        beneficiary_jurisdiction=jurisdiction,
    )


# ── Capture Posting Tests ────────────────────────────────────────────────────


class TestCapturePosting:
    def test_payment_capture_posts_debit_credit(self, service):
        """AC: capture → debit customer funds, credit settlement pending (Decimal, I-01)."""
        result = service.process_event(_event(PaymentEventType.CAPTURED))
        assert isinstance(result, JournalEntry)
        assert result.status == PostingStatus.POSTED
        assert len(result.postings) == 2
        debit = [p for p in result.postings if p.direction == PostingDirection.DEBIT]
        credit = [p for p in result.postings if p.direction == PostingDirection.CREDIT]
        assert len(debit) == 1
        assert len(credit) == 1
        assert debit[0].amount == Decimal("500.00")
        assert credit[0].amount == Decimal("500.00")

    def test_capture_description(self, service):
        """Capture posting has correct description."""
        result = service.process_event(_event(PaymentEventType.CAPTURED, tx_id="tx-abc"))
        assert "tx-abc" in result.description


# ── Settlement Tests ─────────────────────────────────────────────────────────


class TestSettlement:
    def test_payment_settlement_posts(self, service):
        """Settlement → debit settlement pending, credit merchant payable."""
        result = service.process_event(_event(PaymentEventType.SETTLED))
        assert isinstance(result, JournalEntry)
        assert result.status == PostingStatus.POSTED

    def test_payment_settlement_recon(self, service):
        """AC: settled amount matches GL totals — balanced."""
        service.process_event(_event(PaymentEventType.CAPTURED, amount=Decimal("1000.00")))
        service.process_event(_event(PaymentEventType.SETTLED, amount=Decimal("1000.00")))

        cf_balance = service.get_gl_balance("CUSTOMER_FUNDS", "GBP")
        sp_balance = service.get_gl_balance("SETTLEMENT_PENDING", "GBP")
        mp_balance = service.get_gl_balance("MERCHANT_PAYABLE", "GBP")

        # Customer funds debited 1000 (capture).
        assert cf_balance == Decimal("1000.00")
        # Settlement pending: +1000 (capture credit) -1000 (settle debit) = 0.
        assert sp_balance == Decimal("0")
        # Merchant payable: -1000 (settle credit).
        assert mp_balance == Decimal("-1000.00")


# ── Refund Tests ─────────────────────────────────────────────────────────────


class TestRefund:
    def test_payment_refund_reversal_posts(self, service):
        """AC: refund → reverse entries (debit merchant, credit customer)."""
        service.process_event(_event(PaymentEventType.CAPTURED, amount=Decimal("200.00")))
        service.process_event(_event(PaymentEventType.SETTLED, amount=Decimal("200.00")))
        result = service.process_event(_event(PaymentEventType.REFUNDED, amount=Decimal("200.00")))

        assert isinstance(result, JournalEntry)
        assert result.status == PostingStatus.POSTED

    def test_partial_refund(self, service):
        """Partial refund posts correctly."""
        service.process_event(_event(PaymentEventType.CAPTURED, amount=Decimal("500.00")))
        service.process_event(_event(PaymentEventType.SETTLED, amount=Decimal("500.00")))
        result = service.process_event(
            _event(PaymentEventType.PARTIALLY_REFUNDED, amount=Decimal("100.00"))
        )
        assert isinstance(result, JournalEntry)

    def test_refund_balances_correct(self, service):
        """After full refund, customer funds net to zero."""
        service.process_event(_event(PaymentEventType.CAPTURED, amount=Decimal("300.00")))
        service.process_event(_event(PaymentEventType.SETTLED, amount=Decimal("300.00")))
        service.process_event(_event(PaymentEventType.REFUNDED, amount=Decimal("300.00")))

        cf = service.get_gl_balance("CUSTOMER_FUNDS", "GBP")
        mp = service.get_gl_balance("MERCHANT_PAYABLE", "GBP")
        # Capture debit +300, refund credit -300 = 0.
        assert cf == Decimal("0")
        # Settle credit -300, refund debit +300 = 0.
        assert mp == Decimal("0")


# ── Double Entry Balance Tests ───────────────────────────────────────────────


class TestDoubleEntry:
    def test_posting_double_entry_always_balanced(self, service, ledger):
        """AC: sum(debits) == sum(credits) always."""
        service.process_event(_event(PaymentEventType.CAPTURED, amount=Decimal("1000.00")))
        service.process_event(_event(PaymentEventType.SETTLED, amount=Decimal("1000.00")))
        service.process_event(_event(PaymentEventType.REFUNDED, amount=Decimal("500.00")))

        total_debit = Decimal("0")
        total_credit = Decimal("0")
        for entry in ledger.entries.values():
            for posting in entry.postings:
                if posting.direction == PostingDirection.DEBIT:
                    total_debit += posting.amount
                else:
                    total_credit += posting.amount

        assert total_debit == total_credit

    def test_chargeback_posts_balanced(self, service, ledger):
        """Chargeback posting is balanced."""
        service.process_event(_event(PaymentEventType.CAPTURED, amount=Decimal("200.00")))
        service.process_event(_event(PaymentEventType.SETTLED, amount=Decimal("200.00")))
        service.process_event(_event(PaymentEventType.CHARGEBACK, amount=Decimal("200.00")))

        total_debit = Decimal("0")
        total_credit = Decimal("0")
        for entry in ledger.entries.values():
            for posting in entry.postings:
                if posting.direction == PostingDirection.DEBIT:
                    total_debit += posting.amount
                else:
                    total_credit += posting.amount
        assert total_debit == total_credit


# ── Jurisdiction Blocking Tests ──────────────────────────────────────────────


class TestJurisdiction:
    def test_posting_blocked_jurisdiction(self, service):
        """AC: blocked jurisdiction → JurisdictionBlockedError (I-02)."""
        with pytest.raises(JurisdictionBlockedError, match="I-02"):
            service.process_event(_event(jurisdiction="RU"))

    def test_posting_blocked_ir(self, service):
        with pytest.raises(JurisdictionBlockedError):
            service.process_event(_event(jurisdiction="IR"))

    def test_posting_blocked_case_insensitive(self, service):
        with pytest.raises(JurisdictionBlockedError):
            service.process_event(_event(jurisdiction="kp"))


# ── High Value Tests ─────────────────────────────────────────────────────────


class TestHighValue:
    def test_posting_high_value_flagged(self, service):
        """AC: >£10k → flag (I-04)."""
        service.process_event(
            _event(amount=Decimal("15000.00")),
            high_value_approved=True,
        )
        assert len(service.high_value_flags) == 1
        assert service.high_value_flags[0].event.amount == Decimal("15000.00")

    def test_high_value_without_approval_hitl(self, service):
        """High value without approval → HighValueHITLProposal from GLService."""
        # GLService threshold is £50k, posting_rules threshold is £10k.
        # Event with £50k+ triggers GLService HITL.
        result = service.process_event(_event(amount=Decimal("55000.00")))
        assert isinstance(result, HighValueHITLProposal)

    def test_below_threshold_posts_normally(self, service):
        """Below threshold posts without flag."""
        service.process_event(_event(amount=Decimal("9999.99")))
        assert len(service.high_value_flags) == 0


# ── Audit Trail Tests ────────────────────────────────────────────────────────


class TestAuditTrail:
    def test_posting_audit_trail(self, service, posting_audit):
        """AC: every posting logged (I-24)."""
        service.process_event(_event())
        assert len(posting_audit.entries) == 1
        entry = posting_audit.entries[0]
        assert entry.transaction_id == "tx-001"
        assert entry.event_type == "CAPTURED"
        assert entry.action == "POST_PAYMENT_EVENT"
        assert isinstance(entry.amount, Decimal)

    def test_multiple_events_multiple_entries(self, service, posting_audit):
        """Each event produces an audit entry."""
        service.process_event(_event(PaymentEventType.CAPTURED))
        service.process_event(_event(PaymentEventType.SETTLED))
        assert len(posting_audit.entries) == 2

    def test_audit_includes_account_details(self, service, posting_audit):
        """Audit entry includes debit/credit account types."""
        service.process_event(_event(PaymentEventType.CAPTURED))
        entry = posting_audit.entries[0]
        assert "CUSTOMER_FUNDS" in entry.details
        assert "SETTLEMENT_PENDING" in entry.details

    def test_audit_entry_immutable(self):
        """PostingAuditEntry is frozen (I-24)."""
        from services.ledger.payment_posting_service import PostingAuditEntry

        entry = PostingAuditEntry(
            event_id="e-001",
            transaction_id="tx-001",
            event_type="CAPTURED",
            journal_entry_id="je-001",
            amount=Decimal("100"),
            currency="GBP",
            action="TEST",
        )
        with pytest.raises(AttributeError):
            entry.action = "MODIFIED"  # type: ignore[misc]


# ── Posting Rules Tests ──────────────────────────────────────────────────────


class TestPostingRules:
    def test_default_rules_exist(self):
        """Default rules cover CAPTURED, SETTLED, REFUNDED, PARTIALLY_REFUNDED, CHARGEBACK."""
        expected = {
            PaymentEventType.CAPTURED,
            PaymentEventType.SETTLED,
            PaymentEventType.REFUNDED,
            PaymentEventType.PARTIALLY_REFUNDED,
            PaymentEventType.CHARGEBACK,
        }
        assert set(DEFAULT_POSTING_RULES.keys()) == expected

    def test_no_rule_for_authorized(self):
        """AUTHORIZED has no posting rule (no GL impact)."""
        engine = PostingRuleEngine()
        with pytest.raises(NoPostingRuleError):
            engine.resolve(_event(PaymentEventType.AUTHORIZED))

    def test_no_rule_for_failed(self):
        """FAILED has no posting rule."""
        engine = PostingRuleEngine()
        with pytest.raises(NoPostingRuleError):
            engine.resolve(_event(PaymentEventType.FAILED))


# ── Model Tests ──────────────────────────────────────────────────────────────


class TestModels:
    def test_payment_event_decimal_only(self):
        """PaymentEvent rejects non-Decimal (I-01)."""
        with pytest.raises(TypeError, match="Decimal"):
            PaymentEvent(
                event_id="e-001",
                transaction_id="tx-001",
                event_type=PaymentEventType.CAPTURED,
                amount=100.0,  # type: ignore[arg-type]
                currency="GBP",
                customer_id="c-001",
                beneficiary_jurisdiction="GB",
            )

    def test_payment_event_positive_amount(self):
        """PaymentEvent rejects zero/negative amount."""
        with pytest.raises(ValueError, match="positive"):
            PaymentEvent(
                event_id="e-001",
                transaction_id="tx-001",
                event_type=PaymentEventType.CAPTURED,
                amount=Decimal("0"),
                currency="GBP",
                customer_id="c-001",
                beneficiary_jurisdiction="GB",
            )

    def test_payment_event_frozen(self):
        """PaymentEvent is immutable (I-24)."""
        event = _event()
        with pytest.raises(AttributeError):
            event.amount = Decimal("999")  # type: ignore[misc]
