"""
tests/test_recon/test_mcp_tools.py — Safeguarding Reconciliation MCP tools tests
IL-REC-01 | Phase 51B | Sprint 36
≥20 tests covering recon_run_daily, recon_get_report, recon_list_breaches
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── recon_run_daily ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recon_run_daily_success() -> None:
    from banxe_mcp.server import recon_run_daily

    mock_data = {
        "report_id": "rpt001",
        "recon_date": "2026-04-21",
        "breach_detected": False,
        "net_discrepancy_gbp": "0",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await recon_run_daily("2026-04-21")
        data = json.loads(result)
        assert data["breach_detected"] is False


@pytest.mark.asyncio
async def test_recon_run_daily_returns_string() -> None:
    from banxe_mcp.server import recon_run_daily

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        result = await recon_run_daily("2026-04-21")
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_recon_run_daily_http_error() -> None:
    from banxe_mcp.server import recon_run_daily

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            "500",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(500),
        )
        result = await recon_run_daily("2026-04-21")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_recon_run_daily_connect_error() -> None:
    from banxe_mcp.server import recon_run_daily

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        result = await recon_run_daily("2026-04-21")
        data = json.loads(result)
        assert "error" in data
        assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_recon_run_daily_calls_run_endpoint() -> None:
    from banxe_mcp.server import recon_run_daily

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        await recon_run_daily("2026-04-21")
        called_path = mock_post.call_args[0][0]
        assert "safeguarding-recon" in called_path or "recon" in called_path


@pytest.mark.asyncio
async def test_recon_run_daily_hitl_response() -> None:
    from banxe_mcp.server import recon_run_daily

    mock_data = {
        "action": "resolve_breach",
        "entity_id": "abc12345",
        "requires_approval_from": "COMPLIANCE_OFFICER",
        "reason": "Breach detected",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await recon_run_daily("2026-04-21")
        data = json.loads(result)
        assert data["requires_approval_from"] == "COMPLIANCE_OFFICER"


# ── recon_get_report ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recon_get_report_success() -> None:
    from banxe_mcp.server import recon_get_report

    mock_data = {
        "report_id": "rpt001",
        "recon_date": "2026-04-21",
        "breach_detected": False,
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await recon_get_report("2026-04-21")
        data = json.loads(result)
        assert data["recon_date"] == "2026-04-21"


@pytest.mark.asyncio
async def test_recon_get_report_http_error() -> None:
    from banxe_mcp.server import recon_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "404",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(404),
        )
        result = await recon_get_report("2026-04-21")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_recon_get_report_connect_error() -> None:
    from banxe_mcp.server import recon_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await recon_get_report("2026-04-21")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_recon_get_report_returns_string() -> None:
    from banxe_mcp.server import recon_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        result = await recon_get_report("2026-04-21")
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_recon_get_report_calls_reports_endpoint() -> None:
    from banxe_mcp.server import recon_get_report

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        await recon_get_report("2026-04-21")
        called_path = mock_get.call_args[0][0]
        assert "reports" in called_path or "recon" in called_path


# ── recon_list_breaches ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_recon_list_breaches_success() -> None:
    from banxe_mcp.server import recon_list_breaches

    mock_data = [{"report_id": "rpt001", "breach_detected": True}]
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await recon_list_breaches()
        data = json.loads(result)
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_recon_list_breaches_empty_list() -> None:
    from banxe_mcp.server import recon_list_breaches

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        result = await recon_list_breaches()
        data = json.loads(result)
        assert data == []


@pytest.mark.asyncio
async def test_recon_list_breaches_http_error() -> None:
    from banxe_mcp.server import recon_list_breaches

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "500",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(500),
        )
        result = await recon_list_breaches()
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_recon_list_breaches_connect_error() -> None:
    from banxe_mcp.server import recon_list_breaches

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await recon_list_breaches()
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_recon_list_breaches_returns_string() -> None:
    from banxe_mcp.server import recon_list_breaches

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        result = await recon_list_breaches()
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_recon_list_breaches_calls_breaches_endpoint() -> None:
    from banxe_mcp.server import recon_list_breaches

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        await recon_list_breaches()
        called_path = mock_get.call_args[0][0]
        assert "breach" in called_path or "recon" in called_path
