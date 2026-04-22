"""FX Rate Agent — scheduled ECB rate fetching with HITL overrides.

IL-FXR-01 | Phase 52A | Sprint 37
Autonomy: L4 for manual overrides (TREASURY_OFFICER), L1 for scheduled fetch.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
from typing import Any

from services.fx_rates.frankfurter_client import FXRateService, get_fx_rate_service

logger = logging.getLogger("banxe.fx_rates.agent")

DEFAULT_BASE_CURRENCIES = ["GBP", "EUR", "USD"]


class FXRateAgent:
    """Agent for scheduled FX rate fetching and manual override proposals."""

    def __init__(self, service: FXRateService | None = None) -> None:
        self._service = service or get_fx_rate_service()

    def schedule_daily_fetch(self, base_currencies: list[str] | None = None) -> dict[str, Any]:
        """Fetch latest rates for each base currency. Append to store (I-24).

        Returns:
            {"fetched": [...], "failed": [...], "timestamp": "..."}
        """
        currencies = base_currencies or DEFAULT_BASE_CURRENCIES
        fetched: list[str] = []
        failed: list[dict[str, str]] = []

        for base in currencies:
            try:
                rates = self._service.get_latest(base=base)
                fetched.append(base)
                logger.info(
                    "fx_agent.daily_fetch base=%s symbols=%d",
                    base,
                    len(rates),
                )
            except Exception as exc:  # noqa: BLE001
                failed.append({"base": base, "error": str(exc)})
                logger.warning("fx_agent.daily_fetch_failed base=%s error=%s", base, exc)

        return {
            "fetched": fetched,
            "failed": failed,
            "timestamp": datetime.now(UTC).isoformat(),
        }

    def override_rate(
        self, base: str, symbol: str, rate: Decimal, operator: str, reason: str
    ) -> dict[str, Any]:
        """Propose manual rate override — always HITL L4 (I-27, TREASURY_OFFICER).

        Returns:
            HITLProposal dict — must be approved by TREASURY_OFFICER before applying.
        """
        return self._service.override_rate(
            base=base, symbol=symbol, rate=rate, operator=operator, reason=reason
        )

    def get_rate_dashboard(self) -> dict[str, Any]:
        """Return a summary of cached rates for monitoring dashboard."""
        entries = self._service._store.list_recent(limit=30)
        by_base: dict[str, Any] = {}
        for entry in entries:
            by_base[entry.base] = {
                "date": entry.date,
                "symbols": list(entry.rates.keys()),
                "fetched_at": entry.fetched_at,
                "source": entry.source,
            }
        return {
            "cached_bases": list(by_base.keys()),
            "entries_count": len(entries),
            "details": by_base,
            "generated_at": datetime.now(UTC).isoformat(),
        }
