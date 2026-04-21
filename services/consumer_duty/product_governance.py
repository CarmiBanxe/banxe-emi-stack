"""
services/consumer_duty/product_governance.py
Consumer Duty Product Governance
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9, FCA PROD (Product & Market Intervention Power)
Trust Zone: AMBER

record_product_assessment — records assessment; below threshold → RESTRICT + HITLProposal (I-27).
get_failing_products — list RESTRICT/WITHDRAW products.
propose_product_withdrawal — always HITLProposal (I-27: L4).
Append-only (I-24). SHA-256 IDs. I-01: Decimal for fair_value_score.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import logging

from services.consumer_duty.models_v2 import (
    HITLProposal,
    InMemoryProductGovernance,
    InterventionType,
    ProductGovernancePort,
    ProductGovernanceRecord,
)

logger = logging.getLogger(__name__)

# I-01: Fair value threshold is Decimal
FAIR_VALUE_THRESHOLD = Decimal("0.6")


def _make_record_id(product_id: str, ts: str) -> str:
    """Generate SHA-256-based record ID."""
    raw = f"{product_id}:{ts}"
    return f"pgr_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


class ProductGovernanceService:
    """Product governance service (FCA PROD).

    Protocol DI: ProductGovernancePort.
    I-01: All scores use Decimal.
    I-24: Append-only governance store.
    I-27: Restriction and withdrawal always return HITLProposal.
    """

    def __init__(self, governance_store: ProductGovernancePort | None = None) -> None:
        """Initialise with injectable governance store (default: InMemory stub)."""
        self._store: ProductGovernancePort = governance_store or InMemoryProductGovernance()

    def record_product_assessment(
        self,
        product_id: str,
        product_name: str,
        target_market: str,
        fair_value_score: Decimal,
        evidence: str = "",
    ) -> ProductGovernanceRecord | HITLProposal:
        """Record a product fair value assessment.

        fair_value_score < FAIR_VALUE_THRESHOLD (0.6) → RESTRICT + HITLProposal (I-27).
        Otherwise → MONITOR.
        Append-only (I-24).

        Args:
            product_id: Product identifier.
            product_name: Product display name.
            target_market: Target market description.
            fair_value_score: Fair value score as Decimal 0.0–1.0 (I-01).
            evidence: Supporting evidence string.

        Returns:
            ProductGovernanceRecord for MONITOR, or HITLProposal for RESTRICT.
        """
        ts = datetime.now(UTC).isoformat()
        record_id = _make_record_id(product_id, ts)

        if fair_value_score < FAIR_VALUE_THRESHOLD:
            intervention_type = InterventionType.RESTRICT
        else:
            intervention_type = InterventionType.MONITOR

        record = ProductGovernanceRecord(
            record_id=record_id,
            product_id=product_id,
            product_name=product_name,
            target_market=target_market,
            fair_value_score=fair_value_score,
            last_review_at=ts,
            intervention_type=intervention_type,
        )
        self._store.append(record)  # I-24

        if fair_value_score < FAIR_VALUE_THRESHOLD:
            logger.warning(
                "Product fair value BELOW threshold product_id=%s score=%s < %s — HITL (I-27)",
                product_id,
                fair_value_score,
                FAIR_VALUE_THRESHOLD,
            )
            return HITLProposal(
                action="RESTRICT_PRODUCT",
                entity_id=product_id,
                requires_approval_from="CONSUMER_DUTY_OFFICER",
                reason=(
                    f"Product fair value score {fair_value_score} < threshold {FAIR_VALUE_THRESHOLD} "
                    f"— RESTRICT intervention required (I-27, FCA PROD): product_id={product_id}"
                ),
            )

        logger.info(
            "Product assessment recorded product_id=%s score=%s intervention=%s",
            product_id,
            fair_value_score,
            intervention_type,
        )
        return record

    def get_failing_products(self) -> list[ProductGovernanceRecord]:
        """Get all products with RESTRICT or WITHDRAW intervention.

        Returns:
            List of ProductGovernanceRecord with failing interventions.
        """
        return self._store.list_failing()

    def propose_product_withdrawal(
        self, product_id: str, reason: str, operator: str
    ) -> HITLProposal:
        """Propose product withdrawal — always HITLProposal (I-27: L4).

        Product withdrawal is a significant regulated action under FCA PROD.

        Args:
            product_id: Product to withdraw.
            reason: Withdrawal reason.
            operator: Requesting operator.

        Returns:
            HITLProposal requiring CONSUMER_DUTY_OFFICER approval.
        """
        logger.warning(
            "Product withdrawal proposed product_id=%s operator=%s — HITL required (I-27)",
            product_id,
            operator,
        )
        return HITLProposal(
            action="WITHDRAW_PRODUCT",
            entity_id=product_id,
            requires_approval_from="CONSUMER_DUTY_OFFICER",
            reason=(
                f"Product withdrawal is L4 HITL action (I-27, FCA PROD): "
                f"product_id={product_id} reason={reason} operator={operator}"
            ),
        )

    def get_product_governance_summary(self) -> dict[str, object]:
        """Get product governance summary.

        Returns:
            Dict with total, monitor_count, restrict_count, withdraw_count.
        """
        all_records = self._store.list_failing()

        # Get all via list_all if supported
        if hasattr(self._store, "list_all"):
            all_records_full = self._store.list_all()  # type: ignore[attr-defined]
        else:
            all_records_full = all_records

        summary: dict[str, object] = {
            "total_products": len(all_records_full),
            "monitor_count": sum(
                1 for r in all_records_full if r.intervention_type == InterventionType.MONITOR
            ),
            "restrict_count": sum(
                1 for r in all_records_full if r.intervention_type == InterventionType.RESTRICT
            ),
            "withdraw_count": sum(
                1 for r in all_records_full if r.intervention_type == InterventionType.WITHDRAW
            ),
            "fair_value_threshold": str(FAIR_VALUE_THRESHOLD),
        }
        return summary
