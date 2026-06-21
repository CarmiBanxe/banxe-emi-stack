"""services/open_banking/cbpii_consent.py — Advisory CBPII funds-confirmation-consent lifecycle (MIG-M2.4e).

PARTIAL OB-delta: the CBPII funds-confirmation **check** already exists
(`consent_management` → `handle_cbpii_check(consent_id, amount)`), and the generic consent-grant
lifecycle exists. The only missing slice is the **dedicated OBIE `funds-confirmation-consents`
lifecycle** (create / get / revoke of a CBPII funds-confirmation consent, distinct from the generic
grant). This adds that thin facade — it **references** the existing check by name (descriptive), it does
**NOT** re-implement it and does **NOT** perform funds-confirmation against live balances.

Advisory / sandbox: consumes accounts SoT projection (M2.2) by `account_ref` (no balance). NO live
funds-confirmation, NO Midaz LedgerPort, NO KYC/KYB/AML. `timestamp` caller-supplied (no wall-clock).
DI id-generator (collision-safe) + fail-closed. No monetary numerics here (amounts belong to the
existing check); no float (I-01 trivially).
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum
import secrets

from services.open_banking.m24_int_bridge import AccountSoTProjection

SANDBOX_SOURCE = "sandbox-mock"
_MAX_ID_ATTEMPTS = 5
#: The existing funds-confirmation check this facade references (NOT re-implemented here).
EXISTING_CHECK_REF = "consent_management.handle_cbpii_check"


def _default_consent_id() -> str:
    """Safe default consent-id generator (overridable via constructor DI)."""
    return f"CBPII-{secrets.token_hex(6)}"


class CbpiiConsentStage(str, Enum):
    """OBIE funds-confirmation-consent lifecycle stages (advisory)."""

    AWAITING_AUTHORISATION = "awaiting_authorisation"
    AUTHORISED = "authorised"
    REVOKED = "revoked"
    EXPIRED = "expired"


#: Allowed advisory transitions (no live side effects).
CONSENT_TRANSITIONS: dict[CbpiiConsentStage, tuple[CbpiiConsentStage, ...]] = {
    CbpiiConsentStage.AWAITING_AUTHORISATION: (
        CbpiiConsentStage.AUTHORISED,
        CbpiiConsentStage.REVOKED,
    ),
    CbpiiConsentStage.AUTHORISED: (CbpiiConsentStage.REVOKED, CbpiiConsentStage.EXPIRED),
    CbpiiConsentStage.REVOKED: (),
    CbpiiConsentStage.EXPIRED: (),
}


@dataclass(frozen=True)
class CbpiiFundsConfirmationConsent:
    """Descriptive CBPII funds-confirmation-consent (OBIE shape; no live balance access)."""

    consent_id: str
    idempotency_key: str
    debtor_account_ref: str  # accounts SoT projection (no balance)
    stage: CbpiiConsentStage
    timestamp: str  # caller-supplied (no wall-clock)
    source: str = SANDBOX_SOURCE


@dataclass(frozen=True)
class FundsConfirmationRef:
    """Descriptive pointer to the EXISTING funds-confirmation check (no live execution here)."""

    consent_id: str
    delegates_to: str  # EXISTING_CHECK_REF — the live check lives there, not duplicated
    note: str = "advisory descriptor; not evaluated against live balances in this facade"


class CbpiiPort(ABC):
    """Read-only advisory CBPII funds-confirmation-consent lifecycle contract (fail-closed)."""

    @abstractmethod
    def create_consent(
        self, *, idempotency_key: str, debtor_account_ref: str, timestamp: str
    ) -> CbpiiFundsConfirmationConsent:
        """Create (idempotently) a CBPII funds-confirmation consent (no live balance access)."""

    @abstractmethod
    def advance(
        self, *, consent_id: str, to_stage: CbpiiConsentStage
    ) -> CbpiiFundsConfirmationConsent:
        """Advance the consent lifecycle (validated; fail-closed)."""

    @abstractmethod
    def get_consent(self, consent_id: str) -> CbpiiFundsConfirmationConsent | None:
        """Return the consent, or None if unknown (fail-closed)."""

    @abstractmethod
    def funds_confirmation_ref(self, consent_id: str) -> FundsConfirmationRef:
        """Return a descriptive pointer to the existing funds-confirmation check (no live exec)."""


class SandboxCbpiiProvider(CbpiiPort):
    """Sandbox config-as-data CBPII consent facade; references existing check; no live balances."""

    def __init__(self, *, id_generator: Callable[[], str] | None = None) -> None:
        self._by_key: dict[str, CbpiiFundsConfirmationConsent] = {}
        self._by_id: dict[str, CbpiiFundsConfirmationConsent] = {}
        self._gen_id: Callable[[], str] = id_generator or _default_consent_id
        self._accounts = AccountSoTProjection()

    def create_consent(
        self, *, idempotency_key: str, debtor_account_ref: str, timestamp: str
    ) -> CbpiiFundsConfirmationConsent:
        existing = self._by_key.get(idempotency_key)
        if existing is not None:
            return existing
        consent_id = self._gen_id()
        attempts = 0
        while consent_id in self._by_id:
            attempts += 1
            if attempts >= _MAX_ID_ATTEMPTS:
                raise RuntimeError("cbpii: could not generate a unique consent_id (fail-closed)")
            consent_id = self._gen_id()
        c = CbpiiFundsConfirmationConsent(
            consent_id=consent_id,
            idempotency_key=idempotency_key,
            debtor_account_ref=debtor_account_ref,
            stage=CbpiiConsentStage.AWAITING_AUTHORISATION,
            timestamp=timestamp,
            source=SANDBOX_SOURCE,
        )
        self._by_key[idempotency_key] = c
        self._by_id[consent_id] = c
        return c

    def advance(
        self, *, consent_id: str, to_stage: CbpiiConsentStage
    ) -> CbpiiFundsConfirmationConsent:
        cur = self._by_id.get(consent_id)
        if cur is None:
            raise KeyError(f"cbpii consent not found: {consent_id!r}")  # fail-closed
        if to_stage not in CONSENT_TRANSITIONS[cur.stage]:
            raise ValueError(
                f"illegal transition {cur.stage.value} -> {to_stage.value}"
            )  # fail-closed
        import dataclasses

        nxt = dataclasses.replace(cur, stage=to_stage)
        self._by_id[consent_id] = nxt
        self._by_key[cur.idempotency_key] = nxt
        return nxt

    def get_consent(self, consent_id: str) -> CbpiiFundsConfirmationConsent | None:
        return self._by_id.get(consent_id)  # fail-closed

    def funds_confirmation_ref(self, consent_id: str) -> FundsConfirmationRef:
        # descriptive only — the actual check is the existing handle_cbpii_check (not duplicated)
        return FundsConfirmationRef(consent_id=consent_id, delegates_to=EXISTING_CHECK_REF)

    def known_account_refs(self) -> list[str]:
        return self._accounts.account_refs()
