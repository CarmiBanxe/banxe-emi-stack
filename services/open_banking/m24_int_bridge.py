"""services/open_banking/m24_int_bridge.py — MIG-M2.4-INT open-banking integration bridge.

Advisory, additive integration seam wiring the existing open-banking PISP/AISP surface to:
  - the **payments engine contract** (MIG-M2.1 ``PaymentEnginePort``, which lives in banxe-payment-core
    — a DIFFERENT repo). We therefore mirror its intent contract here as a local Protocol
    (``PaymentEngineContract``) and map a PISP ``PaymentInitiation`` to an M2.1-shaped intent ref.
    This is **contract-level** consumption — NO cross-repo import, NO live engine call.
  - the **accounts SoT** (MIG-M2.2 ``api/models/account_sot.py``, same repo) — a **balance-free**
    account-ref projection. Balances are NOT sourced here (no live funds-confirmation against live
    balances; the existing ``InMemoryAccountData`` / live balance path is untouched).

Does NOT modify the live FCA PISP/AISP services, does NOT call Midaz LedgerPort, does NOT touch the
KYC/KYB/AML carve-out (pending I-27 sign-off). Advisory / read-only. I-05: amount_minor int (never
float); I-01: amounts as Decimal upstream.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Protocol, runtime_checkable

from api.models.account_sot import SandboxAccountSoT

SANDBOX_SOURCE = "sandbox-mock"

# ISO 4217 minor-unit exponents (config-as-data; default 2dp).
_MINOR_UNITS: dict[str, int] = {"EUR": 2, "GBP": 2, "USD": 2, "CHF": 2}


def to_minor_units(amount: Decimal, currency: str) -> int:
    """Convert a Decimal amount to integer minor units (I-05; never float)."""
    if not isinstance(amount, Decimal):  # I-01: Decimal upstream only
        raise TypeError("amount must be Decimal")
    dp = _MINOR_UNITS.get(currency.upper(), 2)
    scaled = (amount * (Decimal(10) ** dp)).to_integral_value(rounding=ROUND_HALF_UP)
    return int(scaled)


@dataclass(frozen=True)
class PaymentIntentRef:
    """M2.1-aligned advisory payment-intent ref (mirrors banxe-payment-core PaymentIntent shape).

    amount_minor: int minor units (I-05). account refs are projections — no balance.
    """

    idempotency_key: str
    debtor_account_ref: str
    creditor_account_ref: str
    amount_minor: int
    currency: str
    source: str = SANDBOX_SOURCE


@runtime_checkable
class PaymentEngineContract(Protocol):
    """Local mirror of the MIG-M2.1 PaymentEnginePort.create_intent contract (no cross-repo import).

    A prod wiring would supply a real client implementing this Protocol against banxe-payment-core;
    here it is contract-level only (advisory; no live execution).
    """

    def create_intent(
        self,
        *,
        idempotency_key: str,
        debtor_account_ref: str,
        creditor_account_ref: str,
        amount_minor: int,
        currency: str,
    ) -> object: ...


class AccountSoTProjection:
    """Balance-free account-ref projection over the accounts SoT (MIG-M2.2). No balances, no Midaz."""

    def __init__(self) -> None:
        self._sot = SandboxAccountSoT()

    def account_refs(self) -> list[str]:
        """Return account-type refs from the accounts SoT (descriptive; no balance)."""
        return [a.account_type for a in self._sot.list_account_metadata()]

    def is_known_ref(self, account_ref: str) -> bool:
        return account_ref in set(self.account_refs())


def pisp_to_engine_intent(
    *,
    idempotency_key: str,
    debtor_account_ref: str,
    creditor_account_ref: str,
    amount: Decimal,
    currency: str,
) -> PaymentIntentRef:
    """Map a PISP initiation to an M2.1-shaped advisory intent ref (contract-level; no live call).

    Amount (Decimal, I-01) -> minor units (int, I-05). Projection over accounts SoT by ref (no balance).
    """
    return PaymentIntentRef(
        idempotency_key=idempotency_key,
        debtor_account_ref=debtor_account_ref,
        creditor_account_ref=creditor_account_ref,
        amount_minor=to_minor_units(amount, currency),
        currency=currency,
        source=SANDBOX_SOURCE,
    )
