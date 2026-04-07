"""
kyc_port.py — KYCWorkflowPort: hexagonal interface for KYC/KYB orchestration
S5-13 (Ballerine) | FCA MLR 2017 | AML CTFF Act 2002 | banxe-emi-stack

WHY THIS FILE EXISTS
--------------------
FCA MLR 2017 requires Know Your Customer (KYC) and Know Your Business (KYB)
checks before onboarding any customer or corporate. Ballerine is the target
open-source KYC workflow engine (ballerine.com).

This Port defines the canonical workflow interface so that:
  - Onboarding service depends ONLY on this interface
  - MockKYCWorkflow works for tests without Ballerine instance
  - BallerineAdapter (live) can be plugged in when Ballerine is deployed
  - Alternative providers (Sumsub, Onfido) implement the same Port

KYC Workflow States (FCA MLR 2017 §18-27):
  PENDING           → workflow created, awaiting document submission
  DOCUMENT_REVIEW   → documents submitted, under review
  RISK_ASSESSMENT   → documents verified, AML/PEP/sanctions check running
  EDD_REQUIRED      → Enhanced Due Diligence triggered (PEP / high-risk / £10k+)
  MLRO_REVIEW       → EDD case referred to MLRO for sign-off
  APPROVED          → KYC passed, customer can be onboarded
  REJECTED          → KYC failed (sanctions hit / document fraud / risk too high)
  EXPIRED           → workflow not completed within TTL (30 days)

FCA rules:
  - MLR 2017 §18: CDD required for all new customers
  - MLR 2017 §33: EDD for PEPs, high-risk third countries, complex transactions
  - I-04: transactions ≥ £10,000 → EDD mandatory
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol


class KYCStatus(str, Enum):
    PENDING = "PENDING"
    DOCUMENT_REVIEW = "DOCUMENT_REVIEW"
    RISK_ASSESSMENT = "RISK_ASSESSMENT"
    EDD_REQUIRED = "EDD_REQUIRED"
    MLRO_REVIEW = "MLRO_REVIEW"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    EXPIRED = "EXPIRED"


class KYCType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"     # Retail customer
    BUSINESS = "BUSINESS"         # Corporate (KYB)
    SOLE_TRADER = "SOLE_TRADER"


class RejectionReason(str, Enum):
    SANCTIONS_HIT = "SANCTIONS_HIT"
    DOCUMENT_FRAUD = "DOCUMENT_FRAUD"
    HIGH_RISK_JURISDICTION = "HIGH_RISK_JURISDICTION"
    PEP_NO_EDD = "PEP_NO_EDD"
    RISK_SCORE_TOO_HIGH = "RISK_SCORE_TOO_HIGH"
    INCOMPLETE_DOCUMENTS = "INCOMPLETE_DOCUMENTS"
    AML_PATTERN = "AML_PATTERN"


@dataclass
class KYCWorkflowRequest:
    """Input to create a new KYC workflow."""
    customer_id: str
    kyc_type: KYCType
    first_name: str
    last_name: str
    date_of_birth: str               # ISO-8601 date string
    nationality: str                  # ISO-3166-1 alpha-2
    country_of_residence: str
    expected_transaction_volume: Decimal  # monthly GBP equivalent
    is_pep: bool = False             # Politically Exposed Person
    business_name: Optional[str] = None   # KYB only
    registration_number: Optional[str] = None  # KYB only


@dataclass
class KYCWorkflowResult:
    """State snapshot of a KYC workflow."""
    workflow_id: str
    customer_id: str
    status: KYCStatus
    kyc_type: KYCType
    created_at: datetime
    updated_at: datetime
    expires_at: datetime                  # 30 days from creation (FCA MLR 2017)
    edd_required: bool = False
    rejection_reason: Optional[RejectionReason] = None
    risk_score: Optional[int] = None      # 0–100
    notes: list[str] = field(default_factory=list)
    mlro_sign_off: bool = False           # True after MLRO approves EDD

    @property
    def is_terminal(self) -> bool:
        return self.status in (KYCStatus.APPROVED, KYCStatus.REJECTED, KYCStatus.EXPIRED)

    @property
    def requires_human_review(self) -> bool:
        return self.status in (KYCStatus.EDD_REQUIRED, KYCStatus.MLRO_REVIEW)


class KYCWorkflowPort(Protocol):
    """Hexagonal port for KYC/KYB workflow orchestration."""
    def create_workflow(self, request: KYCWorkflowRequest) -> KYCWorkflowResult: ...
    def get_workflow(self, workflow_id: str) -> Optional[KYCWorkflowResult]: ...
    def submit_documents(self, workflow_id: str, document_ids: list[str]) -> KYCWorkflowResult: ...
    def approve_edd(self, workflow_id: str, mlro_user_id: str) -> KYCWorkflowResult: ...
    def reject_workflow(self, workflow_id: str, reason: RejectionReason) -> KYCWorkflowResult: ...
    def health(self) -> bool: ...
