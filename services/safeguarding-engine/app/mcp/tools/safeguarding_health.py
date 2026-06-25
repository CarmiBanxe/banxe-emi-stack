"""MCP Tool: safeguarding_health.

Overall safeguarding health dashboard.
Input: {} (no params)
Output: {position_compliant, shortfall, status}
"""

from typing import Dict

from app.services.position_calculator import PositionCalculator


async def safeguarding_health(params: Dict) -> Dict:
    """Overall safeguarding health via PositionCalculator."""
    calc = PositionCalculator(db=None)
    shortfall = await calc.check_shortfall()
    return {
        "position_compliant": shortfall.is_compliant,
        "shortfall": str(shortfall.shortfall),
        "status": "healthy" if shortfall.is_compliant else "breach",
    }
