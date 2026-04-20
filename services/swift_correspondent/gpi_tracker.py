"""
services/swift_correspondent/gpi_tracker.py
SWIFT gpi Tracker
IL-SWF-01 | Sprint 34 | Phase 47

FCA: SWIFT gpi SRD, FCA SUP 15.8
Trust Zone: RED

UUID4 UETR generation. ACSP/ACCC/RJCT status tracking.
UTC timestamps (I-23). Webhook registration stub.
"""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import logging
import uuid

from services.swift_correspondent.models import (
    GPIStatus,
    InMemoryMessageStore,
    MessageStatus,
    MessageStore,
    SWIFTMessage,
)

logger = logging.getLogger(__name__)


class SWIFTGPITracker:
    """SWIFT gpi transaction tracker.

    Tracks UETR-based gpi status per SWIFT gpi SRD.
    All timestamps UTC (I-23). Simulated status for sandbox.
    """

    def __init__(self, store: MessageStore | None = None) -> None:
        """Initialise tracker with optional message store."""
        self._store: MessageStore = store or InMemoryMessageStore()
        self._gpi_statuses: dict[str, GPIStatus] = {}
        self._webhooks: dict[str, str] = {}

    def generate_uetr(self) -> str:
        """Generate a UUID4 UETR per SWIFT gpi SRD.

        Returns:
            UUID4-format UETR string.
        """
        return str(uuid.uuid4())

    def attach_uetr(self, message_id: str, uetr: str) -> SWIFTMessage:
        """Attach a UETR to an existing SWIFT message.

        Args:
            message_id: ID of the SWIFT message.
            uetr: UUID4 UETR to attach.

        Returns:
            Updated SWIFTMessage with UETR attached.

        Raises:
            ValueError: If message not found.
        """
        msg = self._store.get(message_id)
        if msg is None:
            raise ValueError(f"Message {message_id} not found")
        updated = msg.model_copy(update={"uetr": uetr})
        self._store.save(updated)
        logger.info("Attached UETR %s to message_id=%s", uetr, message_id)
        return updated

    def get_gpi_status(self, uetr: str) -> GPIStatus:
        """Get gpi status for a UETR.

        Stub: returns simulated status based on UETR hash.
        I-23: UTC timestamps.

        Args:
            uetr: UUID4 UETR.

        Returns:
            GPIStatus with simulated status.
        """
        if uetr in self._gpi_statuses:
            return self._gpi_statuses[uetr]

        digest = int(hashlib.sha256(uetr.encode()).hexdigest()[:2], 16)
        statuses = [MessageStatus.ACSP, MessageStatus.ACCC, MessageStatus.RJCT]
        simulated = statuses[digest % len(statuses)]

        status = GPIStatus(
            uetr=uetr,
            status=simulated,
            last_updated=datetime.now(UTC).isoformat(),
            tracker_url=f"https://tracker.swift.com/gpi/{uetr}",
        )
        self._gpi_statuses[uetr] = status
        return status

    def update_status(self, uetr: str, new_status: MessageStatus, actor: str) -> GPIStatus:
        """Update gpi status for a UETR.

        I-23: last_updated = UTC now.

        Args:
            uetr: UUID4 UETR.
            new_status: New MessageStatus to set.
            actor: Actor performing the update.

        Returns:
            Updated GPIStatus.
        """
        now = datetime.now(UTC).isoformat()
        existing = self._gpi_statuses.get(uetr)
        completion_time = now if new_status == MessageStatus.ACCC else None

        status = GPIStatus(
            uetr=uetr,
            status=new_status,
            last_updated=now,
            tracker_url=f"https://tracker.swift.com/gpi/{uetr}",
            completion_time=completion_time or (existing.completion_time if existing else None),
        )
        self._gpi_statuses[uetr] = status
        logger.info("Updated gpi status uetr=%s status=%s actor=%s", uetr, new_status, actor)
        return status

    def register_webhook_callback(self, uetr: str, callback_url: str) -> dict[str, object]:
        """Register a webhook callback for gpi status updates.

        Stub implementation — logs registration.

        Args:
            uetr: UUID4 UETR to watch.
            callback_url: URL to POST status updates to.

        Returns:
            Dict confirming registration.
        """
        self._webhooks[uetr] = callback_url
        logger.info("Registered webhook uetr=%s callback_url=%s", uetr, callback_url)
        return {"registered": True, "uetr": uetr, "callback_url": callback_url}

    def get_pending_transactions(self) -> list[GPIStatus]:
        """Get all transactions in ACSP (settlement in process) status.

        Returns:
            List of GPIStatus with ACSP status.
        """
        return [s for s in self._gpi_statuses.values() if s.status == MessageStatus.ACSP]

    def get_tracker_summary(self) -> dict[str, object]:
        """Get summary of tracked gpi transactions.

        Returns:
            Dict with total and by_status counts.
        """
        by_status: dict[str, int] = {}
        for status in self._gpi_statuses.values():
            by_status[status.status] = by_status.get(status.status, 0) + 1
        return {
            "total": len(self._gpi_statuses),
            "by_status": by_status,
        }
