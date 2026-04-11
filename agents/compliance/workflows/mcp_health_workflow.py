"""
agents/compliance/workflows/mcp_health_workflow.py — MCP Server Health Monitoring
IL-MCP-01 | banxe-emi-stack | 2026-04-11

Schedule: on startup + every 6 hours (via n8n or cron).

Steps:
  1. Import banxe_mcp.server, verify all tools load
  2. Check each tool has docstring and type hints
  3. Report results (optionally write to ClickHouse banxe.mcp_health_events)

MCPHealthSkill is registered in agents/compliance/orchestrator.py.
"""
from __future__ import annotations

import inspect
import logging
from datetime import UTC, datetime
from typing import Any

logger = logging.getLogger("banxe.swarm.mcp_health")

# Tool functions exported from banxe_mcp.server that we validate
_EXPECTED_TOOL_NAMES = [
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
]


class MCPHealthSkill:
    """
    MCP Server health monitoring skill.

    Validates that all registered MCP tools:
    - Are importable from banxe_mcp.server
    - Have non-empty docstrings (banxe-mcp-tool-must-have-docstring rule)
    - Have return type annotations

    Reports: status (healthy | degraded | unhealthy), failed tools list, inventory.
    """

    def list_tools(self) -> list[str]:
        """Return list of expected MCP tool names from banxe_mcp.server.

        Returns:
            List of tool function names registered on mcp_server.
        """
        try:
            from banxe_mcp.server import mcp_server

            registered = list(mcp_server._tool_manager._tools.keys())
            if registered:
                return registered
        except Exception:
            pass
        # Fallback to expected list if server cannot be imported
        return list(_EXPECTED_TOOL_NAMES)

    def check(self) -> dict[str, Any]:
        """Run a full health check on the MCP server.

        Steps:
          1. Import mcp_server — verify it loads
          2. Check each expected tool for docstring
          3. Check each expected tool for type hints (return annotation)
          4. Build health report

        Returns:
            dict with keys:
              status: "healthy" | "degraded" | "unhealthy"
              tools_checked: int
              tools_failed: list[str]  — tools missing docstring
              tools_without_type_hints: list[str]  — tools missing return annotation
              tool_inventory: list[str]  — all registered tool names
              server_importable: bool
              checked_at: str  — ISO-8601 UTC timestamp
              error: str | None  — import error if server not importable
        """
        checked_at = datetime.now(UTC).isoformat()
        tools_failed: list[str] = []
        tools_without_hints: list[str] = []
        server_importable = False
        import_error: str | None = None
        tool_inventory: list[str] = []

        # Step 1: Import server
        try:
            import banxe_mcp.server as srv

            server_importable = True
            logger.info("MCP server imported successfully: %s", srv.mcp_server.name)
        except Exception as exc:
            import_error = str(exc)
            logger.error("MCP server import failed: %s", exc)
            return {
                "status": "unhealthy",
                "tools_checked": 0,
                "tools_failed": [],
                "tools_without_type_hints": [],
                "tool_inventory": [],
                "server_importable": False,
                "checked_at": checked_at,
                "error": import_error,
            }

        # Step 2: Get tool inventory from registry
        try:
            tool_inventory = list(srv.mcp_server._tool_manager._tools.keys())
        except Exception:
            tool_inventory = list(_EXPECTED_TOOL_NAMES)

        # Step 3: Validate each expected tool function
        for tool_name in _EXPECTED_TOOL_NAMES:
            fn = getattr(srv, tool_name, None)
            if fn is None:
                logger.warning("Tool %s not found as module attribute", tool_name)
                tools_failed.append(tool_name)
                continue

            # Check docstring (banxe-mcp-tool-must-have-docstring)
            doc = inspect.getdoc(fn)
            if not doc or len(doc.strip()) <= 10:
                logger.warning("Tool %s missing docstring", tool_name)
                tools_failed.append(tool_name)

            # Check return type annotation
            hints = getattr(fn, "__annotations__", {})
            if "return" not in hints:
                logger.warning("Tool %s missing return type annotation", tool_name)
                tools_without_hints.append(tool_name)

        # Step 4: Determine status
        tools_checked = len(_EXPECTED_TOOL_NAMES)
        failure_rate = len(tools_failed) / max(tools_checked, 1)

        if len(tools_failed) == 0:
            status = "healthy"
        elif failure_rate < 0.3:
            status = "degraded"
        else:
            status = "unhealthy"

        result: dict[str, Any] = {
            "status": status,
            "tools_checked": tools_checked,
            "tools_failed": tools_failed,
            "tools_without_type_hints": tools_without_hints,
            "tool_inventory": tool_inventory,
            "server_importable": server_importable,
            "checked_at": checked_at,
            "error": import_error,
        }
        logger.info(
            "MCP health check: status=%s tools_checked=%d failed=%d",
            status,
            tools_checked,
            len(tools_failed),
        )
        return result


def run_health_check() -> dict[str, Any]:
    """Entry point for scheduled health check (called by n8n, cron, or startup hook).

    Returns health check result dict.
    Logs to ClickHouse banxe.mcp_health_events if client available.
    """
    skill = MCPHealthSkill()
    result = skill.check()

    # Optionally write to ClickHouse (non-blocking — failure here must not crash health check)
    _try_log_to_clickhouse(result)

    # Alert if degraded or unhealthy
    if result["status"] != "healthy":
        logger.warning(
            "MCP SERVER HEALTH: %s | failed_tools=%s",
            result["status"].upper(),
            result["tools_failed"],
        )

    return result


def _try_log_to_clickhouse(result: dict[str, Any]) -> None:
    """Write health check event to ClickHouse banxe.mcp_health_events (best-effort)."""
    try:
        import clickhouse_connect  # type: ignore[import-untyped]

        client = clickhouse_connect.get_client(
            host="clickhouse",
            port=8123,
            database="banxe",
        )
        client.insert(
            "mcp_health_events",
            [[
                result["checked_at"],
                result["status"],
                result["tools_checked"],
                len(result["tools_failed"]),
                ",".join(result["tools_failed"]),
                result.get("error") or "",
            ]],
            column_names=[
                "checked_at", "status", "tools_checked",
                "tools_failed_count", "tools_failed_names", "error_message",
            ],
        )
    except Exception as exc:
        # Non-critical — sandbox environment without ClickHouse is expected
        logger.debug("ClickHouse health event write skipped: %s", exc)


if __name__ == "__main__":
    import json
    import logging as _logging

    _logging.basicConfig(level=_logging.INFO)
    health = run_health_check()
    print(json.dumps(health, indent=2))
