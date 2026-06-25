"""MCP Tool: reconciliation_status.

Get latest reconciliation results.
Input: {type?: 'daily'|'monthly', limit?: int}
Output: {recon_type, count, results[]}
"""

from typing import Dict

from app.services.reconciliation_service import ReconciliationService


async def reconciliation_status(params: Dict) -> Dict:
    """Get latest reconciliation results via ReconciliationService."""
    recon_type = params.get("type")
    limit = params.get("limit", 50)
    service = ReconciliationService(db=None)
    results = await service.get_history(recon_type=recon_type, limit=limit)
    return {
        "recon_type": recon_type or "daily",
        "count": len(results),
        "results": [r.model_dump(mode="json") for r in results],
    }
