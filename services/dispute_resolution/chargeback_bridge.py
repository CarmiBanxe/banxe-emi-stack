"""
services/dispute_resolution/chargeback_bridge.py — Visa/MC chargeback scheme adapter
IL-DRM-01 | Phase 33 | banxe-emi-stack
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime
from decimal import Decimal
import uuid

from services.dispute_resolution.models import (
    ChargebackPort,
    ChargebackRecord,
    InMemoryChargebackStore,
)

_VALID_SCHEMES = {"VISA", "MASTERCARD"}


class ChargebackBridge:
    def __init__(self, store: ChargebackPort | None = None) -> None:
        self._store = store or InMemoryChargebackStore()

    def initiate_chargeback(
        self,
        dispute_id: str,
        scheme: str,
        amount: Decimal,
        reason_code: str,
    ) -> dict[str, str]:
        if scheme not in _VALID_SCHEMES:
            raise ValueError(f"Unknown scheme: {scheme}. Must be one of {_VALID_SCHEMES}")
        if amount <= Decimal("0"):
            raise ValueError("Chargeback amount must be positive (I-01)")
        record = ChargebackRecord(
            chargeback_id=str(uuid.uuid4()),
            dispute_id=dispute_id,
            scheme=scheme,
            amount=amount,
            reason_code=reason_code,
            initiated_at=datetime.now(UTC),
        )
        self._store.save(record)
        return {
            "chargeback_id": record.chargeback_id,
            "dispute_id": dispute_id,
            "scheme": scheme,
            "amount": str(amount),
            "status": "INITIATED",
        }

    def submit_representment(
        self,
        chargeback_id: str,
        evidence_hashes: list[str],
    ) -> dict[str, object]:
        record = self._store.get(chargeback_id)
        if record is None:
            raise ValueError(f"Chargeback {chargeback_id} not found")
        updated = dataclasses.replace(record, status="REPRESENTMENT_SUBMITTED")
        self._store.save(updated)
        return {
            "chargeback_id": chargeback_id,
            "status": "REPRESENTMENT_SUBMITTED",
            "evidence_count": len(evidence_hashes),
        }

    def get_chargeback_status(self, chargeback_id: str) -> dict[str, str]:
        record = self._store.get(chargeback_id)
        if record is None:
            raise ValueError(f"Chargeback {chargeback_id} not found")
        return {
            "chargeback_id": chargeback_id,
            "dispute_id": record.dispute_id,
            "scheme": record.scheme,
            "amount": str(record.amount),
            "status": record.status,
        }

    def list_chargebacks_for_dispute(self, dispute_id: str) -> dict[str, object]:
        records = self._store.list_by_dispute(dispute_id)
        return {
            "dispute_id": dispute_id,
            "count": len(records),
            "chargebacks": [
                {
                    "chargeback_id": r.chargeback_id,
                    "scheme": r.scheme,
                    "amount": str(r.amount),
                    "status": r.status,
                }
                for r in records
            ],
        }
