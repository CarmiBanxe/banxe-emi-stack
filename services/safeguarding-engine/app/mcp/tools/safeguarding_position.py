"""MCP Tool: safeguarding_position.

Get current safeguarding position, shortfall, compliance status.
Input: {date?: string} (defaults to today)
Output: {total_client_funds, total_safeguarded, shortfall, is_compliant, accounts[]}
"""

from typing import Dict


async def safeguarding_position(params: Dict) -> Dict:
    """Get current safeguarding position."""
    _date_param = params.get("date")  # defaults to today
    # TODO: Query position calculator service
    raise NotImplementedError("Implement MCP tool")
