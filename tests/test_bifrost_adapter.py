"""MIG-M2.5-BIF — Bifrost Wave-D adapter (advisory/sandbox; PaymentRailPort; no live GCP).

characterization: BifrostAdapter implements PaymentRailPort (submit/get_status/health); outbound XML
(requestToGCPProcessing-shape) + inbound message mapping. contract: consume AbsPaymentStatus
state-machine; Decimal amount (I-24) -> int minor units. fence: no live GCP/httpx/grpc; no Midaz/ledger
imports; no float.
"""

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest

from services.payment.legacy.bifrost_adapter import (
    BifrostAdapter,
    BifrostInboundMessage,
    BifrostXmlRequest,
    to_minor_units,
)
from services.payment.legacy.legacy_abs_payment_adapter import AbsPaymentStatus
from services.payment.payment_port import (
    BankAccount,
    PaymentDirection,
    PaymentIntent,
    PaymentRail,
    PaymentResult,
    PaymentStatus,
)


def _intent(key: str = "k1") -> PaymentIntent:
    acct = BankAccount(
        account_holder_name="ACME",
        iban="DE89370400440532013000",
        sort_code=None,
        account_number=None,
        bic=None,
    )
    return PaymentIntent(
        idempotency_key=key,
        rail=PaymentRail.SEPA_CT,
        direction=PaymentDirection.OUTBOUND,
        amount=Decimal("100.00"),
        currency="EUR",
        debtor_account=acct,
        creditor_account=acct,
        reference="inv-1",
        end_to_end_id="e2e-1",
        requested_at=datetime.now(UTC),
    )


def test_implements_payment_rail_port() -> None:
    a = BifrostAdapter()
    assert hasattr(a, "submit_payment") and hasattr(a, "get_payment_status") and a.health() is True


def test_submit_idempotent_pending() -> None:
    a = BifrostAdapter()
    r1 = a.submit_payment(_intent("dup"))
    r2 = a.submit_payment(_intent("dup"))
    assert isinstance(r1, PaymentResult) and r1.provider_payment_id == r2.provider_payment_id
    assert r1.status is PaymentStatus.PENDING


def test_outbound_xml_shape_and_minor_units() -> None:
    a = BifrostAdapter()
    req = a.build_outbound_xml(_intent(), "bifrost-x")
    assert isinstance(req, BifrostXmlRequest)
    assert req.request_type == "requestToGCPProcessing"
    assert req.amount_minor == 10000 and isinstance(
        req.amount_minor, int
    )  # 100.00 EUR -> minor int
    assert "requestToGCPProcessing" in req.xml and req.source == "sandbox-mock"


def test_inbound_consumes_abs_state_machine() -> None:
    a = BifrostAdapter()
    res = a.submit_payment(_intent("k2"))
    new = a.handle_inbound(
        BifrostInboundMessage(
            message_id="m1", provider_payment_id=res.provider_payment_id, bifrost_status="SETTLED"
        )
    )
    assert new is AbsPaymentStatus.SETTLED
    assert a.get_payment_status(res.provider_payment_id).status is PaymentStatus.COMPLETED


def test_to_minor_units_decimal_only_no_float() -> None:
    assert to_minor_units(Decimal("1.005"), "EUR") == 101
    with pytest.raises(TypeError):
        to_minor_units(1.5, "EUR")  # float rejected


def test_fail_closed_unknown() -> None:
    a = BifrostAdapter()
    with pytest.raises(KeyError):
        a.get_payment_status("nope")
    with pytest.raises(ValueError):
        a.handle_inbound(
            BifrostInboundMessage(message_id="m", provider_payment_id="x", bifrost_status="???")
        )


def test_fence_no_live_gcp_or_midaz() -> None:
    import services.payment.legacy.bifrost_adapter as mod

    import_lines = "\n".join(
        ln
        for ln in Path(mod.__file__).read_text().splitlines()
        if ln.strip().startswith(("import ", "from "))
    ).lower()
    for bad in (
        "httpx",
        "requests",
        "aiohttp",
        "grpc",
        "google.cloud",
        "socket",
        "midaz",
        "ledger_port",
    ):
        assert bad not in import_lines, f"forbidden live/transport import: {bad}"
