"""Tests for Observability MCP tools (IL-OBS-01)."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
class TestObsMCPTools:
    async def test_obs_health_check_all_returns_json(self):
        from banxe_mcp.server import obs_health_check

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"overall_status": "healthy", "healthy_count": 6}
            result = await obs_health_check()
            data = json.loads(result)
            assert "overall_status" in data

    async def test_obs_health_check_specific_service(self):
        from banxe_mcp.server import obs_health_check

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {"service": "postgres", "status": "healthy"}
            result = await obs_health_check(service="postgres")
            data = json.loads(result)
            assert data["service"] == "postgres"

    async def test_obs_health_check_http_error(self):
        from banxe_mcp.server import obs_health_check

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ):
            result = await obs_health_check()
            data = json.loads(result)
            assert "error" in data

    async def test_obs_get_metrics_returns_json(self):
        from banxe_mcp.server import obs_get_metrics

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "test_count": 8100,
                "endpoint_count": 453,
                "mcp_tool_count": 228,
                "passport_count": 57,
                "coverage_pct": "82.5",
            }
            result = await obs_get_metrics()
            data = json.loads(result)
            assert data["test_count"] == 8100

    async def test_obs_get_metrics_http_error(self):
        from banxe_mcp.server import obs_get_metrics

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "503", request=MagicMock(), response=MagicMock(status_code=503)
            ),
        ):
            result = await obs_get_metrics()
            data = json.loads(result)
            assert "error" in data

    async def test_obs_compliance_scan_returns_json(self):
        from banxe_mcp.server import obs_compliance_scan

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = {
                "overall_flag": "compliant",
                "violation_count": 0,
                "warning_count": 0,
                "checks": [],
            }
            result = await obs_compliance_scan()
            data = json.loads(result)
            assert data["overall_flag"] == "compliant"

    async def test_obs_compliance_scan_http_error(self):
        from banxe_mcp.server import obs_compliance_scan

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ):
            result = await obs_compliance_scan()
            data = json.loads(result)
            assert "error" in data
