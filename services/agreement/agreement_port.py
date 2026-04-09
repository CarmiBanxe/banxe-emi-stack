"""
agreement_port.py — Agreement Service Port (Hexagonal Architecture)
S17-02: T&C generation per product + DocuSign e-signature + version history
FCA: FCA COBS 6 (product disclosure), eIDAS Reg.910/2014 (qualified e-sig)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


class ProductType(str, Enum):
    EMONEY_ACCOUNT = "EMONEY_ACCOUNT"
    FX_SERVICE = "FX_SERVICE"
    SAVINGS_ACCOUNT = "SAVINGS_ACCOUNT"
    PAYMENT_SERVICES = "PAYMENT_SERVICES"


class SignatureStatus(str, Enum):
    PENDING = "PENDING"  # Awaiting customer signature
    SIGNED = "SIGNED"  # Qualified e-signature collected
    EXPIRED = "EXPIRED"  # Signature window expired (>30 days)
    REVOKED = "REVOKED"  # Customer withdrew consent


class AgreementStatus(str, Enum):
    DRAFT = "DRAFT"
    SENT_FOR_SIGNATURE = "SENT_FOR_SIGNATURE"
    ACTIVE = "ACTIVE"  # Signed + in force
    SUPERSEDED = "SUPERSEDED"  # Replaced by newer version
    TERMINATED = "TERMINATED"


@dataclass
class TermsVersion:
    """One version of T&C content — immutable once published."""

    version: str  # semver: "1.0.0"
    product_type: ProductType
    content_hash: str  # SHA-256 of T&C text for audit
    effective_date: datetime
    is_current: bool = True


@dataclass
class Agreement:
    """
    Customer-product agreement — FCA COBS 6 product disclosure.
    Signed via DocuSign (eIDAS Reg.910/2014 qualified e-sig).
    """

    agreement_id: str
    customer_id: str
    product_type: ProductType
    terms_version: str
    status: AgreementStatus
    signature_status: SignatureStatus
    created_at: datetime
    updated_at: datetime

    # DocuSign / e-sig metadata
    docusign_envelope_id: str | None = None
    signed_at: datetime | None = None
    signature_provider: str = "DocuSign"

    # Version history (all past versions for this agreement)
    version_history: list[str] = field(default_factory=list)


@dataclass
class CreateAgreementRequest:
    customer_id: str
    product_type: ProductType
    terms_version: str = "1.0.0"


@dataclass
class SignAgreementRequest:
    agreement_id: str
    customer_id: str
    signature_provider: str = "DocuSign"
    docusign_envelope_id: str | None = None


@dataclass
class AgreementError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


class AgreementPort(Protocol):
    def create_agreement(self, req: CreateAgreementRequest) -> Agreement: ...
    def get_agreement(self, agreement_id: str) -> Agreement: ...
    def record_signature(self, req: SignAgreementRequest) -> Agreement: ...
    def supersede(self, agreement_id: str, new_version: str, operator_id: str) -> Agreement: ...
    def list_customer_agreements(self, customer_id: str) -> list[Agreement]: ...
    def get_current_terms_version(self, product_type: ProductType) -> TermsVersion: ...
