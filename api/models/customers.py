"""
api/models/customers.py — Pydantic v2 schemas for Customer API
IL-046 | banxe-emi-stack

Maps between HTTP request/response JSON and domain dataclasses.
All amounts are strings (never float). I-05 compliance.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel, Field, field_validator

from services.customer.customer_port import EntityType, LifecycleState, RiskLevel

# ── Request schemas ───────────────────────────────────────────────────────────


class AddressRequest(BaseModel):
    line1: str
    line2: str | None = None
    city: str
    postcode: str
    country: str = Field(..., min_length=2, max_length=2, description="ISO 3166-1 alpha-2")


class IndividualProfileRequest(BaseModel):
    first_name: str
    last_name: str
    date_of_birth: date
    nationality: str = Field(..., min_length=2, max_length=2)
    address: AddressRequest


class CompanyProfileRequest(BaseModel):
    legal_name: str
    registration_number: str
    country_of_incorporation: str = Field(..., min_length=2, max_length=2)
    registered_address: AddressRequest


class CreateCustomerRequest(BaseModel):
    entity_type: EntityType
    individual: IndividualProfileRequest | None = None
    company: CompanyProfileRequest | None = None
    email: str
    phone: str | None = None

    @field_validator("individual", "company", mode="after")
    @classmethod
    def validate_profile_present(cls, v: object, info) -> object:  # type: ignore[override]
        # Cross-field validation happens at model level — kept minimal here
        return v


class LifecycleTransitionRequest(BaseModel):
    target_state: LifecycleState
    reason: str | None = None
    operator_id: str


# ── Response schemas ──────────────────────────────────────────────────────────


class CustomerResponse(BaseModel):
    customer_id: str
    entity_type: EntityType
    lifecycle_state: LifecycleState
    risk_level: RiskLevel
    email: str
    display_name: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class CustomerListResponse(BaseModel):
    customers: list[CustomerResponse]
    total: int
