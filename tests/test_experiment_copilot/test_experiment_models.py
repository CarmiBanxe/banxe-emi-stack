"""
tests/test_experiment_copilot/test_experiment_models.py
IL-CEC-01 | banxe-emi-stack

Tests for experiment Pydantic models: ComplianceExperiment, ExperimentSummary,
ApproveRequest, RejectRequest, DesignRequest, HITLChecklist, ChangeProposal.
"""

from __future__ import annotations

from decimal import Decimal

from services.experiment_copilot.models.experiment import (
    ApproveRequest,
    ComplianceExperiment,
    DesignRequest,
    ExperimentScope,
    ExperimentStatus,
    ExperimentSummary,
    RejectRequest,
)
from services.experiment_copilot.models.metrics import (
    ExperimentMetrics,
)
from services.experiment_copilot.models.proposal import (
    HITLChecklist,
)


class TestComplianceExperiment:
    def test_create_draft_experiment(self):
        exp = ComplianceExperiment(
            id="exp-2026-04-trans-test",
            title="Test Experiment",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            status=ExperimentStatus.DRAFT,
            hypothesis="By implementing velocity controls, we expect to reduce false positives.",
            kb_citations=["eba-gl-2021-02"],
            created_by="compliance@banxe.com",
            metrics_baseline={"hit_rate_24h": 0.25},
            metrics_target={"hit_rate_24h": 0.35},
        )
        assert exp.status == ExperimentStatus.DRAFT
        assert exp.scope == ExperimentScope.TRANSACTION_MONITORING
        assert exp.id == "exp-2026-04-trans-test"
        assert len(exp.kb_citations) == 1

    def test_experiment_default_timestamps(self):
        exp = ComplianceExperiment(
            id="exp-2026-04-sar-test",
            title="SAR Test",
            scope=ExperimentScope.SAR_FILING,
            status=ExperimentStatus.DRAFT,
            hypothesis="Testing SAR yield improvements.",
            kb_citations=[],
            created_by="user@banxe.com",
            metrics_baseline={},
            metrics_target={},
        )
        assert exp.created_at is not None
        assert exp.updated_at is not None

    def test_experiment_summary_from_experiment(self):
        exp = ComplianceExperiment(
            id="exp-2026-04-kyc-test",
            title="KYC Test",
            scope=ExperimentScope.KYC_ONBOARDING,
            status=ExperimentStatus.ACTIVE,
            hypothesis="Hypothesis about KYC.",
            kb_citations=["fca-aml-guide"],
            created_by="kyc@banxe.com",
            metrics_baseline={"hit_rate_24h": 0.3},
            metrics_target={"hit_rate_24h": 0.4},
        )
        summary = ExperimentSummary.from_experiment(exp)
        assert summary.id == "exp-2026-04-kyc-test"
        assert summary.status == ExperimentStatus.ACTIVE


class TestApproveRejectRequests:
    def test_approve_request_with_notes(self):
        req = ApproveRequest(steward_notes="Looks good, well-cited.")
        assert req.steward_notes == "Looks good, well-cited."

    def test_approve_request_empty_notes(self):
        req = ApproveRequest()
        assert req.steward_notes is None

    def test_reject_request_requires_reason(self):
        req = RejectRequest(reason="Hypothesis not falsifiable.")
        assert req.reason == "Hypothesis not falsifiable."

    def test_design_request_defaults(self):
        req = DesignRequest(
            query="reduce false positive rate for EU wire transfers",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            created_by="analyst@banxe.com",
        )
        assert req.query.startswith("reduce")
        assert req.tags == []


class TestHITLChecklist:
    def test_hitl_checklist_defaults_incomplete(self):
        checklist = HITLChecklist()
        assert not checklist.is_complete
        assert len(checklist.missing_items) == 4

    def test_hitl_checklist_complete(self):
        checklist = HITLChecklist(
            ctio_reviewed=True,
            compliance_officer_signoff=True,
            backtest_results_reviewed=True,
            rollback_plan_defined=True,
        )
        assert checklist.is_complete
        assert checklist.missing_items == []

    def test_hitl_checklist_partial(self):
        checklist = HITLChecklist(ctio_reviewed=True, backtest_results_reviewed=True)
        assert not checklist.is_complete
        assert len(checklist.missing_items) == 2


class TestExperimentMetrics:
    def test_metrics_monetary_field_is_decimal(self):
        metrics = ExperimentMetrics(
            hit_rate_24h=0.25,
            false_positive_rate=0.75,
            sar_yield=0.10,
            amount_blocked_gbp=Decimal("45000.00"),
            cases_reviewed=120,
            period_days=1,
        )
        assert isinstance(metrics.amount_blocked_gbp, Decimal)
        assert metrics.amount_blocked_gbp == Decimal("45000.00")

    def test_metrics_nullable_defaults(self):
        metrics = ExperimentMetrics(period_days=7)
        assert metrics.hit_rate_24h is None
        assert metrics.false_positive_rate is None
        assert metrics.amount_blocked_gbp is None
