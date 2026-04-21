"""
services/fx_engine/hedging_engine.py
FX Hedging Engine
IL-FXE-01 | Sprint 34 | Phase 48

FCA: EMIR (FX derivatives), PS22/9
Trust Zone: AMBER

Net exposure Decimal (I-22). HITL if >= £500k (I-27).
Append-only HedgeStore (I-24). UTC timestamps (I-23).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import logging
import uuid

from services.fx_engine.models import (
    HedgePosition,
    HedgeStore,
    HITLProposal,
    InMemoryHedgeStore,
    InMemoryRateStore,
    RateStore,
)

logger = logging.getLogger(__name__)

HEDGE_ALERT_THRESHOLD_GBP = Decimal("500000")  # I-22: net exposure alert


class HedgingEngine:
    """FX hedge position tracking engine.

    Append-only position log (I-24). All amounts Decimal (I-22).
    UTC snapshots (I-23). HITL escalation if |exposure| >= £500k (I-27).
    """

    def __init__(
        self,
        store: HedgeStore | None = None,
        rate_store: RateStore | None = None,
    ) -> None:
        """Initialise engine with optional hedge and rate stores."""
        self._store: HedgeStore = store or InMemoryHedgeStore()
        self._rate_store: RateStore = rate_store or InMemoryRateStore()
        self._pairs: set[str] = set()

    def record_position(
        self,
        currency_pair: str,
        long_amount: Decimal,
        short_amount: Decimal,
    ) -> HedgePosition:
        """Record a hedge position snapshot.

        I-22: net_exposure = long_amount - short_amount.
        I-24: append to HedgeStore.
        I-23: snapshot_date = UTC.

        Args:
            currency_pair: e.g. "GBP/EUR".
            long_amount: Long position (Decimal, I-22).
            short_amount: Short position (Decimal, I-22).

        Returns:
            Appended HedgePosition.
        """
        net_exposure = long_amount - short_amount
        position = HedgePosition(
            position_id=f"hp_{uuid.uuid4().hex[:8]}",
            currency_pair=currency_pair,
            net_long=long_amount,
            net_short=short_amount,
            net_exposure=net_exposure,
            snapshot_date=datetime.now(UTC).isoformat(),
        )
        self._store.append(position)  # I-24
        self._pairs.add(currency_pair)
        logger.info(
            "Hedge position recorded %s long=%s short=%s net=%s",
            currency_pair,
            long_amount,
            short_amount,
            net_exposure,
        )
        return position

    def get_net_exposure(self, currency_pair: str) -> Decimal:
        """Get current net exposure for a currency pair.

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            Net exposure as Decimal (I-22), or 0 if no position.
        """
        latest = self._store.get_latest(currency_pair)
        return latest.net_exposure if latest else Decimal("0")

    def take_eod_snapshot(self) -> list[HedgePosition]:
        """Take end-of-day snapshot for all tracked pairs.

        Returns:
            List of latest HedgePosition snapshots.
        """
        snapshots: list[HedgePosition] = []
        for pair in self._pairs:
            latest = self._store.get_latest(pair)
            if latest is not None:
                eod = latest.model_copy(update={"snapshot_date": datetime.now(UTC).isoformat()})
                self._store.append(eod)  # I-24
                snapshots.append(eod)
        logger.info("EOD snapshot taken for %d pairs", len(snapshots))
        return snapshots

    def check_threshold(self, currency_pair: str) -> HITLProposal | None:
        """Check if net exposure breaches alert threshold.

        I-27: if |net_exposure| >= £500k → HITLProposal.

        Args:
            currency_pair: e.g. "GBP/EUR".

        Returns:
            HITLProposal if threshold breached, None otherwise.
        """
        exposure = abs(self.get_net_exposure(currency_pair))
        if exposure >= HEDGE_ALERT_THRESHOLD_GBP:
            logger.warning(
                "Hedge threshold breached %s exposure=%s >= £500k — HITL (I-27)",
                currency_pair,
                exposure,
            )
            return HITLProposal(
                action="HEDGE_THRESHOLD_BREACH",
                quote_id=currency_pair,
                requires_approval_from="TREASURY_OPS",
                reason=f"Net exposure {exposure} {currency_pair} >= £500k alert threshold (I-27)",
                autonomy_level="L4",
            )
        return None

    def get_hedging_summary(self) -> dict[str, object]:
        """Get hedging engine summary statistics.

        Returns:
            Dict with pairs, total_long, total_short, alert_count (all Decimal I-22).
        """
        total_long = Decimal("0")
        total_short = Decimal("0")
        alert_count = 0

        for pair in self._pairs:
            latest = self._store.get_latest(pair)
            if latest is not None:
                total_long += latest.net_long
                total_short += latest.net_short
                if abs(latest.net_exposure) >= HEDGE_ALERT_THRESHOLD_GBP:
                    alert_count += 1

        return {
            "pairs": list(self._pairs),
            "total_long": total_long,
            "total_short": total_short,
            "alert_count": alert_count,
        }
