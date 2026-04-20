from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Protocol


class BusinessType(StrEnum):
    SOLE_TRADER = "sole_trader"
    LTD = "ltd"
    LLP = "llp"
    PLC = "plc"
    PARTNERSHIP = "partnership"
    CHARITY = "charity"


class KYBStatus(StrEnum):
    SUBMITTED = "submitted"
    DOCUMENTS_PENDING = "documents_pending"
    UNDER_REVIEW = "under_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUSPENDED = "suspended"


class UBOVerification(StrEnum):
    PENDING = "pending"
    VERIFIED = "verified"
    FAILED = "failed"
    EXEMPTED = "exempted"


class RiskTier(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"


class DocumentType(StrEnum):
    CERTIFICATE_OF_INCORPORATION = "certificate_of_incorporation"
    MEMORANDUM_ARTICLES = "memorandum_articles"
    PROOF_OF_ADDRESS = "proof_of_address"
    SHAREHOLDER_REGISTER = "shareholder_register"
    LATEST_ACCOUNTS = "latest_accounts"
    UBO_ID_PASSPORT = "ubo_id_passport"


@dataclass(frozen=True)
class BusinessApplication:
    application_id: str
    business_name: str
    business_type: BusinessType
    companies_house_number: str
    jurisdiction: str
    status: KYBStatus
    submitted_at: str
    ubo_ids: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UltimateBeneficialOwner:
    ubo_id: str
    application_id: str
    full_name: str
    nationality: str
    date_of_birth: str
    ownership_pct: Decimal  # I-01: Decimal, not float
    verification_status: UBOVerification
    is_psc: bool = False  # Person of Significant Control


@dataclass(frozen=True)
class KYBDocument:
    document_id: str
    application_id: str
    document_type: DocumentType
    file_hash: str  # I-12: SHA-256
    uploaded_at: str
    verified: bool = False


@dataclass(frozen=True)
class KYBDecision:
    decision_id: str
    application_id: str
    decision: KYBStatus  # APPROVED or REJECTED
    decided_by: str
    decided_at: str
    reason: str
    risk_tier: RiskTier


@dataclass(frozen=True)
class KYBRiskAssessment:
    assessment_id: str
    application_id: str
    risk_score: Decimal  # I-01: 0-100 Decimal
    risk_tier: RiskTier
    factors: list[str] = field(default_factory=list)
    assessed_at: str = ""


@dataclass
class HITLProposal:
    action: str
    application_id: str
    requires_approval_from: str
    reason: str
    autonomy_level: str = "L4"


# Protocols
class ApplicationStore(Protocol):
    def get(self, application_id: str) -> BusinessApplication | None: ...
    def save(self, app: BusinessApplication) -> None: ...
    def list_by_status(self, status: KYBStatus | None) -> list[BusinessApplication]: ...


class UBOStore(Protocol):
    def get(self, ubo_id: str) -> UltimateBeneficialOwner | None: ...
    def save(self, ubo: UltimateBeneficialOwner) -> None: ...
    def list_by_application(self, application_id: str) -> list[UltimateBeneficialOwner]: ...


class KYBDocumentStore(Protocol):
    def get(self, document_id: str) -> KYBDocument | None: ...
    def save(self, doc: KYBDocument) -> None: ...
    def list_by_application(self, application_id: str) -> list[KYBDocument]: ...


class KYBDecisionStore(Protocol):
    def append(self, decision: KYBDecision) -> None: ...  # I-24: append-only
    def list_by_application(self, application_id: str) -> list[KYBDecision]: ...
    def get_latest(self, application_id: str) -> KYBDecision | None: ...


# InMemory stubs
class InMemoryApplicationStore:
    def __init__(self) -> None:
        self._data: dict[str, BusinessApplication] = {}
        apps = [
            BusinessApplication(
                "app_001",
                "Acme Ltd",
                BusinessType.LTD,
                "12345678",
                "GB",
                KYBStatus.APPROVED,
                "2026-01-01T00:00:00Z",
            ),
            BusinessApplication(
                "app_002",
                "Beta LLP",
                BusinessType.LLP,
                "OC123456",
                "GB",
                KYBStatus.UNDER_REVIEW,
                "2026-02-01T00:00:00Z",
            ),
            BusinessApplication(
                "app_003",
                "Solo Trader",
                BusinessType.SOLE_TRADER,
                "",
                "GB",
                KYBStatus.SUBMITTED,
                "2026-03-01T00:00:00Z",
            ),
        ]
        for a in apps:
            self._data[a.application_id] = a

    def get(self, application_id: str) -> BusinessApplication | None:
        return self._data.get(application_id)

    def save(self, app: BusinessApplication) -> None:
        self._data[app.application_id] = app

    def list_by_status(self, status: KYBStatus | None) -> list[BusinessApplication]:
        if status is None:
            return list(self._data.values())
        return [a for a in self._data.values() if a.status == status]


class InMemoryUBOStore:
    def __init__(self) -> None:
        self._data: dict[str, UltimateBeneficialOwner] = {}

    def get(self, ubo_id: str) -> UltimateBeneficialOwner | None:
        return self._data.get(ubo_id)

    def save(self, ubo: UltimateBeneficialOwner) -> None:
        self._data[ubo.ubo_id] = ubo

    def list_by_application(self, application_id: str) -> list[UltimateBeneficialOwner]:
        return [u for u in self._data.values() if u.application_id == application_id]


class InMemoryKYBDocumentStore:
    def __init__(self) -> None:
        self._data: dict[str, KYBDocument] = {}

    def get(self, document_id: str) -> KYBDocument | None:
        return self._data.get(document_id)

    def save(self, doc: KYBDocument) -> None:
        self._data[doc.document_id] = doc

    def list_by_application(self, application_id: str) -> list[KYBDocument]:
        return [d for d in self._data.values() if d.application_id == application_id]


class InMemoryKYBDecisionStore:
    def __init__(self) -> None:
        self._log: list[KYBDecision] = []

    def append(self, decision: KYBDecision) -> None:  # I-24
        self._log.append(decision)

    def list_by_application(self, application_id: str) -> list[KYBDecision]:
        return [d for d in self._log if d.application_id == application_id]

    def get_latest(self, application_id: str) -> KYBDecision | None:
        matches = self.list_by_application(application_id)
        return matches[-1] if matches else None
