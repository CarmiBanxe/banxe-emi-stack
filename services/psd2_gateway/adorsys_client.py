"""adorsys XS2A PSD2 Gateway client.

Credentials via environment variables ONLY (I-02 secrets rule):
  ADORSYS_BASE_URL    — default http://localhost:8889
  ADORSYS_CLIENT_ID
  ADORSYS_CLIENT_SECRET

I-02: IBAN country code check — blocked jurisdictions raise ValueError.
I-24: All fetched transactions are append-only stored.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import logging
import os

from services.psd2_gateway.psd2_models import (
    BLOCKED_JURISDICTIONS,
    AccountInfo,
    BalanceResponse,
    ConsentRequest,
    ConsentResponse,
    ConsentStorePort,
    InMemoryConsentStore,
    InMemoryTransactionStore,
    Transaction,
    TransactionStorePort,
    _iban_country,
)

logger = logging.getLogger("banxe.psd2_gateway")

ADORSYS_BASE_URL = os.environ.get("ADORSYS_BASE_URL", "http://localhost:8889")
# Credentials from env ONLY (I-02)
_CLIENT_ID = os.environ.get("ADORSYS_CLIENT_ID", "")
_CLIENT_SECRET = os.environ.get("ADORSYS_CLIENT_SECRET", "")


class AdorsysClient:
    """Client for adorsys XS2A PSD2 adapter."""

    def __init__(
        self,
        base_url: str = ADORSYS_BASE_URL,
        consent_store: ConsentStorePort | None = None,
        txn_store: TransactionStorePort | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._consent_store = consent_store or InMemoryConsentStore()
        self._txn_store = txn_store or InMemoryTransactionStore()

    def _check_iban(self, iban: str) -> None:
        """I-02: Raise ValueError if IBAN country is in blocked jurisdictions."""
        country = _iban_country(iban)
        if country in BLOCKED_JURISDICTIONS:
            raise ValueError(f"I-02: IBAN from blocked jurisdiction {country!r}: {iban[:6]}***")

    def create_consent(self, request: ConsentRequest) -> ConsentResponse:
        """Create AISP consent for bank account access.

        Real impl calls adorsys XS2A POST /v1/consents.
        Stub: returns InMemory consent (BT-007 live bank integration pending).
        """
        self._check_iban(request.iban)  # I-02
        raw = f"{request.iban}{request.valid_until}".encode()
        consent_id = f"cns_{hashlib.sha256(raw).hexdigest()[:12]}"
        consent = ConsentResponse(
            consent_id=consent_id,
            status="valid",
            valid_until=request.valid_until,
            iban=request.iban,
            created_at=datetime.now(UTC).isoformat(),
        )
        self._consent_store.append(consent)  # I-24
        logger.info(
            "psd2.consent_created consent_id=%s iban=%s***",
            consent_id,
            request.iban[:6],
        )
        return consent

    def get_accounts(self, consent_id: str) -> list[AccountInfo]:
        """Get accounts under consent. Stub returns seeded accounts."""
        consent = self._consent_store.get(consent_id)
        if consent is None:
            raise KeyError(f"Consent {consent_id!r} not found")
        return [
            AccountInfo(
                account_id=f"acc_{hashlib.sha256(consent.iban.encode()).hexdigest()[:8]}",
                iban=consent.iban,
                currency="GBP",
                account_type="CACC",
                name="Banxe Client Account",
            )
        ]

    def get_transactions(
        self,
        consent_id: str,
        account_id: str,
        date_from: str,
        date_to: str,
    ) -> list[Transaction]:
        """Fetch transactions for account. I-24 append-only store."""
        consent = self._consent_store.get(consent_id)
        if consent is None:
            raise KeyError(f"Consent {consent_id!r} not found")
        txn = Transaction(
            transaction_id=f"txn_{hashlib.sha256(f'{account_id}{date_from}'.encode()).hexdigest()[:8]}",
            amount=Decimal("1500.00"),  # I-01
            currency="GBP",
            creditor_name="Banxe Safeguarding Account",
            debtor_name=None,
            booking_date=date_from,
            value_date=date_from,
            reference="Safeguarding transfer",
        )
        self._txn_store.append(txn)  # I-24
        return [txn]

    def get_balances(self, consent_id: str, account_id: str) -> BalanceResponse:
        """Fetch account balance. Returns Decimal (I-01)."""
        consent = self._consent_store.get(consent_id)
        if consent is None:
            raise KeyError(f"Consent {consent_id!r} not found")
        return BalanceResponse(
            account_id=account_id,
            iban=consent.iban,
            currency="GBP",
            balance_amount=Decimal("50000.00"),  # I-01 stub
            balance_type="closingBooked",
            last_change_date_time=datetime.now(UTC).isoformat(),
        )

    def initiate_payment_via_psd2(self) -> None:
        """BT-007: PISP payment initiation — pending live bank integration."""
        raise NotImplementedError(
            "BT-007: PISP payment via adorsys XS2A requires live bank connection"
        )
