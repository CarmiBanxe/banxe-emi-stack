"""
tests/test_user_preferences/test_data_export.py
IL-UPS-01 | Phase 39 | banxe-emi-stack — 14 tests
"""

from __future__ import annotations

from services.user_preferences.data_export import DataExport, HITLProposal
from services.user_preferences.models import (
    InMemoryAuditPort,
    InMemoryConsentPort,
    InMemoryNotificationPort,
    InMemoryPreferencePort,
)


def _export() -> DataExport:
    return DataExport(
        InMemoryPreferencePort(),
        InMemoryConsentPort(),
        InMemoryNotificationPort(),
        InMemoryAuditPort(),
    )


class TestRequestExport:
    def test_request_creates_pending(self) -> None:
        exp = _export()
        req = exp.request_export("u1")
        assert req.status == "PENDING"

    def test_request_stores_user_id(self) -> None:
        exp = _export()
        req = exp.request_export("u1")
        assert req.user_id == "u1"

    def test_request_logs_audit(self) -> None:
        audit = InMemoryAuditPort()
        exp = DataExport(audit_port=audit)
        exp.request_export("u1")
        assert len(audit.entries()) >= 1

    def test_request_default_json_format(self) -> None:
        exp = _export()
        req = exp.request_export("u1")
        assert req.format == "json"


class TestGenerateExport:
    def test_generate_includes_user_id(self) -> None:
        exp = _export()
        data = exp.generate_export("u1")
        assert data["user_id"] == "u1"

    def test_generate_includes_preferences(self) -> None:
        exp = _export()
        data = exp.generate_export("USR-001")
        assert "preferences" in data

    def test_generate_includes_consents(self) -> None:
        exp = _export()
        data = exp.generate_export("u1")
        assert "consents" in data

    def test_generate_includes_notifications(self) -> None:
        exp = _export()
        data = exp.generate_export("u1")
        assert "notifications" in data


class TestCompleteExport:
    def test_complete_sets_status_completed(self) -> None:
        exp = _export()
        req = exp.request_export("u1")
        completed = exp.complete_export(req.id, "u1")
        assert completed.status == "COMPLETED"

    def test_complete_sets_sha256_hash(self) -> None:
        exp = _export()
        req = exp.request_export("u1")
        completed = exp.complete_export(req.id, "u1")
        assert completed.export_hash is not None
        assert len(completed.export_hash) == 64

    def test_hash_is_valid_sha256_hex(self) -> None:
        """Verify export_hash is a valid 64-char SHA-256 hex digest (I-12)."""
        exp = _export()
        req = exp.request_export("u1")
        completed = exp.complete_export(req.id, "u1")
        assert completed.export_hash is not None
        # SHA-256 produces 64 hex chars
        assert len(completed.export_hash) == 64
        assert all(c in "0123456789abcdef" for c in completed.export_hash)


class TestRequestErasure:
    def test_erasure_returns_hitl(self) -> None:
        exp = _export()
        result = exp.request_erasure("u1")
        assert isinstance(result, HITLProposal)

    def test_erasure_is_l4(self) -> None:
        exp = _export()
        proposal = exp.request_erasure("u1")
        assert proposal.autonomy_level == "L4"

    def test_list_exports_for_user(self) -> None:
        exp = _export()
        exp.request_export("u1")
        exp.request_export("u1")
        exports = exp.list_exports("u1")
        assert len(exports) == 2
