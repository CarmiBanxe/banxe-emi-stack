"""
services/fx_engine/__init__.py
FX Engine — Public API
IL-FXE-01 | Sprint 34 | Phase 48
"""

from __future__ import annotations

from services.fx_engine.fx_agent import FXAgent
from services.fx_engine.fx_compliance_reporter import FXComplianceReporter
from services.fx_engine.fx_executor import FXExecutor
from services.fx_engine.fx_quoter import FXQuoter
from services.fx_engine.hedging_engine import HedgingEngine
from services.fx_engine.models import (
    ExecutionStatus,
    FXExecution,
    FXQuote,
    FXRate,
    FXRateType,
    HedgePosition,
    HITLProposal,
    InMemoryExecutionStore,
    InMemoryHedgeStore,
    InMemoryQuoteStore,
    InMemoryRateStore,
    QuoteStatus,
    RiskTier,
)
from services.fx_engine.rate_provider import LiveRateProvider, RateProvider
from services.fx_engine.spread_calculator import SpreadCalculator

__all__ = [
    "ExecutionStatus",
    "FXAgent",
    "FXComplianceReporter",
    "FXExecution",
    "FXExecutor",
    "FXQuote",
    "FXQuoter",
    "FXRate",
    "FXRateType",
    "HedgePosition",
    "HedgingEngine",
    "HITLProposal",
    "InMemoryExecutionStore",
    "InMemoryHedgeStore",
    "InMemoryQuoteStore",
    "InMemoryRateStore",
    "LiveRateProvider",
    "QuoteStatus",
    "RateProvider",
    "RiskTier",
    "SpreadCalculator",
]
