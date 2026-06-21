"""services/open_banking/intl_scheduled.py — Advisory international-scheduled OB payment surface (MIG-M2.4d).

Genuine OB-delta gap: the **international + scheduled + OB-consent** combination is not covered —
`services/scheduled_payments/*` is domestic-only (no cross-border / currency / jurisdiction fields) and
`api/routers/payments.py` is non-scheduled / non-OB-consent. This adds the descriptive OB surface for
OBIE `international-scheduled-payment-consents` + `international-scheduled-payments` (TPP-initiated,
consent-gated, future-dated, cross-border).

Advisory / sandbox: it **consumes** the M2.4-INT contract (`PaymentEngineContract` + accounts SoT
projection by `account_ref`, no balance) and tracks the consent + schedule state-machine. NO live
initiation/execution, NO Midaz LedgerPort, NO KYC/KYB/AML. `execution_date` + `timestamp` are
caller-supplied (no wall-clock). amount Decimal (I-01) -> minor units int (I-05) via the bridge. DI
id-generator (collision-safe) + fail-closed.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
import secrets

from services.open_banking.m24_int_bridge import AccountSoTProjection, to_minor_units

SANDBOX_SOURCE = "sandbox-mock"
_MAX_ID_ATTEMPTS = 5


def _default_intent_id() -> str:
    """Safe default intent-id generator (overridable via constructor DI)."""
    return f"INTLSCHED-{secrets.token_hex(6)}"


class IntlScheduledStage(str, Enum):
    """OB international-scheduled consent + schedule state-machine (advisory)."""

    CONSENT_AWAITING = "consent_awaiting_authorisation"
    CONSENT_AUTHORISED = "consent_authorised"
    SCHEDULED = "scheduled"
    EXECUTED = "executed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


#: Allowed advisory stage transitions (no live side effects).
STAGE_TRANSITIONS: dict[IntlScheduledStage, tuple[IntlScheduledStage, ...]] = {
    IntlScheduledStage.CONSENT_AWAITING: (
        IntlScheduledStage.CONSENT_AUTHORISED,
        IntlScheduledStage.REJECTED,
    ),
    IntlScheduledStage.CONSENT_AUTHORISED: (
        IntlScheduledStage.SCHEDULED,
        IntlScheduledStage.CANCELLED,
    ),
    IntlScheduledStage.SCHEDULED: (IntlScheduledStage.EXECUTED, IntlScheduledStage.CANCELLED),
    IntlScheduledStage.EXECUTED: (),
    IntlScheduledStage.REJECTED: (),
    IntlScheduledStage.CANCELLED: (),
}


@dataclass(frozen=True)
class IntlScheduledIntent:
    """Advisory OB international-scheduled payment intent (consumes payment-engine; accounts projection).

    amount_minor: int minor units (I-05). account refs are projections (no balance). Cross-border fields
    (creditor_country, fx_indicator) distinguish this from the domestic scheduled_payments surface.
    """

    intent_id: str
    file_dedup_key: str  # consent/file idempotency
    payment_intent_ref: str  # consumed from PaymentEngineContract (M2.1 / M2.4-INT)
    debtor_account_ref: str  # accounts SoT projection (no balance)
    creditor_account_ref: str
    creditor_iban: str
    creditor_country: str  # cross-border (ISO 3166)
    amount_minor: int
    currency: str  # ISO 4217
    fx_indicator: bool  # cross-currency settlement involved
    execution_date: str  # future-dated (caller-supplied, ISO-8601)
    stage: IntlScheduledStage = IntlScheduledStage.CONSENT_AWAITING
    source: str = SANDBOX_SOURCE


class IntlScheduledPort(ABC):
    """Read-only advisory OB international-scheduled contract (no live execution; fail-closed)."""

    @abstractmethod
    def create_consent(
        self,
        *,
        file_dedup_key: str,
        payment_intent_ref: str,
        debtor_account_ref: str,
        creditor_account_ref: str,
        creditor_iban: str,
        creditor_country: str,
        amount: Decimal,
        currency: str,
        fx_indicator: bool,
        execution_date: str,
    ) -> IntlScheduledIntent:
        """Create (idempotently) an advisory intl-scheduled consent. No live initiation/FX."""

    @abstractmethod
    def advance(self, *, intent_id: str, to_stage: IntlScheduledStage) -> IntlScheduledIntent:
        """Advance the consent/schedule state-machine (validated; fail-closed)."""

    @abstractmethod
    def get_intent(self, intent_id: str) -> IntlScheduledIntent | None:
        """Return the intent, or None if unknown (fail-closed)."""


class SandboxIntlScheduledProvider(IntlScheduledPort):
    """Sandbox config-as-data provider; consumes accounts SoT projection; no live; idempotent."""

    def __init__(self, *, id_generator: Callable[[], str] | None = None) -> None:
        self._by_key: dict[str, IntlScheduledIntent] = {}
        self._by_id: dict[str, IntlScheduledIntent] = {}
        self._gen_id: Callable[[], str] = id_generator or _default_intent_id
        self._accounts = AccountSoTProjection()  # M2.2 projection (balance-free)

    def create_consent(
        self,
        *,
        file_dedup_key: str,
        payment_intent_ref: str,
        debtor_account_ref: str,
        creditor_account_ref: str,
        creditor_iban: str,
        creditor_country: str,
        amount: Decimal,
        currency: str,
        fx_indicator: bool,
        execution_date: str,
    ) -> IntlScheduledIntent:
        existing = self._by_key.get(file_dedup_key)
        if existing is not None:  # consent/file idempotency
            return existing
        intent_id = self._gen_id()
        attempts = 0
        while intent_id in self._by_id:
            attempts += 1
            if attempts >= _MAX_ID_ATTEMPTS:
                raise RuntimeError(
                    "intl-scheduled: could not generate a unique intent_id (fail-closed)"
                )
            intent_id = self._gen_id()
        intent = IntlScheduledIntent(
            intent_id=intent_id,
            file_dedup_key=file_dedup_key,
            payment_intent_ref=payment_intent_ref,
            debtor_account_ref=debtor_account_ref,
            creditor_account_ref=creditor_account_ref,
            creditor_iban=creditor_iban,
            creditor_country=creditor_country,
            amount_minor=to_minor_units(amount, currency),  # Decimal (I-01) -> int minor (I-05)
            currency=currency,
            fx_indicator=fx_indicator,
            execution_date=execution_date,
            stage=IntlScheduledStage.CONSENT_AWAITING,
            source=SANDBOX_SOURCE,
        )
        self._by_key[file_dedup_key] = intent
        self._by_id[intent_id] = intent
        return intent

    def advance(self, *, intent_id: str, to_stage: IntlScheduledStage) -> IntlScheduledIntent:
        cur = self._by_id.get(intent_id)
        if cur is None:
            raise KeyError(f"intl-scheduled intent not found: {intent_id!r}")  # fail-closed
        if to_stage not in STAGE_TRANSITIONS[cur.stage]:
            raise ValueError(
                f"illegal transition {cur.stage.value} -> {to_stage.value}"
            )  # fail-closed
        import dataclasses

        nxt = dataclasses.replace(cur, stage=to_stage)
        self._by_id[intent_id] = nxt
        self._by_key[cur.file_dedup_key] = nxt
        return nxt

    def get_intent(self, intent_id: str) -> IntlScheduledIntent | None:
        return self._by_id.get(intent_id)  # fail-closed

    def known_account_refs(self) -> list[str]:
        """Balance-free account-ref projection (accounts SoT, M2.2)."""
        return self._accounts.account_refs()
