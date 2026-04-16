"""
services/open_banking/models.py
IL-OBK-01 | Phase 15

Core domain models, Protocol DI ports, and InMemory stubs for the
Open Banking PSD2 Gateway.  Amounts use Decimal exclusively (I-01).
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from decimal import Decimal
from enum import Enum
from typing import Protocol, runtime_checkable
import uuid

# ── Enumerations ──────────────────────────────────────────────────────────────


class ConsentStatus(str, Enum):
    AWAITING_AUTHORISATION = "AWAITING_AUTHORISATION"
    AUTHORISED = "AUTHORISED"
    REJECTED = "REJECTED"
    REVOKED = "REVOKED"
    EXPIRED = "EXPIRED"


class ConsentType(str, Enum):
    AISP = "AISP"
    PISP = "PISP"
    CBPII = "CBPII"


class PaymentStatus(str, Enum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REJECTED = "REJECTED"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"


class FlowType(str, Enum):
    REDIRECT = "REDIRECT"
    DECOUPLED = "DECOUPLED"
    EMBEDDED = "EMBEDDED"


class AccountAccessType(str, Enum):
    ACCOUNTS = "ACCOUNTS"
    BALANCES = "BALANCES"
    TRANSACTIONS = "TRANSACTIONS"
    BENEFICIARIES = "BENEFICIARIES"


class ASPSPStandard(str, Enum):
    BERLIN_GROUP = "BERLIN_GROUP"
    UK_OBIE = "UK_OBIE"


# ── Domain Dataclasses ────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Consent:
    id: str
    type: ConsentType
    aspsp_id: str
    entity_id: str
    permissions: list[AccountAccessType]
    status: ConsentStatus
    created_at: datetime
    expires_at: datetime
    authorised_at: datetime | None = None
    redirect_uri: str | None = None


@dataclass(frozen=True)
class PaymentInitiation:
    id: str
    consent_id: str
    entity_id: str
    aspsp_id: str
    amount: Decimal
    currency: str
    creditor_iban: str
    creditor_name: str
    reference: str
    status: PaymentStatus
    created_at: datetime
    end_to_end_id: str
    debtor_iban: str | None = None
    aspsp_payment_id: str | None = None
    completed_at: datetime | None = None


@dataclass(frozen=True)
class AccountInfo:
    account_id: str
    aspsp_id: str
    iban: str
    currency: str
    owner_name: str
    balance: Decimal | None = None


@dataclass(frozen=True)
class Transaction:
    transaction_id: str
    account_id: str
    amount: Decimal
    currency: str
    booking_date: datetime
    reference: str | None = None
    counterparty_name: str | None = None


@dataclass(frozen=True)
class ASPSP:
    id: str
    name: str
    country: str
    standard: ASPSPStandard
    api_base_url: str
    auth_url: str
    token_url: str
    client_id: str


@dataclass(frozen=True)
class OBEventEntry:
    id: str
    event_type: str
    entity_id: str
    details: dict
    created_at: datetime
    actor: str
    consent_id: str | None = None
    payment_id: str | None = None


# ── Protocol DI Ports ─────────────────────────────────────────────────────────


@runtime_checkable
class ConsentStorePort(Protocol):
    async def save(self, consent: Consent) -> None: ...

    async def get(self, consent_id: str) -> Consent | None: ...

    async def list_by_entity(self, entity_id: str) -> list[Consent]: ...

    async def update_status(
        self,
        consent_id: str,
        status: ConsentStatus,
        **kwargs: object,
    ) -> Consent: ...


@runtime_checkable
class PaymentGatewayPort(Protocol):
    async def submit_payment(self, payment: PaymentInitiation) -> str: ...

    async def get_payment_status(
        self,
        aspsp_payment_id: str,
        aspsp_id: str,
    ) -> PaymentStatus: ...


@runtime_checkable
class ASPSPRegistryPort(Protocol):
    async def get(self, aspsp_id: str) -> ASPSP | None: ...

    async def list_all(self) -> list[ASPSP]: ...


@runtime_checkable
class AccountDataPort(Protocol):
    async def get_accounts(
        self,
        consent_id: str,
        aspsp_id: str,
    ) -> list[AccountInfo]: ...

    async def get_balance(
        self,
        consent_id: str,
        account_id: str,
        aspsp_id: str,
    ) -> Decimal: ...

    async def get_transactions(
        self,
        consent_id: str,
        account_id: str,
        aspsp_id: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Transaction]: ...


@runtime_checkable
class OBAuditTrailPort(Protocol):
    async def append(self, entry: OBEventEntry) -> None: ...

    async def list_events(
        self,
        entity_id: str | None = None,
        event_type: str | None = None,
    ) -> list[OBEventEntry]: ...


# ── InMemory Stubs ────────────────────────────────────────────────────────────


class InMemoryConsentStore:
    def __init__(self) -> None:
        self._store: dict[str, Consent] = {}

    async def save(self, consent: Consent) -> None:
        self._store[consent.id] = consent

    async def get(self, consent_id: str) -> Consent | None:
        return self._store.get(consent_id)

    async def list_by_entity(self, entity_id: str) -> list[Consent]:
        return [c for c in self._store.values() if c.entity_id == entity_id]

    async def update_status(
        self,
        consent_id: str,
        status: ConsentStatus,
        **kwargs: object,
    ) -> Consent:
        existing = self._store[consent_id]
        updated = replace(existing, status=status, **kwargs)
        self._store[consent_id] = updated
        return updated


class InMemoryPaymentGateway:
    def __init__(self, should_accept: bool = True) -> None:
        self._should_accept = should_accept

    async def submit_payment(self, payment: PaymentInitiation) -> str:
        if not self._should_accept:
            raise ValueError("Gateway rejected payment")
        return f"aspsp-pay-{payment.id}"

    async def get_payment_status(
        self,
        aspsp_payment_id: str,
        aspsp_id: str,
    ) -> PaymentStatus:
        return PaymentStatus.ACCEPTED


_SAMPLE_ASPSPS: list[ASPSP] = [
    ASPSP(
        id="barclays-uk",
        name="Barclays UK",
        country="GB",
        standard=ASPSPStandard.UK_OBIE,
        api_base_url="https://api.barclays.co.uk/open-banking/v3.1",
        auth_url="https://auth.barclays.co.uk/oauth2/authorize",
        token_url="https://auth.barclays.co.uk/oauth2/token",  # noqa: S106
        client_id="barclays-client-id",
    ),
    ASPSP(
        id="hsbc-uk",
        name="HSBC UK",
        country="GB",
        standard=ASPSPStandard.UK_OBIE,
        api_base_url="https://api.hsbc.co.uk/open-banking/v3.1",
        auth_url="https://api.hsbc.co.uk/oauth2/authorize",
        token_url="https://api.hsbc.co.uk/oauth2/token",  # noqa: S106
        client_id="hsbc-client-id",
    ),
    ASPSP(
        id="bnp-fr",
        name="BNP Paribas FR",
        country="FR",
        standard=ASPSPStandard.BERLIN_GROUP,
        api_base_url="https://api.bnpparibas.com/psd2/v1",
        auth_url="https://api.bnpparibas.com/oauth2/authorize",
        token_url="https://api.bnpparibas.com/oauth2/token",  # noqa: S106
        client_id="bnp-client-id",
    ),
]


class InMemoryASPSPRegistry:
    def __init__(self) -> None:
        self._registry: dict[str, ASPSP] = {a.id: a for a in _SAMPLE_ASPSPS}

    async def get(self, aspsp_id: str) -> ASPSP | None:
        return self._registry.get(aspsp_id)

    async def list_all(self) -> list[ASPSP]:
        return list(self._registry.values())


class InMemoryAccountData:
    async def get_accounts(
        self,
        consent_id: str,
        aspsp_id: str,
    ) -> list[AccountInfo]:
        return [
            AccountInfo(
                account_id=f"acc-{consent_id[:8]}",
                aspsp_id=aspsp_id,
                iban="GB29NWBK60161331926819",
                currency="GBP",
                owner_name="Test Owner",
                balance=Decimal("1234.56"),
            )
        ]

    async def get_balance(
        self,
        consent_id: str,
        account_id: str,
        aspsp_id: str,
    ) -> Decimal:
        return Decimal("1234.56")

    async def get_transactions(
        self,
        consent_id: str,
        account_id: str,
        aspsp_id: str,
        from_date: datetime | None = None,
        to_date: datetime | None = None,
    ) -> list[Transaction]:
        return [
            Transaction(
                transaction_id=f"txn-{account_id[:8]}",
                account_id=account_id,
                amount=Decimal("42.00"),
                currency="GBP",
                booking_date=datetime(2026, 1, 15, 12, 0, 0, tzinfo=UTC),
                reference="REF-001",
                counterparty_name="Test Merchant",
            )
        ]


class InMemoryOBAuditTrail:
    def __init__(self) -> None:
        self._events: list[OBEventEntry] = []

    async def append(self, entry: OBEventEntry) -> None:
        self._events.append(entry)

    async def list_events(
        self,
        entity_id: str | None = None,
        event_type: str | None = None,
    ) -> list[OBEventEntry]:
        results = self._events
        if entity_id is not None:
            results = [e for e in results if e.entity_id == entity_id]
        if event_type is not None:
            results = [e for e in results if e.event_type == event_type]
        return results


def _new_event(
    event_type: str,
    entity_id: str,
    actor: str,
    consent_id: str | None = None,
    payment_id: str | None = None,
    details: dict | None = None,
) -> OBEventEntry:
    return OBEventEntry(
        id=str(uuid.uuid4()),
        event_type=event_type,
        entity_id=entity_id,
        consent_id=consent_id,
        payment_id=payment_id,
        details=details or {},
        created_at=datetime.now(UTC),
        actor=actor,
    )
