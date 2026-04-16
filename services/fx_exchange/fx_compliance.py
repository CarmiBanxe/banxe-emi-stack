"""
services/fx_exchange/fx_compliance.py
IL-FX-01 | Phase 21

FXCompliance — stateless FX compliance screening.
MLR 2017 §33: EDD trigger at £10,000.
HITL gate at £50,000 (I-27).
Hard-blocked sanctioned currencies (I-02): RUB, IRR, KPW, BYR, SYP, CUC.
All thresholds and amounts are Decimal (I-01).
"""

from __future__ import annotations

from decimal import Decimal

from services.fx_exchange.models import ComplianceFlag, CurrencyPair

# ── Compliance thresholds (Decimal — I-01) ─────────────────────────────────────

_LARGE_FX_THRESHOLD: Decimal = Decimal("10000")  # MLR 2017 §33 EDD trigger
_HITL_THRESHOLD: Decimal = Decimal("50000")  # L4 HITL gate (I-27)

# ── Sanctioned currencies (I-02) ──────────────────────────────────────────────

_BLOCKED_CURRENCIES: frozenset[str] = frozenset({"RUB", "IRR", "KPW", "BYR", "SYP", "CUC"})


class FXCompliance:
    """Stateless FX compliance checks.

    All monetary thresholds use Decimal. No state stored — safe to reuse
    across requests.
    """

    async def check_order(
        self,
        entity_id: str,  # noqa: ARG002 — reserved for entity risk profile lookup
        pair: CurrencyPair,
        amount_gbp: Decimal,
    ) -> ComplianceFlag:
        """Screen an FX order for compliance flags.

        Returns:
            BLOCKED   — sanctioned currency in pair (I-02)
            EDD_REQUIRED — amount >= £10k (MLR 2017 §33) or >= £50k (HITL gate, I-27)
            CLEAR     — no issues found
        """
        if pair.base in _BLOCKED_CURRENCIES or pair.quote in _BLOCKED_CURRENCIES:
            return ComplianceFlag.BLOCKED

        if amount_gbp >= _HITL_THRESHOLD:
            return ComplianceFlag.EDD_REQUIRED

        if amount_gbp >= _LARGE_FX_THRESHOLD:
            return ComplianceFlag.EDD_REQUIRED

        return ComplianceFlag.CLEAR

    async def detect_structuring(
        self,
        entity_id: str,  # noqa: ARG002 — reserved for entity lookup
        recent_amounts: list[Decimal],
    ) -> bool:
        """Detect potential structuring (smurfing) activity.

        Returns True if:
          - The sum of recent_amounts exceeds _LARGE_FX_THRESHOLD, AND
          - No single amount exceeds _LARGE_FX_THRESHOLD

        This simplified check flags patterns where an entity splits a large
        transaction into multiple smaller amounts to avoid EDD thresholds.
        """
        if not recent_amounts:
            return False

        total = sum(recent_amounts, Decimal("0"))
        max_single = max(recent_amounts)

        return total > _LARGE_FX_THRESHOLD and max_single <= _LARGE_FX_THRESHOLD
