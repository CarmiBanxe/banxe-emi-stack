"""
tests/test_experiment_copilot/test_experiment_designer.py
IL-CEC-01 | banxe-emi-stack

Tests for ExperimentDesigner: design(), ID generation, hypothesis generation,
KB port DI, and metrics baseline loading.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from services.experiment_copilot.agents.experiment_designer import (
    ExperimentDesigner,
    InMemoryKBPort,
)
from services.experiment_copilot.models.experiment import (
    DesignRequest,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.store.audit_trail import AuditTrail
from services.experiment_copilot.store.experiment_store import ExperimentStore


def _make_designer(tmp_path: Path, baselines_path: str | None = None) -> ExperimentDesigner:
    store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
    audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
    return ExperimentDesigner(
        store=store,
        audit=audit,
        kb_port=InMemoryKBPort(),
        baselines_path=baselines_path or str(tmp_path / "baselines.yaml"),
    )


class TestExperimentDesignerDesign:
    def test_design_creates_draft_experiment(self, tmp_path):
        designer = _make_designer(tmp_path)
        req = DesignRequest(
            query="reduce false positive rate for EU wire transfers",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            created_by="analyst@banxe.com",
        )
        exp = designer.design(req)
        assert exp.status == ExperimentStatus.DRAFT
        assert exp.scope == ExperimentScope.TRANSACTION_MONITORING
        assert len(exp.kb_citations) > 0

    def test_design_generates_unique_id(self, tmp_path):
        designer = _make_designer(tmp_path)
        req1 = DesignRequest(
            query="reduce false positives",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            created_by="a@banxe.com",
        )
        req2 = DesignRequest(
            query="improve hit rate",
            scope=ExperimentScope.KYC_ONBOARDING,
            created_by="b@banxe.com",
        )
        exp1 = designer.design(req1)
        exp2 = designer.design(req2)
        assert exp1.id != exp2.id

    def test_design_persists_to_store(self, tmp_path):
        designer = _make_designer(tmp_path)
        req = DesignRequest(
            query="improve SAR yield",
            scope=ExperimentScope.SAR_FILING,
            created_by="mlro@banxe.com",
        )
        exp = designer.design(req)
        store = ExperimentStore(experiments_dir=str(tmp_path / "experiments"))
        retrieved = store.get(exp.id)
        assert retrieved is not None
        assert retrieved.id == exp.id

    def test_design_logs_audit_entry(self, tmp_path):
        designer = _make_designer(tmp_path)
        req = DesignRequest(
            query="tune KYC velocity controls",
            scope=ExperimentScope.KYC_ONBOARDING,
            created_by="kyc@banxe.com",
        )
        exp = designer.design(req)
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        entries = audit.get_entries(exp.id)
        assert len(entries) == 1
        assert entries[0].action == "experiment.created"

    def test_design_includes_scope_tag(self, tmp_path):
        designer = _make_designer(tmp_path)
        req = DesignRequest(
            query="velocity controls for high-risk countries",
            scope=ExperimentScope.RISK_SCORING,
            created_by="risk@banxe.com",
        )
        exp = designer.design(req)
        assert ExperimentScope.RISK_SCORING.value in exp.tags

    def test_design_with_baselines_sets_metrics(self, tmp_path):
        baselines_path = tmp_path / "baselines.yaml"
        baselines_data = {
            "baselines": {
                "hit_rate_24h": {"current": 0.25, "target": 0.35},
                "false_positive_rate": {"current": 0.75, "target": 0.60},
                "sar_yield": {"current": 0.10, "target": 0.15},
            }
        }
        baselines_path.write_text(yaml.dump(baselines_data))
        designer = _make_designer(tmp_path, baselines_path=str(baselines_path))
        req = DesignRequest(
            query="improve hit rate via risk scoring",
            scope=ExperimentScope.TRANSACTION_MONITORING,
            created_by="analyst@banxe.com",
        )
        exp = designer.design(req)
        assert exp.metrics_baseline.get("hit_rate_24h") == 0.25
        assert exp.metrics_target.get("hit_rate_24h") == 0.35

    def test_design_hypothesis_is_long_enough(self, tmp_path):
        designer = _make_designer(tmp_path)
        req = DesignRequest(
            query="reduce alert fatigue",
            scope=ExperimentScope.CASE_MANAGEMENT,
            created_by="ops@banxe.com",
        )
        exp = designer.design(req)
        assert len(exp.hypothesis.strip()) >= 20
