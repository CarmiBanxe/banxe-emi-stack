"""
services/ledger/posting_rules.py
PostingRuleEngine — debit/credit mapping per payment event type (IL-CBS-01).

I-01: Decimal amounts.
I-02: Blocked jurisdictions → reject posting.
I-04: High-value postings flagged.
"""

from __future__ import annotations

from decimal import Decimal

from services.ledger.posting_models import (
    DEFAULT_POSTING_RULES,
    PaymentEvent,
    PaymentEventType,
    PostingRule,
)

BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)

HIGH_VALUE_THRESHOLD: Decimal = Decimal("10000")


class JurisdictionBlockedError(ValueError):
    """Posting blocked for sanctioned jurisdiction (I-02)."""


class NoPostingRuleError(ValueError):
    """No posting rule defined for this event type."""


class HighValuePostingFlag:
    """Flag indicating a high-value posting (I-04)."""

    def __init__(self, event: PaymentEvent, threshold: Decimal) -> None:
        self.event = event
        self.threshold = threshold
        self.reason = (
            f"Payment {event.transaction_id} amount {event.currency} {event.amount} "
            f"exceeds threshold {threshold} (I-04)"
        )


class PostingRuleEngine:
    """
    Resolves payment events to posting rules.

    I-02: Rejects events from blocked jurisdictions.
    I-04: Flags high-value events.
    """

    def __init__(
        self,
        rules: dict[PaymentEventType, PostingRule] | None = None,
    ) -> None:
        self._rules = rules or dict(DEFAULT_POSTING_RULES)

    def resolve(self, event: PaymentEvent) -> PostingRule:
        """
        Resolve a payment event to its posting rule.

        Raises JurisdictionBlockedError for blocked jurisdictions (I-02).
        Raises NoPostingRuleError if no rule exists for the event type.
        """
        if event.beneficiary_jurisdiction.upper() in BLOCKED_JURISDICTIONS:
            raise JurisdictionBlockedError(
                f"Posting blocked for jurisdiction {event.beneficiary_jurisdiction!r} (I-02)"
            )

        rule = self._rules.get(event.event_type)
        if rule is None:
            raise NoPostingRuleError(f"No posting rule for event type {event.event_type.value}")
        return rule

    def check_high_value(self, event: PaymentEvent) -> HighValuePostingFlag | None:
        """Return flag if event amount exceeds threshold (I-04)."""
        if event.amount >= HIGH_VALUE_THRESHOLD:
            return HighValuePostingFlag(event, HIGH_VALUE_THRESHOLD)
        return None

    def get_description(self, rule: PostingRule, event: PaymentEvent) -> str:
        """Generate posting description from rule template."""
        return rule.description_template.format(transaction_id=event.transaction_id)
