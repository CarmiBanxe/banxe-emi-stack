"""
customer_service.py — Customer Management Service (In-Memory + ClickHouse stub)
S17-01: Dual Entity Model | S17-09: Lifecycle State Machine
FCA: UK GDPR Art.5, FCA COBS 9A, MLR 2017
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from typing import Optional

from .customer_port import (
    CreateCustomerRequest,
    CustomerManagementError,
    CustomerProfile,
    EntityType,
    LifecycleState,
    LifecycleTransitionRequest,
    RiskLevel,
    UBORecord,
)

logger = logging.getLogger(__name__)

# ── Blocked jurisdictions (I-02) ───────────────────────────────────────────────

_BLOCKED_NATIONALITIES = {"RU", "BY", "IR", "KP", "CU", "MM"}
_BLOCKED_COUNTRIES = {"RU", "BY", "IR", "KP", "CU", "MM"}


def _check_blocked(req: CreateCustomerRequest) -> None:
    """I-02: Reject customers from sanctioned jurisdictions."""
    if req.individual:
        if req.individual.nationality in _BLOCKED_NATIONALITIES:
            raise CustomerManagementError(
                code="BLOCKED_JURISDICTION",
                message=f"Nationality {req.individual.nationality} is in sanctioned jurisdiction list (I-02)",
            )
        if req.individual.address.country in _BLOCKED_COUNTRIES:
            raise CustomerManagementError(
                code="BLOCKED_JURISDICTION",
                message=f"Country {req.individual.address.country} is in sanctioned jurisdiction list (I-02)",
            )
    if req.company:
        if req.company.country_of_incorporation in _BLOCKED_COUNTRIES:
            raise CustomerManagementError(
                code="BLOCKED_JURISDICTION",
                message=f"Incorporation country {req.company.country_of_incorporation} blocked (I-02)",
            )


# ── In-memory implementation ───────────────────────────────────────────────────

class InMemoryCustomerService:
    """
    In-memory CustomerManagement service for tests + development.
    Enforces I-02 (blocked jurisdictions) and S17-09 lifecycle transitions.

    Swap for ClickHouseCustomerService in production by setting
    CUSTOMER_BACKEND=clickhouse.
    """

    def __init__(self) -> None:
        self._store: dict[str, CustomerProfile] = {}

    def _now(self) -> datetime:
        return datetime.now(timezone.utc)

    def create_customer(self, req: CreateCustomerRequest) -> CustomerProfile:
        # Validate entity type consistency
        if req.entity_type == EntityType.INDIVIDUAL and req.individual is None:
            raise CustomerManagementError(
                code="MISSING_PROFILE",
                message="IndividualProfile required for INDIVIDUAL entity type",
            )
        if req.entity_type == EntityType.COMPANY and req.company is None:
            raise CustomerManagementError(
                code="MISSING_PROFILE",
                message="CompanyProfile required for COMPANY entity type",
            )

        # I-02: Blocked jurisdictions
        _check_blocked(req)

        now = self._now()
        customer_id = f"cust-{uuid.uuid4().hex[:12]}"

        profile = CustomerProfile(
            customer_id=customer_id,
            entity_type=req.entity_type,
            kyc_status="PENDING",
            risk_level=req.risk_level,
            lifecycle_state=LifecycleState.ONBOARDING,
            created_at=now,
            updated_at=now,
            individual=req.individual,
            company=req.company,
        )
        self._store[customer_id] = profile
        logger.info("Customer created: %s (%s)", customer_id, req.entity_type)
        return profile

    def get_customer(self, customer_id: str) -> CustomerProfile:
        if customer_id not in self._store:
            raise CustomerManagementError(
                code="NOT_FOUND",
                message=f"Customer {customer_id} not found",
            )
        return self._store[customer_id]

    def update_risk_level(self, customer_id: str, risk_level: RiskLevel) -> CustomerProfile:
        profile = self.get_customer(customer_id)
        profile.risk_level = risk_level
        profile.updated_at = self._now()
        logger.info("Risk updated: %s → %s", customer_id, risk_level)
        return profile

    def transition_lifecycle(self, req: LifecycleTransitionRequest) -> CustomerProfile:
        profile = self.get_customer(req.customer_id)

        if not profile.lifecycle_state.can_transition_to(req.target_state):
            raise CustomerManagementError(
                code="INVALID_TRANSITION",
                message=(
                    f"Cannot transition {profile.lifecycle_state} → {req.target_state} "
                    f"for customer {req.customer_id}"
                ),
            )

        old_state = profile.lifecycle_state
        profile.lifecycle_state = req.target_state
        profile.updated_at = self._now()
        profile.metadata["last_transition"] = {
            "from": old_state,
            "to": req.target_state,
            "reason": req.reason,
            "operator_id": req.operator_id,
            "at": profile.updated_at.isoformat(),
        }
        logger.info(
            "Lifecycle transition: %s %s → %s (by %s, reason: %s)",
            req.customer_id, old_state, req.target_state, req.operator_id, req.reason,
        )
        return profile

    def add_ubo(self, customer_id: str, ubo: UBORecord) -> CustomerProfile:
        profile = self.get_customer(customer_id)
        if profile.entity_type != EntityType.COMPANY:
            raise CustomerManagementError(
                code="NOT_COMPANY",
                message=f"UBO registry only applies to COMPANY entities (customer: {customer_id})",
            )
        if profile.company is None:
            raise CustomerManagementError(code="NO_COMPANY_PROFILE", message="Company profile missing")
        profile.company.ubo_registry.append(ubo)
        profile.updated_at = self._now()
        logger.info("UBO added: %s → %s (%s)", customer_id, ubo.full_name, ubo.role)
        return profile

    def list_customers(self, lifecycle_state: Optional[LifecycleState] = None) -> list[CustomerProfile]:
        customers = list(self._store.values())
        if lifecycle_state is not None:
            customers = [c for c in customers if c.lifecycle_state == lifecycle_state]
        return customers

    def link_agreement(self, customer_id: str, agreement_id: str) -> None:
        profile = self.get_customer(customer_id)
        if agreement_id not in profile.agreement_ids:
            profile.agreement_ids.append(agreement_id)
            profile.updated_at = self._now()
            logger.info("Agreement linked: %s → %s", customer_id, agreement_id)


# ── ClickHouse-backed stub (production) ───────────────────────────────────────

class ClickHouseCustomerService:  # pragma: no cover
    """
    Production customer service backed by ClickHouse + Midaz.
    STATUS: STUB — requires ClickHouse banxe.customers table (CEO action: deploy schema).
    """

    def create_customer(self, req: CreateCustomerRequest) -> CustomerProfile:
        raise NotImplementedError(
            "ClickHouseCustomerService not implemented. "
            "Run scripts/schema/clickhouse_customers.sql to create the table."
        )

    def get_customer(self, customer_id: str) -> CustomerProfile:
        raise NotImplementedError

    def update_risk_level(self, customer_id: str, risk_level: RiskLevel) -> CustomerProfile:
        raise NotImplementedError

    def transition_lifecycle(self, req: LifecycleTransitionRequest) -> CustomerProfile:
        raise NotImplementedError

    def add_ubo(self, customer_id: str, ubo: UBORecord) -> CustomerProfile:
        raise NotImplementedError

    def list_customers(self, lifecycle_state: Optional[LifecycleState] = None) -> list[CustomerProfile]:
        raise NotImplementedError

    def link_agreement(self, customer_id: str, agreement_id: str) -> None:
        raise NotImplementedError


# ── Factory ────────────────────────────────────────────────────────────────────

def get_customer_service() -> InMemoryCustomerService | ClickHouseCustomerService:
    import os
    backend = os.environ.get("CUSTOMER_BACKEND", "memory")
    if backend == "clickhouse":
        return ClickHouseCustomerService()
    return InMemoryCustomerService()
