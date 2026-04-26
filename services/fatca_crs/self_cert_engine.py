"""
services/fatca_crs/self_cert_engine.py
FATCA/CRS self-certification workflow (IL-FAT-01).
I-02: blocked jurisdictions on tax_residency countries.
I-24: CertificationStore and AuditLog are append-only.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from typing import Protocol

from services.fatca_crs.fatca_models import (
    CertificationStatus,
    CRSClassification,
    SelfCertification,
    TaxResidency,
    ValidationResult,
)

BLOCKED_JURISDICTIONS = {"RU", "BY", "IR", "KP", "CU", "MM", "AF", "VE", "SY"}
CERT_TTL_DAYS = 365


class CertStorePort(Protocol):
    def save(self, cert: SelfCertification) -> None: ...
    def get_by_customer(self, customer_id: str) -> list[SelfCertification]: ...
    def get_by_id(self, cert_id: str) -> SelfCertification | None: ...


class InMemoryCertStore:
    def __init__(self) -> None:
        self._certs: list[SelfCertification] = []  # I-24 append-only

    def save(self, cert: SelfCertification) -> None:
        self._certs.append(cert)

    def get_by_customer(self, customer_id: str) -> list[SelfCertification]:
        return [c for c in self._certs if c.customer_id == customer_id]

    def get_by_id(self, cert_id: str) -> SelfCertification | None:
        return next((c for c in self._certs if c.cert_id == cert_id), None)


class SelfCertEngine:
    """FATCA/CRS self-certification engine.

    I-02: blocked jurisdictions on tax residency countries.
    I-24: append-only store and audit log.
    Annual review: certs older than 365 days require renewal.
    """

    def __init__(self, store: CertStorePort | None = None) -> None:
        self._store: CertStorePort = store or InMemoryCertStore()
        self._audit_log: list[dict] = []  # I-24 append-only

    def create_cert(
        self,
        customer_id: str,
        tax_residencies: list[TaxResidency],
        us_person: bool,
        crs_classification: CRSClassification = CRSClassification.INDIVIDUAL,
    ) -> SelfCertification:
        """Create a FATCA/CRS self-certification.

        Raises ValueError if any tax_residency country is in BLOCKED_JURISDICTIONS (I-02).
        """
        for res in tax_residencies:
            if res.country in BLOCKED_JURISDICTIONS:
                raise ValueError(
                    f"Tax residency country {res.country!r} is in blocked jurisdictions (I-02)"
                )

        cert_id = f"cert_{hashlib.sha256(f'{customer_id}{datetime.now(UTC).isoformat()}'.encode()).hexdigest()[:8]}"
        now = datetime.now(UTC)
        expires = now + timedelta(days=CERT_TTL_DAYS)

        cert = SelfCertification(
            cert_id=cert_id,
            customer_id=customer_id,
            tax_residencies=tax_residencies,
            us_person=us_person,
            crs_classification=crs_classification,
            status=CertificationStatus.ACTIVE,
            created_at=now.isoformat(),
            expires_at=expires.isoformat(),
        )
        self._store.save(cert)
        # I-24: log without TIN (masked)
        self._audit_log.append(
            {
                "event": "cert.created",
                "cert_id": cert_id,
                "customer_id": customer_id,
                "us_person": us_person,
                "residency_countries": [r.country for r in tax_residencies],
                "logged_at": now.isoformat(),
            }
        )
        return cert

    def validate_cert(self, cert_id: str) -> ValidationResult:
        cert = self._store.get_by_id(cert_id)
        if cert is None:
            return ValidationResult(
                cert_id=cert_id, valid=False, errors=["Certification not found"]
            )

        errors: list[str] = []
        renewal_required = False

        # Check expiry
        expires = datetime.fromisoformat(cert.expires_at)
        now = datetime.now(UTC)
        if now > expires:
            errors.append("Certification has expired")
            renewal_required = True

        # Check blocked jurisdiction
        for res in cert.tax_residencies:
            if res.country in BLOCKED_JURISDICTIONS:
                errors.append(f"Blocked jurisdiction: {res.country}")

        valid = len(errors) == 0
        return ValidationResult(
            cert_id=cert_id, valid=valid, errors=errors, renewal_required=renewal_required
        )

    def get_renewal_due(self) -> list[SelfCertification]:
        """Return certs approaching or past expiry (RENEWAL_REQUIRED)."""
        now = datetime.now(UTC)
        warning_days = 30
        result = []
        # Scan all certs from store — iterate known customers via audit log
        seen = set()
        for entry in self._audit_log:
            cid = entry.get("customer_id")
            if cid and cid not in seen:
                seen.add(cid)
                for cert in self._store.get_by_customer(cid):
                    expires = datetime.fromisoformat(cert.expires_at)
                    if (expires - now).days <= warning_days:
                        result.append(cert)
        return result

    @property
    def audit_log(self) -> list[dict]:
        """I-24: append-only."""
        return list(self._audit_log)
