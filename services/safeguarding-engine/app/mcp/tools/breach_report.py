"""MCP Tool: breach_report.

List active breaches or report new breach.
Input: {action: 'list'|'report', breach_type?, severity?, description?}
Output: {breaches[], total, active_count, fca_notifications_pending}
"""

from typing import Dict

from app.services.breach_service import BreachService


async def breach_report(params: Dict) -> Dict:
    """List or report breaches via BreachService."""
    action = params.get("action", "list")
    service = BreachService(db=None)
    if action == "report":
        breach = await service.report_breach(
            breach_type=params.get("breach_type", "other"),
            severity=params.get("severity", "minor"),
            description=params.get("description", ""),
        )
        return breach.model_dump(mode="json")
    listing = await service.list_breaches()
    return listing.model_dump(mode="json")
