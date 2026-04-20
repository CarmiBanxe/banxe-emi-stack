"""
services/swift_correspondent/swift_agent.py
SWIFT Agent — HITL L4 Orchestration
IL-SWF-01 | Sprint 34 | Phase 47

FCA: PSR 2017, SWIFT gpi SRD
Trust Zone: RED

SEND/HOLD/REJECT always HITL L4 (I-11, I-27).
L1 auto for validation only. Requires TREASURY_OPS approval.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging

from services.swift_correspondent.message_builder import SWIFTMessageBuilder
from services.swift_correspondent.models import InMemoryMessageStore

logger = logging.getLogger(__name__)


@dataclass
class HITLProposal:
    """HITL L4 escalation proposal for SWIFT agent actions.

    Irreversible SWIFT operations (SEND/HOLD/REJECT) always
    require TREASURY_OPS human approval (I-11, I-27).
    """

    action: str
    message_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class SWIFTAgent:
    """SWIFT message lifecycle agent.

    L1 autonomy: validation only (no side effects).
    L4 HITL required for: SEND, HOLD, REJECT (I-11, I-27).
    All critical actions escalated to TREASURY_OPS.
    """

    def __init__(self, builder: SWIFTMessageBuilder | None = None) -> None:
        """Initialise agent with optional message builder."""
        self._builder = builder or SWIFTMessageBuilder(InMemoryMessageStore())
        self._pending_sends: list[str] = []
        self._pending_holds: list[str] = []
        self._pending_rejects: list[str] = []

    def process_send(self, message_id: str) -> HITLProposal:
        """Propose SWIFT message send (always L4 HITL, I-27).

        SEND is irreversible — always requires TREASURY_OPS approval.

        Args:
            message_id: Message to send.

        Returns:
            HITLProposal requiring TREASURY_OPS approval.
        """
        self._pending_sends.append(message_id)
        logger.warning("SEND proposed for message_id=%s — HITL L4 required (I-27)", message_id)
        return HITLProposal(
            action="SEND_MESSAGE",
            message_id=message_id,
            requires_approval_from="TREASURY_OPS",
            reason="SWIFT SEND is irreversible — requires TREASURY_OPS approval",
            autonomy_level="L4",
        )

    def process_hold(self, message_id: str, reason: str) -> HITLProposal:
        """Propose SWIFT message hold (always L4 HITL, I-27).

        Args:
            message_id: Message to hold.
            reason: Reason for hold.

        Returns:
            HITLProposal requiring TREASURY_OPS approval.
        """
        self._pending_holds.append(message_id)
        logger.warning(
            "HOLD proposed for message_id=%s reason=%s — HITL L4 (I-27)", message_id, reason
        )
        return HITLProposal(
            action="HOLD_MESSAGE",
            message_id=message_id,
            requires_approval_from="TREASURY_OPS",
            reason=f"Hold requested: {reason}",
            autonomy_level="L4",
        )

    def process_reject(self, message_id: str, reason: str) -> HITLProposal:
        """Propose SWIFT message rejection (always L4 HITL, I-27).

        REJECT is irreversible — always requires TREASURY_OPS approval.

        Args:
            message_id: Message to reject.
            reason: Reason for rejection.

        Returns:
            HITLProposal requiring TREASURY_OPS approval.
        """
        self._pending_rejects.append(message_id)
        logger.warning(
            "REJECT proposed for message_id=%s reason=%s — HITL L4 (I-27)", message_id, reason
        )
        return HITLProposal(
            action="REJECT_MESSAGE",
            message_id=message_id,
            requires_approval_from="TREASURY_OPS",
            reason=f"Rejection requested: {reason}",
            autonomy_level="L4",
        )

    def process_validation(self, message_id: str) -> dict[str, object]:
        """Validate a SWIFT message (L1 auto — no side effects).

        Validation is read-only — no HITL required.

        Args:
            message_id: Message to validate.

        Returns:
            Dict with is_valid, errors, and autonomy_level.
        """
        is_valid, errors = self._builder.validate_message(message_id)
        logger.info("Validation completed message_id=%s valid=%s", message_id, is_valid)
        return {
            "message_id": message_id,
            "is_valid": is_valid,
            "errors": errors,
            "autonomy_level": "L1",
        }

    def get_agent_status(self) -> dict[str, object]:
        """Get current agent status and pending action queues.

        Returns:
            Dict with pending action counts and autonomy level.
        """
        return {
            "pending_sends": len(self._pending_sends),
            "pending_holds": len(self._pending_holds),
            "pending_rejects": len(self._pending_rejects),
            "autonomy_level": "L4",
            "send_ids": self._pending_sends.copy(),
            "hold_ids": self._pending_holds.copy(),
            "reject_ids": self._pending_rejects.copy(),
        }
