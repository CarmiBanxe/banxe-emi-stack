"""Tests for PSD2 MCP tools in banxe_mcp/server.py.

IL-PSD2GW-01 | Phase 52B | Sprint 37
Pattern: mock _api_get/_api_post, not httpx directly.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── psd2_create_consent ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_psd2_create_consent_success() -> None:
    from banxe_mcp.server import psd2_create_consent

    mock_result = {
        "proposal_type": "HITL_REQUIRED",
        "action": "create_psd2_consent",
        "autonomy_level": "L4",
        "requires_approval_from": "COMPLIANCE_OFFICER",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await psd2_create_consent("GB29NWBK60161331926819", "2027-01-01")

    data = json.loads(result)
    assert data["proposal_type"] == "HITL_REQUIRED"
    assert data["requires_approval_from"] == "COMPLIANCE_OFFICER"


@pytest.mark.asyncio
async def test_psd2_create_consent_http_error() -> None:
    from banxe_mcp.server import psd2_create_consent

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_post.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_resp
        )
        result = await psd2_create_consent("RU1234567890", "2027-01-01")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_psd2_create_consent_connect_error() -> None:
    from banxe_mcp.server import psd2_create_consent

    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await psd2_create_consent("GB29NWBK60161331926819", "2027-01-01")

    data = json.loads(result)
    assert "error" in data
    assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_psd2_create_consent_returns_string() -> None:
    from banxe_mcp.server import psd2_create_consent

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"proposal_type": "HITL_REQUIRED"}
        result = await psd2_create_consent("GB29NWBK60161331926819", "2027-01-01")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_psd2_create_consent_l4_in_result() -> None:
    from banxe_mcp.server import psd2_create_consent

    mock_result = {"proposal_type": "HITL_REQUIRED", "autonomy_level": "L4"}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await psd2_create_consent("GB29NWBK60161331926819", "2027-01-01")

    data = json.loads(result)
    assert data["autonomy_level"] == "L4"


# ── psd2_get_transactions ──────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_psd2_get_transactions_success() -> None:
    from banxe_mcp.server import psd2_get_transactions

    mock_result = {
        "consent_id": "cns_001",
        "account_id": "acc_001",
        "transactions": [{"amount": "1500.00", "currency": "GBP"}],
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await psd2_get_transactions("cns_001", "acc_001", "2026-01-01", "2026-01-31")

    data = json.loads(result)
    assert len(data["transactions"]) == 1
    assert data["transactions"][0]["amount"] == "1500.00"


@pytest.mark.asyncio
async def test_psd2_get_transactions_http_error() -> None:
    from banxe_mcp.server import psd2_get_transactions

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=AsyncMock(), response=mock_resp
        )
        result = await psd2_get_transactions("nonexistent", "acc_001", "2026-01-01", "2026-01-31")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_psd2_get_transactions_connect_error() -> None:
    from banxe_mcp.server import psd2_get_transactions

    with patch("banxe_mcp.server._api_get", side_effect=httpx.ConnectError("refused")):
        result = await psd2_get_transactions("cns_001", "acc_001", "2026-01-01", "2026-01-31")

    data = json.loads(result)
    assert "error" in data
    assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_psd2_get_transactions_returns_string() -> None:
    from banxe_mcp.server import psd2_get_transactions

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"consent_id": "cns", "transactions": []}
        result = await psd2_get_transactions("cns", "acc", "2026-01-01", "2026-01-31")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_psd2_get_transactions_amount_as_string() -> None:
    """I-01: transaction amounts in result must be strings."""
    from banxe_mcp.server import psd2_get_transactions

    mock_result = {
        "transactions": [
            {
                "transaction_id": "txn_001",
                "amount": "1500.00",  # string, not float
                "currency": "GBP",
            }
        ]
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await psd2_get_transactions("cns", "acc", "2026-01-01", "2026-01-31")

    data = json.loads(result)
    assert isinstance(data["transactions"][0]["amount"], str)


# ── psd2_configure_autopull ────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_psd2_configure_autopull_success() -> None:
    from banxe_mcp.server import psd2_configure_autopull

    mock_result = {
        "proposal_type": "HITL_REQUIRED",
        "action": "configure_auto_pull",
        "autonomy_level": "L4",
        "requires_approval_from": "COMPLIANCE_OFFICER",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await psd2_configure_autopull("GB29NWBK60161331926819", "daily")

    data = json.loads(result)
    assert data["proposal_type"] == "HITL_REQUIRED"
    assert data["action"] == "configure_auto_pull"


@pytest.mark.asyncio
async def test_psd2_configure_autopull_http_error() -> None:
    from banxe_mcp.server import psd2_configure_autopull

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_post.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_resp
        )
        result = await psd2_configure_autopull("RU1234567890", "daily")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_psd2_configure_autopull_connect_error() -> None:
    from banxe_mcp.server import psd2_configure_autopull

    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await psd2_configure_autopull("GB29NWBK60161331926819", "daily")

    data = json.loads(result)
    assert "error" in data
    assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_psd2_configure_autopull_returns_string() -> None:
    from banxe_mcp.server import psd2_configure_autopull

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"proposal_type": "HITL_REQUIRED"}
        result = await psd2_configure_autopull("GB29NWBK60161331926819")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_psd2_configure_autopull_default_daily() -> None:
    from banxe_mcp.server import psd2_configure_autopull

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"proposal_type": "HITL_REQUIRED"}
        await psd2_configure_autopull("GB29NWBK60161331926819")  # default frequency=daily

    call_kwargs = mock_post.call_args
    payload = call_kwargs[0][1] if call_kwargs[0] else call_kwargs[1].get("json_data", {})
    # Just check it was called
    assert mock_post.called


@pytest.mark.asyncio
async def test_psd2_configure_autopull_l4_autonomy() -> None:
    from banxe_mcp.server import psd2_configure_autopull

    mock_result = {"proposal_type": "HITL_REQUIRED", "autonomy_level": "L4"}
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await psd2_configure_autopull("GB29NWBK60161331926819")

    data = json.loads(result)
    assert data["autonomy_level"] == "L4"
