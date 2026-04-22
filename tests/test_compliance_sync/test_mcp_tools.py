"""Tests for Compliance Sync MCP tools."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest


@pytest.mark.asyncio
class TestComplianceMCPTools:
    async def test_compliance_scan_returns_json(self):
        from banxe_mcp.server import compliance_scan

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = {
                "coverage_pct": "85.0",
                "done_count": 9,
                "not_started_count": 2,
            }
            result = await compliance_scan()
            data = json.loads(result)
            assert "coverage_pct" in data

    async def test_compliance_gaps_returns_json(self):
        from banxe_mcp.server import compliance_gaps

        with patch("banxe_mcp.server._api_get", new_callable=AsyncMock) as mock:
            mock.return_value = {"gap_count": 2, "gaps": []}
            result = await compliance_gaps()
            data = json.loads(result)
            assert "gap_count" in data

    async def test_compliance_scan_http_error(self):
        from banxe_mcp.server import compliance_scan

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ):
            result = await compliance_scan()
            data = json.loads(result)
            assert "error" in data

    async def test_compliance_gaps_http_error(self):
        from banxe_mcp.server import compliance_gaps

        with patch(
            "banxe_mcp.server._api_get",
            side_effect=httpx.HTTPStatusError(
                "500", request=MagicMock(), response=MagicMock(status_code=500)
            ),
        ):
            result = await compliance_gaps()
            assert "error" in json.loads(result)
