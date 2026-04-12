"""
tests/test_experiment_copilot/test_api_routes.py
IL-CEC-01 | banxe-emi-stack

Tests for the 8 experiment FastAPI endpoints using TestClient with InMemory stubs.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

from api.routers.experiments import (
    get_audit,
    get_designer,
    get_proposer,
    get_reporter,
    get_steward,
    get_store,
    router,
)
from services.experiment_copilot.agents.change_proposer import (
    ChangeProposer,
    InMemoryGitHubPort,
)
from services.experiment_copilot.agents.experiment_designer import (
    ExperimentDesigner,
    InMemoryKBPort,
)
from services.experiment_copilot.agents.experiment_steward import ExperimentSteward
from services.experiment_copilot.agents.metrics_reporter import (
    InMemoryClickHousePort,
    MetricsReporter,
)
from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore


@pytest.fixture
def app_with_overrides(tmp_path):
    """Create a FastAPI app with dependency overrides using tmp_path stores."""
    store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
    audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
    github = InMemoryGitHubPort()

    app = FastAPI()
    app.include_router(router)

    app.dependency_overrides[get_store] = lambda: store
    app.dependency_overrides[get_audit] = lambda: audit
    app.dependency_overrides[get_designer] = lambda: ExperimentDesigner(
        store=store, audit=audit, kb_port=InMemoryKBPort()
    )
    app.dependency_overrides[get_steward] = lambda: ExperimentSteward(store=store, audit=audit)
    app.dependency_overrides[get_reporter] = lambda: MetricsReporter(
        store=store, audit=audit, clickhouse=InMemoryClickHousePort()
    )
    app.dependency_overrides[get_proposer] = lambda: ChangeProposer(audit=audit, github=github)
    return app, store, audit


def _make_valid_experiment(
    exp_id: str = "exp-test-001",
    status: ExperimentStatus = ExperimentStatus.DRAFT,
) -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title="Test Experiment",
        scope=ExperimentScope.TRANSACTION_MONITORING,
        status=status,
        hypothesis="By implementing risk-based velocity controls, we expect to reduce false positives.",
        kb_citations=["eba-gl-2021-02"],
        created_by="test@banxe.com",
        metrics_baseline={"hit_rate_24h": 0.25},
        metrics_target={"hit_rate_24h": 0.35},
    )


class TestDesignEndpoint:
    def test_post_design_returns_201(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        payload = {
            "query": "reduce false positives for EU wire transfers",
            "scope": "transaction_monitoring",
            "created_by": "analyst@banxe.com",
        }
        response = client.post("/experiments/design", json=payload)
        assert response.status_code == 201
        data = response.json()
        assert data["status"] == "draft"
        assert data["scope"] == "transaction_monitoring"

    def test_post_design_persists_experiment(self, app_with_overrides):
        app, store, _ = app_with_overrides
        client = TestClient(app)
        payload = {
            "query": "tune KYC velocity controls",
            "scope": "kyc_onboarding",
            "created_by": "kyc@banxe.com",
        }
        response = client.post("/experiments/design", json=payload)
        assert response.status_code == 201
        exp_id = response.json()["id"]
        assert store.get(exp_id) is not None


class TestListEndpoint:
    def test_get_list_returns_empty_initially(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.get("/experiments")
        assert response.status_code == 200
        assert response.json() == []

    def test_get_list_returns_saved_experiments(self, app_with_overrides):
        app, store, _ = app_with_overrides
        store.save(_make_valid_experiment("exp-list-1"))
        store.save(_make_valid_experiment("exp-list-2"))
        client = TestClient(app)
        response = client.get("/experiments")
        assert response.status_code == 200
        assert len(response.json()) == 2

    def test_get_list_filters_by_status(self, app_with_overrides):
        app, store, _ = app_with_overrides
        store.save(_make_valid_experiment("exp-draft", ExperimentStatus.DRAFT))
        store.save(_make_valid_experiment("exp-active", ExperimentStatus.ACTIVE))
        client = TestClient(app)
        response = client.get("/experiments?status=draft")
        assert response.status_code == 200
        results = response.json()
        assert all(r["status"] == "draft" for r in results)

    def test_get_list_invalid_status_returns_400(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.get("/experiments?status=invalid_status")
        assert response.status_code == 400


class TestGetExperimentEndpoint:
    def test_get_experiment_returns_experiment(self, app_with_overrides):
        app, store, _ = app_with_overrides
        store.save(_make_valid_experiment("exp-get-test"))
        client = TestClient(app)
        response = client.get("/experiments/exp-get-test")
        assert response.status_code == 200
        assert response.json()["id"] == "exp-get-test"

    def test_get_experiment_not_found_returns_404(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.get("/experiments/nonexistent-id")
        assert response.status_code == 404


class TestApproveRejectEndpoints:
    def test_patch_approve_valid_draft(self, app_with_overrides):
        app, store, _ = app_with_overrides
        store.save(_make_valid_experiment("exp-approve"))
        client = TestClient(app)
        response = client.patch(
            "/experiments/exp-approve/approve",
            json={"steward_notes": "Approved after review."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "active"

    def test_patch_approve_missing_returns_404(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.patch(
            "/experiments/missing-id/approve",
            json={"steward_notes": ""},
        )
        assert response.status_code == 404

    def test_patch_reject_draft(self, app_with_overrides):
        app, store, _ = app_with_overrides
        store.save(_make_valid_experiment("exp-reject"))
        client = TestClient(app)
        response = client.patch(
            "/experiments/exp-reject/reject",
            json={"reason": "Insufficient evidence base."},
        )
        assert response.status_code == 200
        assert response.json()["status"] == "rejected"


class TestMetricsEndpoint:
    def test_get_current_metrics_returns_200(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.get("/experiments/metrics/current")
        assert response.status_code == 200
        data = response.json()
        assert "hit_rate_24h" in data

    def test_get_current_metrics_custom_period(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.get("/experiments/metrics/current?period_days=7")
        assert response.status_code == 200
        assert response.json()["period_days"] == 7


class TestProposeEndpoint:
    def test_post_propose_dry_run(self, app_with_overrides):
        app, store, _ = app_with_overrides
        store.save(_make_valid_experiment("exp-propose", ExperimentStatus.ACTIVE))
        client = TestClient(app)
        response = client.post(
            "/experiments/exp-propose/propose",
            json={"dry_run": True},
        )
        assert response.status_code == 200
        data = response.json()
        assert data["experiment_id"] == "exp-propose"
        assert "compliance/exp-" in data["branch_name"]

    def test_post_propose_not_found_returns_404(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.post(
            "/experiments/missing-id/propose",
            json={"dry_run": True},
        )
        assert response.status_code == 404


class TestAuditTrailEndpoint:
    def test_get_audit_returns_entries(self, app_with_overrides):
        app, store, audit = app_with_overrides
        store.save(_make_valid_experiment("exp-audit-trail"))
        audit.log(
            actor="steward",
            action="experiment.approved",
            experiment_id="exp-audit-trail",
        )
        client = TestClient(app)
        response = client.get("/experiments/exp-audit-trail/audit")
        assert response.status_code == 200
        entries = response.json()
        assert len(entries) == 1
        assert entries[0]["action"] == "experiment.approved"

    def test_get_audit_not_found_returns_404(self, app_with_overrides):
        app, _, _ = app_with_overrides
        client = TestClient(app)
        response = client.get("/experiments/nonexistent/audit")
        assert response.status_code == 404
