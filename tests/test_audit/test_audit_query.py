"""
tests/test_audit/test_audit_query.py — AuditQueryService tests
IL-PGA-01 | Phase 51A | Sprint 36
≥20 tests covering query_audit_log, get_stats, export_report, health_check
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from services.audit.audit_query import AuditQueryService, HITLProposal
from services.audit.pgaudit_config import AuditStats, InMemoryAuditLogPort

# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def service() -> AuditQueryService:
    return AuditQueryService(port=InMemoryAuditLogPort())


# ── query_audit_log ───────────────────────────────────────────────────────────


def test_query_audit_log_returns_list(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_core", None, "2020-01-01", "2099-12-31")
    assert isinstance(result, list)


def test_query_audit_log_filters_by_db(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_core", None, "2020-01-01", "2099-12-31")
    for e in result:
        assert e.db_name == "banxe_core"


def test_query_audit_log_invalid_db_raises(service: AuditQueryService) -> None:
    with pytest.raises(ValueError, match="Unknown database"):
        service.query_audit_log("invalid_db", None, "2020-01-01", "2099-12-31")


def test_query_audit_log_filters_by_table(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_core", "payments", "2020-01-01", "2099-12-31")
    for e in result:
        assert e.table_name == "payments"


def test_query_audit_log_limit_applied(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_core", None, "2020-01-01", "2099-12-31", limit=1)
    assert len(result) <= 1


def test_query_audit_log_compliance_db(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_compliance", None, "2020-01-01", "2099-12-31")
    assert isinstance(result, list)


def test_query_audit_log_analytics_db(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_analytics", None, "2020-01-01", "2099-12-31")
    assert isinstance(result, list)


def test_query_audit_log_default_limit_100(service: AuditQueryService) -> None:
    result = service.query_audit_log("banxe_core", None, "2020-01-01", "2099-12-31")
    assert len(result) <= 100


# ── get_stats ────────────────────────────────────────────────────────────────


def test_get_stats_returns_auditstats(service: AuditQueryService) -> None:
    stats = service.get_stats("banxe_core")
    assert isinstance(stats, AuditStats)


def test_get_stats_correct_db_name(service: AuditQueryService) -> None:
    stats = service.get_stats("banxe_core")
    assert stats.db_name == "banxe_core"


def test_get_stats_invalid_db_raises(service: AuditQueryService) -> None:
    with pytest.raises(ValueError, match="Unknown database"):
        service.get_stats("bad_db")


def test_get_stats_nonnegative_writes(service: AuditQueryService) -> None:
    stats = service.get_stats("banxe_compliance")
    assert stats.total_writes >= 0


def test_get_stats_nonnegative_ddl(service: AuditQueryService) -> None:
    stats = service.get_stats("banxe_analytics")
    assert stats.total_ddl >= 0


def test_get_all_stats_returns_three(service: AuditQueryService) -> None:
    all_stats = service.get_all_stats()
    assert len(all_stats) == 3


def test_get_all_stats_covers_all_dbs(service: AuditQueryService) -> None:
    all_stats = service.get_all_stats()
    db_names = {s.db_name for s in all_stats}
    assert "banxe_compliance" in db_names
    assert "banxe_core" in db_names
    assert "banxe_analytics" in db_names


# ── export_audit_report → HITLProposal ───────────────────────────────────────


def test_export_audit_report_returns_hitl_proposal(service: AuditQueryService) -> None:
    proposal = service.export_audit_report("banxe_core", "2026-01-01", "2026-04-21", "operator_123")
    assert isinstance(proposal, HITLProposal)


def test_export_audit_report_requires_compliance_officer(service: AuditQueryService) -> None:
    proposal = service.export_audit_report("banxe_compliance", "2026-01-01", "2026-04-21", "op")
    assert proposal.requires_approval_from == "COMPLIANCE_OFFICER"


def test_export_audit_report_autonomy_l4(service: AuditQueryService) -> None:
    proposal = service.export_audit_report("banxe_core", "2026-01-01", "2026-04-21", "op")
    assert proposal.autonomy_level == "L4"


def test_export_audit_report_action_field(service: AuditQueryService) -> None:
    proposal = service.export_audit_report("banxe_analytics", "2026-01-01", "2026-04-21", "op")
    assert proposal.action == "export_audit_report"


def test_export_audit_report_entity_id_8_chars(service: AuditQueryService) -> None:
    proposal = service.export_audit_report("banxe_core", "2026-01-01", "2026-04-21", "op")
    assert len(proposal.entity_id) == 8


def test_export_audit_report_reason_contains_db_name(service: AuditQueryService) -> None:
    proposal = service.export_audit_report("banxe_core", "2026-01-01", "2026-04-21", "op")
    assert "banxe_core" in proposal.reason


def test_export_audit_report_never_auto_executes(service: AuditQueryService) -> None:
    # I-27: must return HITLProposal, never execute export
    proposal = service.export_audit_report("banxe_core", "2026-01-01", "2026-04-21", "op")
    assert isinstance(proposal, HITLProposal)
    assert proposal.autonomy_level == "L4"


# ── health_check ──────────────────────────────────────────────────────────────


def test_health_check_status_ok(service: AuditQueryService) -> None:
    result = service.health_check()
    assert result["status"] == "ok"


def test_health_check_databases_list(service: AuditQueryService) -> None:
    result = service.health_check()
    assert isinstance(result["databases"], list)
    assert len(result["databases"]) == 3


def test_health_check_pgaudit_version(service: AuditQueryService) -> None:
    result = service.health_check()
    assert result["pgaudit_version"] == "1.7"


def test_health_check_settings_present(service: AuditQueryService) -> None:
    result = service.health_check()
    assert "settings" in result
    assert "pgaudit.log" in result["settings"]


def test_health_check_checked_at_utc(service: AuditQueryService) -> None:
    result = service.health_check()
    assert "checked_at" in result
    assert "T" in result["checked_at"]


# ── HITLProposal dataclass ────────────────────────────────────────────────────


def test_hitl_proposal_frozen() -> None:
    proposal = HITLProposal(
        action="test",
        entity_id="abc",
        requires_approval_from="COMPLIANCE_OFFICER",
        reason="test reason",
    )
    with pytest.raises(FrozenInstanceError):
        proposal.action = "modified"  # type: ignore[misc]


def test_hitl_proposal_default_autonomy_l4() -> None:
    proposal = HITLProposal(
        action="export",
        entity_id="xyz",
        requires_approval_from="COMPLIANCE_OFFICER",
        reason="reason",
    )
    assert proposal.autonomy_level == "L4"
