"""
services/swift_correspondent/message_builder.py
SWIFT Message Builder — MT103 / MT202
IL-SWF-01 | Sprint 34 | Phase 47

FCA: PSR 2017, SWIFT gpi SRD
Trust Zone: RED

Builds validated SWIFT messages. FATF greylist check (I-03).
All amounts Decimal (I-22). UTC timestamps (I-23).
Cancel is always HITL (I-27).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import logging

from services.swift_correspondent.models import (
    ChargeCode,
    HITLProposal,
    InMemoryMessageStore,
    MessageStatus,
    MessageStore,
    SWIFTMessage,
    SWIFTMessageType,
)

logger = logging.getLogger(__name__)

FATF_GREYLIST: set[str] = {
    "PK",
    "AE",
    "JO",
    "TN",
    "VN",
    "LK",
    "NG",
    "ET",
    "KH",
    "SN",
    "MN",
    "YE",
}
BLOCKED_JURISDICTIONS: set[str] = {
    "RU",
    "BY",
    "IR",
    "KP",
    "CU",
    "MM",
    "AF",
    "VE",
    "SY",
}


class SWIFTMessageBuilder:
    """Builds and validates SWIFT MT103/MT202 messages.

    Performs FATF greylist checks (I-03), BIC validation,
    and SHA-256 message ID generation. Cancellation always
    returns HITLProposal (I-27, irreversible action).
    """

    def __init__(self, store: MessageStore | None = None) -> None:
        """Initialise builder with optional message store."""
        self._store: MessageStore = store or InMemoryMessageStore()

    def _generate_message_id(
        self, sender_bic: str, receiver_bic: str, amount: Decimal, ts: str
    ) -> str:
        """Generate SHA-256 based message ID (I-22)."""
        raw = f"{sender_bic}{receiver_bic}{amount}{ts}"
        digest = hashlib.sha256(raw.encode()).hexdigest()[:8]
        return f"msg_{digest}"

    def _get_country_from_bic(self, bic: str) -> str:
        """Extract ISO country code from BIC chars 5-6."""
        return bic[4:6].upper() if len(bic) >= 6 else ""

    def build_mt103(
        self,
        sender_bic: str,
        receiver_bic: str,
        amount: Decimal,
        currency: str,
        ordering_customer: str,
        beneficiary_customer: str,
        remittance_info: str,
        charge_code: ChargeCode = ChargeCode.SHA,
    ) -> SWIFTMessage:
        """Build a SWIFT MT103 Customer Credit Transfer.

        I-03: FATF greylist check on receiver country.
        I-22: amount as Decimal.
        I-23: value_date in UTC.

        Args:
            sender_bic: 8 or 11 char BIC of sending institution.
            receiver_bic: 8 or 11 char BIC of receiving institution.
            amount: Transfer amount as Decimal (I-22).
            currency: ISO 4217 currency code.
            ordering_customer: Name/account of ordering customer.
            beneficiary_customer: Name/account of beneficiary.
            remittance_info: Field 70 text, max 140 chars.
            charge_code: SHA/BEN/OUR charge allocation.

        Returns:
            Validated SWIFTMessage with DRAFT status.
        """
        ts = datetime.now(UTC).isoformat()
        value_date = datetime.now(UTC).strftime("%Y%m%d")
        message_id = self._generate_message_id(sender_bic, receiver_bic, amount, ts)

        receiver_country = self._get_country_from_bic(receiver_bic)
        if receiver_country in BLOCKED_JURISDICTIONS:
            raise ValueError(f"Receiver country {receiver_country} is a blocked jurisdiction")

        if receiver_country in FATF_GREYLIST:
            logger.warning(
                "FATF greylist country detected: %s — adding EDD prefix (I-03)",
                receiver_country,
            )
            remittance_info = f"[EDD]{remittance_info}"

        msg = SWIFTMessage(
            message_id=message_id,
            message_type=SWIFTMessageType.MT103,
            sender_bic=sender_bic,
            receiver_bic=receiver_bic,
            amount=amount,
            currency=currency,
            value_date=value_date,
            ordering_customer=ordering_customer,
            beneficiary_customer=beneficiary_customer,
            remittance_info=remittance_info,
            charge_code=charge_code,
            status=MessageStatus.DRAFT,
        )
        self._store.save(msg)
        logger.info("Built MT103 message_id=%s amount=%s %s", message_id, amount, currency)
        return msg

    def build_mt202(
        self,
        sender_bic: str,
        receiver_bic: str,
        amount: Decimal,
        currency: str,
        ordering_institution: str,
        beneficiary_institution: str,
    ) -> SWIFTMessage:
        """Build a SWIFT MT202 Financial Institution Transfer.

        I-22: amount as Decimal. I-23: value_date UTC.

        Args:
            sender_bic: Sending institution BIC.
            receiver_bic: Receiving institution BIC.
            amount: Transfer amount as Decimal (I-22).
            currency: ISO 4217 currency code.
            ordering_institution: Ordering FI name/account.
            beneficiary_institution: Beneficiary FI name/account.

        Returns:
            Validated SWIFTMessage with DRAFT status.
        """
        ts = datetime.now(UTC).isoformat()
        value_date = datetime.now(UTC).strftime("%Y%m%d")
        message_id = self._generate_message_id(sender_bic, receiver_bic, amount, ts)

        receiver_country = self._get_country_from_bic(receiver_bic)
        if receiver_country in BLOCKED_JURISDICTIONS:
            raise ValueError(f"Receiver country {receiver_country} is a blocked jurisdiction")

        msg = SWIFTMessage(
            message_id=message_id,
            message_type=SWIFTMessageType.MT202,
            sender_bic=sender_bic,
            receiver_bic=receiver_bic,
            amount=amount,
            currency=currency,
            value_date=value_date,
            ordering_customer=ordering_institution,
            beneficiary_customer=beneficiary_institution,
            remittance_info="FI Transfer",
            charge_code=ChargeCode.OUR,
            status=MessageStatus.DRAFT,
        )
        self._store.save(msg)
        logger.info("Built MT202 message_id=%s amount=%s %s", message_id, amount, currency)
        return msg

    def validate_message(self, message_id: str) -> tuple[bool, list[str]]:
        """Validate a SWIFT message for compliance.

        Checks: BIC format, remittance ≤140, amount > 0, currency 3-char.

        Args:
            message_id: ID of message to validate.

        Returns:
            Tuple of (is_valid, list_of_errors).
        """
        msg = self._store.get(message_id)
        if msg is None:
            return False, [f"Message {message_id} not found"]

        errors: list[str] = []
        if len(msg.sender_bic) not in (8, 11):
            errors.append(f"sender_bic invalid length: {len(msg.sender_bic)}")
        if len(msg.receiver_bic) not in (8, 11):
            errors.append(f"receiver_bic invalid length: {len(msg.receiver_bic)}")
        if len(msg.remittance_info) > 140:
            errors.append(f"remittance_info exceeds 140 chars: {len(msg.remittance_info)}")
        if msg.amount <= Decimal("0"):
            errors.append(f"amount must be > 0, got {msg.amount}")
        if len(msg.currency) != 3:
            errors.append(f"currency must be 3-char ISO, got {msg.currency!r}")

        if not errors:
            updated = msg.model_copy(update={"status": MessageStatus.VALIDATED})
            self._store.save(updated)

        return len(errors) == 0, errors

    def get_message(self, message_id: str) -> SWIFTMessage | None:
        """Retrieve a SWIFT message by ID.

        Args:
            message_id: The message ID to retrieve.

        Returns:
            SWIFTMessage if found, None otherwise.
        """
        return self._store.get(message_id)

    def list_messages(self, status: MessageStatus | None = None) -> list[SWIFTMessage]:
        """List SWIFT messages, optionally filtered by status.

        Args:
            status: Optional status filter.

        Returns:
            List of matching SWIFTMessage objects.
        """
        if status is not None:
            return self._store.list_by_status(status)
        all_statuses = list(MessageStatus)
        result: list[SWIFTMessage] = []
        seen: set[str] = set()
        for s in all_statuses:
            for m in self._store.list_by_status(s):
                if m.message_id not in seen:
                    result.append(m)
                    seen.add(m.message_id)
        return result

    def cancel_message(self, message_id: str, reason: str, actor: str) -> HITLProposal:
        """Propose cancellation of a SWIFT message (always HITL, I-27).

        Cancellation is irreversible — always returns HITLProposal requiring
        TREASURY_OPS approval.

        Args:
            message_id: Message to cancel.
            reason: Cancellation reason.
            actor: Actor requesting cancellation.

        Returns:
            HITLProposal for L4 human approval.
        """
        logger.warning(
            "Cancel proposed for message_id=%s by actor=%s reason=%s",
            message_id,
            actor,
            reason,
        )
        return HITLProposal(
            action="CANCEL_MESSAGE",
            message_id=message_id,
            requires_approval_from="TREASURY_OPS",
            reason=f"Cancel requested by {actor}: {reason}",
            autonomy_level="L4",
        )
