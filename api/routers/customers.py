"""
api/routers/customers.py — Customer management endpoints
IL-046 | banxe-emi-stack

POST /v1/customers          — onboard new customer
GET  /v1/customers          — list customers (optional ?state= filter)
GET  /v1/customers/{id}     — get customer profile
POST /v1/customers/{id}/lifecycle — transition lifecycle state

Persistence: customer records are written to PostgreSQL/SQLite (best-effort)
on creation so the auth endpoint can look them up by email after restarts.
The InMemoryCustomerService remains the source-of-truth for domain logic.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from api.db.models import Customer as DBCustomer
from api.deps import get_customer_service, get_db
from api.models.customers import (
    CreateCustomerRequest,
    CustomerListResponse,
    CustomerResponse,
    LifecycleTransitionRequest,
)
from services.customer.customer_port import (
    CreateCustomerRequest as DomainCreateRequest,
)
from services.customer.customer_port import (
    CustomerManagementError,
    EntityType,
    LifecycleState,
    RiskLevel,
)
from services.customer.customer_port import (
    LifecycleTransitionRequest as DomainTransitionRequest,
)
from services.customer.customer_service import InMemoryCustomerService

logger = logging.getLogger("banxe.customers")

router = APIRouter(tags=["Customers"])


def _profile_to_response(profile) -> CustomerResponse:  # type: ignore[return]
    return CustomerResponse(
        customer_id=profile.customer_id,
        entity_type=profile.entity_type,
        lifecycle_state=profile.lifecycle_state,
        risk_level=profile.risk_level,
        email=profile.metadata.get("email", ""),
        display_name=profile.display_name,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
    )


@router.post(
    "/customers",
    response_model=CustomerResponse,
    status_code=201,
    summary="Onboard a new customer",
)
async def create_customer(
    body: CreateCustomerRequest,
    svc: InMemoryCustomerService = Depends(get_customer_service),
    db: AsyncSession = Depends(get_db),
) -> CustomerResponse:
    """
    Create a new Individual or Corporate customer.
    Starts in ONBOARDING lifecycle state.
    FCA MLR 2017: KYC workflow must be started before ACTIVE state.

    Side-effect: writes a minimal record to the persistent DB so the
    auth endpoint can find this customer by email across restarts.
    """
    individual = None
    if body.entity_type == EntityType.INDIVIDUAL and body.individual:
        ind = body.individual
        from datetime import datetime

        from services.customer.customer_port import Address, IndividualProfile

        individual = IndividualProfile(
            first_name=ind.first_name,
            last_name=ind.last_name,
            date_of_birth=datetime.combine(ind.date_of_birth, datetime.min.time()),
            nationality=ind.nationality,
            address=Address(
                line1=ind.address.line1,
                line2=ind.address.line2,
                city=ind.address.city,
                postcode=ind.address.postcode,
                country=ind.address.country,
            ),
        )

    try:
        domain_req = DomainCreateRequest(
            entity_type=body.entity_type,
            individual=individual,
            risk_level=RiskLevel.LOW,
        )
        profile = svc.create_customer(domain_req)
        # Store email in metadata
        profile.metadata["email"] = body.email
        if body.phone:
            profile.metadata["phone"] = body.phone
    except CustomerManagementError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e

    # Persist to DB (best-effort — don't fail if DB unavailable or email duplicated)
    try:
        db_customer = DBCustomer(
            customer_id=profile.customer_id,
            email=body.email,
            display_name=profile.display_name,
            entity_type=profile.entity_type.value
            if hasattr(profile.entity_type, "value")
            else str(profile.entity_type),
            lifecycle_state=profile.lifecycle_state.value
            if hasattr(profile.lifecycle_state, "value")
            else str(profile.lifecycle_state),
            risk_level=profile.risk_level.value
            if hasattr(profile.risk_level, "value")
            else str(profile.risk_level),
        )
        db.add(db_customer)
        await db.flush()
    except IntegrityError:
        # Duplicate email (e.g. test re-creates same customer) — ignore silently
        await db.rollback()
    except Exception:
        logger.warning(
            "customers.create db_sync_failed customer_id=%s — InMemory still updated",
            profile.customer_id,
        )
        await db.rollback()

    return _profile_to_response(profile)


@router.get(
    "/customers",
    response_model=CustomerListResponse,
    summary="List customers",
)
def list_customers(
    state: LifecycleState | None = Query(None, description="Filter by lifecycle state"),
    svc: InMemoryCustomerService = Depends(get_customer_service),
) -> CustomerListResponse:
    profiles = svc.list_customers(lifecycle_state=state)
    items = [_profile_to_response(p) for p in profiles]
    return CustomerListResponse(customers=items, total=len(items))


@router.get(
    "/customers/{customer_id}",
    response_model=CustomerResponse,
    summary="Get customer profile",
)
def get_customer(
    customer_id: str,
    svc: InMemoryCustomerService = Depends(get_customer_service),
) -> CustomerResponse:
    try:
        profile = svc.get_customer(customer_id)
        return _profile_to_response(profile)
    except CustomerManagementError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e


@router.post(
    "/customers/{customer_id}/lifecycle",
    response_model=CustomerResponse,
    summary="Transition customer lifecycle state",
)
def transition_lifecycle(
    customer_id: str,
    body: LifecycleTransitionRequest,
    svc: InMemoryCustomerService = Depends(get_customer_service),
) -> CustomerResponse:
    """
    Transition customer lifecycle (e.g. ONBOARDING → ACTIVE, ACTIVE → SUSPENDED).
    Requires operator_id for FCA audit trail (I-24).
    """
    try:
        domain_req = DomainTransitionRequest(
            customer_id=customer_id,
            target_state=body.target_state,
            reason=body.reason or "",
            operator_id=body.operator_id,
        )
        profile = svc.transition_lifecycle(domain_req)
        return _profile_to_response(profile)
    except CustomerManagementError as e:
        raise HTTPException(status_code=422, detail=str(e)) from e
