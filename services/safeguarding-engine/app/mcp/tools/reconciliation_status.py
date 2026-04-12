"""MCP Tool: reconciliation_status.

Get latest reconciliation results.
Input: {type?: 'daily'|'monthly', limit?: number}
Output: {reconciliations[], last_matched, breaks_count}
"""

from typing import Dict


async def reconciliation_status(params: Dict) -> Dict:
    """Get latest reconciliation results."""
    _recon_type = params.get("type")  # daily or monthly
    _limit = params.get("limit", 10)
    raise NotImplementedError("Implement MCP tool")
