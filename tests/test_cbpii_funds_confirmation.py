"""MIG-M2.4e — advisory CBPII funds-confirmation-consent lifecycle (partial OB-delta facade).

characterization: CbpiiPort / consent DTO / lifecycle state-machine. contract: idempotent consent;
funds_confirmation_ref DELEGATES to the existing check (not re-implemented; no live balance); accounts
projection by account_ref. fence: no midaz/ledger/kyc; no live funds-confirmation; no wall-clock; no float.
"""

from dataclasses import fields
from pathlib import Path

import pytest

from services.open_banking.cbpii_consent import (
    CONSENT_TRANSITIONS,
    EXISTING_CHECK_REF,
    CbpiiConsentStage,
    CbpiiFundsConfirmationConsent,
    CbpiiPort,
    FundsConfirmationRef,
    SandboxCbpiiProvider,
)

_BALANCE_FIELDS = {"balance", "available", "ledger_balance", "amount", "balance_minor"}


def _p() -> SandboxCbpiiProvider:
    return SandboxCbpiiProvider()


def test_port_dto_state_machine() -> None:
    assert issubclass(SandboxCbpiiProvider, CbpiiPort)
    assert {f.name for f in fields(CbpiiFundsConfirmationConsent)} == {
        "consent_id",
        "idempotency_key",
        "debtor_account_ref",
        "stage",
        "timestamp",
        "source",
    }
    assert {s.value for s in CbpiiConsentStage} == {
        "awaiting_authorisation",
        "authorised",
        "revoked",
        "expired",
    }
    assert CONSENT_TRANSITIONS[CbpiiConsentStage.REVOKED] == ()
    # no balance/amount fields on the consent DTO (funds-confirmation is delegated, not stored)
    assert _BALANCE_FIELDS.isdisjoint({f.name for f in fields(CbpiiFundsConfirmationConsent)})


def test_create_idempotent_and_lifecycle() -> None:
    p = _p()
    a = p.create_consent(
        idempotency_key="k1", debtor_account_ref="INTERNAL", timestamp="2026-06-22T01:00:00Z"
    )
    b = p.create_consent(
        idempotency_key="k1", debtor_account_ref="INTERNAL", timestamp="2026-06-22T01:00:00Z"
    )
    assert a.consent_id == b.consent_id and a.stage is CbpiiConsentStage.AWAITING_AUTHORISATION
    c = p.advance(consent_id=a.consent_id, to_stage=CbpiiConsentStage.AUTHORISED)
    assert c.stage is CbpiiConsentStage.AUTHORISED
    with pytest.raises(ValueError):  # illegal: revoked is terminal -> cannot re-authorise
        p.advance(
            consent_id=p.advance(
                consent_id=a.consent_id, to_stage=CbpiiConsentStage.REVOKED
            ).consent_id,
            to_stage=CbpiiConsentStage.AUTHORISED,
        )


def test_funds_confirmation_delegates_not_reimplemented() -> None:
    p = _p()
    c = p.create_consent(idempotency_key="k", debtor_account_ref="INTERNAL", timestamp="t")
    ref = p.funds_confirmation_ref(c.consent_id)
    assert isinstance(ref, FundsConfirmationRef)
    assert (
        ref.delegates_to == EXISTING_CHECK_REF == "consent_management.handle_cbpii_check"
    )  # not duplicated


def test_fail_closed_and_accounts_projection() -> None:
    p = _p()
    assert p.get_consent("CBPII-nope") is None
    with pytest.raises(KeyError):
        p.advance(consent_id="CBPII-nope", to_stage=CbpiiConsentStage.AUTHORISED)
    assert "INTERNAL" in p.known_account_refs()


def test_fence_no_midaz_ledger_kyc_no_wallclock_no_float() -> None:
    import services.open_banking.cbpii_consent as mod

    text = Path(mod.__file__).read_text()
    low = text.lower()
    import_lines = "\n".join(
        ln for ln in text.splitlines() if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in ("midaz", "ledger", "kyc", "kyb", "sumsub", "httpx", "requests"):
        assert bad not in import_lines, f"forbidden import: {bad}"
    assert "datetime.now(" not in low and ".utcnow(" not in low and "date.now(" not in low
    assert "float(" not in text and ": float" not in text and "-> float" not in text
