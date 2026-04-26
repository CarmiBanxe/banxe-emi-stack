"""
services/fatca_crs/fatca_models.py
Pydantic models for FATCA/CRS Self-Certification (IL-FAT-01).
TIN masked in all logs (last 4 chars only).
"""

from __future__ import annotations

from enum import Enum

from pydantic import BaseModel


class CRSClassification(str, Enum):
    ACTIVE_NFE = "Active_NFE"
    PASSIVE_NFE = "Passive_NFE"
    FINANCIAL_INSTITUTION = "Financial_Institution"
    GOVT_ENTITY = "Govt_Entity"
    INDIVIDUAL = "Individual"


class CertificationStatus(str, Enum):
    ACTIVE = "ACTIVE"
    RENEWAL_REQUIRED = "RENEWAL_REQUIRED"
    EXPIRED = "EXPIRED"
    PENDING = "PENDING"


class TaxResidency(BaseModel):
    country: str  # ISO-2
    tin: str  # Tax Identification Number (masked in logs)
    tin_unavailable: bool = False
    model_config = {"frozen": True}

    def masked_tin(self) -> str:
        return f"****{self.tin[-4:]}" if len(self.tin) >= 4 else "****"


class SelfCertification(BaseModel):
    cert_id: str
    customer_id: str
    tax_residencies: list[TaxResidency]
    us_person: bool
    crs_classification: CRSClassification
    status: CertificationStatus = CertificationStatus.ACTIVE
    created_at: str
    expires_at: str  # 365 days from created_at
    model_config = {"frozen": True}


class ValidationResult(BaseModel):
    cert_id: str
    valid: bool
    errors: list[str] = []
    renewal_required: bool = False
    model_config = {"frozen": True}


class W8BENData(BaseModel):
    customer_id: str
    country_of_residence: str
    claim_of_treaty_benefits: bool = False
    treaty_country: str | None = None
    model_config = {"frozen": True}
