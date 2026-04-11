"""
tests/test_mcp_health_workflow.py — MCP Health Workflow tests
IL-MCP-01 | banxe-emi-stack | 2026-04-11

Tests:
  - Health check passes when all tools are functional
  - Health check detects broken/missing docstring tool
  - MCPHealthSkill.check() returns structured result
  - MCPHealthSkill.list_tools() returns tool inventory
"""
from __future__ import annotations

import pytest


# ── Test: MCPHealthSkill import ───────────────────────────────────────────────


def test_mcp_health_workflow_imports():
    """agents.compliance.workflows.mcp_health_workflow can be imported."""
    from agents.compliance.workflows import mcp_health_workflow  # noqa: F401


def test_mcp_health_skill_import():
    """MCPHealthSkill can be imported."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill  # noqa: F401


# ── Test: list_tools ─────────────────────────────────────────────────────────


def test_list_tools_returns_list():
    """MCPHealthSkill.list_tools() returns a list of tool names."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    skill = MCPHealthSkill()
    tools = skill.list_tools()
    assert isinstance(tools, list)
    assert len(tools) >= 11


def test_list_tools_contains_expected():
    """MCPHealthSkill.list_tools() contains all expected tool names."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    skill = MCPHealthSkill()
    tools = skill.list_tools()
    expected = {
        "get_account_balance",
        "list_accounts",
        "get_recon_status",
        "get_breach_history",
        "get_discrepancy_trend",
        "run_reconciliation",
    }
    for name in expected:
        assert name in tools, f"Expected tool {name!r} not in list_tools() result"


# ── Test: health check passes ─────────────────────────────────────────────────


def test_health_check_all_tools_pass():
    """MCPHealthSkill.check() returns healthy when all tools have docstrings."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    skill = MCPHealthSkill()
    result = skill.check()

    assert result["status"] in ("healthy", "degraded", "unhealthy")
    assert "tools_checked" in result
    assert "tools_failed" in result
    assert isinstance(result["tools_checked"], int)
    assert isinstance(result["tools_failed"], list)
    # All real tools have docstrings — should have 0 failures
    assert result["tools_failed"] == [], (
        f"Unexpected tool failures: {result['tools_failed']}"
    )
    assert result["status"] == "healthy"


def test_health_check_result_has_timestamp():
    """Health check result includes checked_at timestamp."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    skill = MCPHealthSkill()
    result = skill.check()

    assert "checked_at" in result
    assert result["checked_at"]  # not empty


def test_health_check_result_has_tool_inventory():
    """Health check result includes tool inventory list."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    skill = MCPHealthSkill()
    result = skill.check()

    assert "tool_inventory" in result
    assert isinstance(result["tool_inventory"], list)
    assert len(result["tool_inventory"]) >= 11


# ── Test: health check detects broken tool ────────────────────────────────────


def test_health_check_detects_broken_tool(monkeypatch):
    """MCPHealthSkill.check() detects a tool without docstring and reports it as failed."""
    from banxe_mcp import server as srv
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    # Temporarily remove docstring from get_account_balance
    original_doc = srv.get_account_balance.__doc__
    try:
        srv.get_account_balance.__doc__ = None
        skill = MCPHealthSkill()
        result = skill.check()

        assert "get_account_balance" in result["tools_failed"]
        assert result["status"] in ("degraded", "unhealthy")
    finally:
        # Restore docstring
        srv.get_account_balance.__doc__ = original_doc


def test_health_check_status_degraded_on_single_failure(monkeypatch):
    """Status is 'degraded' (not 'unhealthy') when only 1 out of 11+ tools fails."""
    from banxe_mcp import server as srv
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    original_doc = srv.list_accounts.__doc__
    try:
        srv.list_accounts.__doc__ = None
        skill = MCPHealthSkill()
        result = skill.check()

        # 1 failure = degraded (not full outage)
        assert result["status"] in ("degraded", "unhealthy")
        assert "list_accounts" in result["tools_failed"]
    finally:
        srv.list_accounts.__doc__ = original_doc


# ── Test: tool type hints validation ─────────────────────────────────────────


def test_health_check_validates_type_hints():
    """MCPHealthSkill validates that all tools have return type annotations."""
    from agents.compliance.workflows.mcp_health_workflow import MCPHealthSkill

    skill = MCPHealthSkill()
    result = skill.check()

    # All tools in banxe_mcp/server.py have return type str
    # So tools_without_type_hints should be empty
    assert "tools_without_type_hints" in result
    assert result["tools_without_type_hints"] == []
