"""
tx_monitor.py — Transaction Monitor (Dual-Entity AML Rules)
MLR 2017 | POCA 2002 s.330 | FCA SYSC 6.3 | Banxe I-04/I-06
Geniusto v5 — dual entity monitoring

WHY THIS FILE EXISTS
--------------------
FCA SYSC 6.3 requires an automated transaction monitoring layer that flags:
  1. Transactions requiring EDD (Enhanced Due Diligence) per MLR 2017 Reg.28
  2. Velocity breaches (unusual daily/monthly volumes)
  3. Structuring signals (POCA 2002 s.330 — deliberate sub-threshold splitting)
  4. SAR considerations (Suspicious Activity Reports — POCA 2002 s.330)

Key insight from Geniusto v5: Individual and Corporate customers have DIFFERENT
risk profiles. Using individual thresholds for corporate clients creates a flood
of false-positive HOLD decisions that violate FCA COBS 4.2 (treating customers
fairly). This monitor applies entity-type-aware rules via AMLThresholdSet.

Architecture:
  - TxMonitorService.evaluate() is called BEFORE payment submission
  - Uses InMemoryVelocityTracker for dev/tests; RedisVelocityTracker for prod
  - Returns MonitorResult with actionable flags (edd_required, sar_required, etc.)
  - All events logged for FCA audit trail (SYSC 6.3 record-keeping)

Integration points:
  - Called from payment_service.py after fraud score, before rail submission
  - MonitorResult feeds into HITL gate (MEDIUM/HIGH risk → manual review)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Protocol

from services.aml.aml_thresholds import get_thresholds

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


logger = logging.getLogger(__name__)


# ── Monitor request / result ───────────────────────────────────────────────────


@dataclass(frozen=True)
class TxMonitorRequest:
    """Single transaction submitted for AML monitoring."""

    transaction_id: str
    customer_id: str
    entity_type: str  # "INDIVIDUAL" | "COMPANY"
    amount: Decimal  # GBP-equivalent amount
    currency: str
    is_pep: bool = False
    is_sanctions_hit: bool = False
    is_fx: bool = False  # True for currency exchange transactions


@dataclass
class MonitorResult:
    """
    AML monitoring decision for one transaction.

    Flags are non-exclusive — a single transaction can trigger multiple.
    Action priority: sanctions_block > sar_required > edd_required > velocity_alert.
    """

    transaction_id: str
    customer_id: str
    entity_type: str
    amount: Decimal
    thresholds_applied: str  # "INDIVIDUAL" or "COMPANY"

    # ── Decision flags ──────────────────────────────────────────────────────
    sanctions_block: bool = False  # Hard block — I-06 invariant
    edd_required: bool = False  # EDD before proceeding (MLR 2017 Reg.28)
    velocity_daily_breach: bool = False  # Daily velocity alert
    velocity_monthly_breach: bool = False
    structuring_signal: bool = False  # Potential structuring (POCA 2002 s.330)
    sar_required: bool = False  # SAR consideration required (MLRO to review)

    reasons: list[str] = field(default_factory=list)
    evaluated_at: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def requires_hitl(self) -> bool:
        """True if any flag requires human review."""
        return (
            self.sanctions_block
            or self.sar_required
            or self.structuring_signal
            or self.edd_required
            or self.velocity_daily_breach
        )

    @property
    def should_block(self) -> bool:
        """Hard block (sanctions) — payment must not proceed."""
        return self.sanctions_block


# ── Velocity tracker protocol + implementations ───────────────────────────────


@dataclass
class _TxRecord:
    amount: Decimal
    timestamp: datetime


class VelocityTrackerPort(Protocol):
    def record(self, customer_id: str, amount: Decimal) -> None: ...
    def get_daily(self, customer_id: str) -> tuple[Decimal, int]: ...
    def get_monthly(self, customer_id: str) -> tuple[Decimal, int]: ...
    def get_recent_window(self, customer_id: str, hours: int) -> tuple[Decimal, int]: ...


class InMemoryVelocityTracker:
    """
    In-memory velocity tracker. For tests and dev.
    Uses UTC timestamps — TTL cleanup on read.

    In production: replace with RedisVelocityTracker
    (Redis sorted sets, TTL per key, cluster-safe).
    """

    def __init__(self) -> None:
        self._records: dict[str, list[_TxRecord]] = {}

    def record(self, customer_id: str, amount: Decimal) -> None:
        self._records.setdefault(customer_id, []).append(
            _TxRecord(amount=amount, timestamp=datetime.now(UTC))
        )

    def _recent(self, customer_id: str, since: datetime) -> list[_TxRecord]:
        return [r for r in self._records.get(customer_id, []) if r.timestamp >= since]

    def get_daily(self, customer_id: str) -> tuple[Decimal, int]:
        since = datetime.now(UTC) - timedelta(days=1)
        records = self._recent(customer_id, since)
        return sum(r.amount for r in records), len(records)

    def get_monthly(self, customer_id: str) -> tuple[Decimal, int]:
        since = datetime.now(UTC) - timedelta(days=30)
        records = self._recent(customer_id, since)
        return sum(r.amount for r in records), len(records)

    def get_recent_window(self, customer_id: str, hours: int) -> tuple[Decimal, int]:
        since = datetime.now(UTC) - timedelta(hours=hours)
        records = self._recent(customer_id, since)
        return sum(r.amount for r in records), len(records)

    def reset(self, customer_id: str) -> None:
        """Test helper: clear velocity for a customer."""
        self._records.pop(customer_id, None)


# ── Transaction monitor service ────────────────────────────────────────────────


class TxMonitorService:
    """
    AML Transaction Monitor — dual-entity rule engine.

    Evaluates one transaction against AML thresholds appropriate for
    the customer's entity type (INDIVIDUAL vs COMPANY).

    Usage:
        tracker = InMemoryVelocityTracker()
        monitor = TxMonitorService(tracker)

        result = monitor.evaluate(TxMonitorRequest(
            transaction_id="tx-001",
            customer_id="cust-001",
            entity_type="INDIVIDUAL",
            amount=Decimal("15000"),
            currency="GBP",
        ))
        if result.edd_required:
            trigger_edd_flow(result.customer_id)
        if result.sar_required:
            notify_mlro(result)
    """

    def __init__(self, velocity_tracker: VelocityTrackerPort | None = None) -> None:
        self._tracker: VelocityTrackerPort = velocity_tracker or InMemoryVelocityTracker()

    def evaluate(self, req: TxMonitorRequest) -> MonitorResult:
        """
        Evaluate a transaction against AML thresholds.
        Does NOT record the transaction — call record() after payment succeeds.
        """
        thresholds = get_thresholds(req.entity_type)
        result = MonitorResult(
            transaction_id=req.transaction_id,
            customer_id=req.customer_id,
            entity_type=req.entity_type,
            amount=req.amount,
            thresholds_applied=thresholds.entity_type,
        )

        # ── 1. Sanctions hard-block (I-06) ──────────────────────────────────
        if req.is_sanctions_hit:
            result.sanctions_block = True
            result.reasons.append("Customer has active sanctions hit (I-06 HARD_BLOCK)")
            logger.warning(
                "AML SANCTIONS_BLOCK: tx=%s customer=%s amount=%s",
                req.transaction_id,
                req.customer_id,
                req.amount,
            )
            return result  # No further checks — hard block

        # ── 2. EDD threshold (MLR 2017 Reg.28) ──────────────────────────────
        edd_threshold = thresholds.edd_for_pep() if req.is_pep else thresholds.edd_trigger
        if req.is_fx:
            edd_threshold = min(edd_threshold, thresholds.fx_single_edd)

        if req.amount >= edd_threshold:
            result.edd_required = True
            result.reasons.append(
                f"Amount £{req.amount:,.2f} ≥ EDD threshold £{edd_threshold:,.2f}"
                + (" (PEP reduced threshold)" if req.is_pep else "")
                + f" [{req.entity_type}]"
            )

        # ── 3. Velocity checks ───────────────────────────────────────────────
        daily_total, daily_count = self._tracker.get_daily(req.customer_id)
        monthly_total, monthly_count = self._tracker.get_monthly(req.customer_id)

        if thresholds.is_velocity_daily_breach(daily_total + req.amount, daily_count + 1):
            result.velocity_daily_breach = True
            result.reasons.append(
                f"Daily velocity breach: £{daily_total + req.amount:,.2f} / "
                f"{daily_count + 1} txs"
                f" (limits: £{thresholds.velocity_daily_amount:,.2f} / "
                f"{thresholds.velocity_daily_count} [{req.entity_type}])"
            )

        if thresholds.is_velocity_monthly_breach(monthly_total + req.amount, monthly_count + 1):
            result.velocity_monthly_breach = True
            result.reasons.append(
                f"Monthly velocity breach: £{monthly_total + req.amount:,.2f} / "
                f"{monthly_count + 1} txs [{req.entity_type}]"
            )

        # ── 4. Structuring detection (POCA 2002 s.330) ──────────────────────
        window_total, window_count = self._tracker.get_recent_window(req.customer_id, hours=24)
        if thresholds.is_structuring_signal(window_count + 1, window_total + req.amount):
            # Only flag structuring if individual txs are BELOW edd_trigger
            # (structuring = intentionally splitting to avoid EDD)
            if req.amount < thresholds.edd_trigger:
                result.structuring_signal = True
                result.reasons.append(
                    f"Potential structuring: {window_count + 1} txs totalling "
                    f"£{window_total + req.amount:,.2f} in 24h "
                    f"(threshold: {thresholds.structuring_window_count} txs / "
                    f"£{thresholds.structuring_window_gbp:,.2f} [{req.entity_type}])"
                )

        # ── 5. SAR consideration (POCA 2002) ─────────────────────────────────
        if thresholds.requires_sar_consideration(req.amount):
            result.sar_required = True
            result.reasons.append(
                f"SAR consideration: amount £{req.amount:,.2f} ≥ "
                f"auto-SAR threshold £{thresholds.sar_auto_single:,.2f} [{req.entity_type}]"
            )
        elif (
            not thresholds.requires_sar_consideration(req.amount)  # not already SAR-flagged
            and thresholds.is_velocity_daily_breach(daily_total + req.amount, daily_count)
            and (daily_total + req.amount) >= thresholds.sar_auto_daily
        ):
            result.sar_required = True
            result.reasons.append(
                f"SAR consideration: daily total £{daily_total + req.amount:,.2f} ≥ "
                f"daily SAR threshold £{thresholds.sar_auto_daily:,.2f} [{req.entity_type}]"
            )

        if result.requires_hitl:
            logger.info(
                "AML MONITOR: tx=%s customer=%s entity=%s amount=£%s flags=%s",
                req.transaction_id,
                req.customer_id,
                req.entity_type,
                req.amount,
                [
                    r
                    for r, v in [
                        ("EDD", result.edd_required),
                        ("VELOCITY_D", result.velocity_daily_breach),
                        ("VELOCITY_M", result.velocity_monthly_breach),
                        ("STRUCTURING", result.structuring_signal),
                        ("SAR", result.sar_required),
                    ]
                    if v
                ],
            )

        return result

    def record(self, customer_id: str, amount: Decimal) -> None:
        """
        Record a completed transaction in the velocity tracker.
        Call AFTER payment succeeds (not before evaluate()).
        """
        self._tracker.record(customer_id, amount)
