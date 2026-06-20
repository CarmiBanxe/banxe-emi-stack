"""
services/quant_advisory — Quant pricing/risk advisory seam (GAP-070, IMPL-4 FINAL).

Heston/Bates pricing, SABR/SVI vol-surface, Avellaneda-Stoikov optimal spread,
Greeks + VaR99 + stress (ADR-113; ties GAP-036 treasury, GAP-020 ICARA).
ADVISORY-SEAM ONLY — QUANT_CAN_EXECUTE = False; outputs feed the Dynamic Spread
Engine and a human decides (MiCA broker-dealer avoidance, ADR-089/090/091/093).
"""

from __future__ import annotations

from services.quant_advisory.pricing import HestonParams, JumpParams, PricingModel
from services.quant_advisory.risk_metrics import Greeks
from services.quant_advisory.service import (
    QUANT_CAN_EXECUTE,
    AdvisoryRecommendation,
    QuantAdvisoryService,
    VolSurfacePoint,
)

__all__ = [
    "QUANT_CAN_EXECUTE",
    "AdvisoryRecommendation",
    "Greeks",
    "HestonParams",
    "JumpParams",
    "PricingModel",
    "QuantAdvisoryService",
    "VolSurfacePoint",
]
