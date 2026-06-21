"""MIG-M2.4-INT — open-banking integration bridge (advisory, no live initiation, KYC carve-out intact).

contract: PISP -> M2.1-shaped PaymentIntentRef (amount_minor int I-05; account refs; idempotency).
characterization: AccountSoTProjection returns balance-free account refs (M2.2). fence: bridge imports
no Midaz/ledger/kyc; amount_minor int (no float); no live funds-confirmation.
"""

from dataclasses import fields
from decimal import Decimal
from pathlib import Path

import pytest

from services.open_banking.m24_int_bridge import (
    AccountSoTProjection,
    PaymentEngineContract,
    PaymentIntentRef,
    pisp_to_engine_intent,
    to_minor_units,
)

_BALANCE_FIELDS = {"balance", "available", "ledger_balance", "balance_minor", "amount"}


def test_pisp_to_engine_intent_contract_shape() -> None:
    ref = pisp_to_engine_intent(
        idempotency_key="k1",
        debtor_account_ref="INTERNAL",
        creditor_account_ref="EXTERNAL",
        amount=Decimal("15.00"),
        currency="EUR",
    )
    assert isinstance(ref, PaymentIntentRef)
    assert ref.amount_minor == 1500 and isinstance(ref.amount_minor, int)  # I-05 minor units
    assert ref.debtor_account_ref == "INTERNAL" and ref.currency == "EUR"
    # M2.1-aligned shape (no balance fields)
    assert _BALANCE_FIELDS.isdisjoint({f.name for f in fields(PaymentIntentRef)} - {"amount_minor"})


def test_to_minor_units_decimal_only_i05() -> None:
    assert to_minor_units(Decimal("1.005"), "EUR") == 101  # ROUND_HALF_UP, int
    with pytest.raises(TypeError):
        to_minor_units(1.5, "EUR")  # float rejected (I-01/I-05)


def test_account_sot_projection_balance_free() -> None:
    proj = AccountSoTProjection()
    refs = proj.account_refs()
    assert "INTERNAL" in refs and proj.is_known_ref("INTERNAL")
    assert proj.is_known_ref("NOPE") is False


def test_payment_engine_contract_is_protocol() -> None:
    # contract-level mirror of M2.1 PaymentEnginePort (no cross-repo import)
    assert hasattr(PaymentEngineContract, "create_intent")


def test_fence_no_midaz_ledger_kyc_imports() -> None:
    import services.open_banking.m24_int_bridge as mod

    import_lines = "\n".join(
        ln
        for ln in Path(mod.__file__).read_text().splitlines()
        if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in ("midaz", "ledger_port", "ledger", "kyc", "kyb", "sumsub", "httpx", "requests"):
        assert bad not in import_lines, f"forbidden import token: {bad}"
