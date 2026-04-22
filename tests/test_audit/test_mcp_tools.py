"""
tests/test_audit/test_mcp_tools.py — pgAudit MCP tools tests
IL-PGA-01 | Phase 51A | Sprint 36
≥20 tests covering audit_query_logs, audit_export_report, audit_health_check
"""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch

import httpx
import pytest

# ── audit_query_logs ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_query_logs_success() -> None:
    from banxe_mcp.server import audit_query_logs

    mock_data = [{"entry_id": "abc12345", "db_name": "banxe_core", "operation": "INSERT"}]
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await audit_query_logs("banxe_core")
        data = json.loads(result)
        assert isinstance(data, list)


@pytest.mark.asyncio
async def test_audit_query_logs_returns_string() -> None:
    from banxe_mcp.server import audit_query_logs

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        result = await audit_query_logs()
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_audit_query_logs_http_error() -> None:
    from banxe_mcp.server import audit_query_logs

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "400",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(400),
        )
        result = await audit_query_logs("banxe_core")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_audit_query_logs_connect_error() -> None:
    from banxe_mcp.server import audit_query_logs

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await audit_query_logs()
        data = json.loads(result)
        assert "error" in data
        assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_audit_query_logs_calls_audit_endpoint() -> None:
    from banxe_mcp.server import audit_query_logs

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        await audit_query_logs("banxe_core")
        called_path = mock_get.call_args[0][0]
        assert "audit" in called_path


@pytest.mark.asyncio
async def test_audit_query_logs_with_db_name() -> None:
    from banxe_mcp.server import audit_query_logs

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = []
        await audit_query_logs("banxe_compliance")
        called_path = mock_get.call_args[0][0]
        assert "banxe_compliance" in called_path


# ── audit_export_report ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_export_report_returns_hitl_proposal() -> None:
    from banxe_mcp.server import audit_export_report

    mock_data = {
        "action": "export_audit_report",
        "entity_id": "abc12345",
        "requires_approval_from": "COMPLIANCE_OFFICER",
        "reason": "Export requested",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await audit_export_report("banxe_core", "2026-01-01", "2026-04-21")
        data = json.loads(result)
        assert data["requires_approval_from"] == "COMPLIANCE_OFFICER"


@pytest.mark.asyncio
async def test_audit_export_report_autonomy_l4() -> None:
    from banxe_mcp.server import audit_export_report

    mock_data = {
        "action": "export_audit_report",
        "entity_id": "abc12345",
        "requires_approval_from": "COMPLIANCE_OFFICER",
        "reason": "Export",
        "autonomy_level": "L4",
    }
    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = mock_data
        result = await audit_export_report("banxe_core", "2026-01-01", "2026-04-21")
        data = json.loads(result)
        assert data["autonomy_level"] == "L4"


@pytest.mark.asyncio
async def test_audit_export_report_http_error() -> None:
    from banxe_mcp.server import audit_export_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.HTTPStatusError(
            "403",
            request=httpx.Request("POST", "http://test"),
            response=httpx.Response(403),
        )
        result = await audit_export_report("banxe_core", "2026-01-01", "2026-04-21")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_audit_export_report_connect_error() -> None:
    from banxe_mcp.server import audit_export_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.side_effect = httpx.ConnectError("Connection refused")
        result = await audit_export_report("banxe_core", "2026-01-01", "2026-04-21")
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_audit_export_report_returns_string() -> None:
    from banxe_mcp.server import audit_export_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        result = await audit_export_report("banxe_core", "2026-01-01", "2026-04-21")
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_audit_export_report_calls_export_endpoint() -> None:
    from banxe_mcp.server import audit_export_report

    with patch("banxe_mcp.server._api_post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value = {}
        await audit_export_report("banxe_core", "2026-01-01", "2026-04-21")
        called_path = mock_post.call_args[0][0]
        assert "export" in called_path or "audit" in called_path


# ── audit_health_check ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_audit_health_check_success() -> None:
    from banxe_mcp.server import audit_health_check

    mock_data = {
        "status": "ok",
        "databases": ["banxe_core", "banxe_compliance", "banxe_analytics"],
        "pgaudit_version": "1.7",
    }
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await audit_health_check()
        data = json.loads(result)
        assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_audit_health_check_pgaudit_version() -> None:
    from banxe_mcp.server import audit_health_check

    mock_data = {"status": "ok", "pgaudit_version": "1.7"}
    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = mock_data
        result = await audit_health_check()
        data = json.loads(result)
        assert data["pgaudit_version"] == "1.7"


@pytest.mark.asyncio
async def test_audit_health_check_http_error() -> None:
    from banxe_mcp.server import audit_health_check

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.HTTPStatusError(
            "503",
            request=httpx.Request("GET", "http://test"),
            response=httpx.Response(503),
        )
        result = await audit_health_check()
        data = json.loads(result)
        assert "error" in data


@pytest.mark.asyncio
async def test_audit_health_check_connect_error() -> None:
    from banxe_mcp.server import audit_health_check

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = httpx.ConnectError("Connection refused")
        result = await audit_health_check()
        data = json.loads(result)
        assert "error" in data
        assert "unavailable" in data["error"].lower()


@pytest.mark.asyncio
async def test_audit_health_check_returns_string() -> None:
    from banxe_mcp.server import audit_health_check

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        result = await audit_health_check()
        assert isinstance(result, str)


@pytest.mark.asyncio
async def test_audit_health_check_calls_health_endpoint() -> None:
    from banxe_mcp.server import audit_health_check

    with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = {}
        await audit_health_check()
        called_path = mock_get.call_args[0][0]
        assert "health" in called_path or "audit" in called_path
