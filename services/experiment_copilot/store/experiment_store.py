"""
services/experiment_copilot/store/experiment_store.py — YAML experiment store
IL-CEC-01 | banxe-emi-stack

Git-tracked YAML store for compliance experiments.
Layout: compliance-experiments/{draft|active|finished|rejected}/{experiment_id}.yaml
Index:  compliance-experiments/index.json (auto-regenerated)
"""

from __future__ import annotations

from datetime import datetime
import json
import logging
from pathlib import Path
from typing import Any

import yaml

from services.experiment_copilot.models.experiment import (
    ComplianceExperiment,
    ExperimentStatus,
    ExperimentSummary,
)

logger = logging.getLogger("banxe.experiment_copilot.store")

_STATUS_DIRS = {
    ExperimentStatus.DRAFT: "draft",
    ExperimentStatus.ACTIVE: "active",
    ExperimentStatus.FINISHED: "finished",
    ExperimentStatus.REJECTED: "rejected",
}


class ExperimentStore:
    """YAML-based experiment store with git-friendly file layout.

    Each experiment is persisted as `{experiments_dir}/{status}/{id}.yaml`.
    An `index.json` at the root is auto-regenerated for fast list operations.
    """

    def __init__(self, experiments_dir: str = "compliance-experiments") -> None:
        self._root = Path(experiments_dir)
        self._ensure_dirs()

    # ── Write operations ───────────────────────────────────────────────────

    def save(self, experiment: ComplianceExperiment) -> Path:
        """Persist experiment to YAML. Moves file if status changed."""
        experiment.updated_at = datetime.utcnow()
        target_dir = self._root / _STATUS_DIRS[experiment.status]
        target_dir.mkdir(parents=True, exist_ok=True)

        # Remove from old location(s) if moved between statuses
        for dir_name in _STATUS_DIRS.values():
            old_path = self._root / dir_name / f"{experiment.id}.yaml"
            if old_path.exists() and old_path.parent != target_dir:
                old_path.unlink()
                logger.info(
                    "Moved experiment %s from %s → %s",
                    experiment.id,
                    dir_name,
                    _STATUS_DIRS[experiment.status],
                )

        target_path = target_dir / f"{experiment.id}.yaml"
        with open(target_path, "w", encoding="utf-8") as f:
            yaml.dump(
                json.loads(experiment.model_dump_json()),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )

        self._rebuild_index()
        logger.info("Saved experiment %s → %s", experiment.id, target_path)
        return target_path

    def delete(self, experiment_id: str) -> bool:
        """Delete an experiment YAML (any status). Returns True if found."""
        for dir_name in _STATUS_DIRS.values():
            path = self._root / dir_name / f"{experiment_id}.yaml"
            if path.exists():
                path.unlink()
                self._rebuild_index()
                return True
        return False

    # ── Read operations ────────────────────────────────────────────────────

    def get(self, experiment_id: str) -> ComplianceExperiment | None:
        """Load experiment by ID (searches all status directories)."""
        for dir_name in _STATUS_DIRS.values():
            path = self._root / dir_name / f"{experiment_id}.yaml"
            if path.exists():
                return self._load(path)
        return None

    def list_by_status(self, status: ExperimentStatus) -> list[ExperimentSummary]:
        """List all experiments with the given status."""
        dir_path = self._root / _STATUS_DIRS[status]
        if not dir_path.exists():
            return []
        summaries: list[ExperimentSummary] = []
        for yaml_file in sorted(dir_path.glob("*.yaml")):
            try:
                exp = self._load(yaml_file)
                summaries.append(ExperimentSummary.from_experiment(exp))
            except Exception as exc:
                logger.warning("Skipping malformed experiment file %s: %s", yaml_file, exc)
        return summaries

    def list_all(self) -> list[ExperimentSummary]:
        """List all experiments across all statuses."""
        summaries: list[ExperimentSummary] = []
        for status in ExperimentStatus:
            summaries.extend(self.list_by_status(status))
        summaries.sort(key=lambda s: s.updated_at, reverse=True)
        return summaries

    def get_index(self) -> dict[str, Any]:
        """Return the index.json contents (fast summary for API)."""
        index_path = self._root / "index.json"
        if index_path.exists():
            with open(index_path, encoding="utf-8") as f:
                return json.load(f)
        return self._rebuild_index()

    def count_by_status(self) -> dict[str, int]:
        """Return counts per status."""
        return {
            status.value: len(list((self._root / dir_name).glob("*.yaml")))
            for status, dir_name in _STATUS_DIRS.items()
            if (self._root / dir_name).exists()
        }

    # ── Internal ───────────────────────────────────────────────────────────

    def _ensure_dirs(self) -> None:
        for dir_name in _STATUS_DIRS.values():
            (self._root / dir_name).mkdir(parents=True, exist_ok=True)

    def _load(self, path: Path) -> ComplianceExperiment:
        with open(path, encoding="utf-8") as f:
            raw = yaml.safe_load(f)
        return ComplianceExperiment.model_validate(raw)

    def _rebuild_index(self) -> dict[str, Any]:
        summaries = self.list_all()
        index: dict[str, Any] = {
            "total": len(summaries),
            "by_status": self.count_by_status(),
            "experiments": [
                {
                    "id": s.id,
                    "title": s.title,
                    "scope": s.scope.value,
                    "status": s.status.value,
                    "updated_at": s.updated_at.isoformat(),
                    "has_pr": s.has_pr,
                }
                for s in summaries
            ],
        }
        index_path = self._root / "index.json"
        with open(index_path, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2)
        return index
