"""
customer_service.py — Customer Management Service (In-Memory + ClickHouse stub)
S17-01: Dual Entity Model | S17-09: Lifecycle State Machine
FCA: UK GDPR Art.5, FCA COBS 9A, MLR 2017
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, date, datetime
from decimal import Decimal
import json
import logging
import uuid

from .customer_port import (
    Address,
    CompanyProfile,
    CreateCustomerRequest,
    CustomerManagementError,
    CustomerProfile,
    EntityType,
    IndividualProfile,
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
        return datetime.now(UTC)

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
            req.customer_id,
            old_state,
            req.target_state,
            req.operator_id,
            req.reason,
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
            raise CustomerManagementError(
                code="NO_COMPANY_PROFILE", message="Company profile missing"
            )
        profile.company.ubo_registry.append(ubo)
        profile.updated_at = self._now()
        logger.info("UBO added: customer=%s role=%s", customer_id, ubo.role)  # I-09: no PII in logs
        return profile

    def list_customers(
        self, lifecycle_state: LifecycleState | None = None
    ) -> list[CustomerProfile]:
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


# ── Serialisation helpers (shared by ClickHouseCustomerService) ───────────────


def _json_default(obj: object) -> object:
    """Custom JSON encoder for CustomerProfile fields."""
    if isinstance(obj, datetime | date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return str(obj)
    return str(obj)


def _profile_to_json(profile: CustomerProfile) -> str:
    return json.dumps(dataclasses.asdict(profile), default=_json_default)


def _profile_from_dict(d: dict) -> CustomerProfile:
    """Reconstruct a CustomerProfile from a JSON-decoded dict."""

    def _addr(a: dict | None) -> Address | None:
        if not a:
            return None
        return Address(
            line1=a["line1"],
            city=a["city"],
            country=a["country"],
            postcode=a.get("postcode"),
            line2=a.get("line2"),
        )

    def _ubo(u: dict) -> UBORecord:
        return UBORecord(
            full_name=u["full_name"],
            role=u["role"],
            ownership_pct=Decimal(str(u["ownership_pct"]))
            if u.get("ownership_pct") is not None
            else None,
            nationality=u.get("nationality"),
            date_of_birth=date.fromisoformat(u["date_of_birth"])
            if u.get("date_of_birth")
            else None,
            kyc_verified=bool(u.get("kyc_verified", False)),
        )

    individual: IndividualProfile | None = None
    if d.get("individual"):
        ind = d["individual"]
        individual = IndividualProfile(
            first_name=ind["first_name"],
            last_name=ind["last_name"],
            date_of_birth=date.fromisoformat(ind["date_of_birth"]),
            nationality=ind["nationality"],
            address=_addr(ind["address"]),  # type: ignore[arg-type]
            title=ind.get("title"),
            middle_name=ind.get("middle_name"),
            email=ind.get("email"),
            phone=ind.get("phone"),
            preferred_language=ind.get("preferred_language", "EN"),
            correspondence_address=_addr(ind.get("correspondence_address")),
            pep=bool(ind.get("pep", False)),
            sanctions_hit=bool(ind.get("sanctions_hit", False)),
            fatca_us_person=bool(ind.get("fatca_us_person", False)),
            crs_tax_residencies=list(ind.get("crs_tax_residencies", [])),
            notes=ind.get("notes"),
        )

    company: CompanyProfile | None = None
    if d.get("company"):
        comp = d["company"]
        company = CompanyProfile(
            company_name=comp["company_name"],
            registration_number=comp["registration_number"],
            country_of_incorporation=comp["country_of_incorporation"],
            registered_address=_addr(comp["registered_address"]),  # type: ignore[arg-type]
            company_type=comp.get("company_type"),
            industry=comp.get("industry"),
            tax_id=comp.get("tax_id"),
            date_of_registration=date.fromisoformat(comp["date_of_registration"])
            if comp.get("date_of_registration")
            else None,
            correspondence_address=_addr(comp.get("correspondence_address")),
            email=comp.get("email"),
            phone=comp.get("phone"),
            preferred_language=comp.get("preferred_language", "EN"),
            ubo_registry=[_ubo(u) for u in comp.get("ubo_registry", [])],
            companies_house_verified=bool(comp.get("companies_house_verified", False)),
        )

    return CustomerProfile(
        customer_id=d["customer_id"],
        entity_type=EntityType(d["entity_type"]),
        kyc_status=d["kyc_status"],
        risk_level=RiskLevel(d["risk_level"]),
        lifecycle_state=LifecycleState(d["lifecycle_state"]),
        created_at=datetime.fromisoformat(d["created_at"]),
        updated_at=datetime.fromisoformat(d["updated_at"]),
        individual=individual,
        company=company,
        agreement_ids=list(d.get("agreement_ids", [])),
        account_ids=list(d.get("account_ids", [])),
        metadata=dict(d.get("metadata", {})),
    )


# ── ClickHouse-backed implementation (production) ─────────────────────────────


class ClickHouseCustomerService:
    """
    Production customer service — persists CustomerProfile to ClickHouse.

    Uses ReplacingMergeTree(updated_at): every mutation INSERTs a new row;
    ClickHouse deduplicates asynchronously. Reads use SELECT FINAL for
    consistency (FCA I-24 audit trail requirement).

    Prerequisites:
        Run scripts/schema/clickhouse_customers.sql on GMKtec ClickHouse.
        Set CLICKHOUSE_HOST / CLICKHOUSE_PORT / CLICKHOUSE_DB / CLICKHOUSE_PASSWORD.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 9000,
        database: str = "banxe",
        user: str = "default",
        password: str = "",
    ) -> None:
        from services.config import (
            CLICKHOUSE_DB,
            CLICKHOUSE_HOST,
            CLICKHOUSE_PASSWORD,
            CLICKHOUSE_PORT,
            CLICKHOUSE_USER,
        )

        try:
            import clickhouse_driver  # type: ignore[import]

            self._client = clickhouse_driver.Client(
                host=host or CLICKHOUSE_HOST,
                port=port or CLICKHOUSE_PORT,
                database=database or CLICKHOUSE_DB,
                user=user or CLICKHOUSE_USER,
                password=password or CLICKHOUSE_PASSWORD,
            )
        except ImportError as exc:
            raise RuntimeError(
                "clickhouse-driver not installed: pip install clickhouse-driver"
            ) from exc

    # ── Internal ──────────────────────────────────────────────────────────────

    def _persist(self, profile: CustomerProfile) -> None:
        """INSERT CustomerProfile row (ReplacingMergeTree deduplicates by customer_id)."""
        self._client.execute(
            """
            INSERT INTO banxe.customers
            (customer_id, entity_type, kyc_status, risk_level, lifecycle_state,
             created_at, updated_at, profile_json, agreement_ids, account_ids)
            VALUES
            """,
            [
                {
                    "customer_id": profile.customer_id,
                    "entity_type": profile.entity_type.value,
                    "kyc_status": profile.kyc_status,
                    "risk_level": profile.risk_level.value,
                    "lifecycle_state": profile.lifecycle_state.value,
                    "created_at": profile.created_at,
                    "updated_at": profile.updated_at,
                    "profile_json": _profile_to_json(profile),
                    "agreement_ids": profile.agreement_ids,
                    "account_ids": profile.account_ids,
                }
            ],
        )

    def _load(self, customer_id: str) -> CustomerProfile | None:
        """SELECT FINAL and deserialise the latest version of a customer."""
        rows, col_types = self._client.execute(
            "SELECT profile_json FROM banxe.customers FINAL WHERE customer_id = %(cid)s LIMIT 1",
            {"cid": customer_id},
            with_column_types=True,
        )
        if not rows:
            return None
        return _profile_from_dict(json.loads(rows[0][0]))

    def _get_or_raise(self, customer_id: str) -> CustomerProfile:
        profile = self._load(customer_id)
        if profile is None:
            raise CustomerManagementError(
                code="NOT_FOUND",
                message=f"Customer {customer_id} not found",
            )
        return profile

    # ── Public API ────────────────────────────────────────────────────────────

    def create_customer(self, req: CreateCustomerRequest) -> CustomerProfile:
        if req.entity_type == EntityType.INDIVIDUAL and req.individual is None:
            raise CustomerManagementError(
                code="MISSING_PROFILE", message="IndividualProfile required"
            )
        if req.entity_type == EntityType.COMPANY and req.company is None:
            raise CustomerManagementError(code="MISSING_PROFILE", message="CompanyProfile required")
        _check_blocked(req)
        now = datetime.now(UTC)
        profile = CustomerProfile(
            customer_id=f"cust-{uuid.uuid4().hex[:12]}",
            entity_type=req.entity_type,
            kyc_status="PENDING",
            risk_level=req.risk_level,
            lifecycle_state=LifecycleState.ONBOARDING,
            created_at=now,
            updated_at=now,
            individual=req.individual,
            company=req.company,
        )
        self._persist(profile)
        logger.info("CH customer created: %s (%s)", profile.customer_id, req.entity_type)
        return profile

    def get_customer(self, customer_id: str) -> CustomerProfile:
        return self._get_or_raise(customer_id)

    def update_risk_level(self, customer_id: str, risk_level: RiskLevel) -> CustomerProfile:
        profile = self._get_or_raise(customer_id)
        profile.risk_level = risk_level
        profile.updated_at = datetime.now(UTC)
        self._persist(profile)
        logger.info("CH risk updated: %s → %s", customer_id, risk_level)
        return profile

    def transition_lifecycle(self, req: LifecycleTransitionRequest) -> CustomerProfile:
        profile = self._get_or_raise(req.customer_id)
        if not profile.lifecycle_state.can_transition_to(req.target_state):
            raise CustomerManagementError(
                code="INVALID_TRANSITION",
                message=f"Cannot transition {profile.lifecycle_state} → {req.target_state}",
            )
        old_state = profile.lifecycle_state
        profile.lifecycle_state = req.target_state
        profile.updated_at = datetime.now(UTC)
        profile.metadata["last_transition"] = {
            "from": old_state,
            "to": req.target_state,
            "reason": req.reason,
            "operator_id": req.operator_id,
            "at": profile.updated_at.isoformat(),
        }
        self._persist(profile)
        logger.info("CH lifecycle: %s %s → %s", req.customer_id, old_state, req.target_state)
        return profile

    def add_ubo(self, customer_id: str, ubo: UBORecord) -> CustomerProfile:
        profile = self._get_or_raise(customer_id)
        if profile.entity_type != EntityType.COMPANY or profile.company is None:
            raise CustomerManagementError(
                code="NOT_COMPANY",
                message="UBO registry only applies to COMPANY entities",
            )
        profile.company.ubo_registry.append(ubo)
        profile.updated_at = datetime.now(UTC)
        self._persist(profile)
        logger.info("CH UBO added: customer=%s", customer_id)  # I-09: no PII in logs
        return profile

    def list_customers(
        self, lifecycle_state: LifecycleState | None = None
    ) -> list[CustomerProfile]:
        if lifecycle_state is not None:
            rows, _ = self._client.execute(
                "SELECT profile_json FROM banxe.customers FINAL WHERE lifecycle_state = %(ls)s",
                {"ls": lifecycle_state.value},
                with_column_types=True,
            )
        else:
            rows, _ = self._client.execute(
                "SELECT profile_json FROM banxe.customers FINAL",
                with_column_types=True,
            )
        return [_profile_from_dict(json.loads(row[0])) for row in (rows or [])]

    def link_agreement(self, customer_id: str, agreement_id: str) -> None:
        profile = self._get_or_raise(customer_id)
        if agreement_id not in profile.agreement_ids:
            profile.agreement_ids.append(agreement_id)
            profile.updated_at = datetime.now(UTC)
            self._persist(profile)
            logger.info("CH agreement linked: %s → %s", customer_id, agreement_id)


# ── Factory ────────────────────────────────────────────────────────────────────


def get_customer_service() -> InMemoryCustomerService | ClickHouseCustomerService:
    import os

    backend = os.environ.get("CUSTOMER_BACKEND", "memory")
    if backend == "clickhouse":
        return ClickHouseCustomerService()
    return InMemoryCustomerService()
