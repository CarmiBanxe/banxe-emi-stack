"""
tests/test_experiment_copilot/test_audit_trail.py
IL-CEC-01 | banxe-emi-stack

Tests for AuditTrail: log(), get_entries(), export_to_clickhouse_rows(),
and the delete_entries() immutability invariant (I-24).
"""

from __future__ import annotations

import pytest

from services.experiment_copilot.store.audit_trail import AuditTrail


class TestAuditTrailLog:
    def test_log_creates_entry(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        entry = audit.log(
            actor="steward",
            action="experiment.approved",
            experiment_id="exp-test-001",
            details={"notes": "OK"},
        )
        assert entry.actor == "steward"
        assert entry.action == "experiment.approved"
        assert entry.experiment_id == "exp-test-001"
        assert entry.entry_id is not None

    def test_log_is_append_only(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        audit.log(actor="a", action="action.1", experiment_id="exp-001")
        audit.log(actor="b", action="action.2", experiment_id="exp-001")
        entries = audit.get_entries("exp-001")
        assert len(entries) == 2

    def test_log_persists_to_file(self, tmp_path):
        path = str(tmp_path / "audit.jsonl")
        audit1 = AuditTrail(log_path=path)
        audit1.log(actor="system", action="experiment.created", experiment_id="exp-persist")
        audit2 = AuditTrail(log_path=path)
        entries = audit2.get_entries("exp-persist")
        assert len(entries) == 1


class TestAuditTrailGet:
    def test_get_entries_filters_by_experiment_id(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        audit.log(actor="a", action="action.1", experiment_id="exp-001")
        audit.log(actor="b", action="action.2", experiment_id="exp-002")
        entries = audit.get_entries("exp-001")
        assert len(entries) == 1
        assert entries[0].experiment_id == "exp-001"

    def test_get_entries_no_filter_returns_all(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        audit.log(actor="a", action="x", experiment_id="exp-001")
        audit.log(actor="b", action="y", experiment_id="exp-002")
        all_entries = audit.get_entries()
        assert len(all_entries) == 2

    def test_get_entries_empty_file_returns_empty_list(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "empty.jsonl"))
        assert audit.get_entries() == []

    def test_get_entry_count(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        audit.log(actor="a", action="x", experiment_id="exp-001")
        audit.log(actor="b", action="y", experiment_id="exp-001")
        assert audit.get_entry_count("exp-001") == 2


class TestAuditTrailImmutability:
    def test_delete_entries_raises_runtime_error(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        with pytest.raises(RuntimeError, match="I-24"):
            audit.delete_entries()

    def test_export_to_clickhouse_rows(self, tmp_path):
        audit = AuditTrail(log_path=str(tmp_path / "audit.jsonl"))
        audit.log(actor="reporter", action="report.generated", experiment_id="exp-export")
        rows = audit.export_to_clickhouse_rows("exp-export")
        assert len(rows) == 1
        assert "entry_id" in rows[0]
        assert "timestamp" in rows[0]
        assert rows[0]["actor"] == "reporter"
