"""MCP tool server for Safeguarding Engine.

Registers 4 tools:
1. safeguarding_position - Get current position/shortfall/compliance
2. reconciliation_status - Get latest reconciliation results
3. breach_report - List/report breaches
4. safeguarding_health - Overall health dashboard
"""
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


class SafeguardingMCPServer:
    """MCP tool server registering safeguarding tools."""

    def __init__(self, app: Any = None):
        self.app = app
        self.tools = {}

    def register_tools(self) -> None:
        """Register all 4 MCP tools."""
        from app.mcp.tools.safeguarding_position import safeguarding_position
        from app.mcp.tools.reconciliation_status import reconciliation_status
        from app.mcp.tools.breach_report import breach_report
        from app.mcp.tools.safeguarding_health import safeguarding_health

        self.tools = {
            "safeguarding_position": safeguarding_position,
            "reconciliation_status": reconciliation_status,
            "breach_report": breach_report,
            "safeguarding_health": safeguarding_health,
        }
        logger.info("Registered %d MCP tools", len(self.tools))

    async def handle_tool_call(self, tool_name: str, params: Dict) -> Dict:
        """Handle incoming MCP tool call."""
        if tool_name not in self.tools:
            return {"error": f"Unknown tool: {tool_name}"}
        return await self.tools[tool_name](params)
