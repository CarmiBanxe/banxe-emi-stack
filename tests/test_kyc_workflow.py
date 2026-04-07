"""
test_kyc_workflow.py — Tests for MockKYCWorkflow / Ballerine KYC (S5-13)
FCA MLR 2017 §18-33 | banxe-emi-stack
"""
from __future__ import annotations

from decimal import Decimal

import pytest

from services.kyc.kyc_port import (
    KYCStatus,
    KYCType,
    KYCWorkflowRequest,
    RejectionReason,
)
from services.kyc.mock_kyc_workflow import MockKYCWorkflow, get_kyc_adapter


def _req(**kwargs) -> KYCWorkflowRequest:
    defaults = dict(
        customer_id="cust-test",
        kyc_type=KYCType.INDIVIDUAL,
        first_name="John",
        last_name="Smith",
        date_of_birth="1980-01-01",
        nationality="GB",
        country_of_residence="GB",
        expected_transaction_volume=Decimal("500"),
        is_pep=False,
    )
    defaults.update(kwargs)
    return KYCWorkflowRequest(**defaults)


@pytest.fixture
def kyc() -> MockKYCWorkflow:
    return MockKYCWorkflow()


class TestWorkflowCreation:
    def test_creates_workflow_pending(self, kyc):
        result = kyc.create_workflow(_req())
        assert result.status == KYCStatus.PENDING
        assert result.workflow_id.startswith("kyc-")

    def test_customer_id_preserved(self, kyc):
        result = kyc.create_workflow(_req(customer_id="cust-xyz"))
        assert result.customer_id == "cust-xyz"

    def test_expires_at_30_days(self, kyc):
        result = kyc.create_workflow(_req())
        delta = result.expires_at - result.created_at
        assert abs(delta.days - 30) <= 1


class TestBlockedJurisdictions:
    @pytest.mark.parametrize("country", ["RU", "BY", "IR", "KP", "CU", "MM"])
    def test_blocked_nationality_immediate_reject(self, kyc, country):
        result = kyc.create_workflow(_req(nationality=country))
        assert result.status == KYCStatus.REJECTED
        assert result.rejection_reason == RejectionReason.HIGH_RISK_JURISDICTION

    def test_blocked_residence_immediate_reject(self, kyc):
        result = kyc.create_workflow(_req(country_of_residence="IR"))
        assert result.status == KYCStatus.REJECTED

    def test_clean_uk_customer_pending(self, kyc):
        result = kyc.create_workflow(_req(nationality="GB", country_of_residence="GB"))
        assert result.status == KYCStatus.PENDING


class TestEDDTriggers:
    def test_pep_triggers_edd(self, kyc):
        result = kyc.create_workflow(_req(is_pep=True))
        assert result.edd_required is True

    def test_high_risk_country_triggers_edd(self, kyc):
        result = kyc.create_workflow(_req(nationality="SY"))  # FATF greylist
        assert result.edd_required is True

    def test_high_volume_triggers_edd(self, kyc):
        # I-04: ≥ £10,000 → EDD
        result = kyc.create_workflow(_req(expected_transaction_volume=Decimal("10000")))
        assert result.edd_required is True

    def test_low_volume_no_edd(self, kyc):
        result = kyc.create_workflow(_req(expected_transaction_volume=Decimal("500")))
        assert result.edd_required is False

    def test_just_below_threshold_no_edd(self, kyc):
        result = kyc.create_workflow(_req(expected_transaction_volume=Decimal("9999.99")))
        assert result.edd_required is False


class TestDocumentSubmission:
    def test_clean_customer_approved_after_documents(self, kyc):
        wf = kyc.create_workflow(_req())
        result = kyc.submit_documents(wf.workflow_id, ["passport-001", "utility-bill-001"])
        assert result.status == KYCStatus.APPROVED

    def test_approved_notes_contain_fca_reference(self, kyc):
        wf = kyc.create_workflow(_req())
        result = kyc.submit_documents(wf.workflow_id, ["passport-001"])
        assert any("MLR 2017" in n for n in result.notes)

    def test_pep_goes_to_mlro_review(self, kyc):
        wf = kyc.create_workflow(_req(is_pep=True))
        result = kyc.submit_documents(wf.workflow_id, ["passport-001"])
        assert result.status == KYCStatus.MLRO_REVIEW

    def test_high_volume_goes_to_mlro_review(self, kyc):
        wf = kyc.create_workflow(_req(expected_transaction_volume=Decimal("15000")))
        result = kyc.submit_documents(wf.workflow_id, ["passport-001"])
        assert result.status == KYCStatus.MLRO_REVIEW

    def test_requires_human_review_mlro(self, kyc):
        wf = kyc.create_workflow(_req(is_pep=True))
        result = kyc.submit_documents(wf.workflow_id, ["passport-001"])
        assert result.requires_human_review is True

    def test_empty_documents_raises(self, kyc):
        wf = kyc.create_workflow(_req())
        with pytest.raises(ValueError, match="document_id"):
            kyc.submit_documents(wf.workflow_id, [])

    def test_unknown_workflow_raises(self, kyc):
        with pytest.raises(ValueError, match="not found"):
            kyc.submit_documents("invalid-id", ["doc-001"])

    def test_risk_score_set(self, kyc):
        wf = kyc.create_workflow(_req())
        result = kyc.submit_documents(wf.workflow_id, ["passport-001"])
        assert result.risk_score is not None
        assert 0 <= result.risk_score <= 100


class TestMLROApproval:
    def test_mlro_approves_edd(self, kyc):
        wf = kyc.create_workflow(_req(is_pep=True))
        kyc.submit_documents(wf.workflow_id, ["passport-001"])
        result = kyc.approve_edd(wf.workflow_id, mlro_user_id="mlro@banxe.io")
        assert result.status == KYCStatus.APPROVED
        assert result.mlro_sign_off is True

    def test_mlro_approval_adds_audit_note(self, kyc):
        wf = kyc.create_workflow(_req(is_pep=True))
        kyc.submit_documents(wf.workflow_id, ["passport-001"])
        result = kyc.approve_edd(wf.workflow_id, mlro_user_id="mlro@banxe.io")
        assert any("mlro@banxe.io" in n for n in result.notes)

    def test_approve_edd_wrong_state_raises(self, kyc):
        wf = kyc.create_workflow(_req())
        with pytest.raises(ValueError, match="MLRO_REVIEW"):
            kyc.approve_edd(wf.workflow_id, mlro_user_id="mlro@banxe.io")

    def test_is_terminal_after_approval(self, kyc):
        wf = kyc.create_workflow(_req(is_pep=True))
        kyc.submit_documents(wf.workflow_id, ["passport-001"])
        result = kyc.approve_edd(wf.workflow_id, mlro_user_id="mlro@banxe.io")
        assert result.is_terminal is True


class TestRejection:
    def test_reject_workflow(self, kyc):
        wf = kyc.create_workflow(_req())
        result = kyc.reject_workflow(wf.workflow_id, RejectionReason.DOCUMENT_FRAUD)
        assert result.status == KYCStatus.REJECTED
        assert result.rejection_reason == RejectionReason.DOCUMENT_FRAUD

    def test_reject_terminal_raises(self, kyc):
        wf = kyc.create_workflow(_req())
        kyc.submit_documents(wf.workflow_id, ["passport-001"])  # → APPROVED
        with pytest.raises(ValueError, match="terminal"):
            kyc.reject_workflow(wf.workflow_id, RejectionReason.AML_PATTERN)


class TestGetWorkflow:
    def test_get_existing_workflow(self, kyc):
        wf = kyc.create_workflow(_req())
        fetched = kyc.get_workflow(wf.workflow_id)
        assert fetched is not None
        assert fetched.workflow_id == wf.workflow_id

    def test_get_nonexistent_returns_none(self, kyc):
        assert kyc.get_workflow("nonexistent-id") is None

    def test_health_returns_true(self, kyc):
        assert kyc.health() is True


class TestFactory:
    def test_mock_is_default(self, monkeypatch):
        monkeypatch.delenv("KYC_ADAPTER", raising=False)
        adapter = get_kyc_adapter()
        assert isinstance(adapter, MockKYCWorkflow)

    def test_explicit_mock(self, monkeypatch):
        monkeypatch.setenv("KYC_ADAPTER", "mock")
        adapter = get_kyc_adapter()
        assert isinstance(adapter, MockKYCWorkflow)
