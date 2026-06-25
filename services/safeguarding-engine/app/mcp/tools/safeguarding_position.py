"""MCP Tool: safeguarding_position.

Get current safeguarding position, shortfall, compliance status.
Input: {date?: string} (defaults to today)
Output: {total_client_funds, total_safeguarded, shortfall, is_compliant, position_date}
"""

from typing import Dict

from app.services.position_calculator import PositionCalculator


async def safeguarding_position(params: Dict) -> Dict:
    """Get current safeguarding position via PositionCalculator."""
    calc = PositionCalculator(db=None)
    position = await calc.calculate_position()
    return {
        "total_client_funds": str(position.total_client_funds),
        "total_safeguarded": str(position.total_safeguarded),
        "shortfall": str(position.shortfall),
        "is_compliant": position.is_compliant,
        "position_date": position.position_date.isoformat(),
    }
