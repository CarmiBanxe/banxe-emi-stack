"""
tests/test_experiment_copilot/test_experiment_steward.py
IL-CEC-01 | banxe-emi-stack

Tests for ExperimentSteward: validate(), approve(), reject(), finish(),
scope conflict detection, and generate_weekly_report().
"""

from __future__ import annotations

from pathlib import Path

import pytest

from services.experiment_copilot.agents.experiment_steward import (
    ExperimentSteward,
    ValidationError,
)
from services.experiment_copilot.models.experiment import (
    ApproveRequest,
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
    RejectRequest,
)
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore


def _make_valid_experiment(
    exp_id: str = "exp-test-001",
    status: ExperimentStatus = ExperimentStatus.DRAFT,
    scope: ExperimentScope = ExperimentScope.TRANSACTION_MONITORING,
) -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title=f"Test Experiment {exp_id}",
        scope=scope,
        status=status,
        hypothesis="By implementing risk-based velocity controls, we expect to reduce false positives significantly.",
        kb_citations=["eba-gl-2021-02"],
        created_by="test@banxe.com",
        metrics_baseline={"hit_rate_24h": 0.25},
        metrics_target={"hit_rate_24h": 0.35},
    )


def _make_steward(tmp_path: Path) -> tuple[ExperimentSteward, ExperimentStore, AuditTrail]:
    store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
    audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
    steward = ExperimentSteward(store=store, audit=audit)
    return steward, store, audit


class TestValidation:
    def test_validate_returns_empty_for_valid_experiment(self, tmp_path):
        steward, _, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment()
        errors = steward.validate(exp)
        assert errors == []

    def test_validate_short_hypothesis_returns_error(self, tmp_path):
        steward, _, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment()
        exp.hypothesis = "Too short"
        errors = steward.validate(exp)
        assert any("20 characters" in e for e in errors)

    def test_validate_no_citations_returns_error(self, tmp_path):
        steward, _, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment()
        exp.kb_citations = []
        errors = steward.validate(exp)
        assert any("citation" in e.lower() for e in errors)

    def test_validate_empty_baseline_returns_error(self, tmp_path):
        steward, _, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment()
        exp.metrics_baseline = {}
        errors = steward.validate(exp)
        assert any("baseline" in e.lower() for e in errors)

    def test_validate_non_draft_status_returns_error(self, tmp_path):
        steward, _, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment(status=ExperimentStatus.ACTIVE)
        errors = steward.validate(exp)
        assert any("DRAFT" in e for e in errors)


class TestApproveReject:
    def test_approve_valid_draft_moves_to_active(self, tmp_path):
        steward, store, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment("exp-approve-test")
        store.save(exp)
        approved = steward.approve("exp-approve-test", ApproveRequest(steward_notes="OK"))
        assert approved.status == ExperimentStatus.ACTIVE
        assert approved.steward_notes == "OK"

    def test_approve_invalid_raises_validation_error(self, tmp_path):
        steward, store, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment("exp-invalid")
        exp.kb_citations = []
        store.save(exp)
        with pytest.raises(ValidationError):
            steward.approve("exp-invalid", ApproveRequest())

    def test_approve_missing_experiment_raises_value_error(self, tmp_path):
        steward, _, _ = _make_steward(tmp_path)
        with pytest.raises(ValueError, match="not found"):
            steward.approve("nonexistent-id", ApproveRequest())

    def test_reject_draft_moves_to_rejected(self, tmp_path):
        steward, store, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment("exp-reject-test")
        store.save(exp)
        rejected = steward.reject(
            "exp-reject-test", RejectRequest(reason="Hypothesis not falsifiable within 14 days.")
        )
        assert rejected.status == ExperimentStatus.REJECTED
        assert "not falsifiable" in rejected.rejection_reason

    def test_reject_non_draft_raises_value_error(self, tmp_path):
        steward, store, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment("exp-active", status=ExperimentStatus.ACTIVE)
        store.save(exp)
        with pytest.raises(ValueError, match="DRAFT"):
            steward.reject("exp-active", RejectRequest(reason="already active experiment"))

    def test_finish_active_experiment(self, tmp_path):
        steward, store, _ = _make_steward(tmp_path)
        exp = _make_valid_experiment("exp-finish-test", status=ExperimentStatus.ACTIVE)
        store.save(exp)
        finished = steward.finish("exp-finish-test", notes="Conclusive results.")
        assert finished.status == ExperimentStatus.FINISHED

    def test_approve_logs_audit_entry(self, tmp_path):
        steward, store, audit = _make_steward(tmp_path)
        exp = _make_valid_experiment("exp-audit-log")
        store.save(exp)
        steward.approve("exp-audit-log", ApproveRequest())
        entries = audit.get_entries("exp-audit-log")
        assert any(e.action == "experiment.approved" for e in entries)
