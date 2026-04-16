"""
services/treasury/cash_flow_forecaster.py
IL-TLM-01 | Phase 17

Cash flow forecasting using historical positions (simple linear trend).
Uses only stdlib + Decimal — no scikit-learn dependency for InMemory stub.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.treasury.models import (
    CashPosition,
    ForecastHorizon,
    ForecastResult,
    ForecastStorePort,
    LiquidityStorePort,
    TreasuryAuditPort,
)

_MODEL_VERSION = "linear-trend-v1"

_MIN_CONFIDENCE = Decimal("0.50")
_MAX_CONFIDENCE = Decimal("0.90")

# Thresholds for confidence scaling
_FEW_THRESHOLD = 3
_MANY_THRESHOLD = 10


class CashFlowForecaster:
    """Cash flow forecaster using simple linear trend from historical positions."""

    def __init__(
        self,
        store: LiquidityStorePort,
        forecast_store: ForecastStorePort,
        audit: TreasuryAuditPort,
    ) -> None:
        self._store = store
        self._forecast_store = forecast_store
        self._audit = audit

    async def forecast(
        self,
        pool_id: str,
        horizon: ForecastHorizon,
        actor: str,
    ) -> ForecastResult:
        """Generate a cash flow forecast for the given pool and horizon."""
        pool = await self._store.get_pool(pool_id)
        if pool is None:
            raise ValueError(f"Pool {pool_id!r} not found")

        positions = await self._store.list_positions(pool_id)

        if len(positions) < 2:
            forecast_amount = pool.current_balance
            confidence = _MIN_CONFIDENCE
        else:
            forecast_amount = self._compute_trend(positions)
            confidence = self._compute_confidence(len(positions))

        shortfall_risk = forecast_amount < pool.required_minimum

        result = ForecastResult(
            id=str(uuid.uuid4()),
            pool_id=pool_id,
            horizon=horizon,
            forecast_amount=forecast_amount,
            confidence=confidence,
            generated_at=datetime.now(UTC),
            model_version=_MODEL_VERSION,
            shortfall_risk=shortfall_risk,
        )

        await self._forecast_store.save_forecast(result)
        await self._audit.log(
            event_type="forecast.generated",
            entity_id=pool_id,
            details={
                "forecast_id": result.id,
                "horizon": horizon.value,
                "forecast_amount": str(forecast_amount),
                "confidence": str(confidence),
                "shortfall_risk": shortfall_risk,
            },
            actor=actor,
        )
        return result

    async def get_latest_forecast(
        self, pool_id: str, horizon: ForecastHorizon
    ) -> ForecastResult | None:
        """Return the most recent forecast for a pool+horizon combination."""
        return await self._forecast_store.get_latest(pool_id, horizon)

    async def list_forecasts(self, pool_id: str) -> list[ForecastResult]:
        """Return all forecasts for a given pool."""
        return await self._forecast_store.list_forecasts(pool_id)

    def _compute_trend(self, positions: list[CashPosition]) -> Decimal:
        """Compute simple average of last 3 positions as forecast amount.

        Uses integer arithmetic on Decimal — no float involved.
        """
        recent = positions[-3:]
        total = sum((p.amount for p in recent), Decimal("0"))
        count = Decimal(str(len(recent)))
        return total / count

    def _compute_confidence(self, n_positions: int) -> Decimal:
        """Scale confidence between 0.50 and 0.90 based on data volume."""
        if n_positions <= _FEW_THRESHOLD:
            return _MIN_CONFIDENCE
        if n_positions >= _MANY_THRESHOLD:
            return _MAX_CONFIDENCE
        # Linear interpolation between thresholds
        span = Decimal(str(_MANY_THRESHOLD - _FEW_THRESHOLD))
        offset = Decimal(str(n_positions - _FEW_THRESHOLD))
        range_conf = _MAX_CONFIDENCE - _MIN_CONFIDENCE
        return _MIN_CONFIDENCE + (offset / span) * range_conf
