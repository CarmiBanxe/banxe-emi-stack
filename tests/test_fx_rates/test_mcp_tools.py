"""Tests for FX Rates MCP tools in banxe_mcp/server.py.

IL-FXR-01 | Phase 52A | Sprint 37
Pattern: mock _api_get/_api_post, not httpx directly.
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest


@pytest.mark.asyncio
async def test_fx_get_latest_rates_success() -> None:
    from banxe_mcp.server import fx_get_latest_rates

    mock_result = {
        "base": "GBP",
        "rates": {"EUR": "1.165", "USD": "1.234"},
        "source": "frankfurter-ecb",
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await fx_get_latest_rates(base="GBP", symbols="EUR,USD")

    data = json.loads(result)
    assert data["base"] == "GBP"
    assert "EUR" in data["rates"]


@pytest.mark.asyncio
async def test_fx_get_latest_rates_default_base() -> None:
    from banxe_mcp.server import fx_get_latest_rates

    mock_result = {"base": "GBP", "rates": {"EUR": "1.165"}, "source": "frankfurter-ecb"}
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await fx_get_latest_rates()

    data = json.loads(result)
    assert data["base"] == "GBP"


@pytest.mark.asyncio
async def test_fx_get_latest_rates_http_error() -> None:
    from banxe_mcp.server import fx_get_latest_rates

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_get.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_resp
        )
        result = await fx_get_latest_rates(base="GBP")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_fx_get_latest_rates_connect_error() -> None:
    from banxe_mcp.server import fx_get_latest_rates

    with patch("banxe_mcp.server._api_get", side_effect=httpx.ConnectError("refused")):
        result = await fx_get_latest_rates(base="GBP")

    data = json.loads(result)
    assert "error" in data
    assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_fx_convert_amount_success() -> None:
    from banxe_mcp.server import fx_convert_amount

    mock_result = {
        "from_currency": "GBP",
        "to_currency": "EUR",
        "amount": "100.00",
        "converted_amount": "116.5000",
        "rate": "1.1650",
        "date": "2026-01-01",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await fx_convert_amount("100.00", "GBP", "EUR")

    data = json.loads(result)
    assert data["from_currency"] == "GBP"
    assert data["converted_amount"] == "116.5000"


@pytest.mark.asyncio
async def test_fx_convert_amount_http_error() -> None:
    from banxe_mcp.server import fx_convert_amount

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_post.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_resp
        )
        result = await fx_convert_amount("100", "GBP", "RUB")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_fx_convert_amount_connect_error() -> None:
    from banxe_mcp.server import fx_convert_amount

    with patch("banxe_mcp.server._api_post", side_effect=httpx.ConnectError("refused")):
        result = await fx_convert_amount("100", "GBP", "EUR")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_fx_get_historical_rates_success() -> None:
    from banxe_mcp.server import fx_get_historical_rates

    mock_result = {
        "base": "GBP",
        "date": "2026-01-15",
        "rates": {"EUR": "1.160"},
        "source": "frankfurter-ecb",
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await fx_get_historical_rates("2026-01-15", base="GBP")

    data = json.loads(result)
    assert data["date"] == "2026-01-15"
    assert "EUR" in data["rates"]


@pytest.mark.asyncio
async def test_fx_get_historical_rates_http_error() -> None:
    from banxe_mcp.server import fx_get_historical_rates

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=AsyncMock(), response=mock_resp
        )
        result = await fx_get_historical_rates("1900-01-01")

    data = json.loads(result)
    assert "error" in data


@pytest.mark.asyncio
async def test_fx_get_historical_rates_connect_error() -> None:
    from banxe_mcp.server import fx_get_historical_rates

    with patch("banxe_mcp.server._api_get", side_effect=httpx.ConnectError("refused")):
        result = await fx_get_historical_rates("2026-01-15")

    data = json.loads(result)
    assert "error" in data
    assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_fx_get_latest_rates_returns_string() -> None:
    """MCP tools must return str."""
    from banxe_mcp.server import fx_get_latest_rates

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"base": "GBP", "rates": {}}
        result = await fx_get_latest_rates()

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_fx_convert_amount_returns_string() -> None:
    from banxe_mcp.server import fx_convert_amount

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"from_currency": "GBP", "converted_amount": "100"}
        result = await fx_convert_amount("100", "GBP", "EUR")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_fx_get_historical_rates_returns_string() -> None:
    from banxe_mcp.server import fx_get_historical_rates

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"base": "GBP", "date": "2026-01-01", "rates": {}}
        result = await fx_get_historical_rates("2026-01-01")

    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_fx_convert_amount_no_float_in_result() -> None:
    """I-01: amounts in MCP response must be strings, not floats."""
    from banxe_mcp.server import fx_convert_amount

    mock_result = {
        "from_currency": "GBP",
        "to_currency": "EUR",
        "amount": "100.00",
        "converted_amount": "116.5000",
        "rate": "1.1650",
        "date": "2026-01-01",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await fx_convert_amount("100.00", "GBP", "EUR")

    data = json.loads(result)
    # Amounts returned as strings, not float
    assert isinstance(data["amount"], str)
    assert isinstance(data["converted_amount"], str)
