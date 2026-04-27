"""Tests for Client Statement MCP tools (IL-CST-01).

Pattern: mock _api_get/_api_post, not httpx directly.
Phase 56C | Sprint 41
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── statement_generate ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_statement_generate_success() -> None:
    from banxe_mcp.server import statement_generate

    mock_result = {
        "statement_id": "stmt_abc123",
        "customer_id": "CUST001",
        "entry_count": 5,
        "generated_at": "2026-04-27T10:00:00+00:00",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await statement_generate("CUST001", "2026-01-01", "2026-01-31")

    data = json.loads(result)
    assert data["statement_id"] == "stmt_abc123"
    assert data["entry_count"] == 5


@pytest.mark.asyncio
async def test_statement_generate_returns_string() -> None:
    from banxe_mcp.server import statement_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"statement_id": "stmt_001"}
        result = await statement_generate("CUST001", "2026-01-01", "2026-01-31")

    assert isinstance(result, str)
    assert json.loads(result)


@pytest.mark.asyncio
async def test_statement_generate_default_format_json() -> None:
    from banxe_mcp.server import statement_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"statement_id": "stmt_001"}
        await statement_generate("CUST001", "2026-01-01", "2026-01-31")

    body = mock_post.call_args[0][1]
    assert body["format"] == "json"


@pytest.mark.asyncio
async def test_statement_generate_pdf_format() -> None:
    from banxe_mcp.server import statement_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"statement_id": "stmt_002", "format": "pdf"}
        result = await statement_generate("CUST002", "2026-02-01", "2026-02-28", fmt="pdf")

    body = mock_post.call_args[0][1]
    assert body["format"] == "pdf"


@pytest.mark.asyncio
async def test_statement_generate_posts_to_correct_endpoint() -> None:
    from banxe_mcp.server import statement_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"statement_id": "stmt_003"}
        await statement_generate("CUST003", "2026-03-01", "2026-03-31")

    endpoint = mock_post.call_args[0][0]
    assert endpoint == "/v1/statements/generate"


@pytest.mark.asyncio
async def test_statement_generate_http_error() -> None:
    from banxe_mcp.server import statement_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 422
        mock_post.side_effect = httpx.HTTPStatusError(
            "Unprocessable", request=AsyncMock(), response=mock_resp
        )
        result = await statement_generate("CUST001", "bad-date", "bad-date")

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 422


@pytest.mark.asyncio
async def test_statement_generate_passes_customer_id() -> None:
    from banxe_mcp.server import statement_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"statement_id": "stmt_004"}
        await statement_generate("CUST_TARGET", "2026-01-01", "2026-01-31")

    body = mock_post.call_args[0][1]
    assert body["customer_id"] == "CUST_TARGET"


# ── statement_download ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_statement_download_success() -> None:
    from banxe_mcp.server import statement_download

    mock_result = {
        "statement_id": "stmt_abc123",
        "download_url": "/files/statements/stmt_abc123",
        "status": "ready",
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_result
        result = await statement_download("stmt_abc123")

    data = json.loads(result)
    assert data["statement_id"] == "stmt_abc123"
    assert "download_url" in data


@pytest.mark.asyncio
async def test_statement_download_returns_string() -> None:
    from banxe_mcp.server import statement_download

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {"statement_id": "stmt_001", "download_url": "/files/stmt_001"}
        result = await statement_download("stmt_001")

    assert isinstance(result, str)
    assert json.loads(result)


@pytest.mark.asyncio
async def test_statement_download_404_error() -> None:
    from banxe_mcp.server import statement_download

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_get.side_effect = httpx.HTTPStatusError(
            "Not Found", request=AsyncMock(), response=mock_resp
        )
        result = await statement_download("nonexistent_stmt")

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 404


@pytest.mark.asyncio
async def test_statement_download_gets_correct_endpoint() -> None:
    from banxe_mcp.server import statement_download

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {
            "statement_id": "stmt_TARGET",
            "download_url": "/files/stmt_TARGET",
        }
        await statement_download("stmt_TARGET")

    endpoint = mock_get.call_args[0][0]
    assert "stmt_TARGET" in endpoint
    assert "download" in endpoint
