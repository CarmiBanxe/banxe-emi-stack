"""MIG-M2.4d — advisory OB international-scheduled payment surface (genuine gap; descriptive, no live).

characterization: IntlScheduledPort / IntlScheduledIntent / IntlScheduledStage state-machine + cross-border
fields. contract: consume M2.4-INT bridge (to_minor_units; accounts projection by account_ref, no balance);
file idempotency; Decimal->minor int. fence: no midaz/ledger/kyc; no live initiation; no wall-clock; no float.
"""

from dataclasses import fields
from decimal import Decimal
from pathlib import Path

import pytest

from services.open_banking.intl_scheduled import (
    STAGE_TRANSITIONS,
    IntlScheduledIntent,
    IntlScheduledPort,
    IntlScheduledStage,
    SandboxIntlScheduledProvider,
)

_BALANCE_FIELDS = {"balance", "available", "ledger_balance", "balance_minor"}


def _p() -> SandboxIntlScheduledProvider:
    return SandboxIntlScheduledProvider()


def _mk(p, key="f1"):
    return p.create_consent(
        file_dedup_key=key,
        payment_intent_ref="PI-1",
        debtor_account_ref="INTERNAL",
        creditor_account_ref="EXTERNAL",
        creditor_iban="DE89370400440532013000",
        creditor_country="DE",
        amount=Decimal("100.00"),
        currency="EUR",
        fx_indicator=True,
        execution_date="2026-07-01",
    )


def test_port_dto_state_machine_and_cross_border() -> None:
    assert issubclass(SandboxIntlScheduledProvider, IntlScheduledPort)
    names = {f.name for f in fields(IntlScheduledIntent)}
    assert {
        "creditor_country",
        "fx_indicator",
        "execution_date",
        "payment_intent_ref",
    } <= names  # cross-border
    assert _BALANCE_FIELDS.isdisjoint(names)  # accounts projection, no balance
    assert STAGE_TRANSITIONS[IntlScheduledStage.EXECUTED] == ()


def test_create_consume_bridge_and_minor_units() -> None:
    i = _mk(_p())
    assert i.payment_intent_ref == "PI-1"  # consumed engine intent ref
    assert i.amount_minor == 10000 and isinstance(i.amount_minor, int)  # Decimal->minor (I-05)
    assert i.creditor_country == "DE" and i.fx_indicator is True
    assert i.stage is IntlScheduledStage.CONSENT_AWAITING


def test_file_idempotency_and_state_machine() -> None:
    p = _p()
    a = _mk(p, "dup")
    b = _mk(p, "dup")
    assert a.intent_id == b.intent_id  # idempotent
    c = p.advance(intent_id=a.intent_id, to_stage=IntlScheduledStage.CONSENT_AUTHORISED)
    assert c.stage is IntlScheduledStage.CONSENT_AUTHORISED
    with pytest.raises(ValueError):  # illegal: authorised -> executed (must go via scheduled)
        p.advance(intent_id=a.intent_id, to_stage=IntlScheduledStage.EXECUTED)


def test_fail_closed_and_accounts_projection() -> None:
    p = _p()
    assert p.get_intent("INTLSCHED-nope") is None
    with pytest.raises(KeyError):
        p.advance(intent_id="INTLSCHED-nope", to_stage=IntlScheduledStage.SCHEDULED)
    assert "INTERNAL" in p.known_account_refs()  # accounts SoT projection (M2.2)


def test_fence_no_midaz_ledger_kyc_no_wallclock_no_float() -> None:
    import services.open_banking.intl_scheduled as mod

    text = Path(mod.__file__).read_text()
    low = text.lower()
    import_lines = "\n".join(
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in ("midaz", "ledger", "kyc", "kyb", "sumsub", "httpx", "requests"):
        assert bad not in import_lines, f"forbidden import: {bad}"
    assert "datetime.now(" not in low and ".utcnow(" not in low and "date.now(" not in low
    assert "float(" not in text and ": float" not in text and "-> float" not in text
