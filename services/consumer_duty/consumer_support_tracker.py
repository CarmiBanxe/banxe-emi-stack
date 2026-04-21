"""
services/consumer_duty/consumer_support_tracker.py
Consumer Support Interaction Tracker
IL-CDO-01 | Phase 50 | Sprint 35

FCA: PS22/9 §8 (Consumer Support outcome), FCA COBS 2.1
Trust Zone: AMBER

record_interaction — records customer support interaction (I-24 append).
record_resolution — records resolution time and outcome.
get_sla_breach_rate — calculates breach rate (Decimal, I-01).
Append-only (I-24). SHA-256 IDs. UTC timestamps.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
import hashlib
import logging

logger = logging.getLogger(__name__)

# SLA targets in seconds
SLA_TARGETS: dict[str, int] = {
    "complaint": 8 * 24 * 3600,  # 8 business days
    "support": 2 * 3600,  # 2 hours
}


def _make_interaction_id(customer_id: str, interaction_type: str, ts: str) -> str:
    """Generate SHA-256-based interaction ID."""
    raw = f"{customer_id}:{interaction_type}:{ts}"
    return f"int_{hashlib.sha256(raw.encode()).hexdigest()[:8]}"


@dataclass
class SupportInteraction:
    """Support interaction record (append-only, I-24)."""

    interaction_id: str
    customer_id: str
    interaction_type: str
    channel: str
    created_at: str
    resolved_in_seconds: int | None = None
    outcome: str | None = None


class ConsumerSupportTracker:
    """Consumer support SLA tracker.

    I-24: Append-only interaction store.
    I-01: SLA breach rates returned as Decimal.
    """

    def __init__(self) -> None:
        """Initialise empty interaction store."""
        self._interactions: list[SupportInteraction] = []

    def record_interaction(self, customer_id: str, interaction_type: str, channel: str) -> str:
        """Record a new support interaction (I-24 append).

        Args:
            customer_id: Customer identifier.
            interaction_type: Type ('complaint', 'support', etc.).
            channel: Channel ('phone', 'email', 'chat', 'app').

        Returns:
            interaction_id (SHA-256-based).
        """
        ts = datetime.now(UTC).isoformat()
        interaction_id = _make_interaction_id(customer_id, interaction_type, ts)

        interaction = SupportInteraction(
            interaction_id=interaction_id,
            customer_id=customer_id,
            interaction_type=interaction_type,
            channel=channel,
            created_at=ts,
        )
        self._interactions.append(interaction)  # I-24
        logger.info(
            "Support interaction recorded id=%s customer=%s type=%s channel=%s",
            interaction_id,
            customer_id,
            interaction_type,
            channel,
        )
        return interaction_id

    def record_resolution(
        self, interaction_id: str, resolved_in_seconds: int, outcome: str
    ) -> None:
        """Record resolution for an interaction (I-24: appends new resolved version).

        Args:
            interaction_id: Interaction to resolve.
            resolved_in_seconds: Time to resolution in seconds.
            outcome: Resolution outcome description.
        """
        # Find the interaction
        target = next((i for i in self._interactions if i.interaction_id == interaction_id), None)
        if target is None:
            raise ValueError(f"Interaction '{interaction_id}' not found")

        # Append resolved version (I-24 — append new record, not update)
        resolved = SupportInteraction(
            interaction_id=target.interaction_id,
            customer_id=target.customer_id,
            interaction_type=target.interaction_type,
            channel=target.channel,
            created_at=target.created_at,
            resolved_in_seconds=resolved_in_seconds,
            outcome=outcome,
        )
        self._interactions.append(resolved)  # I-24
        logger.info(
            "Interaction resolved id=%s seconds=%d outcome=%s",
            interaction_id,
            resolved_in_seconds,
            outcome,
        )

    def get_sla_breach_rate(self, interaction_type: str) -> Decimal:
        """Calculate SLA breach rate for an interaction type (I-01: Decimal).

        Args:
            interaction_type: Type to calculate breach rate for.

        Returns:
            Breach rate as Decimal 0.0–1.0 (I-01). 0.0 if no resolved interactions.
        """
        sla_target = SLA_TARGETS.get(interaction_type, 2 * 3600)

        # Get latest version per interaction_id
        seen: dict[str, SupportInteraction] = {}
        for i in self._interactions:
            if i.interaction_type == interaction_type:
                seen[i.interaction_id] = i

        resolved = [i for i in seen.values() if i.resolved_in_seconds is not None]
        if not resolved:
            return Decimal("0.0")

        breached = sum(
            1
            for i in resolved
            if i.resolved_in_seconds is not None and i.resolved_in_seconds > sla_target
        )

        rate = Decimal(str(breached)) / Decimal(str(len(resolved)))
        return rate

    def get_support_outcomes_summary(self) -> dict[str, object]:
        """Get support outcomes summary.

        Returns:
            Dict with interaction counts, resolution rates, SLA breach rates.
        """
        # Get latest version per interaction_id
        seen: dict[str, SupportInteraction] = {}
        for i in self._interactions:
            seen[i.interaction_id] = i

        all_interactions = list(seen.values())
        resolved = [i for i in all_interactions if i.resolved_in_seconds is not None]

        complaint_breach_rate = self.get_sla_breach_rate("complaint")
        support_breach_rate = self.get_sla_breach_rate("support")

        return {
            "total_interactions": len(all_interactions),
            "resolved_count": len(resolved),
            "pending_count": len(all_interactions) - len(resolved),
            "complaint_sla_breach_rate": str(complaint_breach_rate),
            "support_sla_breach_rate": str(support_breach_rate),
            "sla_targets_seconds": SLA_TARGETS,
        }
