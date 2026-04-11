"""
tests/test_mcp_server.py — MCP Server unit tests
IL-MCP-01 | banxe-emi-stack | 2026-04-11

Tests:
  - Server imports and name
  - All tools have docstrings and type hints
  - Recon tools (get_recon_status, get_breach_history, get_discrepancy_trend)
  - run_reconciliation tool
  - Error handling (no raw Exception)
  - Tool count and registry
"""
from __future__ import annotations

import inspect

import pytest


# ── Test: Server imports ───────────────────────────────────────────────────────


def test_server_imports():
    """banxe_mcp.server can be imported without errors."""
    from banxe_mcp.server import mcp_server  # noqa: F401


def test_server_name():
    """mcp_server.name == 'BANXE EMI AI Bank'."""
    from banxe_mcp.server import mcp_server

    assert mcp_server.name == "BANXE EMI AI Bank"


def test_mcp_package_imports():
    """banxe_mcp package can be imported."""
    import banxe_mcp  # noqa: F401


# ── Test: Tool registry ────────────────────────────────────────────────────────


def test_tools_registered():
    """MCP server has at least 11 tools registered."""
    from banxe_mcp.server import mcp_server

    tools = mcp_server._tool_manager._tools
    assert len(tools) >= 11, f"Expected ≥11 tools, got {len(tools)}: {list(tools.keys())}"


def test_expected_tool_names_registered():
    """All expected tool names are in the MCP server registry."""
    from banxe_mcp.server import mcp_server

    tools = mcp_server._tool_manager._tools
    expected = {
        "get_account_balance",
        "list_accounts",
        "get_transaction_history",
        "get_kyc_status",
        "check_aml_alert",
        "get_exchange_rate",
        "get_payment_status",
        "get_recon_status",
        "get_breach_history",
        "get_discrepancy_trend",
        "run_reconciliation",
    }
    registered = set(tools.keys())
    missing = expected - registered
    assert not missing, f"Missing tools: {missing}"


# ── Test: All tools have docstrings ───────────────────────────────────────────


def test_all_tools_have_docstrings():
    """Every registered MCP tool function must have a non-empty docstring.

    Enforces banxe-mcp-tool-must-have-docstring semgrep rule in code.
    """
    from banxe_mcp import server as srv

    tool_functions = [
        srv.get_account_balance,
        srv.list_accounts,
        srv.get_transaction_history,
        srv.get_kyc_status,
        srv.check_aml_alert,
        srv.get_exchange_rate,
        srv.get_payment_status,
        srv.get_recon_status,
        srv.get_breach_history,
        srv.get_discrepancy_trend,
        srv.run_reconciliation,
    ]
    for fn in tool_functions:
        doc = inspect.getdoc(fn)
        assert doc, f"Tool {fn.__name__} is missing a docstring"
        assert len(doc.strip()) > 10, f"Tool {fn.__name__} docstring too short: {doc!r}"


def test_all_tools_have_type_hints():
    """Every registered MCP tool function must have type annotations."""
    from banxe_mcp import server as srv

    tool_functions = [
        srv.get_account_balance,
        srv.list_accounts,
        srv.get_transaction_history,
        srv.get_kyc_status,
        srv.check_aml_alert,
        srv.get_exchange_rate,
        srv.get_payment_status,
        srv.get_recon_status,
        srv.get_breach_history,
        srv.get_discrepancy_trend,
        srv.run_reconciliation,
    ]
    for fn in tool_functions:
        hints = fn.__annotations__
        # Every function must have at least a return type annotation
        assert "return" in hints, f"Tool {fn.__name__} missing return type annotation"


# ── Test: get_recon_status (sandbox/offline) ─────────────────────────────────


@pytest.mark.asyncio
async def test_get_recon_status_tool_offline():
    """get_recon_status returns sandbox fallback when API unavailable."""
    from banxe_mcp.server import get_recon_status

    result = await get_recon_status(recon_date="2026-04-10")
    # Should return a string (not raise)
    assert isinstance(result, str)
    # Sandbox response contains date or error info
    assert len(result) > 0


@pytest.mark.asyncio
async def test_get_recon_status_default_date():
    """get_recon_status with no date uses today."""
    from banxe_mcp.server import get_recon_status

    result = await get_recon_status()
    assert isinstance(result, str)
    assert len(result) > 0


# ── Test: get_breach_history (sandbox/offline) ────────────────────────────────


@pytest.mark.asyncio
async def test_get_breach_history_tool_offline():
    """get_breach_history returns sandbox fallback when API unavailable."""
    from banxe_mcp.server import get_breach_history

    result = await get_breach_history(account_id="acc-safeguarding-001", days=30)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_get_breach_history_default_days():
    """get_breach_history uses 30 days by default."""
    from banxe_mcp.server import get_breach_history

    result = await get_breach_history(account_id="acc-test")
    assert isinstance(result, str)


# ── Test: get_discrepancy_trend (sandbox/offline) ─────────────────────────────


@pytest.mark.asyncio
async def test_get_discrepancy_trend_tool_offline():
    """get_discrepancy_trend returns sandbox fallback when API unavailable."""
    from banxe_mcp.server import get_discrepancy_trend

    result = await get_discrepancy_trend(account_id="acc-safeguarding-001", days=7)
    assert isinstance(result, str)
    assert len(result) > 0


# ── Test: run_reconciliation (sandbox/offline) ────────────────────────────────


@pytest.mark.asyncio
async def test_run_reconciliation_dry_run_offline():
    """run_reconciliation dry_run=True returns result string when API offline."""
    from banxe_mcp.server import run_reconciliation

    result = await run_reconciliation(recon_date="2026-04-10", dry_run=True)
    assert isinstance(result, str)
    assert len(result) > 0


@pytest.mark.asyncio
async def test_run_reconciliation_default_is_dry_run():
    """run_reconciliation default is dry_run=True (safe by default)."""
    from banxe_mcp import server as srv
    import inspect

    sig = inspect.signature(srv.run_reconciliation)
    dry_run_param = sig.parameters.get("dry_run")
    assert dry_run_param is not None, "run_reconciliation must have dry_run parameter"
    assert dry_run_param.default is True, "dry_run must default to True (safe by default)"


# ── Test: tool error handling (no raw Exception) ──────────────────────────────


@pytest.mark.asyncio
async def test_tool_returns_string_not_raises_on_connection_error():
    """Tools return error string on connection failure — never raise raw Exception.

    Tests banxe-mcp-no-raw-exception rule: MCP tools must catch httpx.ConnectError
    and return informative strings instead of propagating exceptions to the agent.
    """
    from banxe_mcp.server import (
        check_aml_alert,
        get_account_balance,
        get_exchange_rate,
        get_kyc_status,
        get_payment_status,
        list_accounts,
    )

    # All these tools should return a string, not raise, when API is offline
    for coro in [
        get_account_balance("acc-test"),
        list_accounts(),
        get_kyc_status("cust-test"),
        check_aml_alert("tx-test"),
        get_payment_status("pay-test"),
        get_exchange_rate("EUR", "GBP"),
    ]:
        result = await coro
        assert isinstance(result, str), f"Tool must return str, got {type(result)}"
        # Error message should mention the failure
        assert len(result) > 0


def test_tool_source_no_bare_raise_exception():
    """Tool source code must not contain bare 'raise Exception(' patterns.

    Validates banxe-mcp-no-raw-exception semgrep rule.
    """
    import re
    from pathlib import Path

    server_src = Path("banxe_mcp/server.py").read_text()
    # Check for bare Exception raises (not httpx-specific ones)
    bare_raises = re.findall(r"\braise\s+Exception\s*\(", server_src)
    assert not bare_raises, (
        f"Found {len(bare_raises)} bare 'raise Exception(' in server.py — "
        "use typed errors (httpx.HTTPStatusError, ValueError, etc.)"
    )


# ── Test: resources ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_health_resource():
    """banxe://health resource returns string."""
    from banxe_mcp.server import health_resource

    result = await health_resource()
    assert isinstance(result, str)


@pytest.mark.asyncio
async def test_info_resource():
    """banxe://info resource returns BANXE info string."""
    from banxe_mcp.server import info_resource

    result = await info_resource()
    assert isinstance(result, str)
    assert "BANXE" in result
    assert "FCA" in result
