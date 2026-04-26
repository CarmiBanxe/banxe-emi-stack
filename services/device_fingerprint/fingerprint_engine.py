"""
services/device_fingerprint/fingerprint_engine.py
Device fingerprint collection and matching (IL-DFP-01).
I-01: risk scores as Decimal strings.
I-24: DeviceLog append-only.
I-27: suspicious devices and > 5 devices require FRAUD_ANALYST HITL.
Max 5 devices per customer.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
import hashlib
from typing import Protocol

from services.device_fingerprint.fingerprint_models import (
    DeviceProfile,
    FingerprintData,
    MatchResult,
)

MAX_DEVICES_PER_CUSTOMER = 5
SCORE_NEW_DEVICE = Decimal("0.3")
SCORE_KNOWN_DEVICE = Decimal("0.0")
SCORE_SUSPICIOUS = Decimal("0.8")


class DeviceStorePort(Protocol):
    def save(self, profile: DeviceProfile) -> None: ...
    def get_by_customer(self, customer_id: str) -> list[DeviceProfile]: ...
    def get_by_hash(self, fingerprint_hash: str) -> DeviceProfile | None: ...


class InMemoryDeviceStore:
    def __init__(self) -> None:
        self._profiles: list[DeviceProfile] = []  # I-24

    def save(self, profile: DeviceProfile) -> None:
        self._profiles.append(profile)

    def get_by_customer(self, customer_id: str) -> list[DeviceProfile]:
        return [p for p in self._profiles if p.customer_id == customer_id]

    def get_by_hash(self, fingerprint_hash: str) -> DeviceProfile | None:
        return next((p for p in self._profiles if p.fingerprint_hash == fingerprint_hash), None)


def _compute_hash(data: FingerprintData) -> str:
    raw = f"{data.user_agent}|{data.screen_resolution}|{data.timezone}|{data.language}|{data.canvas_hash}|{data.webgl_hash}"
    return hashlib.sha256(raw.encode()).hexdigest()


class FingerprintEngine:
    """Device fingerprint engine.

    I-01: all risk scores Decimal.
    I-24: DeviceLog append-only.
    Max 5 devices per customer → 6th triggers HITL proposal.
    """

    def __init__(self, store: DeviceStorePort | None = None) -> None:
        self._store: DeviceStorePort = store or InMemoryDeviceStore()
        self._device_log: list[dict] = []  # I-24 append-only

    def register_device(self, customer_id: str, data: FingerprintData) -> DeviceProfile:
        fhash = _compute_hash(data)
        did = f"dev_{hashlib.sha256(f'{customer_id}{fhash}'.encode()).hexdigest()[:8]}"
        profile = DeviceProfile(
            device_id=did,
            customer_id=customer_id,
            fingerprint_hash=fhash,
            user_agent=data.user_agent,
            registered_at=datetime.now(UTC).isoformat(),
        )
        self._store.save(profile)
        self._device_log.append(
            {
                "event": "device.registered",
                "device_id": did,
                "customer_id": customer_id,
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )
        return profile

    def match_device(self, customer_id: str, data: FingerprintData) -> MatchResult:
        fhash = _compute_hash(data)
        existing = self._store.get_by_hash(fhash)

        if existing and existing.customer_id == customer_id:
            # Known device for this customer
            match_type = "known"
            score = SCORE_KNOWN_DEVICE
            device_id = existing.device_id
        elif existing and existing.customer_id != customer_id:
            # Device known but for different customer — suspicious
            match_type = "suspicious"
            score = SCORE_SUSPICIOUS
            device_id = existing.device_id
        else:
            # New device
            customer_devices = self._store.get_by_customer(customer_id)
            if len(customer_devices) >= MAX_DEVICES_PER_CUSTOMER:
                match_type = "suspicious"
                score = SCORE_SUSPICIOUS
            else:
                match_type = "new"
                score = SCORE_NEW_DEVICE
            device_id = None

        self._device_log.append(
            {
                "event": "device.matched",
                "match_type": match_type,
                "customer_id": customer_id,
                "logged_at": datetime.now(UTC).isoformat(),
            }
        )

        return MatchResult(
            customer_id=customer_id,
            match_type=match_type,
            risk_score=str(score),
            device_id=device_id,
        )

    @property
    def device_log(self) -> list[dict]:
        """I-24: append-only."""
        return list(self._device_log)
