"""
tests/test_fin060_reporting/test_mcp_tools.py — FIN060 MCP tools tests
IL-FIN060-01 | Phase 51C | Sprint 36
≥20 tests covering fin060_generate, fin060_get_report, fin060_approve, fin060_dashboard
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── fin060_generate ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fin060_generate_returns_hitl_proposal() -> None:
    from banxe_mcp.server import fin060_generate

    mock_data = {
        "action": "generate_fin060",
        "entity_id": "abc12345",
        "requires_approval_from": "CFO",
        "reason": "FIN060 generated",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await fin060_generate(4, 2026)
        data = json.loads(result)
        assert data["requires_approval_from"] == "CFO"


@pytest.mark.asyncio
async def test_fin060_generate_autonomy_l4() -> None:
    from banxe_mcp.server import fin060_generate

    mock_data = {
        "action": "generate_fin060",
        "entity_id": "abc12345",
        "requires_approval_from": "CFO",
        "reason": "reason",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await fin060_generate(4, 2026)
        data = json.loads(result)
        assert data["autonomy_level"] == "L4"


@pytest.mark.asyncio
async def test_fin060_generate_http_error() -> None:
    from banxe_mcp.server import fin060_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            "500",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(500),
        )
        result = await fin060_generate(4, 2026)
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_fin060_generate_connect_error() -> None:
    from banxe_mcp.server import fin060_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        result = await fin060_generate(4, 2026)
        data = json.loads(result)
        assert "error" in data
        assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_fin060_generate_returns_string() -> None:
    from banxe_mcp.server import fin060_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        result = await fin060_generate(4, 2026)
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_fin060_generate_calls_generate_endpoint() -> None:
    from banxe_mcp.server import fin060_generate

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        await fin060_generate(4, 2026)
        called_path = mock_post.call_args[0][0]
        assert "fin060" in called_path


# ── fin060_get_report ─────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fin060_get_report_success() -> None:
    from banxe_mcp.server import fin060_get_report

    mock_data = {
        "report_id": "r1",
        "month": 4,
        "year": 2026,
        "status": "DRAFT",
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await fin060_get_report(4, 2026)
        data = json.loads(result)
        assert data["month"] == 4
        assert data["year"] == 2026


@pytest.mark.asyncio
async def test_fin060_get_report_not_found() -> None:
    from banxe_mcp.server import fin060_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = None
        result = await fin060_get_report(1, 2020)
        data = json.loads(result)
        assert data is None or data == {}


@pytest.mark.asyncio
async def test_fin060_get_report_http_error() -> None:
    from banxe_mcp.server import fin060_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(404),
        )
        result = await fin060_get_report(4, 2026)
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_fin060_get_report_connect_error() -> None:
    from banxe_mcp.server import fin060_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await fin060_get_report(4, 2026)
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_fin060_get_report_returns_string() -> None:
    from banxe_mcp.server import fin060_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        result = await fin060_get_report(4, 2026)
        assert isinstance(result, str)


# ── fin060_approve ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fin060_approve_returns_hitl_proposal() -> None:
    from banxe_mcp.server import fin060_approve

    mock_data = {
        "action": "approve_fin060",
        "entity_id": "r1",
        "requires_approval_from": "CFO",
        "reason": "approval",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await fin060_approve("r1")
        data = json.loads(result)
        assert data["requires_approval_from"] == "CFO"


@pytest.mark.asyncio
async def test_fin060_approve_http_error() -> None:
    from banxe_mcp.server import fin060_approve

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            "403",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(403),
        )
        result = await fin060_approve("r1")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_fin060_approve_connect_error() -> None:
    from banxe_mcp.server import fin060_approve

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        result = await fin060_approve("r1")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_fin060_approve_returns_string() -> None:
    from banxe_mcp.server import fin060_approve

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        result = await fin060_approve("r1")
        assert isinstance(result, str)


# ── fin060_dashboard ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_fin060_dashboard_success() -> None:
    from banxe_mcp.server import fin060_dashboard

    mock_data = {
        "total_reports": 5,
        "pending_approval": 2,
        "last_submission": "2026-03",
        "safeguarded_gbp": "1000000.00",
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await fin060_dashboard()
        data = json.loads(result)
        assert data["total_reports"] == 5
        assert data["safeguarded_gbp"] == "1000000.00"


@pytest.mark.asyncio
async def test_fin060_dashboard_http_error() -> None:
    from banxe_mcp.server import fin060_dashboard

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "503",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(503),
        )
        result = await fin060_dashboard()
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_fin060_dashboard_connect_error() -> None:
    from banxe_mcp.server import fin060_dashboard

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await fin060_dashboard()
        data = json.loads(result)
        assert "error" in data
        assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_fin060_dashboard_returns_string() -> None:
    from banxe_mcp.server import fin060_dashboard

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        result = await fin060_dashboard()
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_fin060_dashboard_calls_dashboard_endpoint() -> None:
    from banxe_mcp.server import fin060_dashboard

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        await fin060_dashboard()
        called_path = mock_get.call_args[0][0]
        assert "dashboard" in called_path or "fin060" in called_path
