"""
tests/test_crypto_legacy_router.py — /v1/crypto-legacy router smoke tests.

Uses an isolated FastAPI test app with dependency override so the router
is tested independently of the full application stack.
All responses are structurally checked (status code + key fields).
Amounts are verified as strings (I-05: DecimalString — never float).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers.crypto_legacy import router
from services.ledger.crypto_application_service import CryptoApplicationService
from services.ledger.legacy.legacy_crypto_processing_adapter import (
    LegacyCryptoProcessingAdapter,
)
from services.ledger.legacy.legacy_crypto_rpc_adapter import LegacyCryptoRpcAdapter
from services.ledger.legacy.legacy_crypto_wallet_adapter import LegacyCryptoWalletAdapter


def _make_svc() -> CryptoApplicationService:
    return CryptoApplicationService(
        wallet=LegacyCryptoWalletAdapter(),
        processing=LegacyCryptoProcessingAdapter(),
        rpc=LegacyCryptoRpcAdapter(),
    )


# Isolated test app — avoids importing the full main.py stack.
_test_app = FastAPI()
_test_app.include_router(router)

# Override DI — use scaffold adapters (no lru_cache singleton bleed-through).
from api.deps import get_crypto_application_service  # noqa: E402

_test_app.dependency_overrides[get_crypto_application_service] = _make_svc


@pytest.fixture(scope="module")
def client() -> TestClient:
    return TestClient(_test_app)


# ---------------------------------------------------------------------------
# 1. Health
# ---------------------------------------------------------------------------


def test_health_200(client: TestClient) -> None:
    r = client.get("/health")
    assert r.status_code == 200


def test_health_all_true(client: TestClient) -> None:
    r = client.get("/health")
    body = r.json()
    assert body["wallet"] is True
    assert body["processing"] is True
    assert body["rpc"] is True


# ---------------------------------------------------------------------------
# 2. GET /balance/{blockchain}/{wallet_id}
# ---------------------------------------------------------------------------


def test_get_balance_200(client: TestClient) -> None:
    r = client.get("/balance/BTC/w-btc-001")
    assert r.status_code == 200


def test_get_balance_confirmed_is_string(client: TestClient) -> None:
    r = client.get("/balance/ETH/w-eth-001")
    body = r.json()
    assert isinstance(body["confirmed_balance"], str)


def test_get_balance_default_zero(client: TestClient) -> None:
    r = client.get("/balance/BTC/unknown-wallet")
    body = r.json()
    assert body["confirmed_balance"] == "0"


def test_get_balance_blockchain_preserved(client: TestClient) -> None:
    r = client.get("/balance/TRX/w-trx")
    body = r.json()
    assert body["blockchain"] == "TRX"


def test_get_balance_wallet_id_preserved(client: TestClient) -> None:
    r = client.get("/balance/XRP/my-wallet-123")
    body = r.json()
    assert body["wallet_id"] == "my-wallet-123"


# ---------------------------------------------------------------------------
# 3. POST /wallet-address
# ---------------------------------------------------------------------------


def test_create_wallet_address_200(client: TestClient) -> None:
    r = client.post("/wallet-address", json={"customer_id": "cust-r-001", "blockchain": "ETH"})
    assert r.status_code == 200


def test_create_wallet_address_customer_preserved(client: TestClient) -> None:
    r = client.post("/wallet-address", json={"customer_id": "cust-r-002", "blockchain": "BTC"})
    body = r.json()
    assert body["customer_id"] == "cust-r-002"


def test_create_wallet_address_has_address_field(client: TestClient) -> None:
    r = client.post("/wallet-address", json={"customer_id": "cust-r-003", "blockchain": "TRX"})
    body = r.json()
    assert "address" in body
    assert len(body["address"]) > 0


# ---------------------------------------------------------------------------
# 4. POST /tx
# ---------------------------------------------------------------------------

_TX_BODY = {
    "tx_id": "r-tx-001",
    "from_wallet_id": "w-btc",
    "to_address": "1A1zP1eP5QGefi2DMPTfTL5SLmv7Divf",
    "blockchain": "BTC",
    "amount": "0.5",
    "currency": "BTC",
    "fee_level": "MEDIUM",
    "customer_id": "cust-r-001",
}


def test_create_tx_200(client: TestClient) -> None:
    r = client.post("/tx", json=_TX_BODY)
    assert r.status_code == 200


def test_create_tx_tx_id_preserved(client: TestClient) -> None:
    r = client.post("/tx", json=_TX_BODY)
    body = r.json()
    assert body["tx_id"] == "r-tx-001"


def test_create_tx_amount_is_string(client: TestClient) -> None:
    r = client.post("/tx", json=_TX_BODY)
    body = r.json()
    assert isinstance(body["amount"], str)
    assert body["amount"] == "0.5"


def test_create_tx_fee_is_string(client: TestClient) -> None:
    r = client.post("/tx", json=_TX_BODY)
    body = r.json()
    assert isinstance(body["fee"], str)


def test_create_tx_status_pending(client: TestClient) -> None:
    r = client.post("/tx", json=_TX_BODY)
    body = r.json()
    assert body["status"] == "PENDING"


# ---------------------------------------------------------------------------
# 5. GET /fee-estimate/{blockchain}
# ---------------------------------------------------------------------------


def test_get_fee_estimate_200(client: TestClient) -> None:
    r = client.get("/fee-estimate/ETH")
    assert r.status_code == 200


def test_get_fee_estimate_fee_is_string(client: TestClient) -> None:
    r = client.get("/fee-estimate/BTC")
    body = r.json()
    assert isinstance(body["fee"], str)


def test_get_fee_estimate_blockchain_bound(client: TestClient) -> None:
    r = client.get("/fee-estimate/TRX")
    body = r.json()
    assert body["blockchain"] == "TRX"


# ---------------------------------------------------------------------------
# 6. POST /broadcast
# ---------------------------------------------------------------------------


def test_broadcast_200(client: TestClient) -> None:
    r = client.post("/broadcast", json={"signed_tx": "0xabc123", "blockchain": "ETH"})
    assert r.status_code == 200


def test_broadcast_returns_tx_hash(client: TestClient) -> None:
    r = client.post("/broadcast", json={"signed_tx": "0xabc123", "blockchain": "ETH"})
    body = r.json()
    assert "tx_hash" in body
    assert body["tx_hash"].startswith("0x")


# ---------------------------------------------------------------------------
# 7. GET /block/{blockchain}/{block_hash}
# ---------------------------------------------------------------------------


def test_get_block_200(client: TestClient) -> None:
    r = client.get("/block/BTC/some-hash-001")
    assert r.status_code == 200


def test_get_block_hash_preserved(client: TestClient) -> None:
    r = client.get("/block/ETH/my-block-hash")
    body = r.json()
    assert body["block_hash"] == "my-block-hash"


def test_get_block_scaffold_tx_count_zero(client: TestClient) -> None:
    r = client.get("/block/XRP/new-block")
    body = r.json()
    assert body["tx_count"] == 0


# ---------------------------------------------------------------------------
# 8. GET /rpc/fee-estimate/{blockchain}/{priority}
# ---------------------------------------------------------------------------


def test_rpc_fee_estimate_200(client: TestClient) -> None:
    r = client.get("/rpc/fee-estimate/ETH/HIGH")
    assert r.status_code == 200


def test_rpc_fee_estimate_fee_is_string(client: TestClient) -> None:
    r = client.get("/rpc/fee-estimate/BTC/MEDIUM")
    body = r.json()
    assert isinstance(body["fee"], str)


def test_rpc_fee_estimate_priority_bound(client: TestClient) -> None:
    r = client.get("/rpc/fee-estimate/DOT/LOW")
    body = r.json()
    assert body["priority"] == "LOW"


def test_rpc_fee_estimate_confirmation_blocks_positive(client: TestClient) -> None:
    r = client.get("/rpc/fee-estimate/TRX/HIGH")
    body = r.json()
    assert body["estimated_confirmation_blocks"] > 0
