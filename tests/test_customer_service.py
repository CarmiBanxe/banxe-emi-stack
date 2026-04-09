"""
test_customer_service.py — CustomerManagement service tests
S17-01 (dual entity) + S17-09 (lifecycle state machine)
FCA: UK GDPR Art.5, FCA COBS 9A, MLR 2017
"""

from __future__ import annotations

from datetime import date

import pytest

from services.customer.customer_port import (
    Address,
    CompanyProfile,
    CreateCustomerRequest,
    CustomerManagementError,
    EntityType,
    IndividualProfile,
    LifecycleState,
    LifecycleTransitionRequest,
    RiskLevel,
    UBORecord,
)
from services.customer.customer_service import InMemoryCustomerService

# ── Fixtures ───────────────────────────────────────────────────────────────────


@pytest.fixture
def svc():
    return InMemoryCustomerService()


@pytest.fixture
def uk_address():
    return Address(line1="1 High Street", city="London", country="GB", postcode="EC1A 1BB")


@pytest.fixture
def individual_req(uk_address):
    return CreateCustomerRequest(
        entity_type=EntityType.INDIVIDUAL,
        individual=IndividualProfile(
            first_name="Alice",
            last_name="Smith",
            date_of_birth=date(1990, 5, 15),
            nationality="GB",
            address=uk_address,
        ),
    )


@pytest.fixture
def company_req():
    return CreateCustomerRequest(
        entity_type=EntityType.COMPANY,
        company=CompanyProfile(
            company_name="Acme Ltd",
            registration_number="12345678",
            country_of_incorporation="GB",
            registered_address=Address(line1="100 Business Park", city="London", country="GB"),
        ),
    )


@pytest.fixture
def created_individual(svc, individual_req):
    return svc.create_customer(individual_req)


@pytest.fixture
def created_company(svc, company_req):
    return svc.create_customer(company_req)


# ── Create customer ────────────────────────────────────────────────────────────


class TestCreateIndividual:
    def test_returns_profile(self, svc, individual_req):
        profile = svc.create_customer(individual_req)
        assert profile.customer_id.startswith("cust-")
        assert profile.entity_type == EntityType.INDIVIDUAL

    def test_initial_state_onboarding(self, svc, individual_req):
        profile = svc.create_customer(individual_req)
        assert profile.lifecycle_state == LifecycleState.ONBOARDING

    def test_initial_kyc_pending(self, svc, individual_req):
        profile = svc.create_customer(individual_req)
        assert profile.kyc_status == "PENDING"

    def test_display_name(self, created_individual):
        assert created_individual.display_name == "Alice Smith"

    def test_is_not_active_when_onboarding(self, created_individual):
        assert not created_individual.is_active

    def test_missing_individual_profile_raises(self, svc):
        req = CreateCustomerRequest(entity_type=EntityType.INDIVIDUAL)
        with pytest.raises(CustomerManagementError, match="IndividualProfile required"):
            svc.create_customer(req)


class TestCreateCompany:
    def test_returns_profile(self, svc, company_req):
        profile = svc.create_customer(company_req)
        assert profile.entity_type == EntityType.COMPANY

    def test_display_name(self, created_company):
        assert created_company.display_name == "Acme Ltd"

    def test_missing_company_profile_raises(self, svc):
        req = CreateCustomerRequest(entity_type=EntityType.COMPANY)
        with pytest.raises(CustomerManagementError, match="CompanyProfile required"):
            svc.create_customer(req)


# ── Blocked jurisdictions (I-02) ───────────────────────────────────────────────


@pytest.mark.parametrize("nationality", ["RU", "BY", "IR", "KP", "CU", "MM"])
class TestBlockedNationality:
    def test_blocked_nationality_raises(self, nationality, svc):
        req = CreateCustomerRequest(
            entity_type=EntityType.INDIVIDUAL,
            individual=IndividualProfile(
                first_name="Test",
                last_name="User",
                date_of_birth=date(1990, 1, 1),
                nationality=nationality,
                address=Address(line1="1 St", city="Moscow", country="GB"),
            ),
        )
        with pytest.raises(CustomerManagementError, match="BLOCKED_JURISDICTION"):
            svc.create_customer(req)


@pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM"])
class TestBlockedAddressCountry:
    def test_blocked_country_raises(self, country, svc):
        req = CreateCustomerRequest(
            entity_type=EntityType.INDIVIDUAL,
            individual=IndividualProfile(
                first_name="Test",
                last_name="User",
                date_of_birth=date(1990, 1, 1),
                nationality="GB",
                address=Address(line1="1 St", city="City", country=country),
            ),
        )
        with pytest.raises(CustomerManagementError, match="BLOCKED_JURISDICTION"):
            svc.create_customer(req)


# ── Lifecycle state machine (S17-09) ───────────────────────────────────────────


class TestLifecycleTransitions:
    def test_onboarding_to_active(self, svc, created_individual):
        req = LifecycleTransitionRequest(
            customer_id=created_individual.customer_id,
            target_state=LifecycleState.ACTIVE,
            reason="KYC approved",
            operator_id="kyc-agent",
        )
        profile = svc.transition_lifecycle(req)
        assert profile.lifecycle_state == LifecycleState.ACTIVE
        assert profile.is_active

    def test_active_to_dormant(self, svc, created_individual):
        svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=created_individual.customer_id,
                target_state=LifecycleState.ACTIVE,
                reason="KYC approved",
                operator_id="op",
            )
        )
        svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=created_individual.customer_id,
                target_state=LifecycleState.DORMANT,
                reason=">12 months inactive",
                operator_id="cron",
            )
        )
        profile = svc.get_customer(created_individual.customer_id)
        assert profile.lifecycle_state == LifecycleState.DORMANT

    def test_dormant_back_to_active(self, svc, created_individual):
        cid = created_individual.customer_id
        for state, reason in [
            (LifecycleState.ACTIVE, "KYC"),
            (LifecycleState.DORMANT, "inactive"),
        ]:
            svc.transition_lifecycle(
                LifecycleTransitionRequest(
                    customer_id=cid,
                    target_state=state,
                    reason=reason,
                    operator_id="op",
                )
            )
        profile = svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=cid,
                target_state=LifecycleState.ACTIVE,
                reason="Customer reactivated",
                operator_id="support",
            )
        )
        assert profile.lifecycle_state == LifecycleState.ACTIVE

    def test_invalid_transition_raises(self, svc, created_individual):
        # ONBOARDING → DECEASED is not allowed
        with pytest.raises(CustomerManagementError, match="INVALID_TRANSITION"):
            svc.transition_lifecycle(
                LifecycleTransitionRequest(
                    customer_id=created_individual.customer_id,
                    target_state=LifecycleState.DECEASED,
                    reason="error",
                    operator_id="op",
                )
            )

    def test_offboarded_no_transitions(self, svc, created_individual):
        cid = created_individual.customer_id
        svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=cid,
                target_state=LifecycleState.ACTIVE,
                reason="ok",
                operator_id="op",
            )
        )
        svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=cid,
                target_state=LifecycleState.OFFBOARDED,
                reason="account closure",
                operator_id="op",
            )
        )
        with pytest.raises(CustomerManagementError, match="INVALID_TRANSITION"):
            svc.transition_lifecycle(
                LifecycleTransitionRequest(
                    customer_id=cid,
                    target_state=LifecycleState.ACTIVE,
                    reason="re-open",
                    operator_id="op",
                )
            )

    def test_transition_records_metadata(self, svc, created_individual):
        cid = created_individual.customer_id
        svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=cid,
                target_state=LifecycleState.ACTIVE,
                reason="KYC approved",
                operator_id="kyc-agent",
            )
        )
        profile = svc.get_customer(cid)
        meta = profile.metadata["last_transition"]
        assert meta["reason"] == "KYC approved"
        assert meta["operator_id"] == "kyc-agent"


# ── Risk level ─────────────────────────────────────────────────────────────────


class TestRiskLevel:
    def test_update_risk_level(self, svc, created_individual):
        profile = svc.update_risk_level(created_individual.customer_id, RiskLevel.HIGH)
        assert profile.risk_level == RiskLevel.HIGH

    def test_update_nonexistent_raises(self, svc):
        with pytest.raises(CustomerManagementError, match="NOT_FOUND"):
            svc.update_risk_level("no-such-id", RiskLevel.HIGH)


# ── UBO registry (S17-10, KYB) ────────────────────────────────────────────────


class TestUBORegistry:
    def test_add_ubo_to_company(self, svc, created_company):
        ubo = UBORecord(
            full_name="Bob Owner", role="ubo", ownership_pct=__import__("decimal").Decimal("51.0")
        )
        profile = svc.add_ubo(created_company.customer_id, ubo)
        assert len(profile.company.ubo_registry) == 1
        assert profile.company.ubo_registry[0].full_name == "Bob Owner"

    def test_add_ubo_to_individual_raises(self, svc, created_individual):
        ubo = UBORecord(full_name="Test", role="director")
        with pytest.raises(CustomerManagementError, match="NOT_COMPANY"):
            svc.add_ubo(created_individual.customer_id, ubo)

    def test_multiple_ubos(self, svc, created_company):
        from decimal import Decimal

        svc.add_ubo(created_company.customer_id, UBORecord("Alice", "director", Decimal("30")))
        svc.add_ubo(created_company.customer_id, UBORecord("Bob", "ubo", Decimal("70")))
        profile = svc.get_customer(created_company.customer_id)
        assert len(profile.company.ubo_registry) == 2


# ── Listing + agreement linking ────────────────────────────────────────────────


class TestListAndLink:
    def test_list_all(self, svc, individual_req, company_req):
        svc.create_customer(individual_req)
        svc.create_customer(company_req)
        assert len(svc.list_customers()) == 2

    def test_list_by_state(self, svc, individual_req, company_req):
        c1 = svc.create_customer(individual_req)
        svc.create_customer(company_req)
        svc.transition_lifecycle(
            LifecycleTransitionRequest(
                customer_id=c1.customer_id,
                target_state=LifecycleState.ACTIVE,
                reason="approved",
                operator_id="op",
            )
        )
        active = svc.list_customers(LifecycleState.ACTIVE)
        onboarding = svc.list_customers(LifecycleState.ONBOARDING)
        assert len(active) == 1
        assert len(onboarding) == 1

    def test_link_agreement(self, svc, created_individual):
        svc.link_agreement(created_individual.customer_id, "agr-abc123")
        profile = svc.get_customer(created_individual.customer_id)
        assert "agr-abc123" in profile.agreement_ids

    def test_link_agreement_idempotent(self, svc, created_individual):
        cid = created_individual.customer_id
        svc.link_agreement(cid, "agr-abc123")
        svc.link_agreement(cid, "agr-abc123")
        profile = svc.get_customer(cid)
        assert profile.agreement_ids.count("agr-abc123") == 1
