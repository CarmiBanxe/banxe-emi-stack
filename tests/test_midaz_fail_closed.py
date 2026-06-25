"""
tests/test_midaz_fail_closed.py — MidazLedgerAdapter fail-closed behaviour.

D-gl build-spec DoD #8 (`test_midaz_unavailable_surfaces_infra_failure`):
an unreachable Midaz / transport error / 5xx MUST surface as
LedgerInfrastructureError (no silent zero balance — a false 0 can drive a wrong
reconciliation / safeguarding figure). A reachable, definite answer (4xx, or a
200 with no GBP item) is NOT an infra failure and keeps the safe default.

All offline — httpx.AsyncClient is mocked; no live Midaz.
"""

from __future__ import annotations

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from services.ledger.ledger_port import LedgerInfrastructureError
from services.ledger.midaz_adapter import MidazLedgerAdapter, TransactionRequest

ORG = "org-001"
LEDGER = "ledger-001"
ACCOUNT = "acct-001"


def _adapter() -> MidazLedgerAdapter:
    return MidazLedgerAdapter(base_url="http://test-midaz:8095", token="t", timeout=5.0)


def _resp(json_data: dict, status_code: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status_code >= 400:
        resp.raise_for_status.side_effect = httpx.HTTPStatusError(
            "error", request=MagicMock(), response=resp
        )
    return resp


# ── get_balance ───────────────────────────────────────────────────────────────


def test_get_balance_network_error_raises_infra_error():
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(LedgerInfrastructureError):
            adapter.get_balance(ORG, LEDGER, ACCOUNT)


def test_get_balance_timeout_raises_infra_error():
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(side_effect=httpx.ReadTimeout("slow"))
        with pytest.raises(LedgerInfrastructureError):
            adapter.get_balance(ORG, LEDGER, ACCOUNT)


def test_get_balance_http_500_raises_infra_error():
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(return_value=_resp({}, status_code=500))
        with pytest.raises(LedgerInfrastructureError):
            adapter.get_balance(ORG, LEDGER, ACCOUNT)


def test_get_balance_200_no_gbp_returns_zero_not_error():
    """Reachable backend, no GBP item → genuine Decimal('0'), NOT an infra failure."""
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(
            return_value=_resp({"items": [{"assetCode": "USD", "available": 999}]})
        )
        result = adapter.get_balance(ORG, LEDGER, ACCOUNT)
    assert result == Decimal("0")
    assert isinstance(result, Decimal)


def test_get_balance_4xx_returns_zero_not_error():
    """A 4xx is a reachable, definite answer (e.g. not found) → 0, not infra failure."""
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(return_value=_resp({}, status_code=404))
        result = adapter.get_balance(ORG, LEDGER, ACCOUNT)
    assert result == Decimal("0")


# ── create_transaction ────────────────────────────────────────────────────────


def test_create_transaction_5xx_raises_infra_error():
    adapter = _adapter()
    req = TransactionRequest(amount_gbp=Decimal("100.00"), description="X")
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.post = AsyncMock(return_value=_resp({}, status_code=502))
        with pytest.raises(LedgerInfrastructureError):
            adapter.create_transaction(ORG, LEDGER, req)


def test_create_transaction_network_error_raises_infra_error():
    adapter = _adapter()
    req = TransactionRequest(amount_gbp=Decimal("100.00"), description="X")
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.post = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(LedgerInfrastructureError):
            adapter.create_transaction(ORG, LEDGER, req)


# ── list_transactions ─────────────────────────────────────────────────────────


def test_list_transactions_5xx_raises_infra_error():
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(return_value=_resp({}, status_code=503))
        with pytest.raises(LedgerInfrastructureError):
            adapter.list_transactions(ORG, LEDGER, ACCOUNT)


def test_list_transactions_network_error_raises_infra_error():
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(side_effect=httpx.ConnectError("refused"))
        with pytest.raises(LedgerInfrastructureError):
            adapter.list_transactions(ORG, LEDGER, ACCOUNT)


def test_list_transactions_4xx_returns_empty_not_error():
    adapter = _adapter()
    with patch("httpx.AsyncClient") as mock_cls:
        client = AsyncMock()
        mock_cls.return_value.__aenter__.return_value = client
        client.get = AsyncMock(return_value=_resp({}, status_code=404))
        assert adapter.list_transactions(ORG, LEDGER, ACCOUNT) == []
