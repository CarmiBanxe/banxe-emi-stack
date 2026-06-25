"""Wave A tests — PaybisCryptoAdapter + webhook intake (mock-first, fenced-live).

Real assertions: provider routing through an injectable mock transport, I-01 Decimal guards,
non-custodial OUT_OF_PAYBIS_SCOPE boundary, fenced-live behaviour, order-state mapping, config,
and the webhook structural parse + idempotency + fenced signature verification. No live HTTP,
no secrets, no funds.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from services.ledger.crypto_ledger_port import (
    CryptoFeeEstimate,
    CryptoLedgerError,
    CryptoTransactionRequest,
    CryptoTransactionResult,
    CryptoTransactionStatus,
    FeePriority,
    SupportedBlockchain,
)
from services.ledger.production.paybis_crypto_adapter import (
    FencedLivePaybisTransport,
    PaybisConfig,
    PaybisCryptoAdapter,
    PaybisEnv,
    PaybisLiveFencedError,
    PaybisTransportPort,
    map_order_status,
)
from services.ledger.production.paybis_webhook import (
    PaybisWebhookEvent,
    PaybisWebhookSpecUnknownError,
    parse_event,
    verify_signature,
)

BTC = SupportedBlockchain.BTC


class MockPaybisTransport:
    """In-memory PAYBIS transport for tests (implements PaybisTransportPort). No live calls."""

    def __init__(self) -> None:
        self.orders: list[CryptoTransactionRequest] = []

    def health(self) -> bool:
        return True

    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=Decimal("0.50"),
            currency="GBP",
            priority=FeePriority.MEDIUM,
            estimated_confirmation_blocks=3,
        )

    def initiate_order(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        self.orders.append(request)
        return CryptoTransactionResult(
            tx_id=request.tx_id,
            tx_hash=None,
            blockchain=request.blockchain,
            amount=request.amount,
            fee=Decimal("0.50"),
            currency=request.currency,
            status=CryptoTransactionStatus.PENDING,
            from_wallet_id=request.from_wallet_id,
            to_address=request.to_address,
            created_at=datetime.now(UTC),
            confirmed_at=None,
        )


def _req(amount: Decimal = Decimal("100.00")) -> CryptoTransactionRequest:
    return CryptoTransactionRequest(
        tx_id="ord-1",
        from_wallet_id="w1",
        to_address="addr1",
        blockchain=BTC,
        amount=amount,
        currency="BTC",
        fee_level=FeePriority.MEDIUM,
        customer_id="cust-1",
    )


# ── port conformance + mock routing ─────────────────────────────────────────────
def test_adapter_satisfies_frozen_port_and_routes_via_transport():
    mock = MockPaybisTransport()
    assert isinstance(mock, PaybisTransportPort)
    adapter = PaybisCryptoAdapter(transport=mock)
    assert adapter.health() is True
    fee = adapter.get_fee_estimate(BTC, Decimal("100.00"))
    assert isinstance(fee, CryptoFeeEstimate) and fee.fee == Decimal("0.50")
    res = adapter.create_tx(_req())
    assert isinstance(res, CryptoTransactionResult)
    assert res.status is CryptoTransactionStatus.PENDING and res.tx_id == "ord-1"
    assert mock.orders[0].amount == Decimal("100.00")


# ── I-01 Decimal + amount guards ────────────────────────────────────────────────
def test_i01_decimal_and_amount_guards():
    adapter = PaybisCryptoAdapter(transport=MockPaybisTransport())
    with pytest.raises(CryptoLedgerError) as e1:
        adapter.get_fee_estimate(BTC, 100.0)  # float → I-01 violation
    assert e1.value.code == "I01_DECIMAL"
    bad = CryptoTransactionRequest(
        tx_id="x",
        from_wallet_id="w",
        to_address="a",
        blockchain=BTC,
        amount=Decimal("0"),
        currency="BTC",
        fee_level=FeePriority.LOW,
        customer_id="c",
    )
    with pytest.raises(CryptoLedgerError) as e2:
        adapter.create_tx(bad)
    assert e2.value.code == "AMOUNT_NONPOSITIVE"
    # create_tx float amount → I-01 violation (frozen dataclass does not enforce at runtime)
    float_req = CryptoTransactionRequest(
        tx_id="f",
        from_wallet_id="w",
        to_address="a",
        blockchain=BTC,
        amount=1.0,
        currency="BTC",
        fee_level=FeePriority.LOW,
        customer_id="c",  # type: ignore[arg-type]
    )
    with pytest.raises(CryptoLedgerError) as e3:
        adapter.create_tx(float_req)
    assert e3.value.code == "I01_DECIMAL"


# ── non-custodial boundary (ADR-108) ────────────────────────────────────────────
def test_non_custodial_scope_raises():
    adapter = PaybisCryptoAdapter(transport=MockPaybisTransport())
    with pytest.raises(CryptoLedgerError) as e1:
        adapter.get_balance("w1", BTC)
    assert e1.value.code == "OUT_OF_PAYBIS_SCOPE"
    with pytest.raises(CryptoLedgerError) as e2:
        adapter.create_wallet_address("cust-1", BTC)
    assert e2.value.code == "OUT_OF_PAYBIS_SCOPE"


# ── fenced live default (no secrets, no funds) ──────────────────────────────────
def test_default_transport_is_fenced():
    adapter = PaybisCryptoAdapter()  # default = FencedLivePaybisTransport
    for call in (
        lambda: adapter.health(),
        lambda: adapter.get_fee_estimate(BTC, Decimal("1.00")),
        lambda: adapter.create_tx(_req()),
    ):
        with pytest.raises(PaybisLiveFencedError) as e:
            call()
        assert e.value.code == "PAYBIS_LIVE_FENCED"
    # direct transport too
    t = FencedLivePaybisTransport()
    with pytest.raises(PaybisLiveFencedError):
        t.initiate_order(_req())


# ── order-state mapping ─────────────────────────────────────────────────────────
def test_order_state_mapping():
    assert map_order_status("pending") is CryptoTransactionStatus.PENDING
    assert map_order_status("Completed") is CryptoTransactionStatus.CONFIRMED
    for s in ("cancelled", "rejected", "expired", "refunded"):
        assert map_order_status(s) is CryptoTransactionStatus.FAILED
    assert map_order_status("something-unknown") is CryptoTransactionStatus.PENDING  # safe default


# ── config (no secrets) ─────────────────────────────────────────────────────────
def test_config_from_env(monkeypatch):
    monkeypatch.setenv("PAYBIS_ENV", "PRODUCTION")
    monkeypatch.setenv("PAYBIS_BASE_URL", "https://example.invalid")
    cfg = PaybisConfig.from_env()
    assert cfg.env is PaybisEnv.PRODUCTION and cfg.base_url == "https://example.invalid"
    assert cfg.api_key_env_var == "PAYBIS_API_KEY"  # NAME only, not a secret value
    monkeypatch.setenv("PAYBIS_ENV", "garbage")
    assert PaybisConfig.from_env().env is PaybisEnv.SANDBOX  # invalid → safe default


# ── webhook intake (structural parse + idempotency + fenced verify) ─────────────
def test_webhook_parse_and_idempotency():
    ev = parse_event(
        {
            "eventType": "paymentCompleted",
            "requestId": "r1",
            "partnerOrderId": "po-9",
            "transactionId": "tx-9",
            "status": "completed",
        }
    )
    assert isinstance(ev, PaybisWebhookEvent)
    assert ev.status is CryptoTransactionStatus.CONFIRMED
    assert ev.idempotency_key == "po-9"
    # fallback to transaction_id when partnerOrderId missing
    ev2 = parse_event({"transactionId": "tx-only", "status": "pending"})
    assert ev2.idempotency_key == "tx-only"
    # no key → error
    ev_nokey = parse_event({"status": "pending"})
    with pytest.raises(CryptoLedgerError) as e:
        _ = ev_nokey.idempotency_key
    assert e.value.code == "PAYBIS_WEBHOOK_NO_IDEMPOTENCY_KEY"


def test_webhook_bad_payload_and_fenced_signature():
    with pytest.raises(CryptoLedgerError) as e:
        parse_event("not-a-dict")  # type: ignore[arg-type]
    assert e.value.code == "PAYBIS_WEBHOOK_BAD_PAYLOAD"
    with pytest.raises(PaybisWebhookSpecUnknownError):
        verify_signature(b"{}", "sig")
