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
from services.kyc.kyc_port import KYCStatus


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
        agr = svc.create_agreement(
            CreateAgreementRequest(
                customer_id="cust-001",
                product_type=product,
            )
        )
        assert agr.product_type == product


# ── Sign ───────────────────────────────────────────────────────────────────────


class TestSignAgreement:
    def test_sign_sets_active(self, svc, created_agreement):
        agr = svc.record_signature(
            SignAgreementRequest(
                agreement_id=created_agreement.agreement_id,
                customer_id=created_agreement.customer_id,
                docusign_envelope_id="env-abc123",
            )
        )
        assert agr.status == AgreementStatus.ACTIVE
        assert agr.signature_status == SignatureStatus.SIGNED

    def test_sign_records_envelope_id(self, svc, created_agreement):
        agr = svc.record_signature(
            SignAgreementRequest(
                agreement_id=created_agreement.agreement_id,
                customer_id=created_agreement.customer_id,
                docusign_envelope_id="env-xyz999",
            )
        )
        assert agr.docusign_envelope_id == "env-xyz999"

    def test_sign_records_timestamp(self, svc, created_agreement):
        agr = svc.record_signature(
            SignAgreementRequest(
                agreement_id=created_agreement.agreement_id,
                customer_id=created_agreement.customer_id,
            )
        )
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
            svc.record_signature(
                SignAgreementRequest(
                    agreement_id=created_agreement.agreement_id,
                    customer_id="cust-wrong",
                )
            )

    def test_not_found_raises(self, svc):
        with pytest.raises(AgreementError, match="NOT_FOUND"):
            svc.record_signature(
                SignAgreementRequest(
                    agreement_id="agr-does-not-exist",
                    customer_id="cust-001",
                )
            )


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


# ── S13-04: KYC gate ──────────────────────────────────────────────────────────


def _make_kyc_checker(status: KYCStatus):
    """Factory: returns a callable that always returns the given KYCStatus."""

    def checker(customer_id: str) -> KYCStatus:
        return status

    return checker


class TestKycGate:
    """record_signature() must enforce KYC APPROVED gate (FCA COBS 6)."""

    def _svc(self, kyc_status: KYCStatus | None = None):
        checker = _make_kyc_checker(kyc_status) if kyc_status is not None else None
        return InMemoryAgreementService(kyc_checker=checker)

    def _create_and_sign(self, svc, customer_id="cust-kyc"):
        agr = svc.create_agreement(CreateAgreementRequest(customer_id, ProductType.EMONEY_ACCOUNT))
        req = SignAgreementRequest(
            agreement_id=agr.agreement_id,
            customer_id=customer_id,
            signature_provider="docusign",
        )
        return svc.record_signature(req)

    def test_no_kyc_checker_allows_signing(self):
        """Default (no KYC checker) preserves existing behaviour — no gate."""
        svc = self._svc(kyc_status=None)
        result = self._create_and_sign(svc)
        assert result.status == AgreementStatus.ACTIVE

    def test_approved_kyc_allows_signing(self):
        svc = self._svc(KYCStatus.APPROVED)
        result = self._create_and_sign(svc)
        assert result.status == AgreementStatus.ACTIVE

    def test_pending_kyc_blocks_signing(self):
        svc = self._svc(KYCStatus.PENDING)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        with pytest.raises(AgreementError, match="KYC_REQUIRED"):
            svc.record_signature(SignAgreementRequest(agr.agreement_id, "cust-kyc", "docusign"))

    def test_rejected_kyc_blocks_signing(self):
        svc = self._svc(KYCStatus.REJECTED)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        with pytest.raises(AgreementError, match="KYC_REQUIRED"):
            svc.record_signature(SignAgreementRequest(agr.agreement_id, "cust-kyc", "docusign"))

    def test_edd_required_kyc_blocks_signing(self):
        svc = self._svc(KYCStatus.EDD_REQUIRED)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        with pytest.raises(AgreementError, match="KYC_REQUIRED"):
            svc.record_signature(SignAgreementRequest(agr.agreement_id, "cust-kyc", "docusign"))

    def test_mlro_review_blocks_signing(self):
        svc = self._svc(KYCStatus.MLRO_REVIEW)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        with pytest.raises(AgreementError, match="KYC_REQUIRED"):
            svc.record_signature(SignAgreementRequest(agr.agreement_id, "cust-kyc", "docusign"))

    def test_kyc_error_message_contains_status(self):
        svc = self._svc(KYCStatus.PENDING)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        try:
            svc.record_signature(SignAgreementRequest(agr.agreement_id, "cust-kyc", "docusign"))
        except AgreementError as e:
            assert "KYCStatus.PENDING" in e.message or "PENDING" in e.message

    def test_kyc_checker_receives_correct_customer_id(self):
        called_with = []

        def tracker(cid: str) -> KYCStatus:
            called_with.append(cid)
            return KYCStatus.APPROVED

        svc = InMemoryAgreementService(kyc_checker=tracker)
        self._create_and_sign(svc, customer_id="cust-abc-123")
        assert called_with == ["cust-abc-123"]

    def test_kyc_gate_does_not_affect_create_agreement(self):
        """create_agreement should never block — KYC gate only on signing."""
        svc = self._svc(KYCStatus.REJECTED)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        assert agr.status == AgreementStatus.SENT_FOR_SIGNATURE

    @pytest.mark.parametrize(
        "status",
        [
            KYCStatus.PENDING,
            KYCStatus.DOCUMENT_REVIEW,
            KYCStatus.RISK_ASSESSMENT,
            KYCStatus.EDD_REQUIRED,
            KYCStatus.MLRO_REVIEW,
            KYCStatus.REJECTED,
            KYCStatus.EXPIRED,
        ],
    )
    def test_all_non_approved_statuses_block_signing(self, status):
        svc = self._svc(status)
        agr = svc.create_agreement(CreateAgreementRequest("cust-kyc", ProductType.EMONEY_ACCOUNT))
        with pytest.raises(AgreementError, match="KYC_REQUIRED"):
            svc.record_signature(SignAgreementRequest(agr.agreement_id, "cust-kyc", "docusign"))
