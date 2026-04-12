"""
tests/test_experiment_copilot/test_experiment_store.py
IL-CEC-01 | banxe-emi-stack

Tests for ExperimentStore: save, get, list_by_status, list_all,
count_by_status, index rebuild, and status transitions.
"""

from __future__ import annotations

import json

from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentScope,
    ExperimentStatus,
)
from services.experiment_copilot.store.experiment_store import ExperimentStore


def _make_experiment(
    exp_id: str = "exp-2026-04-test-001",
    status: ExperimentStatus = ExperimentStatus.DRAFT,
    scope: ExperimentScope = ExperimentScope.TRANSACTION_MONITORING,
) -> ComplianceExperiment:
    return ComplianceExperiment(
        id=exp_id,
        title=f"Test Experiment {exp_id}",
        scope=scope,
        status=status,
        hypothesis="Hypothesis: by tuning velocity we expect to reduce false positives.",
        kb_citations=["eba-gl-2021-02"],
        created_by="test@banxe.com",
        metrics_baseline={"hit_rate_24h": 0.25},
        metrics_target={"hit_rate_24h": 0.35},
    )


class TestExperimentStoreSaveGet:
    def test_save_and_get_draft(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        exp = _make_experiment("exp-2026-04-save-test", ExperimentStatus.DRAFT)
        store.save(exp)
        retrieved = store.get("exp-2026-04-save-test")
        assert retrieved is not None
        assert retrieved.id == "exp-2026-04-save-test"
        assert retrieved.status == ExperimentStatus.DRAFT

    def test_get_missing_returns_none(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        assert store.get("nonexistent-id") is None

    def test_save_moves_between_status_dirs(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        exp = _make_experiment("exp-2026-04-move-test", ExperimentStatus.DRAFT)
        store.save(exp)
        draft_file = tmp_path / "draft" / "exp-2026-04-move-test.yaml"
        assert draft_file.exists()

        exp.status = ExperimentStatus.ACTIVE
        store.save(exp)
        active_file = tmp_path / "active" / "exp-2026-04-move-test.yaml"
        assert active_file.exists()
        assert not draft_file.exists()

    def test_save_updates_index(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        exp = _make_experiment("exp-2026-04-index-test", ExperimentStatus.DRAFT)
        store.save(exp)
        index_file = tmp_path / "index.json"
        assert index_file.exists()
        idx = json.loads(index_file.read_text())
        assert idx["total"] == 1


class TestExperimentStoreList:
    def test_list_by_status_draft(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        store.save(_make_experiment("exp-draft-1", ExperimentStatus.DRAFT))
        store.save(_make_experiment("exp-draft-2", ExperimentStatus.DRAFT))
        store.save(_make_experiment("exp-active-1", ExperimentStatus.ACTIVE))

        drafts = store.list_by_status(ExperimentStatus.DRAFT)
        assert len(drafts) == 2
        assert all(s.status == ExperimentStatus.DRAFT for s in drafts)

    def test_list_all_returns_all_experiments(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        store.save(_make_experiment("exp-a", ExperimentStatus.DRAFT))
        store.save(_make_experiment("exp-b", ExperimentStatus.ACTIVE))
        store.save(_make_experiment("exp-c", ExperimentStatus.FINISHED))

        all_exps = store.list_all()
        assert len(all_exps) == 3

    def test_list_empty_returns_empty(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        assert store.list_by_status(ExperimentStatus.DRAFT) == []
        assert store.list_all() == []


class TestExperimentStoreCountAndIndex:
    def test_count_by_status(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        store.save(_make_experiment("exp-1", ExperimentStatus.DRAFT))
        store.save(_make_experiment("exp-2", ExperimentStatus.DRAFT))
        store.save(_make_experiment("exp-3", ExperimentStatus.ACTIVE))
        store.save(_make_experiment("exp-4", ExperimentStatus.FINISHED))

        counts = store.count_by_status()
        assert counts["draft"] == 2
        assert counts["active"] == 1
        assert counts["finished"] == 1
        assert counts.get("rejected", 0) == 0

    def test_get_index(self, tmp_path):
        store = ExperimentStore(experiments_dir=str(tmp_path))
        store.save(_make_experiment("exp-idx-1", ExperimentStatus.DRAFT))
        idx = store.get_index()
        assert idx["total"] == 1
        assert len(idx["experiments"]) == 1
