"""
test_agreement_service.py — Agreement service tests
S17-02: T&C generation + e-signature + version history
FCA COBS 6, eIDAS Reg.910/2014
"""
from __future__ import annotations

import pytest

from services.agreement.agreement_port import (
    AgreementError,
    AgreementStatus,
    CreateAgreementRequest,
    ProductType,
    SignAgreementRequest,
    SignatureStatus,
)
from services.agreement.agreement_service import InMemoryAgreementService


@pytest.fixture
def svc():
    return InMemoryAgreementService()


@pytest.fixture
def emoney_req():
    return CreateAgreementRequest(
        customer_id="cust-001",
        product_type=ProductType.EMONEY_ACCOUNT,
    )


@pytest.fixture
def created_agreement(svc, emoney_req):
    return svc.create_agreement(emoney_req)


# ── Create ─────────────────────────────────────────────────────────────────────

class TestCreateAgreement:
    def test_returns_agreement(self, svc, emoney_req):
        agr = svc.create_agreement(emoney_req)
        assert agr.agreement_id.startswith("agr-")

    def test_initial_status_sent_for_signature(self, created_agreement):
        assert created_agreement.status == AgreementStatus.SENT_FOR_SIGNATURE

    def test_initial_signature_pending(self, created_agreement):
        assert created_agreement.signature_status == SignatureStatus.PENDING

    def test_terms_version_set(self, created_agreement):
        assert created_agreement.terms_version == "1.0.0"

    def test_version_history_initialized(self, created_agreement):
        assert "1.0.0" in created_agreement.version_history

    @pytest.mark.parametrize("product", list(ProductType))
    def test_all_product_types(self, svc, product):
        agr = svc.create_agreement(CreateAgreementRequest(
            customer_id="cust-001",
            product_type=product,
        ))
        assert agr.product_type == product


# ── Sign ───────────────────────────────────────────────────────────────────────

class TestSignAgreement:
    def test_sign_sets_active(self, svc, created_agreement):
        agr = svc.record_signature(SignAgreementRequest(
            agreement_id=created_agreement.agreement_id,
            customer_id=created_agreement.customer_id,
            docusign_envelope_id="env-abc123",
        ))
        assert agr.status == AgreementStatus.ACTIVE
        assert agr.signature_status == SignatureStatus.SIGNED

    def test_sign_records_envelope_id(self, svc, created_agreement):
        agr = svc.record_signature(SignAgreementRequest(
            agreement_id=created_agreement.agreement_id,
            customer_id=created_agreement.customer_id,
            docusign_envelope_id="env-xyz999",
        ))
        assert agr.docusign_envelope_id == "env-xyz999"

    def test_sign_records_timestamp(self, svc, created_agreement):
        agr = svc.record_signature(SignAgreementRequest(
            agreement_id=created_agreement.agreement_id,
            customer_id=created_agreement.customer_id,
        ))
        assert agr.signed_at is not None

    def test_double_sign_raises(self, svc, created_agreement):
        req = SignAgreementRequest(
            agreement_id=created_agreement.agreement_id,
            customer_id=created_agreement.customer_id,
        )
        svc.record_signature(req)
        with pytest.raises(AgreementError, match="ALREADY_SIGNED"):
            svc.record_signature(req)

    def test_wrong_customer_raises(self, svc, created_agreement):
        with pytest.raises(AgreementError, match="WRONG_CUSTOMER"):
            svc.record_signature(SignAgreementRequest(
                agreement_id=created_agreement.agreement_id,
                customer_id="cust-wrong",
            ))

    def test_not_found_raises(self, svc):
        with pytest.raises(AgreementError, match="NOT_FOUND"):
            svc.record_signature(SignAgreementRequest(
                agreement_id="agr-does-not-exist",
                customer_id="cust-001",
            ))


# ── Supersede / versioning ─────────────────────────────────────────────────────

class TestSupersede:
    def test_supersede_adds_version(self, svc, created_agreement):
        agr = svc.supersede(created_agreement.agreement_id, "2.0.0", "legal-counsel")
        assert "2.0.0" in agr.version_history
        assert agr.terms_version == "2.0.0"

    def test_supersede_sets_status(self, svc, created_agreement):
        agr = svc.supersede(created_agreement.agreement_id, "2.0.0", "legal-counsel")
        assert agr.status == AgreementStatus.SUPERSEDED

    def test_supersede_requires_resignature(self, svc, created_agreement):
        agr = svc.supersede(created_agreement.agreement_id, "2.0.0", "legal-counsel")
        assert agr.signature_status == SignatureStatus.PENDING

    def test_cannot_supersede_terminated(self, svc, created_agreement):
        # Force terminated status
        created_agreement.status = AgreementStatus.TERMINATED
        with pytest.raises(AgreementError, match="CANNOT_SUPERSEDE"):
            svc.supersede(created_agreement.agreement_id, "2.0.0", "op")


# ── List + terms versions ──────────────────────────────────────────────────────

class TestListAndVersions:
    def test_list_customer_agreements(self, svc):
        svc.create_agreement(CreateAgreementRequest("cust-001", ProductType.EMONEY_ACCOUNT))
        svc.create_agreement(CreateAgreementRequest("cust-001", ProductType.FX_SERVICE))
        svc.create_agreement(CreateAgreementRequest("cust-002", ProductType.EMONEY_ACCOUNT))
        agreements = svc.list_customer_agreements("cust-001")
        assert len(agreements) == 2

    def test_list_empty_for_unknown_customer(self, svc):
        assert svc.list_customer_agreements("cust-unknown") == []

    @pytest.mark.parametrize("product", list(ProductType))
    def test_get_current_terms_version(self, svc, product):
        tv = svc.get_current_terms_version(product)
        assert tv.product_type == product
        assert tv.version == "1.0.0"
        assert tv.is_current
        assert len(tv.content_hash) == 64  # SHA-256 hex

    def test_terms_version_hash_deterministic(self, svc):
        tv1 = svc.get_current_terms_version(ProductType.EMONEY_ACCOUNT)
        tv2 = svc.get_current_terms_version(ProductType.EMONEY_ACCOUNT)
        assert tv1.content_hash == tv2.content_hash
