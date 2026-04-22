"""FX Rates service — Frankfurter ECB self-hosted rates.

IL-FXR-01 | Phase 52A | Sprint 37

Public API:
    FXRateService      — application service (convert, latest, historical, override HITL)
    FrankfurterClient  — HTTP client for Frankfurter ECB service
    FXRateAgent        — scheduled fetch + dashboard
    RateEntry          — value object (frozen dataclass)
    ConversionResult   — value object (frozen dataclass)
    RateOverride       — value object (frozen dataclass)
    InMemoryRateStore  — in-memory store stub for testing
    get_fx_rate_service — singleton factory
"""

from __future__ import annotations

from services.fx_rates.frankfurter_client import (
    BLOCKED_CURRENCIES,
    FrankfurterClient,
    FXRateService,
    get_fx_rate_service,
)
from services.fx_rates.fx_rate_agent import FXRateAgent
from services.fx_rates.fx_rate_models import (
    ConversionResult,
    InMemoryRateStore,
    RateEntry,
    RateOverride,
    RateStorePort,
)

__all__ = [
    "FXRateAgent",
    "FXRateService",
    "FrankfurterClient",
    "RateEntry",
    "ConversionResult",
    "RateOverride",
    "RateStorePort",
    "InMemoryRateStore",
    "BLOCKED_CURRENCIES",
    "get_fx_rate_service",
]
