"""
aml_thresholds.py — Dual-Entity AML Threshold Sets
Geniusto v5 — separate monitoring rules for Individual vs Corporate
MLR 2017 | POCA 2002 | FCA SYSC 6.3 | Banxe I-04

WHY THIS FILE EXISTS
--------------------
MLR 2017 Reg.28(3) requires Enhanced Due Diligence (EDD) for transactions
above defined thresholds. These thresholds DIFFER between natural persons
(individuals) and legal entities (companies):

  INDIVIDUAL thresholds (retail — tighter controls):
    - EDD/structuring alert: £10,000 (FCA I-04 invariant)
    - Daily velocity cap: £25,000 / 10 transactions
    - Monthly cap: £100,000 / 100 transactions
    - Auto-SAR trigger: single tx ≥ £50,000

  COMPANY thresholds (B2B — higher volumes are normal):
    - EDD/structuring alert: £50,000
    - Daily velocity cap: £500,000 / 50 transactions
    - Monthly cap: £2,000,000 / 500 transactions
    - Auto-SAR trigger: single tx ≥ £250,000

Previously these were hardcoded in mock_fraud_adapter.py (_AMOUNT_HIGH = £10,000)
which meant ALL customers got individual-level scrutiny — causing false-positive
HOLD decisions for legitimate corporate transactions.

Usage:
    thresholds = get_thresholds("INDIVIDUAL")
    if amount >= thresholds.edd_trigger:
        require_edd()
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

# ─── BANXE COMPLIANCE RAG (auto-injected) ───
try:
    import sys as _sys

    _sys.path.insert(0, "/data/compliance")
    from compliance_agent_client import rag_context as _rag_context

    _RAG_AVAILABLE = True
except ImportError:
    _RAG_AVAILABLE = False

    def _rag_context(agent, query, k=3):
        return ""


def get_compliance_context(query, agent_name=None, k=3):
    """Получить compliance-контекст из базы знаний для промпта."""
    if not _RAG_AVAILABLE:
        return ""
    return _rag_context(agent_name or "banxe_aml_screening_agent", query, k)


# ─────────────────────────────────────────────


@dataclass(frozen=True)
class AMLThresholdSet:
    """
    Full threshold configuration for one entity type.
    All amounts in GBP (or GBP-equivalent for FX transactions).
    """

    entity_type: str  # "INDIVIDUAL" or "COMPANY"

    # ── EDD / structuring detection ───────────────────────────────────────────
    edd_trigger: Decimal  # Single tx ≥ this → EDD required (MLR 2017 Reg.28)
    structuring_window_count: int  # Number of txs in window that = structuring signal
    structuring_window_gbp: Decimal  # Total GBP in window that = structuring signal

    # ── Velocity limits (monitored, not hard-blocked — use PaymentLimits for hard stops) ──
    velocity_daily_amount: Decimal  # Alert if daily outbound exceeds this
    velocity_daily_count: int  # Alert if daily tx count exceeds this
    velocity_monthly_amount: Decimal  # Alert if monthly outbound exceeds this
    velocity_monthly_count: int  # Alert if monthly tx count exceeds this

    # ── SAR thresholds ────────────────────────────────────────────────────────
    sar_auto_single: Decimal  # Single tx ≥ this → auto SAR consideration (POCA 2002)
    sar_auto_daily: Decimal  # Daily total ≥ this → auto SAR consideration

    # ── FX-specific ───────────────────────────────────────────────────────────
    fx_single_edd: Decimal  # FX single tx ≥ this → EDD (often lower than payment)
    fx_daily_alert: Decimal  # FX daily alert threshold

    # ── PEP/Sanctions multiplier ──────────────────────────────────────────────
    pep_edd_multiplier: Decimal = Decimal("0.5")  # PEP gets EDD at 50% of normal threshold

    def edd_for_pep(self) -> Decimal:
        """EDD trigger for PEP customers (tighter — FCA SYSC 6.3)."""
        return (self.edd_trigger * self.pep_edd_multiplier).quantize(Decimal("0.01"))

    def requires_edd(self, amount: Decimal, is_pep: bool = False) -> bool:
        threshold = self.edd_for_pep() if is_pep else self.edd_trigger
        return amount >= threshold

    def requires_sar_consideration(self, amount: Decimal) -> bool:
        return amount >= self.sar_auto_single

    def is_velocity_daily_breach(self, daily_total: Decimal, daily_count: int) -> bool:
        return daily_total >= self.velocity_daily_amount or daily_count >= self.velocity_daily_count

    def is_velocity_monthly_breach(self, monthly_total: Decimal, monthly_count: int) -> bool:
        return (
            monthly_total >= self.velocity_monthly_amount
            or monthly_count >= self.velocity_monthly_count
        )

    def is_structuring_signal(
        self,
        recent_count: int,
        recent_total: Decimal,
    ) -> bool:
        """
        POCA 2002 s.330 — structuring detection.
        Multiple sub-threshold transactions totalling above EDD threshold.
        """
        return (
            recent_count >= self.structuring_window_count
            and recent_total >= self.structuring_window_gbp
        )


# ── Canonical threshold sets ───────────────────────────────────────────────────

INDIVIDUAL_THRESHOLDS = AMLThresholdSet(
    entity_type="INDIVIDUAL",
    # MLR 2017 Reg.28(3): £10,000 EDD trigger for retail customers
    # Banxe I-04 invariant
    edd_trigger=Decimal("10000"),
    structuring_window_count=3,  # 3+ txs in 24h totalling ≥ £9,000
    structuring_window_gbp=Decimal("9000"),
    velocity_daily_amount=Decimal("25000"),
    velocity_daily_count=10,
    velocity_monthly_amount=Decimal("100000"),
    velocity_monthly_count=100,
    sar_auto_single=Decimal("50000"),  # Auto SAR consideration for retail
    sar_auto_daily=Decimal("25000"),
    fx_single_edd=Decimal("5000"),  # Lower FX threshold (currency risk)
    fx_daily_alert=Decimal("10000"),
)

COMPANY_THRESHOLDS = AMLThresholdSet(
    entity_type="COMPANY",
    # B2B: £50,000 EDD trigger — normal for commercial payments
    edd_trigger=Decimal("50000"),
    structuring_window_count=5,  # 5+ txs in 24h totalling ≥ £45,000
    structuring_window_gbp=Decimal("45000"),
    velocity_daily_amount=Decimal("500000"),
    velocity_daily_count=50,
    velocity_monthly_amount=Decimal("2000000"),
    velocity_monthly_count=500,
    sar_auto_single=Decimal("250000"),  # Auto SAR consideration for corporate
    sar_auto_daily=Decimal("500000"),
    fx_single_edd=Decimal("50000"),
    fx_daily_alert=Decimal("200000"),
)


_THRESHOLD_MAP: dict[str, AMLThresholdSet] = {
    "INDIVIDUAL": INDIVIDUAL_THRESHOLDS,
    "COMPANY": COMPANY_THRESHOLDS,
}


def get_thresholds(entity_type: str) -> AMLThresholdSet:
    """
    Return threshold set for entity type.
    Defaults to INDIVIDUAL (conservative) if entity_type is unknown.
    """
    return _THRESHOLD_MAP.get(entity_type, INDIVIDUAL_THRESHOLDS)
