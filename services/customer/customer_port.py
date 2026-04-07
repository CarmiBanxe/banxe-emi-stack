"""
customer_port.py — Customer Management Port (Hexagonal Architecture)
S17-01: Dual Entity Model (Individual / Company + UBO Registry)
S17-09: Customer Lifecycle State Machine
FCA: UK GDPR Art.5, FCA COBS 9A, MLR 2017 record-keeping
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from enum import Enum
from typing import Optional, Protocol


# ── Entity type ────────────────────────────────────────────────────────────────

class EntityType(str, Enum):
    INDIVIDUAL = "INDIVIDUAL"   # Natural person
    COMPANY = "COMPANY"         # Legal entity (KYB required)


# ── Lifecycle states (S17-09) ──────────────────────────────────────────────────

class LifecycleState(str, Enum):
    ONBOARDING = "ONBOARDING"   # KYC in progress
    ACTIVE = "ACTIVE"           # Full access
    DORMANT = "DORMANT"         # >12 months inactive (MLR 2017 monitoring)
    OFFBOARDED = "OFFBOARDED"   # Account closed; records retained 5yr
    DECEASED = "DECEASED"       # Death notification received

    # Valid transitions: ONBOARDING→ACTIVE, ACTIVE→DORMANT, DORMANT→ACTIVE,
    # ACTIVE|DORMANT→OFFBOARDED, ACTIVE|DORMANT→DECEASED

    def can_transition_to(self, target: LifecycleState) -> bool:
        _ALLOWED = {
            LifecycleState.ONBOARDING: {LifecycleState.ACTIVE, LifecycleState.OFFBOARDED},
            LifecycleState.ACTIVE: {LifecycleState.DORMANT, LifecycleState.OFFBOARDED, LifecycleState.DECEASED},
            LifecycleState.DORMANT: {LifecycleState.ACTIVE, LifecycleState.OFFBOARDED, LifecycleState.DECEASED},
            LifecycleState.OFFBOARDED: set(),
            LifecycleState.DECEASED: set(),
        }
        return target in _ALLOWED[self]


# ── Risk level ─────────────────────────────────────────────────────────────────

class RiskLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    VERY_HIGH = "very_high"
    PROHIBITED = "prohibited"


# ── UBO / Director registry (S17-10, KYB) ─────────────────────────────────────

@dataclass
class UBORecord:
    """Ultimate Beneficial Owner or Director — MLR 2017 §19."""
    full_name: str
    role: str                        # "director" | "shareholder" | "ubo"
    ownership_pct: Optional[Decimal] = None
    nationality: Optional[str] = None
    date_of_birth: Optional[date] = None
    kyc_verified: bool = False


# ── Address ────────────────────────────────────────────────────────────────────

@dataclass
class Address:
    line1: str
    city: str
    country: str                     # ISO-3166-1 alpha-2
    postcode: Optional[str] = None
    line2: Optional[str] = None


# ── Customer profiles ──────────────────────────────────────────────────────────

@dataclass
class IndividualProfile:
    """Natural person (UK GDPR Art.5, MLR 2017 §18)."""
    first_name: str
    last_name: str
    date_of_birth: date
    nationality: str                 # ISO-3166-1 alpha-2
    address: Address
    pep: bool = False                # Politically Exposed Person
    sanctions_hit: bool = False


@dataclass
class CompanyProfile:
    """Legal entity (MLR 2017 §19, Companies House KYB)."""
    company_name: str
    registration_number: str         # Companies House number
    country_of_incorporation: str
    registered_address: Address
    ubo_registry: list[UBORecord] = field(default_factory=list)
    companies_house_verified: bool = False


# ── Main customer entity ───────────────────────────────────────────────────────

@dataclass
class CustomerProfile:
    """
    Full customer record — Individual OR Company.

    FCA obligations:
    - UK GDPR Art.5: purpose limitation, data minimisation
    - FCA COBS 9A: suitability record-keeping
    - MLR 2017: AML record-keeping (5yr post offboarding)
    """
    customer_id: str
    entity_type: EntityType
    kyc_status: str                  # KYCStatus string (avoid circular import)
    risk_level: RiskLevel
    lifecycle_state: LifecycleState
    created_at: datetime
    updated_at: datetime

    # Exactly one of these is set based on entity_type
    individual: Optional[IndividualProfile] = None
    company: Optional[CompanyProfile] = None

    # Linked service IDs
    agreement_ids: list[str] = field(default_factory=list)
    account_ids: list[str] = field(default_factory=list)

    metadata: dict = field(default_factory=dict)

    @property
    def display_name(self) -> str:
        if self.individual:
            return f"{self.individual.first_name} {self.individual.last_name}"
        if self.company:
            return self.company.company_name
        return self.customer_id

    @property
    def is_active(self) -> bool:
        return self.lifecycle_state == LifecycleState.ACTIVE


# ── Request / Result DTOs ──────────────────────────────────────────────────────

@dataclass
class CreateCustomerRequest:
    entity_type: EntityType
    individual: Optional[IndividualProfile] = None
    company: Optional[CompanyProfile] = None
    risk_level: RiskLevel = RiskLevel.LOW


@dataclass
class LifecycleTransitionRequest:
    customer_id: str
    target_state: LifecycleState
    reason: str
    operator_id: str


@dataclass
class CustomerManagementError(Exception):
    code: str
    message: str

    def __str__(self) -> str:
        return f"{self.code}: {self.message}"


# ── Port Protocol ──────────────────────────────────────────────────────────────

class CustomerManagementPort(Protocol):
    def create_customer(self, req: CreateCustomerRequest) -> CustomerProfile: ...
    def get_customer(self, customer_id: str) -> CustomerProfile: ...
    def update_risk_level(self, customer_id: str, risk_level: RiskLevel) -> CustomerProfile: ...
    def transition_lifecycle(self, req: LifecycleTransitionRequest) -> CustomerProfile: ...
    def add_ubo(self, customer_id: str, ubo: UBORecord) -> CustomerProfile: ...
    def list_customers(self, lifecycle_state: Optional[LifecycleState] = None) -> list[CustomerProfile]: ...
    def link_agreement(self, customer_id: str, agreement_id: str) -> None: ...
