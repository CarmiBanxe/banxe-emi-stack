"""
services/crypto_custody/crypto_agent.py — HITL Agent for Crypto Custody
IL-CDC-01 | Phase 35 | banxe-emi-stack
I-27: HITL — AI PROPOSES, human DECIDES. Never autonomous.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

_HITL_THRESHOLD = Decimal("1000")
_BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
_FATF_GREYLIST = {
    "BF",
    "CM",
    "CD",
    "HT",
    "JM",
    "ML",
    "MZ",
    "NG",
    "PA",
    "PH",
    "SN",
    "SS",
    "SY",
    "TZ",
    "UG",
    "YE",
    "ZA",
}


@dataclass
class HITLProposal:
    action: str
    resource_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


class CryptoAgent:
    """L2/L4 orchestration agent for crypto custody decisions (I-27)."""

    def process_transfer_request(
        self, transfer_id: str, amount: Decimal
    ) -> HITLProposal | dict[str, str]:
        """Returns HITLProposal if amount >= £1000 (I-27), else auto-processes."""
        if amount >= _HITL_THRESHOLD:
            return HITLProposal(
                action="EXECUTE_TRANSFER",
                resource_id=transfer_id,
                requires_approval_from="Compliance Officer",
                reason=f"Transfer amount {amount} >= £1000 threshold (I-27 FATF R.16)",
                autonomy_level="L4",
            )
        return {
            "transfer_id": transfer_id,
            "status": "AUTO_APPROVED",
            "autonomy_level": "L2",
            "amount": str(amount),
        }

    def process_archive_request(self, wallet_id: str) -> HITLProposal:
        """Archive always requires HITL L4 (I-27)."""
        return HITLProposal(
            action="ARCHIVE_WALLET",
            resource_id=wallet_id,
            requires_approval_from="Compliance Officer",
            reason="Wallet archival requires human authorisation (I-27)",
            autonomy_level="L4",
        )

    def process_travel_rule(
        self, transfer_id: str, amount_eur: Decimal, jurisdiction: str
    ) -> dict[str, str]:
        """Auto-screens jurisdiction (I-02), flags EDD if FATF greylist (I-03)."""
        jur = jurisdiction.upper()
        if jur in _BLOCKED_JURISDICTIONS:
            return {
                "transfer_id": transfer_id,
                "jurisdiction": jur,
                "decision": "BLOCKED",
                "reason": f"Jurisdiction {jur} is blocked (I-02)",
                "travel_rule_required": str(amount_eur >= Decimal("1000")),
            }
        edd_required = jur in _FATF_GREYLIST
        travel_rule = amount_eur >= Decimal("1000")
        return {
            "transfer_id": transfer_id,
            "jurisdiction": jur,
            "decision": "EDD_REQUIRED" if edd_required else "PASS",
            "travel_rule_required": str(travel_rule),
            "amount_eur": str(amount_eur),
        }

    def get_agent_status(self) -> dict[str, str]:
        return {
            "agent": "CryptoAgent",
            "il_ref": "IL-CDC-01",
            "autonomy_level_default": "L4",
            "hitl_threshold": str(_HITL_THRESHOLD),
            "status": "ACTIVE",
        }
