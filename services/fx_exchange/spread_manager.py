"""
services/fx_exchange/spread_manager.py
IL-FX-01 | Phase 21

SpreadManager — manages FX spread configurations per currency pair.
VIP detection: entity_id starting with "vip-" → vip_spread_bps.
Volume tier: if volume >= tier_volume_threshold → min_spread_bps.
spread_bps is int (basis points — not a monetary amount, OK not Decimal).
"""

from __future__ import annotations

from decimal import Decimal

from services.fx_exchange.models import (
    _DEFAULT_SPREADS,
    CurrencyPair,
    OrderStorePort,
    SpreadConfig,
    get_default_spread_config,
)

_VIP_PREFIX: str = "vip-"


class SpreadManager:
    """Manages per-pair spread configuration and effective spread resolution.

    Effective spread priority:
    1. VIP entity (entity_id starts with "vip-") → vip_spread_bps
    2. High-volume entity (volume >= tier_volume_threshold) → min_spread_bps
    3. Default → base_spread_bps
    """

    def __init__(
        self,
        spread_configs: dict[str, SpreadConfig] | None = None,
        order_store: OrderStorePort | None = None,
    ) -> None:
        self._configs: dict[str, SpreadConfig] = (
            dict(spread_configs) if spread_configs is not None else dict(_DEFAULT_SPREADS)
        )
        self._order_store = order_store  # reserved for future volume lookups

    async def get_spread(self, pair: CurrencyPair) -> SpreadConfig:
        """Return SpreadConfig for a pair, or default if not configured."""
        return self._configs.get(str(pair), get_default_spread_config(pair))

    async def set_spread(self, pair: CurrencyPair, config: SpreadConfig) -> SpreadConfig:
        """Upsert spread configuration for a pair."""
        self._configs[str(pair)] = config
        return config

    async def get_effective_spread(
        self,
        pair: CurrencyPair,
        entity_id: str,
        volume: Decimal,
    ) -> int:
        """Return effective spread_bps for an entity trading a given volume.

        Priority:
        1. VIP entity → vip_spread_bps
        2. Volume >= tier_volume_threshold → min_spread_bps
        3. Default → base_spread_bps
        """
        config = await self.get_spread(pair)

        if entity_id.startswith(_VIP_PREFIX):
            return config.vip_spread_bps

        if volume >= config.tier_volume_threshold:
            return config.min_spread_bps

        return config.base_spread_bps

    async def list_spreads(self) -> list[SpreadConfig]:
        """Return all configured spread configs."""
        return list(self._configs.values())
