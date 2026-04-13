"""
tests/test_api_experiments.py — Experiments router tests
S13-06-FIX-3 | banxe-emi-stack

Tests for GET/POST/PATCH /v1/experiments/* endpoints (experiments.py 43% → ≥85%).
Mocks all DI providers via app.dependency_overrides.
"""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

from fastapi.testclient import TestClient
import pytest

from api.main import app
from api.routers.experiments import (
    get_audit,
    get_designer,
    get_proposer,
    get_reporter,
    get_steward,
    get_store,
)
from services.experiment_copilot.agents.experiment_steward import ValidationError
from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
    ExperimentSummary,
)
from services.experiment_copilot.models.proposal import ChangeProposal, ProposalStatus

client = TestClient(app)


# ── Helpers ────────────────────────────────────────────────────────────────


def _now() -> datetime:
    return datetime.now(UTC)


def _make_experiment(
    exp_id: str = "exp-001",
    status: ExperimentStatus = ExperimentStatus.DRAFT,
) -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title="P2P Velocity Limits Test",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        hypothesis="Tightening P2P velocity limits will reduce the false positive rate by 15%.",
        status=status,
    )


def _make_summary(exp_id: str = "exp-001") -> ExperimentSummary:
    return ExperimentSummary(
        id=exp_id,
        title="P2P Velocity Limits Test",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        status=ExperimentStatus.DRAFT,
        created_at=_now(),
        updated_at=_now(),
        created_by="claude-code",
    )


def _make_proposal(exp_id: str = "exp-001") -> ChangeProposal:
    return ChangeProposal(
        experiment_id=exp_id,
        branch_name="exp/p2p-velocity-limits",
        pr_title="feat: tighten P2P velocity limits",
        pr_body="## Summary\n- Reduces FP rate by 15%\n\n## HITL checklist\n- [ ] CTIO review",
        status=ProposalStatus.PENDING,
    )


# ── Fixtures ───────────────────────────────────────────────────────────────


@pytest.fixture()
def mock_store():
    m = MagicMock()
    m.get.return_value = _make_experiment()
    m.list_all.return_value = [_make_summary()]
    m.list_by_status.return_value = [_make_summary()]
    return m


@pytest.fixture()
def mock_audit():
    m = MagicMock()
    m.get_entries.return_value = []
    return m


@pytest.fixture()
def mock_designer():
    m = MagicMock()
    m.design.return_value = _make_experiment()
    return m


@pytest.fixture()
def mock_steward():
    m = MagicMock()
    m.approve.return_value = _make_experiment(status=ExperimentStatus.ACTIVE)
    m.reject.return_value = _make_experiment(status=ExperimentStatus.REJECTED)
    return m


@pytest.fixture()
def mock_reporter():
    m = MagicMock()
    m.get_current_metrics.return_value.model_dump.return_value = {
        "hit_rate": 0.12,
        "false_positive_rate": 0.35,
        "sar_yield": 0.08,
        "period_days": 1,
    }
    return m


@pytest.fixture()
def mock_proposer():
    m = MagicMock()
    m.propose.return_value = _make_proposal()
    return m


@pytest.fixture(autouse=True)
def setup_overrides(
    mock_store, mock_audit, mock_designer, mock_steward, mock_reporter, mock_proposer
):
    app.dependency_overrides[get_store] = lambda: mock_store
    app.dependency_overrides[get_audit] = lambda: mock_audit
    app.dependency_overrides[get_designer] = lambda: mock_designer
    app.dependency_overrides[get_steward] = lambda: mock_steward
    app.dependency_overrides[get_reporter] = lambda: mock_reporter
    app.dependency_overrides[get_proposer] = lambda: mock_proposer
    yield
    for dep in [get_store, get_audit, get_designer, get_steward, get_reporter, get_proposer]:
        app.dependency_overrides.pop(dep, None)


# ── Design ─────────────────────────────────────────────────────────────────


def test_design_experiment_returns_201():
    resp = client.post(
        "/v1/experiments/design",
        json={
            "query": "velocity limits for P2P EMI under EBA GL 2021",
            "scope": "transaction_monitoring",
        },
    )
    assert resp.status_code == 201


def test_design_experiment_response_has_id():
    resp = client.post(
        "/v1/experiments/design",
        json={"query": "SAR filing velocity", "scope": "sar_filing"},
    )
    assert resp.json()["id"] == "exp-001"


def test_design_experiment_internal_error_returns_500(mock_designer):
    mock_designer.design.side_effect = Exception("KB unavailable")
    resp = client.post(
        "/v1/experiments/design",
        json={"query": "SAR filing velocity", "scope": "sar_filing"},
    )
    assert resp.status_code == 500


# ── List experiments ───────────────────────────────────────────────────────


def test_list_experiments_returns_200():
    resp = client.get("/v1/experiments")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_list_experiments_no_filter_returns_all(mock_store):
    mock_store.list_all.return_value = [_make_summary("e1"), _make_summary("e2")]
    resp = client.get("/v1/experiments")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


def test_list_experiments_filter_by_status_draft():
    resp = client.get("/v1/experiments?status=draft")
    assert resp.status_code == 200


def test_list_experiments_invalid_status_returns_400():
    resp = client.get("/v1/experiments?status=not_a_status")
    assert resp.status_code == 400


# ── Current metrics ────────────────────────────────────────────────────────


def test_get_current_metrics_returns_200():
    resp = client.get("/v1/experiments/metrics/current")
    assert resp.status_code == 200


def test_get_current_metrics_with_period():
    resp = client.get("/v1/experiments/metrics/current?period_days=30")
    assert resp.status_code == 200


def test_get_current_metrics_response_has_hit_rate(mock_reporter):
    mock_reporter.get_current_metrics.return_value.model_dump.return_value = {"hit_rate": 0.12}
    resp = client.get("/v1/experiments/metrics/current")
    assert "hit_rate" in resp.json()


# ── Get experiment ─────────────────────────────────────────────────────────


def test_get_experiment_found_returns_200():
    resp = client.get("/v1/experiments/exp-001")
    assert resp.status_code == 200
    assert resp.json()["id"] == "exp-001"


def test_get_experiment_not_found_returns_404(mock_store):
    mock_store.get.return_value = None
    resp = client.get("/v1/experiments/no-such-exp")
    assert resp.status_code == 404


# ── Approve ────────────────────────────────────────────────────────────────


def test_approve_experiment_returns_200():
    resp = client.patch(
        "/v1/experiments/exp-001/approve",
        json={"steward_notes": "Hypothesis well-evidenced. Approved."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "active"


def test_approve_experiment_not_found_returns_404(mock_steward):
    mock_steward.approve.side_effect = ValueError("Experiment 'no-exp' not found")
    resp = client.patch(
        "/v1/experiments/no-exp/approve",
        json={},
    )
    assert resp.status_code == 404


def test_approve_experiment_validation_error_returns_422(mock_steward):
    mock_steward.approve.side_effect = ValidationError("hypothesis too short (< 50 chars)")
    resp = client.patch(
        "/v1/experiments/exp-001/approve",
        json={},
    )
    assert resp.status_code == 422


# ── Reject ─────────────────────────────────────────────────────────────────


def test_reject_experiment_returns_200():
    resp = client.patch(
        "/v1/experiments/exp-001/reject",
        json={"reason": "Hypothesis is not grounded in the KB citation provided."},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "rejected"


def test_reject_experiment_not_found_returns_404(mock_steward):
    mock_steward.reject.side_effect = ValueError("Experiment 'no-exp' not found")
    resp = client.patch(
        "/v1/experiments/no-exp/reject",
        json={"reason": "Some reason long enough here for validation"},
    )
    assert resp.status_code == 404


def test_reject_experiment_not_draft_returns_400(mock_steward):
    mock_steward.reject.side_effect = ValueError("Experiment is not in DRAFT status")
    resp = client.patch(
        "/v1/experiments/exp-001/reject",
        json={"reason": "Experiment is not in DRAFT, rejection not allowed here."},
    )
    assert resp.status_code == 400


# ── Propose ────────────────────────────────────────────────────────────────


def test_propose_change_returns_200():
    resp = client.post(
        "/v1/experiments/exp-001/propose",
        json={"dry_run": True},
    )
    assert resp.status_code == 200
    assert resp.json()["experiment_id"] == "exp-001"


def test_propose_change_experiment_not_found_returns_404(mock_store):
    mock_store.get.return_value = None
    resp = client.post(
        "/v1/experiments/no-such-exp/propose",
        json={"dry_run": True},
    )
    assert resp.status_code == 404


def test_propose_change_value_error_returns_422(mock_proposer):
    mock_proposer.propose.side_effect = ValueError("experiment not in ACTIVE state")
    resp = client.post(
        "/v1/experiments/exp-001/propose",
        json={"dry_run": True},
    )
    assert resp.status_code == 422


def test_propose_change_runtime_error_returns_500(mock_proposer):
    mock_proposer.propose.side_effect = RuntimeError("GitHub API rate limited")
    resp = client.post(
        "/v1/experiments/exp-001/propose",
        json={"dry_run": False},
    )
    assert resp.status_code == 500


# ── Audit trail ────────────────────────────────────────────────────────────


def test_get_audit_trail_returns_200():
    resp = client.get("/v1/experiments/exp-001/audit")
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


def test_get_audit_trail_not_found_returns_404(mock_store):
    mock_store.get.return_value = None
    resp = client.get("/v1/experiments/no-such-exp/audit")
    assert resp.status_code == 404
