"""
services/crypto_custody/travel_rule_engine.py — FATF R.16 Travel Rule compliance
IL-CDC-01 | Phase 35 | banxe-emi-stack
I-02: Blocked jurisdictions. I-03: FATF greylist EDD.
"""

from __future__ import annotations

from decimal import Decimal

from services.crypto_custody.models import (
    AuditPort,
    InMemoryAuditStore,
    TravelRuleData,
)

TRAVEL_RULE_THRESHOLD_EUR = Decimal("1000")

BLOCKED_JURISDICTIONS: frozenset[str] = frozenset(
    {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
)

_FATF_GREYLIST: frozenset[str] = frozenset(
    {"BF", "CM", "CD", "HT", "JM", "ML", "MZ", "NG", "PA", "PH", "SN", "SS", "TZ", "UG", "YE"}
)


class TravelRuleEngine:
    """FATF R.16 travel rule enforcement."""

    def __init__(self, audit_port: AuditPort | None = None) -> None:
        self._audit: AuditPort = audit_port or InMemoryAuditStore()
        self._travel_rule_data: dict[str, TravelRuleData] = {}

    def requires_travel_rule(self, amount_eur: Decimal) -> bool:
        """True if amount >= EUR 1000 (FATF R.16)."""
        return amount_eur >= TRAVEL_RULE_THRESHOLD_EUR

    def screen_jurisdiction(self, jurisdiction: str) -> str:
        """Returns PASS | BLOCKED | EDD_REQUIRED (I-02 + I-03)."""
        jur = jurisdiction.upper()
        if jur in BLOCKED_JURISDICTIONS:
            return "BLOCKED"
        if jur in _FATF_GREYLIST:
            return "EDD_REQUIRED"
        return "PASS"

    def attach_originator_data(self, transfer_id: str, data: TravelRuleData) -> None:
        """Attach travel rule originator data to transfer."""
        self._travel_rule_data[transfer_id] = data
        self._audit.log(
            "ATTACH_TRAVEL_RULE",
            transfer_id,
            f"originator={data.originator_name}",
            "OK",
        )

    def get_travel_rule_data(self, transfer_id: str) -> TravelRuleData | None:
        return self._travel_rule_data.get(transfer_id)

    def validate_travel_rule_complete(self, transfer_id: str) -> bool:
        """True if all required travel rule data is present."""
        data = self._travel_rule_data.get(transfer_id)
        if data is None:
            return False
        return all(
            [
                bool(data.originator_name),
                bool(data.originator_iban),
                bool(data.originator_address),
                bool(data.beneficiary_name),
                bool(data.beneficiary_vasp),
            ]
        )
