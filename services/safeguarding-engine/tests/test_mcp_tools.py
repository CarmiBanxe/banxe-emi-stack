"""Tests for MCP tools (4 tools)."""

import pytest

from app.mcp.tools.safeguarding_position import safeguarding_position_tool
from app.mcp.tools.reconciliation_status import reconciliation_status_tool
from app.mcp.tools.breach_report import breach_report_tool
from app.mcp.tools.safeguarding_health import safeguarding_health_tool


@pytest.mark.asyncio
async def test_safeguarding_position_tool():
    """Test safeguarding_position MCP tool."""
    result = await safeguarding_position_tool({})
    assert result is not None
    assert "total_client_funds" in result or hasattr(result, "total_client_funds")


@pytest.mark.asyncio
async def test_reconciliation_status_tool():
    """Test reconciliation_status MCP tool."""
    result = await reconciliation_status_tool({"type": "daily", "limit": 5})
    assert result is not None


@pytest.mark.asyncio
async def test_breach_report_tool_list():
    """Test breach_report MCP tool - list action."""
    result = await breach_report_tool({"action": "list"})
    assert result is not None
    assert "breaches" in result or hasattr(result, "breaches")


@pytest.mark.asyncio
async def test_safeguarding_health_tool():
    """Test safeguarding_health MCP tool."""
    result = await safeguarding_health_tool({})
    assert result is not None
    assert "position_compliant" in result or hasattr(result, "position_compliant")
