"""Tests for HMRC FATCA/CRS MCP tools (IL-HMR-01).

Pattern: mock _api_get/_api_post, not httpx directly.
Phase 56B | Sprint 41
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── hmrc_generate_report ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hmrc_generate_report_returns_hitl() -> None:
    from banxe_mcp.server import hmrc_generate_report

    mock_result = {
        "status": "HITL_REQUIRED",
        "proposal_id": "HMRCHITL_abc123",
        "requires_approval_from": ["CFO", "MLRO"],
        "approved": False,
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await hmrc_generate_report(2025)

    data = json.loads(result)
    assert data["status"] == "HITL_REQUIRED"
    assert data["approved"] is False


@pytest.mark.asyncio
async def test_hmrc_generate_report_returns_string() -> None:
    from banxe_mcp.server import hmrc_generate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"status": "HITL_REQUIRED", "proposal_id": "p001"}
        result = await hmrc_generate_report(2025)

    assert isinstance(result, str)
    assert json.loads(result)


@pytest.mark.asyncio
async def test_hmrc_generate_report_passes_tax_year() -> None:
    from banxe_mcp.server import hmrc_generate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"status": "HITL_REQUIRED"}
        await hmrc_generate_report(2024)

    call_body = mock_post.call_args[0][1]
    assert call_body["tax_year"] == 2024


@pytest.mark.asyncio
async def test_hmrc_generate_report_passes_accounts() -> None:
    from banxe_mcp.server import hmrc_generate_report

    accounts = [{"account_id": "ACC001", "balance": "1000.00", "country": "US"}]
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"status": "HITL_REQUIRED"}
        await hmrc_generate_report(2025, json.dumps(accounts))

    call_body = mock_post.call_args[0][1]
    assert len(call_body["accounts"]) == 1
    assert call_body["accounts"][0]["account_id"] == "ACC001"


@pytest.mark.asyncio
async def test_hmrc_generate_report_invalid_accounts_json() -> None:
    from banxe_mcp.server import hmrc_generate_report

    result = await hmrc_generate_report(2025, "not_valid_json{{{")
    data = json.loads(result)
    assert "error" in data
    assert "accounts_json" in data["error"].lower() or "invalid" in data["error"].lower()


@pytest.mark.asyncio
async def test_hmrc_generate_report_http_error() -> None:
    from banxe_mcp.server import hmrc_generate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 400
        mock_post.side_effect = httpx.HTTPStatusError(
            "Bad Request", request=AsyncMock(), response=mock_resp
        )
        result = await hmrc_generate_report(1900)

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 400


@pytest.mark.asyncio
async def test_hmrc_generate_report_posts_to_correct_endpoint() -> None:
    from banxe_mcp.server import hmrc_generate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"status": "HITL_REQUIRED"}
        await hmrc_generate_report(2025)

    endpoint = mock_post.call_args[0][0]
    assert endpoint == "/v1/hmrc/reports/generate"


# ── hmrc_validate_report ──────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_hmrc_validate_report_valid() -> None:
    from banxe_mcp.server import hmrc_validate_report

    mock_result = {
        "report_id": "r2025",
        "valid": True,
        "error_count": 0,
        "errors": [],
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await hmrc_validate_report(2025)

    data = json.loads(result)
    assert data["valid"] is True
    assert data["error_count"] == 0


@pytest.mark.asyncio
async def test_hmrc_validate_report_returns_string() -> None:
    from banxe_mcp.server import hmrc_validate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"report_id": "r001", "valid": True}
        result = await hmrc_validate_report(2025)

    assert isinstance(result, str)
    assert json.loads(result)


@pytest.mark.asyncio
async def test_hmrc_validate_report_invalid_year_error() -> None:
    from banxe_mcp.server import hmrc_validate_report

    mock_result = {
        "report_id": "r2010",
        "valid": False,
        "error_count": 1,
        "errors": [{"field": "tax_year", "message": "FATCA/CRS not applicable before 2014"}],
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_result
        result = await hmrc_validate_report(2010)

    data = json.loads(result)
    assert data["valid"] is False
    assert data["error_count"] == 1


@pytest.mark.asyncio
async def test_hmrc_validate_report_404_error() -> None:
    from banxe_mcp.server import hmrc_validate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_resp = AsyncMock()
        mock_resp.status_code = 404
        mock_post.side_effect = httpx.HTTPStatusError(
            "Not Found", request=AsyncMock(), response=mock_resp
        )
        result = await hmrc_validate_report(1999)

    data = json.loads(result)
    assert "error" in data
    assert data["status_code"] == 404


@pytest.mark.asyncio
async def test_hmrc_validate_report_posts_to_correct_endpoint() -> None:
    from banxe_mcp.server import hmrc_validate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"report_id": "r001", "valid": True}
        await hmrc_validate_report(2025)

    endpoint = mock_post.call_args[0][0]
    assert "2025" in endpoint
    assert "validate" in endpoint


@pytest.mark.asyncio
async def test_hmrc_generate_report_empty_accounts_by_default() -> None:
    from banxe_mcp.server import hmrc_generate_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {"status": "HITL_REQUIRED"}
        await hmrc_generate_report(2025)

    body = mock_post.call_args[0][1]
    assert body["accounts"] == []
