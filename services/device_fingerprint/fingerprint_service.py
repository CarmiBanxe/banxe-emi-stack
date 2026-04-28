"""
services/device_fingerprint/fingerprint_service.py
FingerprintService — session binding + anomaly detection orchestrator (IL-FRAUD-01).

Combines FingerprintEngine (device matching) with AnomalyDetector and session binding.
I-01: Decimal risk scores.
I-02: Blocked jurisdictions → reject.
I-24: Immutable audit trail.
I-27: High-risk anomalies → HITL escalation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import hashlib
from typing import Protocol

from services.device_fingerprint.anomaly_detector import (
    AnomalyDetector,
    AnomalyResult,
    RiskLevel,
)
from services.device_fingerprint.fingerprint_engine import (
    FingerprintEngine,
    InMemoryDeviceStore,
)
from services.device_fingerprint.fingerprint_models import FingerprintData
from services.device_fingerprint.fingerprint_store import (
    InMemoryFingerprintStore,
    SessionBinding,
)

# ── Audit Port ───────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FingerprintAuditEntry:
    """Immutable audit entry (I-24). No raw PII — hashes only."""

    customer_id: str
    action: str
    device_id: str | None
    risk_level: str
    risk_score: str  # Decimal as string (I-01)
    geo_country: str
    ip_hash: str  # Hashed IP, no raw PII
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class FingerprintAuditPort(Protocol):
    """Port for recording fingerprint audit entries (I-24)."""

    def record(self, entry: FingerprintAuditEntry) -> None: ...


class InMemoryFingerprintAuditPort:
    """In-memory audit for tests."""

    def __init__(self) -> None:
        self._entries: list[FingerprintAuditEntry] = []

    def record(self, entry: FingerprintAuditEntry) -> None:
        self._entries.append(entry)

    @property
    def entries(self) -> list[FingerprintAuditEntry]:
        return list(self._entries)


# ── HITL Proposal ────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class FingerprintHITLProposal:
    """High-risk device anomaly requires fraud analyst review (I-27)."""

    customer_id: str
    device_id: str | None
    risk_level: str
    risk_score: str
    anomalies: tuple[str, ...]
    reason: str
    requires_approval_from: str = "FRAUD_ANALYST"


# ── Fingerprint Service ──────────────────────────────────────────────────────


class FingerprintService:
    """
    Orchestrates device fingerprinting, session binding, and anomaly detection.

    I-01: Decimal risk scores.
    I-02: Blocked jurisdictions rejected.
    I-24: All checks logged immutably, no raw PII.
    I-27: HIGH/CRITICAL risk → HITL proposal.
    """

    def __init__(
        self,
        engine: FingerprintEngine | None = None,
        store: InMemoryFingerprintStore | None = None,
        anomaly_detector: AnomalyDetector | None = None,
        audit: FingerprintAuditPort | None = None,
    ) -> None:
        self._engine = engine or FingerprintEngine(store=InMemoryDeviceStore())
        self._store = store or InMemoryFingerprintStore()
        self._anomaly = anomaly_detector or AnomalyDetector()
        self._audit: FingerprintAuditPort = audit or InMemoryFingerprintAuditPort()

    def check_device(
        self,
        customer_id: str,
        fingerprint_data: FingerprintData,
        session_id: str,
        ip_address: str,
        geo_country: str,
    ) -> AnomalyResult | FingerprintHITLProposal:
        """
        Check device fingerprint, bind session, detect anomalies.

        Returns AnomalyResult for LOW/MEDIUM risk.
        Returns FingerprintHITLProposal for HIGH/CRITICAL risk (I-27).
        Raises JurisdictionBlockedError for blocked countries (I-02).
        """
        # Hash IP — never store raw PII (I-24).
        ip_hash = hashlib.sha256(ip_address.encode()).hexdigest()[:16]

        # Match device via engine.
        match_result = self._engine.match_device(customer_id, fingerprint_data)
        is_known = match_result.match_type == "known"
        device_id = match_result.device_id

        # Register new device if not known.
        if not is_known and match_result.match_type == "new":
            profile = self._engine.register_device(customer_id, fingerprint_data)
            device_id = profile.device_id

        # Get previous sessions for anomaly detection.
        recent = self._store.get_recent_sessions(customer_id, limit=5)
        previous_sessions = [
            {"geo_country": b.geo_country, "timestamp": b.bound_at}
            for b in recent
        ]

        # Run anomaly detection (raises JurisdictionBlockedError for I-02).
        anomaly_result = self._anomaly.check(
            customer_id=customer_id,
            device_id=device_id,
            geo_country=geo_country,
            is_known_device=is_known,
            previous_sessions=previous_sessions,
        )

        # Bind session to device.
        binding = SessionBinding(
            session_id=session_id,
            device_id=device_id or "unknown",
            customer_id=customer_id,
            ip_address_hash=ip_hash,
            geo_country=geo_country.upper(),
        )
        self._store.save_session_binding(binding)

        # I-24: audit trail (no raw PII).
        self._record_audit(
            customer_id=customer_id,
            device_id=device_id,
            risk_level=anomaly_result.risk_level.value,
            risk_score=str(anomaly_result.risk_score),
            geo_country=geo_country.upper(),
            ip_hash=ip_hash,
            action="DEVICE_CHECK",
        )

        # I-27: HITL for HIGH/CRITICAL risk.
        if anomaly_result.risk_level in (RiskLevel.HIGH, RiskLevel.CRITICAL):
            return FingerprintHITLProposal(
                customer_id=customer_id,
                device_id=device_id,
                risk_level=anomaly_result.risk_level.value,
                risk_score=str(anomaly_result.risk_score),
                anomalies=anomaly_result.anomalies,
                reason=(
                    f"Device anomaly detected: {', '.join(anomaly_result.anomalies)}. "
                    f"Risk score {anomaly_result.risk_score}. "
                    "Fraud analyst review required (I-27)."
                ),
            )

        return anomaly_result

    def _record_audit(
        self,
        *,
        customer_id: str,
        device_id: str | None,
        risk_level: str,
        risk_score: str,
        geo_country: str,
        ip_hash: str,
        action: str,
    ) -> None:
        entry = FingerprintAuditEntry(
            customer_id=customer_id,
            action=action,
            device_id=device_id,
            risk_level=risk_level,
            risk_score=risk_score,
            geo_country=geo_country,
            ip_hash=ip_hash,
        )
        self._audit.record(entry)
