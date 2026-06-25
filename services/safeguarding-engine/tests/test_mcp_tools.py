"""Tests for MCP tools (4 tools)."""

import pytest

# Canonical non-suffixed tool names (match app/mcp/server.py registration).
from app.mcp.tools.safeguarding_position import safeguarding_position
from app.mcp.tools.reconciliation_status import reconciliation_status
from app.mcp.tools.breach_report import breach_report
from app.mcp.tools.safeguarding_health import safeguarding_health


@pytest.mark.asyncio
async def test_safeguarding_position_tool():
    """Test safeguarding_position MCP tool."""
    result = await safeguarding_position({})
    assert result is not None
    assert "total_client_funds" in result or hasattr(result, "total_client_funds")


@pytest.mark.asyncio
async def test_reconciliation_status_tool():
    """Test reconciliation_status MCP tool."""
    result = await reconciliation_status({"type": "daily", "limit": 5})
    assert result is not None


@pytest.mark.asyncio
async def test_breach_report_tool_list():
    """Test breach_report MCP tool - list action."""
    result = await breach_report({"action": "list"})
    assert result is not None
    assert "breaches" in result or hasattr(result, "breaches")


@pytest.mark.asyncio
async def test_safeguarding_health_tool():
    """Test safeguarding_health MCP tool."""
    result = await safeguarding_health({})
    assert result is not None
    assert "position_compliant" in result or hasattr(result, "position_compliant")
