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
    PaybisTransportError,
    PaybisTransportPort,
    map_order_status,
)
from services.ledger.production.paybis_provider import (
    PaybisFeatureFlags,
    PaybisSandboxProvider,
    SandboxMockPaybisTransport,
    is_paybis_enabled,
    normalize_error,
    run_sandbox_smoke,
    select_paybis_provider,
)
from services.ledger.production.paybis_sandbox import (
    PAYBIS_ENV_CONTRACT,
    PaybisSandboxError,
    PaybisSandboxWebhookSink,
    build_sandbox_config,
    build_sandbox_transport,
    sandbox_guard,
)
from services.ledger.production.paybis_wave_b import (
    PaybisEndpoints,
    auth_headers,
    build_order_request,
    normalize_order_response,
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

    def get_order_status(self, order_id: str) -> CryptoTransactionStatus:
        return CryptoTransactionStatus.PENDING


class ConfigurableMockPaybisTransport:
    """Wave B richer mock — simulates healthy/unhealthy, retriable failure, and a deterministic
    order→status table. Implements PaybisTransportPort. No live calls."""

    def __init__(
        self,
        *,
        healthy: bool = True,
        fail_initiate: PaybisTransportError | None = None,
        statuses: dict[str, CryptoTransactionStatus] | None = None,
    ) -> None:
        self._healthy = healthy
        self._fail_initiate = fail_initiate
        self._statuses = statuses or {}

    def health(self) -> bool:
        return self._healthy

    def get_fee_estimate(
        self, blockchain: SupportedBlockchain, amount: Decimal
    ) -> CryptoFeeEstimate:
        return CryptoFeeEstimate(
            blockchain=blockchain,
            fee=Decimal("0.25"),
            currency="GBP",
            priority=FeePriority.LOW,
            estimated_confirmation_blocks=6,
        )

    def initiate_order(self, request: CryptoTransactionRequest) -> CryptoTransactionResult:
        if self._fail_initiate is not None:
            raise self._fail_initiate
        return CryptoTransactionResult(
            tx_id=request.tx_id,
            tx_hash=None,
            blockchain=request.blockchain,
            amount=request.amount,
            fee=Decimal("0.25"),
            currency=request.currency,
            status=CryptoTransactionStatus.PENDING,
            from_wallet_id=request.from_wallet_id,
            to_address=request.to_address,
            created_at=datetime.now(UTC),
            confirmed_at=None,
        )

    def get_order_status(self, order_id: str) -> CryptoTransactionStatus:
        # deterministic: same order_id → same status across repeated calls
        return self._statuses.get(order_id, CryptoTransactionStatus.PENDING)


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


# ══════════════════════════ Wave B ══════════════════════════


# ── transport failure path (retriable provider error propagates) ────────────────
def test_transport_failure_path_retriable():
    err = PaybisTransportError("provider 503", retriable=True)
    adapter = PaybisCryptoAdapter(transport=ConfigurableMockPaybisTransport(fail_initiate=err))
    with pytest.raises(PaybisTransportError) as e:
        adapter.create_tx(_req())
    assert e.value.retriable is True and e.value.code == "PAYBIS_TRANSPORT"
    # unhealthy provider surfaces via health()
    assert (
        PaybisCryptoAdapter(transport=ConfigurableMockPaybisTransport(healthy=False)).health()
        is False
    )


# ── deterministic order/status lookup (stable across repeated calls) ────────────
def test_get_order_status_deterministic():
    mock = ConfigurableMockPaybisTransport(statuses={"ord-1": CryptoTransactionStatus.CONFIRMED})
    adapter = PaybisCryptoAdapter(transport=mock)
    first = adapter.get_order_status("ord-1")
    second = adapter.get_order_status("ord-1")
    assert first is second is CryptoTransactionStatus.CONFIRMED  # deterministic
    assert adapter.get_order_status("unknown-id") is CryptoTransactionStatus.PENDING  # safe default
    with pytest.raises(CryptoLedgerError) as e:
        adapter.get_order_status("")
    assert e.value.code == "ORDER_ID_REQUIRED"
    # default transport keeps order-status fenced
    with pytest.raises(PaybisLiveFencedError):
        PaybisCryptoAdapter().get_order_status("ord-1")


# ── live-readiness scaffolding: request build (pure) ────────────────────────────
def test_build_order_request_structural():
    payload = build_order_request(_req(Decimal("12.5000")))
    assert payload["partnerOrderId"] == "ord-1"
    assert payload["amount"] == "12.5000" and isinstance(
        payload["amount"], str
    )  # Decimal→str, no float
    assert payload["blockchain"] == "BTC" and payload["customerId"] == "cust-1"
    bad = CryptoTransactionRequest(
        tx_id="x",
        from_wallet_id="w",
        to_address="a",
        blockchain=BTC,
        amount=1.0,
        currency="BTC",
        fee_level=FeePriority.LOW,
        customer_id="c",  # type: ignore[arg-type]
    )
    with pytest.raises(CryptoLedgerError) as e:
        build_order_request(bad)
    assert e.value.code == "I01_DECIMAL"


# ── response normalization (+ malformed failure) ────────────────────────────────
def test_normalize_order_response_and_malformed():
    assert normalize_order_response({"status": "completed"}) is CryptoTransactionStatus.CONFIRMED
    assert normalize_order_response({"state": "cancelled"}) is CryptoTransactionStatus.FAILED
    for bad in ("not-a-dict", {}, {"status": ""}, {"other": "x"}):
        with pytest.raises(CryptoLedgerError) as e:
            normalize_order_response(bad)  # type: ignore[arg-type]
        assert e.value.code == "PAYBIS_MALFORMED_RESPONSE"


# ── endpoint routing + auth injection both FENCED (no guess, no secret) ─────────
def test_endpoints_and_auth_fenced():
    cfg = PaybisConfig()  # base_url empty → unknown
    eps = PaybisEndpoints(paths={"initiate": "v1/orders"})
    with pytest.raises(PaybisLiveFencedError):
        eps.endpoint_for(cfg, "initiate")  # base_url unknown → fenced
    with pytest.raises(PaybisLiveFencedError):
        PaybisEndpoints().endpoint_for(
            PaybisConfig(base_url="https://x"), "initiate"
        )  # path unknown
    # when both known, it routes (pure string build, still no HTTP)
    url = eps.endpoint_for(PaybisConfig(base_url="https://x/"), "initiate")
    assert url == "https://x/v1/orders"
    # auth headers remain fenced (no secret read, no scheme guess)
    with pytest.raises(PaybisLiveFencedError):
        auth_headers(PaybisConfig())


# ── webhook edge: snake_case keys + unknown status maps to PENDING (fenced policy) ──
def test_webhook_edge_cases():
    ev = parse_event({"partner_order_id": "po-x", "state": "weird-state"})
    assert ev.idempotency_key == "po-x"
    assert ev.status is CryptoTransactionStatus.PENDING  # unknown → safe default, no guess


# ══════════════════════════ SANDBOX installation ══════════════════════════


# ── sandbox config forces SANDBOX, refuses PRODUCTION (OPERATOR-GATE) ───────────
def test_build_sandbox_config_forces_sandbox(monkeypatch):
    monkeypatch.delenv("PAYBIS_ENV", raising=False)
    cfg = build_sandbox_config()  # default → SANDBOX
    assert cfg.env is PaybisEnv.SANDBOX
    assert cfg.api_key_env_var == "PAYBIS_API_KEY"  # NAME only, never a secret value
    monkeypatch.setenv("PAYBIS_ENV", "PRODUCTION")
    with pytest.raises(PaybisSandboxError) as e:
        build_sandbox_config()
    assert e.value.code == "PAYBIS_SANDBOX_ONLY"


# ── sandbox guard + transport stays fenced (no live calls) ──────────────────────
def test_sandbox_guard_and_transport_fenced():
    sandbox_guard(PaybisConfig(env=PaybisEnv.SANDBOX))  # ok
    with pytest.raises(PaybisSandboxError):
        sandbox_guard(PaybisConfig(env=PaybisEnv.PRODUCTION))
    transport = build_sandbox_transport(PaybisConfig(env=PaybisEnv.SANDBOX))
    with pytest.raises(PaybisLiveFencedError):
        transport.health()  # sandbox HTTP needs endpoints (SRC-06) → fenced, no live call


# ── sandbox webhook intake: idempotent, unverified, malformed raises ────────────
def test_sandbox_webhook_sink_idempotent():
    sink = PaybisSandboxWebhookSink()
    first = sink.intake({"partnerOrderId": "po-1", "status": "completed"})
    assert first is not None and first.status is CryptoTransactionStatus.CONFIRMED
    dup = sink.intake({"partnerOrderId": "po-1", "status": "completed"})  # same key → deduped
    assert dup is None and sink.duplicates == 1 and len(sink.events) == 1
    # distinct key recorded
    assert sink.intake({"transactionId": "tx-2", "status": "pending"}) is not None
    assert len(sink.events) == 2
    # malformed / no-idempotency-key still raise (no silent accept)
    with pytest.raises(CryptoLedgerError) as e:
        sink.intake({"status": "pending"})
    assert e.value.code == "PAYBIS_WEBHOOK_NO_IDEMPOTENCY_KEY"


# ── env-var contract is names-only (no secret values) ───────────────────────────
def test_env_contract_names_only():
    assert set(PAYBIS_ENV_CONTRACT) == {
        "PAYBIS_ENABLED",
        "PAYBIS_MODE",
        "PAYBIS_ENV",
        "PAYBIS_BASE_URL",
        "PAYBIS_API_KEY",
        "PAYBIS_WEBHOOK_SECRET",
    }
    # values are human descriptions, not credentials (no "KEY=VALUE" literal)
    assert all(isinstance(v, str) and v and "=" not in v for v in PAYBIS_ENV_CONTRACT.values())


# ══════════════════════════ SANDBOX provider (flag + selector + façade + smoke) ══════════════════════════


def test_feature_flag_and_selection(monkeypatch):
    monkeypatch.delenv("PAYBIS_ENABLED", raising=False)
    monkeypatch.delenv("PAYBIS_MODE", raising=False)
    assert is_paybis_enabled() is False
    # disabled → selector refuses
    with pytest.raises(PaybisSandboxError) as e:
        select_paybis_provider()
    assert e.value.code == "PAYBIS_DISABLED"
    # enabled + sandbox → provider
    monkeypatch.setenv("PAYBIS_ENABLED", "true")
    monkeypatch.setenv("PAYBIS_MODE", "sandbox")
    assert is_paybis_enabled() is True
    assert isinstance(select_paybis_provider(), PaybisSandboxProvider)
    # production mode refused (OPERATOR-GATE)
    monkeypatch.setenv("PAYBIS_MODE", "production")
    with pytest.raises(PaybisSandboxError) as e2:
        select_paybis_provider()
    assert e2.value.code == "PAYBIS_SANDBOX_ONLY"


def test_flags_from_env(monkeypatch):
    monkeypatch.setenv("PAYBIS_ENABLED", "yes")
    flags = PaybisFeatureFlags.from_env()
    assert flags.enabled is True and flags.mode == "sandbox"
    assert flags.webhook_secret_env == "PAYBIS_WEBHOOK_SECRET"  # NAME only


def test_provider_mock_quote_order_status():
    provider = PaybisSandboxProvider(transport=SandboxMockPaybisTransport())
    assert provider.health_check() == {"provider": "paybis", "mode": "sandbox", "healthy": True}
    quote = provider.get_quote(BTC, Decimal("100.00"))
    assert isinstance(quote, CryptoFeeEstimate) and quote.fee == Decimal("0.10")
    order = provider.create_order(_req())
    assert order.status is CryptoTransactionStatus.PENDING and order.tx_id == "ord-1"
    assert (
        provider.get_order_status("ord-1") is CryptoTransactionStatus.PENDING
    )  # status-poll shape


def test_provider_webhook_contract_idempotent_unverified():
    provider = PaybisSandboxProvider(transport=SandboxMockPaybisTransport())
    r1 = provider.handle_webhook({}, {"partnerOrderId": "po-1", "status": "completed"})
    assert r1["accepted"] is True and r1["verified"] is False and r1["status"] == "CONFIRMED"
    r2 = provider.handle_webhook({}, {"partnerOrderId": "po-1", "status": "completed"})  # dup
    assert r2 == {"accepted": False, "duplicate": True, "verified": False}


def test_error_mapping_and_smoke():
    err = normalize_error(CryptoLedgerError("boom", code="X1"))
    assert err == {"error": "X1", "message": "boom"}
    # end-to-end sandbox smoke returns a structured ok report (mock path)
    report = run_sandbox_smoke()
    assert report["ok"] is True
    assert report["provider_selected"] == "paybis-sandbox"
    assert report["health"]["healthy"] is True
    assert report["order"]["status"] == "PENDING"
    assert report["webhook"]["accepted"] is True and report["webhook"]["verified"] is False


def test_smoke_error_path_production_refused(monkeypatch):
    monkeypatch.setenv("PAYBIS_ENABLED", "true")
    monkeypatch.setenv("PAYBIS_MODE", "sandbox")
    monkeypatch.setenv(
        "PAYBIS_ENV", "PRODUCTION"
    )  # build_sandbox_config refuses → smoke error path
    report = run_sandbox_smoke()
    assert report["ok"] is False
    assert report["error"]["error"] == "PAYBIS_SANDBOX_ONLY"
